#!/usr/bin/env python3
"""Generate the original Arc engineering desktop wallpapers.

The SVG artwork is authored here as deterministic, self-contained source. Run
this script to write both editable SVGs and PNG renders alongside them.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


NAVY = "#071119"
CYAN = "#62d9ef"
BLUE = "#3989bd"
PALE = "#a5dbe7"
AMBER = "#d19a65"
CORAL = "#bd776f"


def esc(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def line(x1: float, y1: float, x2: float, y2: float, *, color: str = BLUE,
         opacity: float = 0.24, width: float = 2, dash: str | None = None) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<path d="M{x1:g},{y1:g} L{x2:g},{y2:g}" fill="none" stroke="{color}" '
            f'stroke-width="{width:g}" opacity="{opacity:g}"{dash_attr}/>')


def arc(cx: float, cy: float, radius: float, start: float, end: float, *,
        color: str = CYAN, opacity: float = 0.6, width: float = 4) -> str:
    """Return a circular arc whose angles are measured clockwise from 12 o'clock."""
    a0 = math.radians(start - 90)
    a1 = math.radians(end - 90)
    x0, y0 = cx + radius * math.cos(a0), cy + radius * math.sin(a0)
    x1, y1 = cx + radius * math.cos(a1), cy + radius * math.sin(a1)
    sweep = 1 if end >= start else 0
    span = abs(end - start) % 360
    large = 1 if span > 180 else 0
    return (f'<path d="M{x0:.2f},{y0:.2f} A{radius:g},{radius:g} 0 {large} {sweep} '
            f'{x1:.2f},{y1:.2f}" fill="none" stroke="{color}" stroke-width="{width:g}" '
            f'stroke-linecap="round" opacity="{opacity:g}"/>')


def text(x: float, y: float, value: str, *, size: int = 18, color: str = PALE,
         opacity: float = 0.55, spacing: int = 3, anchor: str = "start") -> str:
    return (f'<text x="{x:g}" y="{y:g}" fill="{color}" opacity="{opacity:g}" '
            f'font-family="Inter,Segoe UI,Arial,sans-serif" font-size="{size}" '
            f'font-weight="500" letter-spacing="{spacing}" text-anchor="{anchor}">{esc(value)}</text>')


def background(width: int, height: int, *, portrait: bool) -> str:
    minor = 72 if portrait else 96
    major = minor * 5
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs>
  <pattern id="minor-grid" width="{minor}" height="{minor}" patternUnits="userSpaceOnUse">
    <path d="M {minor} 0 H 0 V {minor}" fill="none" stroke="#4c8ba1" stroke-width="1" opacity=".075"/>
  </pattern>
  <pattern id="major-grid" width="{major}" height="{major}" patternUnits="userSpaceOnUse">
    <path d="M {major} 0 H 0 V {major}" fill="none" stroke="#5da3b7" stroke-width="1.2" opacity=".075"/>
  </pattern>
