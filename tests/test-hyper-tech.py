#!/usr/bin/env python3
"""ARC contrast, config contracts and recovery tests, without a live desktop."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hyper_tech", REPO / "scripts/hyper-tech.py")
arc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arc)


def luminance(color):
    values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    values = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
    return sum(v * weight for v, weight in zip(values, (0.2126, 0.7152, 0.0722)))


def contrast(a, b):
    a, b = sorted((luminance(a), luminance(b)))
    return (b + 0.05) / (a + 0.05)


class PaletteTests(unittest.TestCase):
    def test_roles_and_contrast(self):
        palette = json.loads((REPO / "home/.config/noctalia/palettes/Arc.json").read_text())
        self.assertEqual(set(palette), {"dark", "light"})
        for name, variant in palette.items():
            roles = {"Primary", "Secondary", "Tertiary", "Error", "Surface", "SurfaceVariant", "Hover"}
            for role in roles:
                a, b = variant["m" + role], variant["mOn" + role]
                self.assertGreaterEqual(contrast(a, b), 4.5, (name, role))
            self.assertGreaterEqual(contrast(variant["mOutline"], variant["mSurface"]), 3)
            for role in ("mPrimary", "mSecondary", "mTertiary", "mError"):
                self.assertGreaterEqual(contrast(variant[role], variant["mSurface"]), 3)
            for key, value in variant.items():
                if key != "terminal":
                    self.assertRegex(value, r"^#[0-9a-f]{6}$")
            terminal = variant["terminal"]
            for role in ("foreground", "cursor"):
                self.assertGreaterEqual(contrast(terminal[role], terminal["background"]), 4.5)
            self.assertGreaterEqual(contrast(terminal["selectionBg"], terminal["selectionFg"]), 4.5)
            for kind in ("normal", "bright"):
                self.assertEqual(set(terminal[kind]),
                                 {"black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"})
                for key, value in terminal[kind].items():
                    if kind == "normal" and key == "black":
                        continue
                    self.assertGreaterEqual(contrast(value, terminal["background"]), 4.5, (name, kind, key))

    def test_terminal_and_shell_contracts(self):
        config = tomllib.loads((REPO / "home/.config/noctalia/config.toml").read_text())
        self.assertEqual(config["theme"]["source"], "custom")
        self.assertEqual(config["theme"]["custom_palette"], "Arc")
        self.assertNotIn("hyprland", config["theme"]["templates"]["builtin_ids"])
        alacritty = tomllib.loads((REPO / "seeds/.config/alacritty/alacritty.toml.in").read_text())
        self.assertEqual(alacritty["colors"], {"draw_bold_text_with_bright_colors": True})
        self.assertEqual(alacritty["window"]["opacity"], 0.94)
        self.assertEqual(len(alacritty["keyboard"]["bindings"]), 14)
        kitty = (REPO / "home/.config/kitty/kitty.conf").read_text()
        self.assertIn("include themes/noctalia.conf", kitty)
        self.assertRegex(kitty, r"background_opacity\s+0\.94")

    def test_dry_run_has_no_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = dict(os.environ, HOME=str(root), XDG_CONFIG_HOME=str(root / "config"),
                       XDG_STATE_HOME=str(root / "state"), XDG_DATA_HOME=str(root / "data"))
            result = subprocess.run([sys.executable, "-I", str(REPO / "scripts/hyper-tech.py")],
                                    env=env, cwd=root, capture_output=True, text=True, check=True)
            self.assertIn("DRY-RUN", result.stdout)
            self.assertEqual(list(root.iterdir()), [])


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="arc recovery ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config"
        self.state = self.root / "state"
        self.repo = self.root / "repo"
        for path in (self.config, self.state, self.repo):
            path.mkdir()
        self.source = self.repo / "colors.lua"
        self.source.write_text("original colors\n")
        self.link = self.config / "colors.lua"
        self.link.symlink_to(self.source)
        self.settings = self.state / "noctalia/settings.toml"
        self.settings.parent.mkdir()
        self.settings.write_text('[bar]\norder = ["default"]\n')
        self.new_file = self.config / "generated.conf"
        self.paths = [self.source, self.link, self.settings, self.new_file]
        for name, value in {"REPO": self.repo, "CONFIG": self.config, "STATE": self.state,
                            "BACKUPS": self.state / "themes"}.items():
            patcher = patch.object(arc, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(arc, "managed_paths", return_value=self.paths)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []

        def fake_command(*args):
            self.calls.append(args)
            if args == ("hyprctl", "-j", "monitors"):
                return '[{"name":"DP-2"}]'
            return "'dark'"

        patcher = patch.object(arc, "command", side_effect=fake_command)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(arc, "msg", side_effect=lambda *args:
                               {"color-scheme-get": "wallpaper m3-content", "theme-mode-get": "dark"}
                               .get(args[0], "/wallpapers/original.png"))
        self.msg = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(arc, "check_templates")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)
        self.directory, self.data = arc.make_backup()

    def apply_fixture(self):
        self.source.write_text("ARC colors\n")
        self.settings.write_text('[bar]\norder = ["default"]\n[theme]\nsource = "custom"\n')
        self.new_file.write_text("generated ARC\n")
        arc.seal(self.directory, self.data)

    def test_backup_private_and_exact(self):
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        for path in self.directory.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        directory, data = arc.load_backup(self.directory.name)
        self.assertEqual(data["files"][1]["before"]["link"], str(self.source))
        self.assertEqual(directory, self.directory)

    def test_restore_preview_and_apply(self):
        self.apply_fixture()
        arc.restore(self.directory, self.data, False)
        self.assertEqual(self.source.read_text(), "ARC colors\n")
        arc.restore(self.directory, self.data, True)
        self.assertEqual(self.source.read_text(), "original colors\n")
        self.assertTrue(self.link.is_symlink())
        # IPC is mocked: the mixed state must not be replaced wholesale.
        self.assertEqual(self.settings.read_text(),
                         '[bar]\norder = ["default"]\n[theme]\nsource = "custom"\n')
        self.msg.assert_any_call("color-scheme-set", "wallpaper", "m3-content")
        self.msg.assert_any_call("wallpaper-set", "DP-2", "/wallpapers/original.png")
        self.assertTrue(any(call[:2] == ("hyprctl", "eval") for call in self.calls))
        self.assertFalse(any(call[:2] == ("hyprctl", "reload") for call in self.calls))
        self.assertFalse(self.new_file.exists())

    def test_later_state_edit_blocks_all_writes(self):
        self.apply_fixture()
        self.settings.write_text('[bar]\norder = ["changed by user"]\n')
        before = {p: p.read_bytes() for p in self.paths}
        with self.assertRaisesRegex(ValueError, "posteriores"):
            arc.restore(self.directory, self.data, True)
        self.assertEqual({p: p.read_bytes() for p in self.paths}, before)

    def test_replaced_symlink_blocks_all_writes(self):
        self.apply_fixture()
        self.link.unlink()
        self.link.write_text("unrelated local config")
        with self.assertRaises(ValueError):
            arc.restore(self.directory, self.data, True)
        self.assertEqual(self.source.read_text(), "ARC colors\n")

    def test_tampered_copy_and_path_rejected(self):
        with self.assertRaises(ValueError):
            arc.load_backup("../elsewhere")
        self.data["files"][0]["path"] = "/tmp/not-managed"
        arc.write_json(self.directory / "backup.json", self.data)
        with self.assertRaises(ValueError):
            arc.load_backup(self.directory.name)
        self.data["files"][0]["path"] = str(self.source)
        arc.write_json(self.directory / "backup.json", self.data)
        (self.directory / "0").write_text("corrupt backup")
        with self.assertRaises(ValueError):
            arc.load_backup(self.directory.name)

    def test_incomplete_journal_rejected(self):
        self.data["files"].pop()
        arc.write_json(self.directory / "backup.json", self.data)
        with self.assertRaises(ValueError):
            arc.load_backup(self.directory.name)

    def test_later_gsettings_edit_blocks_restore(self):
        self.apply_fixture()
        self.data["gsettings_after"] = {"color-scheme": "'prefer-dark'"}
        with self.assertRaisesRegex(ValueError, "gsettings"):
            arc.restore(self.directory, self.data, True)
        self.assertEqual(self.source.read_text(), "ARC colors\n")

    def activation_fixture(self, fail=False):
        for relative in ("noctalia/palettes/Arc.json", "noctalia/wallpapers/arc-landscape.png",
                         "noctalia/wallpapers/arc-portrait.png", "kitty/themes/noctalia.conf"):
            path = self.config / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("#57d9ff")
        messages = []

        def fake_msg(*args):
            messages.append(args)
            if fail and args == ("templates-apply",):
                raise ValueError("mock template failure")
            return "custom Arc" if args == ("color-scheme-get",) else "ok"

        monitors = [{"name": "DP-2", "width": 1920, "height": 1080},
                    {"name": "HDMI-A-1", "width": 1366, "height": 768, "transform": 3}]
        with patch.object(arc, "msg", side_effect=fake_msg), \
                patch.object(arc, "command", return_value=json.dumps(monitors)), \
                patch.object(arc.time, "sleep"), contextlib.redirect_stderr(io.StringIO()):
            if fail:
                with self.assertRaisesRegex(ValueError, "mock template failure"):
                    arc.activate(self.directory, self.data)
            else:
                arc.activate(self.directory, self.data)
        return messages

    def test_activation_selects_orientation_without_workflow_commands(self):
        messages = self.activation_fixture()
        self.assertIn(("wallpaper-set", "HDMI-A-1",
                       str(self.config / "noctalia/wallpapers/arc-portrait.png")), messages)
        self.assertIn(("wallpaper-set", "DP-2",
                       str(self.config / "noctalia/wallpapers/arc-landscape.png")), messages)
        self.assertEqual(set(m[0] for m in messages),
                         {"theme-mode-set", "color-scheme-set", "wallpaper-set", "config-reload",
                          "templates-apply", "color-scheme-get"})
        self.assertTrue(self.data["sealed"])

    def test_activation_error_restores_source_and_nonvisual_state(self):
        self.source.write_text("ARC colors\n")
        self.activation_fixture(fail=True)
        self.assertEqual(self.source.read_text(), "original colors\n")
        self.assertEqual(self.settings.read_text(), '[bar]\norder = ["default"]\n')


class TemplateTests(unittest.TestCase):
    def test_unknown_templates_and_hooks_rejected(self):
        with patch.object(arc, "command", return_value='[theme.templates]\nbuiltin_ids=["hyprland"]'):
            with self.assertRaisesRegex(ValueError, "Templates extras"):
                arc.check_templates()
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            manifest = state / "noctalia/community-templates/claude-code/template.toml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text('[templates.example]\ninput_path="input"\noutput_path="/tmp/not-managed"\n')
            with patch.object(arc, "STATE", state), patch.object(arc, "command", return_value=
                    '[theme.templates]\ncommunity_ids=["claude-code"]'):
                with self.assertRaisesRegex(ValueError, "Saída não auditada"):
                    arc.check_templates()
                manifest.write_text('[templates.example]\npost_hook="unexpected script"\n')
                with self.assertRaisesRegex(ValueError, "Hook não auditado"):
                    arc.check_templates()


if __name__ == "__main__":
    unittest.main()
