#!/usr/bin/env python3
"""Apply the real manifest only inside temporary HOME/XDG directories."""

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib

REPO = Path(__file__).resolve().parents[1]
ROWS = [line.split("\t") for line in (REPO / "manifests/desktop.tsv").read_text().splitlines()
        if line and not line.startswith("#")]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    return {str(p.relative_to(root)): ("link", os.readlink(p)) if p.is_symlink()
            else ("file", digest(p)) for p in root.rglob("*") if p.is_symlink() or p.is_file()}


def exercise(profile):
    with tempfile.TemporaryDirectory(prefix="dots manifest ") as temporary:
        root = Path(temporary)
        home, config, state = root / "home with spaces", root / "config files", root / "state files"
        for path in (home, config, state):
            path.mkdir()
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(config), XDG_STATE_HOME=str(state))

        def run(*args):
            result = subprocess.run(["bash", str(REPO / "script.sh"), *args], env=env,
                                    cwd=root, text=True, capture_output=True, check=True)
            return result.stdout

        # Existing seed, overwritten config and unrelated runtime data must survive restore.
        (config / "kitty/themes").mkdir(parents=True)
        (config / "kitty/themes/noctalia.conf").write_text("# keep existing theme\n")
        (config / "kitty/kitty.conf").write_text("# original kitty config\n")
        (state / "noctalia").mkdir()
        (state / "noctalia/settings.toml").write_text("# untouched local overrides\n")
        (config / "unmanaged.txt").write_text("untouched\n")
        before = snapshot(root)
        run("--profile", profile, "--dry-run")
        assert snapshot(root) == before, "dry-run wrote files"
        output = run("--profile", profile, "--apply")
        backup_id = output.strip().split("Backup: ")[-1]
        backup = state / "dots-arch/backups" / backup_id
        assert backup.is_dir() and backup.stat().st_mode & 0o777 == 0o700
        selected = [row for row in ROWS if row[0] in {"all", profile}]
        counts = {"link": 0, "seed": 0, "render": 0}
        for _, mode, source, destination_root, relative in selected:
            target = (config if destination_root == "config" else home) / relative
            counts[mode] += 1
            if mode == "link":
                assert target.is_symlink() and target.resolve() == REPO / source, target
            elif mode == "seed":
                expected = b"# keep existing theme\n" if relative == "kitty/themes/noctalia.conf" else (REPO / source).read_bytes()
                assert not target.is_symlink() and target.read_bytes() == expected, target
            else:
                expected = (REPO / source).read_text().replace("@CONFIG_HOME@", str(config))
                assert not target.is_symlink() and target.read_text() == expected, target
                if target.suffix == ".toml":
                    tomllib.loads(target.read_text())
        applied = snapshot(root)
        assert "Nenhuma alteração necessária" in run("--profile", profile, "--apply")
        assert snapshot(root) == applied, "reapply was not a no-op"
        run("--restore", backup_id, "--dry-run")
        assert snapshot(root) == applied, "restore preview wrote files"
        run("--restore", backup_id, "--apply")
        after = snapshot(root)
        # Only the private recovery journal may remain; empty parent dirs are harmless.
        after = {key: value for key, value in after.items() if not key.startswith("state files/dots-arch/")}
        assert after == before, "restore did not recover the original files"
        print(f"OK real manifest {profile}: {counts}; apply/reapply/restore, spaces and runtime preserved")


if __name__ == "__main__":
    source_hashes = {row[2]: digest(REPO / row[2]) for row in ROWS}
    for selected_profile in ("portable", "desktop"):
        exercise(selected_profile)
    assert all(digest(REPO / name) == value for name, value in source_hashes.items()), "repository source changed"
    print("Real-manifest tests passed without touching the live HOME or installing packages.")
