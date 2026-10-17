#!/usr/bin/env python3
"""Focused invariants for the ARC Motion wallpaper renderer."""
from __future__ import annotations

import hashlib
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render-arc-motion.py"
SPEC = importlib.util.spec_from_file_location("arc_motion_renderer", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)


class ArcMotionRendererTests(unittest.TestCase):
    def test_original_static_assets_remain_byte_identical(self) -> None:
        known = {
            "arc-landscape.png": "f13d6d1c69da599fa1be101c2a16bad5ba1e17c7bf6abdd0ebec8a4831d08769",
            "arc-landscape.svg": "9949bf36c129ff63a460ac0e79a4bcc07556c45c4cadea57875338f134a8da58",
            "arc-portrait.png": "10bb847c2033de29a4f474b41f86152b84b78b2ef68b087cb85165bc69816a8b",
            "arc-portrait.svg": "d81d3fa2d0cddf0b50ce8109e77e698be2b87e1552623f7df596a96cee0fe10a",
        }
        for filename, digest in known.items():
            path = ROOT / "assets" / "arc" / filename
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_static_geometry_excludes_only_selected_segments(self) -> None:
        for spec in render.FORMATS:
            name, width, height, sw, sh, cx, cy, radius, portrait = spec
            static_svg, motion_svg, _ = render.composition(
                name, width, height, sw, sh, cx, cy, radius, portrait)
            renderer = render.load_static_renderer()
            static_reactor = renderer.reactor(cx, cy, radius, portrait=portrait)
            for segment in render.SEGMENTS:
                chosen = render._motion_arc(renderer, cx, cy, radius, segment)
                self.assertIn(chosen, static_reactor)
                self.assertNotIn(chosen, static_svg)
            self.assertEqual(motion_svg.count("<path"), len(render.SEGMENTS))
            self.assertIn(f'width="{width}" height="{height}"', static_svg)
            scale = width / sw
            center = (math.ceil((radius + 80) * scale * 2) + 36) / 2
            phase_zero = render.motion_layer_arcs(renderer, center, radius,
                                                  render.SEGMENTS, scale, 0)
            phase_full_cycle = render.motion_layer_arcs(renderer, center, radius,
                                                        render.SEGMENTS, scale, 360)
            expected_scaled = "\n".join(
                render._motion_arc(renderer, center, center, radius * scale, segment, scale)
                for segment in render.SEGMENTS)
            self.assertEqual(phase_zero, expected_scaled)
            self.assertEqual(phase_zero, phase_full_cycle)
            # The rotating layer's orbit stays clear of the central work area.
            scale = width / sw
            motion_radius = (radius + 43) * scale
            center_distance = ((cx * scale - width / 2) ** 2 +
                               (cy * scale - height / 2) ** 2) ** .5
            self.assertGreater(center_distance, motion_radius)

    def test_rendering_composition_disables_bytecode_writes(self) -> None:
        old_setting = render.sys.dont_write_bytecode
        try:
            render.sys.dont_write_bytecode = False
            render.composition(*render.FORMATS[0])
            self.assertTrue(render.sys.dont_write_bytecode)
        finally:
            render.sys.dont_write_bytecode = old_setting

    def test_output_symlink_paths_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir()
            link = Path(tmp) / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                render.refuse_symlinks(link)
            video_link = real / "arc-motion-landscape.mp4"
            video_link.symlink_to(real / "target.mp4")
            with self.assertRaisesRegex(ValueError, "symlink"):
                render.refuse_symlinks(real, (video_link.name,))

    def test_phase_duration_contract(self) -> None:
        self.assertEqual((render.FPS, render.DURATION), (24, 60))

    def test_bare_cli_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "must-not-exist"
            self.assertEqual(render.main(["--output-dir", str(output)]), 0)
            self.assertFalse(output.exists())

    def test_missing_render_dependencies_fail_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "must-not-exist"
            with mock.patch.object(render.shutil, "which", return_value=None):
                self.assertEqual(render.main(["--apply", "--output-dir", str(output)]), 1)
            self.assertFalse(output.exists())
            with mock.patch.object(render.shutil, "which", return_value=None):
                self.assertEqual(render.main(["--check", "--output-dir", str(output)]), 1)
            self.assertFalse(output.exists())

    def test_check_validates_ffprobe_stream_contract(self) -> None:
        good = {
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1920,
                         "height": 1080, "nb_frames": "1440"}],
            "format": {"duration": "60.000"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "arc-motion-landscape.mp4"
            path.touch()
            with mock.patch.object(render, "probe", return_value=good):
                self.assertEqual(render.validate(path, render.FORMATS[0], "ffprobe"), [])
            with mock.patch.object(render, "probe", return_value={
                    **good, "streams": good["streams"] + [{"codec_type": "audio"}]}):
                self.assertTrue(any("no audio" in item for item in
                                    render.validate(path, render.FORMATS[0], "ffprobe")))

    def test_missing_source_renderer_is_reported(self) -> None:
        with mock.patch.object(render.Path, "is_file", return_value=False):
            with self.assertRaises(FileNotFoundError):
                render.load_static_renderer()


if __name__ == "__main__":
    unittest.main()