</defs>
<rect width="{width}" height="{height}" fill="{NAVY}"/>
<rect width="{width}" height="{height}" fill="url(#minor-grid)"/>
<rect width="{width}" height="{height}" fill="url(#major-grid)"/>
'''


def corner_marks(width: int, height: int) -> str:
    out = []
    m, s = 66, 40
    for x, sx in ((m, 1), (width - m, -1)):
        for y, sy in ((m, 1), (height - m, -1)):
            out.append(line(x, y, x + sx * s, y, color=CYAN, opacity=.42, width=2))
            out.append(line(x, y, x, y + sy * s, color=CYAN, opacity=.42, width=2))
            out.append(f'<circle cx="{x}" cy="{y}" r="3" fill="{CYAN}" opacity=".65"/>')
    return "\n".join(out)


def peripheral_rules(width: int, height: int, *, portrait: bool) -> str:
    out = [corner_marks(width, height)]
    # Quiet edge rails and a few calibrated stops establish a technical frame.
    left, right, top, bottom = 66, width - 66, 66, height - 66
    out.extend([
        line(left + 72, top, width * .32, top, opacity=.16, width=1.5),
        line(width * .68, top, right - 72, top, opacity=.16, width=1.5),
        line(left + 72, bottom, width * .27, bottom, opacity=.16, width=1.5),
        line(width * .73, bottom, right - 72, bottom, opacity=.16, width=1.5),
        line(left, top + 100, left, height * .22, opacity=.13, width=1.2),
        line(right, height * .78, right, bottom - 100, opacity=.13, width=1.2),
    ])
    for i in range(11):
        y = 170 + i * (height - 340) / 10
        out.append(line(left - (8 if i % 5 == 0 else 4), y, left + (8 if i % 5 == 0 else 4), y,
                        color=CYAN, opacity=.22 if i % 5 == 0 else .12, width=1.5))
    if portrait:
        out.extend([
            text(left, height - 105, "ARC   /   SYSTEMS STUDIO", size=14, opacity=.42, spacing=2),
            text(right, height - 105, "01—26", size=13, opacity=.32, spacing=2, anchor="end"),
        ])
    else:
        out.extend([
            text(left, height - 94, "ARC   /   SYSTEMS STUDIO", size=15, opacity=.4, spacing=2),
            text(right, height - 94, "ENGINEERING DESKTOP", size=13, opacity=.32, spacing=2, anchor="end"),
        ])
    return "\n".join(out)


def reactor(cx: int, cy: int, radius: int, *, portrait: bool) -> str:
    out: list[str] = []
    # Partial, non-concentric ring segments; uneven gaps give the core a quiet,
    # engineered cadence rather than a symmetric badge or oversized target.
    out += [arc(cx, cy, radius, 202, 292, color=BLUE, opacity=.36, width=2),
            arc(cx, cy, radius, 310, 354, color=CYAN, opacity=.72, width=4),
            arc(cx, cy, radius, 8, 88, color=BLUE, opacity=.62, width=3),
            arc(cx, cy, radius, 104, 161, color=CYAN, opacity=.58, width=3)]
    out += [arc(cx, cy, radius - 31, 218, 259, color=PALE, opacity=.35, width=1.4),
            arc(cx, cy, radius - 31, 278, 346, color=CYAN, opacity=.46, width=2),
            arc(cx, cy, radius - 31, 12, 71, color=PALE, opacity=.31, width=1.5),
            arc(cx, cy, radius - 31, 92, 142, color=BLUE, opacity=.53, width=2.5)]
    out += [arc(cx, cy, radius - 57, 227, 326, color=BLUE, opacity=.28, width=1.3),
            arc(cx, cy, radius - 57, 345, 416, color=CYAN, opacity=.45, width=2),
            arc(cx, cy, radius - 57, 54, 128, color=BLUE, opacity=.42, width=2)]
    # Delicate radial datum marks, clustered in selected sectors only.
    for angle in (202, 211, 220, 229, 238, 247, 256, 265, 274, 283, 292,
                  310, 322, 334, 346, 358, 12, 24, 36, 48, 60, 72, 84,
                  104, 116, 128, 140, 152, 161):
        a = math.radians(angle - 90)
        inner, outer = radius + (7 if angle % 4 else 2), radius + (15 if angle % 4 else 24)
        out.append(line(cx + inner * math.cos(a), cy + inner * math.sin(a),
                        cx + outer * math.cos(a), cy + outer * math.sin(a),
                        color=CYAN, opacity=.26 if angle % 4 else .48, width=1.5))
    # Off-axis inner geometry: a quiet core aperture and two interrupted rails.
    core_r = radius * .26
    out += [f'<circle cx="{cx}" cy="{cy}" r="{core_r:.1f}" fill="none" stroke="{CYAN}" stroke-width="1.6" opacity=".34"/>',
            arc(cx + radius * .035, cy - radius * .018, core_r * .72, 228, 322,
                color=PALE, opacity=.68, width=2.2),
            arc(cx + radius * .035, cy - radius * .018, core_r * .72, 350, 478,
                color=BLUE, opacity=.46, width=1.5)]
    out += [line(cx - radius * .15, cy, cx - radius * .07, cy, color=CYAN, opacity=.54, width=1.4),
            line(cx + radius * .12, cy + radius * .025, cx + radius * .22, cy + radius * .025,
                 color=AMBER, opacity=.8, width=2)]
    # Sparse connectors and micro annotations kept outside the usable center.
    if portrait:
        out += [line(cx - radius * 1.46, cy + radius * .64, cx - radius * .98, cy + radius * .64,
                     opacity=.38, width=1.4),
                line(cx - radius * 1.46, cy + radius * .64, cx - radius * 1.46, cy + radius * .48,
                     opacity=.38, width=1.4),
                f'<circle cx="{cx - radius * 1.46:.1f}" cy="{cy + radius * .64:.1f}" r="3" fill="{AMBER}" opacity=".76"/>',
                text(cx - radius * 1.46, cy + radius * .64 + 34, "A—07", size=12, opacity=.39, spacing=2)]
    else:
        out += [line(cx + radius * .68, cy - radius * 1.38, cx + radius * 1.36, cy - radius * 1.38,
                     opacity=.37, width=1.4),
                line(cx + radius * 1.36, cy - radius * 1.38, cx + radius * 1.36, cy - radius * 1.05,
                     opacity=.37, width=1.4),
                f'<circle cx="{cx + radius * 1.36:.1f}" cy="{cy - radius * 1.38:.1f}" r="3" fill="{AMBER}" opacity=".8"/>',
                text(cx + radius * 1.36, cy - radius * 1.38 - 14, "A—07", size=13, opacity=.42, spacing=2)]
    # A pair of tiny warm signal marks, never used as a faux status indicator.
    out += [arc(cx, cy, radius + 43, 315, 321, color=AMBER, opacity=.8, width=2.2),
            arc(cx, cy, radius + 43, 73, 76, color=CORAL, opacity=.72, width=2.2)]
    return "\n".join(out)


def landscape_svg() -> str:
    width, height = 3840, 2160
    parts = [background(width, height, portrait=False)]
    parts.append(peripheral_rules(width, height, portrait=False))
    # Sparse peripheral construction lines; the central work zone remains open.
    parts += [line(0, 1500, 640, 1500, opacity=.11, width=1.3),
              line(0, 1540, 420, 1540, opacity=.08, width=1),
              line(3200, 430, width, 430, opacity=.11, width=1.3),
              line(3440, 470, width, 470, opacity=.08, width=1),
              line(3000, 1750, 3400, 1750, color=AMBER, opacity=.19, width=1)]
    # The core occupies the right-hand periphery, leaving the screen center calm.
    parts.append(reactor(3100, 1130, 385, portrait=False))
    parts += [text(2980, 1770, "FIELD / 03", size=13, opacity=.31, spacing=2),
              text(3520, 716, "CORE", size=12, opacity=.31, spacing=2)]
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def portrait_svg() -> str:
    width, height = 1536, 2732
    parts = [background(width, height, portrait=True)]
    parts.append(peripheral_rules(width, height, portrait=True))
    # Fine peripheral paths taper through the lower field, avoiding a central HUD.
    parts += [line(66, 410, 180, 410, opacity=.18, width=1.4),
              line(180, 410, 286, 516, opacity=.14, width=1.2),
              line(1450, 560, 1370, 640, opacity=.16, width=1.2),
              line(1370, 640, 1280, 640, opacity=.16, width=1.2),
              line(66, 2100, 224, 2100, color=AMBER, opacity=.18, width=1.2),
              line(1310, 2190, 1450, 2190, opacity=.15, width=1.2)]
    # Lower-left composition balances a generous quiet upper/central workspace.
    parts.append(reactor(470, 1885, 286, portrait=True))
    parts += [text(790, 1510, "FIELD / 03", size=12, opacity=.29, spacing=2),
              text(828, 1546, "ENGINEERING DESKTOP", size=11, opacity=.26, spacing=2)]
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


ARTWORK = (
    ("arc-landscape", 3840, 2160, landscape_svg),
    ("arc-portrait", 1536, 2732, portrait_svg),
)


def render(output_dir: Path, check: bool) -> bool:
    converter = shutil.which("rsvg-convert")
    if converter is None:
        print("error: rsvg-convert is required but was not found on PATH", file=sys.stderr)
        return False

    if check:
        with tempfile.TemporaryDirectory(prefix="render-arc-check-") as temporary:
            temp_dir = Path(temporary)
            mismatches: list[str] = []
            for name, width, height, factory in ARTWORK:
                svg = factory()
                expected_svg = output_dir / f"{name}.svg"
                expected_png = output_dir / f"{name}.png"
                candidate_svg = temp_dir / f"{name}.svg"
                candidate_png = temp_dir / f"{name}.png"
                candidate_svg.write_text(svg, encoding="utf-8", newline="\n")
                subprocess.run([converter, "-w", str(width), "-h", str(height),
                                "-o", str(candidate_png), str(candidate_svg)], check=True)
                if not expected_svg.is_file() or expected_svg.read_bytes() != candidate_svg.read_bytes():
                    mismatches.append(f"{expected_svg} (missing or differs from generated SVG)")
                if not expected_png.is_file() or expected_png.read_bytes() != candidate_png.read_bytes():
                    mismatches.append(f"{expected_png} (missing or differs from deterministic render)")
                elif png_size(expected_png) != (width, height):
                    mismatches.append(f"{expected_png} (expected {width}x{height})")
            if mismatches:
                print("Arc assets need regeneration:", file=sys.stderr)
                print("\n".join(f"  - {item}" for item in mismatches), file=sys.stderr)
                return False
        print("Arc SVG and PNG assets match deterministic sources and target dimensions.")
        return True

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, width, height, factory in ARTWORK:
        svg_path = output_dir / f"{name}.svg"
        png_path = output_dir / f"{name}.png"
        svg_path.write_text(factory(), encoding="utf-8", newline="\n")
        subprocess.run([converter, "-w", str(width), "-h", str(height),
                        "-o", str(png_path), str(svg_path)], check=True)
        actual = png_size(png_path)
        if actual != (width, height):
            raise RuntimeError(f"{png_path} rendered as {actual[0]}x{actual[1]}, expected {width}x{height}")
        print(f"Rendered {png_path} ({width}x{height})")
    return True


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError(f"not a valid PNG: {path}")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "assets" / "arc",
                        help="directory for editable SVG sources and rendered PNGs")
    parser.add_argument("--check", action="store_true",
                        help="verify checked-in files against freshly generated deterministic assets")
    args = parser.parse_args()
    try:
        return 0 if render(args.output_dir.resolve(), args.check) else 1
    except (OSError, subprocess.CalledProcessError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
