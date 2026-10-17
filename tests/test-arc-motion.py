#!/usr/bin/env python3
"""Isolated safety and recovery tests for scripts/arc-motion.py."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("arc_motion_under_test", REPO / "scripts/arc-motion.py")
arc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(arc)


class ArcMotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-arc-motion-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.config = self.root / "config"
        self.state = self.root / "state"
        self.cache = self.root / "cache"
        self.repo.mkdir()
        self.config.mkdir()
        self.state.mkdir()
        self.cache.mkdir()
        self.source = self.repo / "animations.lua"
        self.source.write_text("-- baseline animations\n", encoding="utf-8")
        self.link = self.config / "hypr/config/animations.lua"
        self.link.parent.mkdir(parents=True)
        self.link.symlink_to(self.source)
        self.settings = self.state / "noctalia/settings.toml"
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(
            '[wallpaper]\nenabled = true\nimage = "old.png"\n\n[other]\nkey = "keep"\n',
            encoding="utf-8",
        )
        self.backups = self.state / "dots-arch/motion/backups"
        self.runtime = self.state / "dots-arch/motion/runtime.json"
        self.root_dir = self.state / "dots-arch/motion"
        self.patch_constants()

    def patch_constants(self):
        self.constant_patches = [
            mock.patch.object(arc, "REPO", self.repo),
            mock.patch.object(arc, "CONFIG", self.config),
            mock.patch.object(arc, "STATE", self.state),
            mock.patch.object(arc, "CACHE", self.cache),
            mock.patch.object(arc, "ROOT", self.root_dir),
            mock.patch.object(arc, "BACKUPS", self.backups),
            mock.patch.object(arc, "RUNTIME", self.runtime),
            mock.patch.object(arc, "SOURCE", self.source),
            mock.patch.object(arc, "LINK", self.link),
            mock.patch.object(arc, "SETTINGS", self.settings),
        ]
        for patcher in self.constant_patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def seed_runtime(self, **updates):
        self.root_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "repo": str(self.repo),
            "unit": arc.UNIT,
            "token": "a" * 32,
            "before_enabled": True,
            "pending": True,
            "geometry": [],
            "session": "test-session",
            "ready": True,
        }
        data.update(updates)
        arc.write_json(self.runtime, data)
        return data

    def backup_data(self, *, sealed=True):
        original = {"name": "animations.lua", "content": "-- baseline animations\n"}
        before_fp = {"sha256": arc.hashlib.sha256(original["content"].encode()).hexdigest(), "link": None}
        data = {
            "version": 1,
            "repo": str(self.repo),
            "source": before_fp,
            "link": arc.fingerprint(self.link),
            "mode": 0o644,
            "animations": [],
            "geometry": [],
            "nonvisual": "not-used",
            "sealed": sealed,
        }
        directory = self.backups / "backup-test"
        directory.mkdir(parents=True)
        (directory / "animations.lua").write_text(original["content"], encoding="utf-8")
        arc.write_json(directory / "backup.json", data)
        return directory, data

    def test_default_dry_run_and_status_do_not_write_or_send_setters(self):
        for argv in ([], ["--status"]):
            with self.subTest(argv=argv):
                output = io.StringIO()
                with mock.patch.object(arc.sys, "argv", ["arc-motion.py", *argv]), \
                     mock.patch.object(arc, "noctalia", side_effect=AssertionError("IPC setter called")), \
                     mock.patch.object(arc, "command", side_effect=AssertionError("process called")), \
                     contextlib.redirect_stdout(output):
                    arc.main()
                self.assertIn("DRY-RUN" if not argv else "parado", output.getvalue())
                self.assertFalse(self.root_dir.exists())
                self.assertFalse(self.settings.is_symlink())
                self.assertEqual(self.settings.read_text().count("enabled = true"), 1)

    def test_patch_enabled_true_false_and_absent_preserve_every_other_toml_value(self):
        samples = [
            (b'[wallpaper]\nenabled = true\nimage = "new.png" # chosen\n\n[other]\nkeep = 7\n', False),
            (b'[wallpaper]\nenabled = false\nimage = "new.png"\n\n[other]\nkeep = 7\n', True),
            (b'[wallpaper]\nimage = "new.png"\n\n[other]\nkeep = 7\n', False),
        ]
        for blob, value in samples:
            with self.subTest(value=value, original=blob):
                before = arc.tomllib.loads(blob.decode())
                result = arc.patch_enabled(blob, value)
                after = arc.tomllib.loads(result.decode())
                self.assertEqual(after["wallpaper"].get("image"), before["wallpaper"]["image"])
                self.assertEqual(after["other"], before["other"])
                self.assertEqual(after["wallpaper"]["enabled"], value)
                self.assertEqual(result.count(b"enabled ="), 1)
        absent = arc.patch_enabled(samples[2][0], None)
        self.assertNotIn(b"enabled =", absent)
        self.assertEqual(arc.tomllib.loads(absent.decode()), arc.tomllib.loads(samples[2][0].decode()))

    def test_patch_enabled_rejects_inline_or_duplicate_wallpaper_tables_and_bad_toml(self):
        invalid = [
            b'wallpaper = { enabled = true, image = "x" }\n',
            b'[wallpaper]\nenabled = true\n[wallpaper]\nimage = "x"\n',
            b'[wallpaper]\nenabled = "true"\n',
        ]
        for blob in invalid:
            with self.subTest(blob=blob), self.assertRaises(ValueError):
                arc.patch_enabled(blob, False)

    def test_set_enabled_rejects_settings_symlink_before_writing(self):
        target = self.root / "settings-target.toml"
        original = self.settings.read_bytes()
        target.write_bytes(original)
        self.settings.unlink()
        self.settings.symlink_to(target)
        with mock.patch.object(arc, "noctalia") as ipc:
            with self.assertRaises(ValueError):
                arc.set_enabled(True, False)
        ipc.assert_not_called()
        self.assertEqual(target.read_bytes(), original)

    def test_check_link_rejects_unexpected_symlink_target(self):
        self.link.unlink()
        unrelated = self.root / "unrelated.lua"
        unrelated.write_text("other", encoding="utf-8")
        self.link.symlink_to(unrelated)
        with self.assertRaises(ValueError):
            arc.check_link()

    def test_output_groups_use_transform_adjusted_orientation(self):
        monitors = [
            {"name": "DP-1", "width": 2560, "height": 1440, "transform": 0},
            {"name": "DP-2", "width": 1080, "height": 1920, "transform": 0},
            {"name": "HDMI-A-1", "width": 1920, "height": 1080, "transform": 1},
        ]
        self.assertEqual(arc.groups(monitors), {"landscape": ["DP-1"], "portrait": ["DP-2", "HDMI-A-1"]})
        with self.assertRaises(ValueError):
            arc.groups([{"name": "unsafe name", "width": 1920, "height": 1080, "transform": 0}])

    def test_scoped_edit_restores_autoreload_setting_after_success_or_failure(self):
        for exception in (None, RuntimeError("simulated reload error")):
            with self.subTest(exception=exception), mock.patch.object(
                arc, "command", side_effect=["bool: false", "", ""]
            ) as command:
                try:
                    with arc.scoped_edit():
                        if exception:
                            raise exception
                except RuntimeError:
                    if exception is None:
                        raise
                self.assertEqual([call.args for call in command.call_args_list], [
                    ("hyprctl", "getoption", "misc:disable_autoreload"),
                    ("hyprctl", "eval", "hl.config({misc={disable_autoreload=true}})"),
                    ("hyprctl", "eval", "hl.config({misc={disable_autoreload=false}})"),
                ])

    def test_scoped_edit_keeps_preexisting_disabled_state(self):
        with mock.patch.object(arc, "command", return_value="bool: true") as command:
            with arc.scoped_edit():
                pass
        command.assert_called_once_with("hyprctl", "getoption", "misc:disable_autoreload")

    def test_backup_copy_tampering_is_rejected(self):
        directory, _ = self.backup_data(sealed=False)
        (directory / "animations.lua").write_text("tampered", encoding="utf-8")
        with self.assertRaises(ValueError):
            arc.load_backup(directory.name)

    def test_restore_refuses_source_conflict_before_stopping_or_reloading(self):
        directory, data = self.backup_data(sealed=True)
        data["after"] = arc.fingerprint(self.source)
        data["after_link"] = arc.fingerprint(self.link)
        data["after_animations"] = {}
        arc.write_json(directory / "backup.json", data)
        self.source.write_text("changed after backup", encoding="utf-8")
        with mock.patch.object(arc, "animation_nodes", return_value={}), \
             mock.patch.object(arc, "stop") as stop, \
             mock.patch.object(arc, "command") as command:
            with self.assertRaises(ValueError):
                arc.restore(directory, data, True)
        stop.assert_not_called()
        command.assert_not_called()

    def test_restore_uses_only_lua_module_reload_and_no_general_reload(self):
        directory, data = self.backup_data(sealed=True)
        data.update(after=arc.fingerprint(self.source), after_link=arc.fingerprint(self.link), after_animations={})
        with mock.patch.object(arc, "animation_nodes", return_value={}), \
             mock.patch.object(arc, "stop") as stop, \
             mock.patch.object(arc, "command", side_effect=["bool: false", "", "", ""]) as command:
            arc.restore(directory, data, True)
        stop.assert_called_once_with()
        self.assertEqual(self.source.read_text(encoding="utf-8"), "-- baseline animations\n")
        self.assertEqual([call.args for call in command.call_args_list], [
            ("hyprctl", "getoption", "misc:disable_autoreload"),
            ("hyprctl", "eval", "hl.config({misc={disable_autoreload=true}})"),
            ("hyprctl", "eval", arc.RELOAD),
            ("hyprctl", "eval", "hl.config({misc={disable_autoreload=false}})"),
        ])
        self.assertFalse(any(call.args == ("hyprctl", "reload") for call in command.call_args_list))

    def test_cleanup_restores_only_enable_and_preserves_new_wallpaper_paths(self):
        self.seed_runtime(before_enabled=True)
        chosen = '/home/test/Pictures/user-selected.jpg'
        self.settings.write_text(f'[wallpaper]\nenabled = false\nimage = "{chosen}"\n\n[other]\nkeep = "yes"\n', encoding="utf-8")
        with mock.patch.object(arc, "noctalia", side_effect=["", '[wallpaper]\nenabled = true\n']) as ipc:
            arc.cleanup("a" * 32)
        parsed = arc.tomllib.loads(self.settings.read_text(encoding="utf-8"))
        self.assertTrue(parsed["wallpaper"]["enabled"])
        self.assertEqual(parsed["wallpaper"]["image"], chosen)
        self.assertEqual(parsed["other"], {"keep": "yes"})
        self.assertFalse(self.runtime.exists())
        self.assertEqual(ipc.call_args_list[0].args, ("msg", "config-reload"))

    def test_stop_refuses_unit_not_owned_by_runtime_journal(self):
        self.seed_runtime()
        with mock.patch.object(arc, "command", side_effect=["loaded", "some other unit"]) as command:
            with self.assertRaises(ValueError):
                arc.stop()
        self.assertEqual([call.args for call in command.call_args_list], [
            ("systemctl", "--user", "show", arc.UNIT, "--property=LoadState", "--value"),
            ("systemctl", "--user", "show", arc.UNIT, "--property=Description", "--value"),
        ])
        self.assertTrue(self.runtime.exists())

    def test_early_missing_dependency_failure_creates_no_state_or_settings_changes(self):
        original = self.settings.read_bytes()
        with mock.patch.object(arc, "check_wallpaper", side_effect=ValueError("missing mpvpaper")), \
             mock.patch.object(arc, "private_dir") as create_dir, \
             mock.patch.object(arc, "command") as command:
            with self.assertRaisesRegex(ValueError, "missing mpvpaper"):
                arc.start()
        create_dir.assert_not_called()
        command.assert_not_called()
        self.assertFalse(self.root_dir.exists())
        self.assertEqual(self.settings.read_bytes(), original)

    def test_interactions_only_cli_skips_wallpaper_preflight_and_start(self):
        self.backup_data(sealed=False)
        with (mock.patch.object(arc.sys, "argv", ["arc-motion.py", "--interactions", "--from-backup", "backup-test", "--apply"]),
              mock.patch.object(arc, "check_wallpaper", side_effect=AssertionError("wallpaper dependency checked")),
              mock.patch.object(arc, "apply_interactions") as apply,
              mock.patch.object(arc, "start") as start):
            arc.main()
        apply.assert_called_once()
        start.assert_not_called()

    def test_full_apply_dependency_failure_precedes_any_lua_or_ipc_changes(self):
        with (mock.patch.object(arc.sys, "argv", ["arc-motion.py", "--from-backup", "backup-test", "--apply"]),
              mock.patch.object(arc, "check_wallpaper", side_effect=ValueError("missing mpvpaper")) as check,
              mock.patch.object(arc, "apply_interactions") as apply,
              mock.patch.object(arc, "start") as start,
              mock.patch.object(arc, "command") as command):
            with self.assertRaisesRegex(ValueError, "missing mpvpaper"):
                arc.main()
        check.assert_called_once_with()
        apply.assert_not_called()
        start.assert_not_called()
        command.assert_not_called()
        self.assertEqual(self.source.read_text(encoding="utf-8"), "-- baseline animations\n")
        self.assertEqual(self.settings.read_text(encoding="utf-8").count("enabled = true"), 1)

    def test_supervisor_startup_failure_never_disables_native_wallpaper(self):
        monitor = {"name": "DP-1", "width": 1920, "height": 1080, "x": 0, "y": 0,
                   "scale": 1, "transform": 0, "refreshRate": 60}
        self.seed_runtime(geometry=[monitor], pending=False)
        before = self.settings.read_bytes()

        class FailedPlayer:
            def poll(self):
                return 1

            def wait(self, timeout=None):
                return 1

        runtime_dir = self.root / "runtime"
        runtime_dir.mkdir()
        with (mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime_dir)}),
              mock.patch.object(arc.subprocess, "Popen", return_value=FailedPlayer()) as popen,
              mock.patch.object(arc, "videos", return_value={"landscape": self.root / "arc.mp4"}),
              mock.patch.object(arc, "set_enabled") as set_enabled,
              mock.patch.object(arc.signal, "signal"),
              mock.patch.object(arc.time, "monotonic", side_effect=[0, 1]),
              mock.patch.object(arc.time, "sleep")):
            with self.assertRaisesRegex(ValueError, "encerrou antes de carregar"):
                arc.supervise("a" * 32)
        self.assertEqual(popen.call_args.args[0][0], "mpvpaper")
        set_enabled.assert_not_called()
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertFalse(self.runtime.exists())

    def test_supervisor_player_crash_restores_enable_and_keeps_user_wallpaper_choice(self):
        monitor = {"name": "DP-1", "width": 1920, "height": 1080, "x": 0, "y": 0,
                   "scale": 1, "transform": 0, "refreshRate": 60}
        self.seed_runtime(geometry=[monitor])
        chosen = '/home/test/Pictures/changed-during-motion.jpg'
        self.settings.write_text(f'[wallpaper]\nenabled = true\nimage = "{chosen}"\n', encoding="utf-8")

        class CrashedPlayer:
            def __init__(self):
                self.polls = iter([None, None, 1, 1])
                self.terminated = False
                self.waited = False

            def poll(self):
                return next(self.polls, 1)

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                self.waited = True
                return 1

        player = CrashedPlayer()
        runtime_dir = self.root / "runtime"
        runtime_dir.mkdir()
        with (mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime_dir)}),
              mock.patch.object(arc.subprocess, "Popen", return_value=player),
              mock.patch.object(arc, "videos", return_value={"landscape": self.root / "arc.mp4"}),
              mock.patch.object(arc, "mpv_request", return_value={"w": 1920, "h": 1080}),
              mock.patch.object(arc, "geometry", return_value=[monitor]),
              mock.patch.object(arc.signal, "signal"),
              mock.patch.object(arc.time, "monotonic", side_effect=[0, 1, 2, 3]),
              mock.patch.object(arc.time, "sleep"),
              mock.patch.object(arc, "noctalia", side_effect=["", '[wallpaper]\nenabled = false\n', "", f'[wallpaper]\nenabled = true\nimage = "{chosen}"\n']) as ipc):
            with self.assertRaisesRegex(ValueError, "Player encerrou"):
                arc.supervise("a" * 32)
        parsed = arc.tomllib.loads(self.settings.read_text(encoding="utf-8"))
        self.assertTrue(parsed["wallpaper"]["enabled"])
        self.assertEqual(parsed["wallpaper"]["image"], chosen)
        self.assertTrue(player.waited)
        self.assertFalse(self.runtime.exists())
        self.assertEqual([call.args for call in ipc.call_args_list], [
            ("msg", "config-reload"), ("config", "export", "merged"),
            ("msg", "config-reload"), ("config", "export", "merged"),
        ])

    def test_wallpaper_preflight_fails_on_missing_asset_before_creating_state(self):
        with mock.patch.object(arc.shutil, "which", return_value="/usr/bin/mock"), \
             mock.patch.object(arc, "command") as command:
            with self.assertRaises(ValueError):
                arc.check_wallpaper()
        command.assert_not_called()
        self.assertFalse(self.root_dir.exists())


if __name__ == "__main__":
    unittest.main()
