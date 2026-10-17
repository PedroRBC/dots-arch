#!/usr/bin/env python3
"""Render lightweight, silent ARC Motion wallpaper loops.

Bare invocation is a read-only preview. Pass --apply to render the two local
H.264 loops, or --check to validate existing files with ffprobe.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

FPS = 24
DURATION = 60
THREADS = 2
SEGMENTS = (
    (0, 310, 354, "#62d9ef", .72, 4),
    (0, 8, 88, "#3989bd", .62, 3),
    (-31, 278, 346, "#62d9ef", .46, 2),
    (-31, 12, 71, "#a5dbe7", .31, 1.5),
)
FORMATS = (
    ("arc-motion-landscape", 1920, 1080, 3840, 2160, 3100, 1130, 385, False),
    ("arc-motion-portrait", 768, 1366, 1536, 2732, 470, 1885, 286, True),
)


def load_static_renderer() -> Any:
    # Dynamic imports otherwise may write a bytecode cache beside repository files.
    sys.dont_write_bytecode = True
    source = Path(__file__).resolve().with_name("render-arc.py")
    if not source.is_file():
        raise FileNotFoundError(f"static renderer is missing: {source}")
    spec = importlib.util.spec_from_file_location("arc_static_renderer", source)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load static renderer: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cache_dir() -> Path:
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "dots-arch" / "arc-motion"


def output_names() -> tuple[str, ...]:
    return tuple(f"{name}{suffix}" for name, *_ in FORMATS
                 for suffix in ("-base.png", "-motion.png", ".mp4"))


def refuse_symlinks(path: Path, names: tuple[str, ...] = ()) -> Path:
    """Reject symlinks in the output directory path and named output files."""
    path = Path(os.path.abspath(path.expanduser()))
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor /= part
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"refusing symlink in output path: {cursor}")
        if cursor == path and not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"output path is not a directory: {cursor}")
    for name in names:
        target = path / name
        try:
            info = target.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"refusing symlink output file: {target}")
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"output target is not a regular file: {target}")
    return path


def _motion_arc(renderer: Any, cx: float, cy: float, radius: float,
                segment: tuple[int, int, int, str, float, float],
                scale: float = 1.0) -> str:
    ring, start, end, color, opacity, width = segment
    return renderer.arc(cx, cy, radius + ring * scale, start, end,
                        color=color, opacity=opacity, width=width * scale)


def motion_layer_arcs(renderer: Any, center: float, radius: float,
                      segments: tuple[tuple[int, int, int, str, float, float], ...],
                      scale: float, phase_degrees: float = 0) -> str:
    paths = []
    for ring, start, end, color, opacity, width in segments:
        paths.append(renderer.arc(center, center, (radius + ring) * scale,
                                  start + phase_degrees, end + phase_degrees,
                                  color=color, opacity=opacity, width=width * scale))
    return "\n".join(paths)


def composition(name: str, width: int, height: int, source_width: int,
                source_height: int, cx: int, cy: int, radius: int,
                portrait: bool) -> tuple[str, str, tuple[int, int, int, int]]:
    """Return static SVG, local rotating-layer SVG, and its pixel overlay box."""
    renderer = load_static_renderer()
    factory = renderer.portrait_svg if portrait else renderer.landscape_svg
    static_svg = factory()
    # Use the original art factories, removing only the exact four ring paths
    # duplicated into the separately rasterized rotating layer.
    reactor = renderer.reactor(cx, cy, radius, portrait=portrait)
    for segment in SEGMENTS:
        path = _motion_arc(renderer, cx, cy, radius, segment)
        if path not in reactor:
            raise RuntimeError(f"motion segment absent from static {name} geometry")
        reactor = reactor.replace(path, "", 1)
    # Replace just this reactor's factory output inside the unchanged original
    # composition. Other central artwork remains the original static source.
    original_reactor = renderer.reactor(cx, cy, radius, portrait=portrait)
    if original_reactor not in static_svg:
        raise RuntimeError(f"reactor geometry absent from static {name} composition")
    static_svg = static_svg.replace(original_reactor, reactor, 1)
    static_svg = _resize_svg(static_svg, width, height, source_width, source_height)

    scale = width / source_width
    pad = 18  # room for antialiasing during rotation
    box = math.ceil((radius + 80) * scale * 2) + 2 * pad
    local_center = box / 2
    local_arcs = motion_layer_arcs(renderer, local_center, radius, SEGMENTS, scale)
    motion_svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{box}" height="{box}" '
                  f'viewBox="0 0 {box} {box}">{local_arcs}</svg>\n')
    left = round(cx * scale - local_center)
    top = round(cy * scale - local_center)
    return static_svg, motion_svg, (left, top, box, box)


def _resize_svg(source: str, width: int, height: int,
                view_width: int, view_height: int) -> str:
    end = source.find(">")
    if end < 0 or "<svg " not in source[:end]:
        raise ValueError("static renderer did not return an SVG root")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {view_width} {view_height}">' + source[end + 1:])


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   text=True)


def render_one(output: Path, spec: tuple[Any, ...], converter: str,
               ffmpeg: str) -> Path:
    name, width, height, sw, sh, cx, cy, radius, portrait = spec
    static_svg, motion_svg, (x, y, layer_width, _) = composition(
        name, width, height, sw, sh, cx, cy, radius, portrait)
    base_png, layer_png = output / f"{name}-base.png", output / f"{name}-motion.png"
    output_mp4 = output / f"{name}.mp4"
    static_source, motion_source = output / f".{name}-base.svg", output / f".{name}-motion.svg"
    static_source.write_text(static_svg, encoding="utf-8", newline="\n")
    motion_source.write_text(motion_svg, encoding="utf-8", newline="\n")
    _run([converter, "-w", str(width), "-h", str(height), "-o", str(base_png), str(static_source)])
    _run([converter, "-w", str(layer_width), "-h", str(layer_width),
          "-o", str(layer_png), str(motion_source)])
    static_source.unlink()
    motion_source.unlink()
    if _png_size(base_png) != (width, height):
        raise RuntimeError(f"{base_png} has the wrong dimensions")
    phase = f"2*PI*t/{DURATION}"
    filters = (f"[1:v]format=rgba,rotate={phase}:c=none:ow=iw:oh=ih[spin];"
               f"[0:v][spin]overlay=x={x}:y={y}:shortest=1,format=yuv420p[v]")
    _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
          "-loop", "1", "-framerate", str(FPS), "-i", str(base_png),
          "-loop", "1", "-framerate", str(FPS), "-i", str(layer_png),
          "-filter_complex_threads", str(THREADS), "-filter_complex", filters,
          "-map", "[v]", "-an", "-t", str(DURATION), "-r", str(FPS),
          "-frames:v", str(FPS * DURATION), "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "22", "-threads", str(THREADS), "-pix_fmt", "yuv420p",
          "-movflags", "+faststart", str(output_mp4)])
    return output_mp4


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError(f"invalid PNG: {path}")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def probe(path: Path, ffprobe: str) -> dict[str, Any]:
    result = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format",
                             "-of", "json", str(path)], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return json.loads(result.stdout)


def validate(path: Path, spec: tuple[Any, ...], ffprobe: str) -> list[str]:
    name, width, height = spec[:3]
    issues: list[str] = []
    if not path.is_file():
        return [f"missing {path}"]
    try:
        metadata = probe(path, ffprobe)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        return [f"cannot probe {path}: {exc}"]
    streams = metadata.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    if len(videos) != 1 or any(stream.get("codec_type") == "audio" for stream in streams):
        issues.append(f"{path}: expected one video stream and no audio")
    if videos:
        video = videos[0]
        if (video.get("width"), video.get("height")) != (width, height):
            issues.append(f"{path}: expected {width}x{height}")
        if video.get("codec_name") != "h264":
            issues.append(f"{path}: expected H.264 video")
        if int(video.get("nb_frames", 0)) != FPS * DURATION:
            issues.append(f"{path}: expected {FPS * DURATION} frames")
    try:
        duration = float(metadata.get("format", {}).get("duration", 0))
        if abs(duration - DURATION) > 0.1:
            issues.append(f"{path}: expected {DURATION}s duration, found {duration:g}s")
    except (TypeError, ValueError):
        issues.append(f"{path}: invalid duration metadata")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="generate the two wallpaper loops")
    mode.add_argument("--check", action="store_true", help="validate existing loops with ffprobe")
    parser.add_argument("--output-dir", type=Path, default=cache_dir(),
                        help="output/cache directory (default: XDG cache dots-arch/arc-motion)")
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser()
    if not args.apply and not args.check:
        print(f"Dry run: would render two {DURATION}s {FPS}fps silent H.264 loops to {output}")
        print("Targets: arc-motion-landscape.mp4 (1920x1080), arc-motion-portrait.mp4 (768x1366)")
        print("Run with --apply to create files; --check validates them without writing.")
        return 0
    if args.check:
        ffprobe = shutil.which("ffprobe")
        if ffprobe is None:
            print("error: ffprobe is required for --check", file=sys.stderr)
            return 1
        try:
            output = refuse_symlinks(output, tuple(f"{spec[0]}.mp4" for spec in FORMATS))
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        issues = [issue for spec in FORMATS
                  for issue in validate(output / f"{spec[0]}.mp4", spec, ffprobe)]
        if issues:
            print("ARC Motion validation failed:\n" + "\n".join(f"- {item}" for item in issues),
                  file=sys.stderr)
            return 1
        print(f"ARC Motion loops validated: {output}")
        return 0
    converter, ffmpeg, ffprobe = (shutil.which("rsvg-convert"), shutil.which("ffmpeg"),
                                  shutil.which("ffprobe"))
    missing = ", ".join(name for name, path in (("rsvg-convert", converter),
                                                  ("ffmpeg", ffmpeg), ("ffprobe", ffprobe))
                         if path is None)
    if missing:
        print(f"error: required renderer(s) not found on PATH: {missing}", file=sys.stderr)
        return 1
    try:
        load_static_renderer()
        output = refuse_symlinks(output, output_names())
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".arc-motion-staging-", dir=output) as staging_name:
            staging = Path(staging_name)
            for spec in FORMATS:
                render_one(staging, spec, converter, ffmpeg)
            issues = [issue for spec in FORMATS
                      for issue in validate(staging / f"{spec[0]}.mp4", spec, ffprobe)]
            if issues:
                print("error: generated loops failed validation:\\n" +
                      "\\n".join(issues), file=sys.stderr)
                return 1
            # Each replacement is atomic; no existing cache file is touched until
            # both staged videos pass ffprobe validation.
            for spec in FORMATS:
                name = spec[0]
                for suffix in ("-base.png", "-motion.png", ".mp4"):
                    os.replace(staging / f"{name}{suffix}", output / f"{name}{suffix}")
                print(f"Rendered {output / f'{name}.mp4'}")
        print("Both loops are 60 seconds, 24fps, silent H.264 with the expected dimensions.")
        return 0
    except (OSError, subprocess.CalledProcessError, ValueError, RuntimeError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
