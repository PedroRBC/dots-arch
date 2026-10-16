#!/usr/bin/env python3
"""Static checks only: never launch the desktop, apps or NAS deployment tools."""

import configparser
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

REPO = Path(__file__).resolve().parents[1]


def check(condition, message):
    if not condition:
        raise ValueError(message)


def run(*args):
    subprocess.run(args, cwd=REPO, check=True, capture_output=True, text=True)


def main():
    rows = []
    for number, line in enumerate((REPO / "manifests/desktop.tsv").read_text().splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        check(len(fields) == 5, f"Manifest line {number}: expected five TAB-separated fields")
        profile, mode, source, root, dest = fields
        check(profile in {"all", "portable", "desktop"}, f"Invalid profile: {profile}")
        check(mode in {"link", "seed", "render"}, f"Invalid mode: {mode}")
        check(root in {"home", "config"}, f"Invalid root: {root}")
        for value in (source, dest):
            parts = value.split("/")
            check(not Path(value).is_absolute() and all(p not in {"", ".", ".."} for p in parts),
                  f"Invalid manifest path: {value}")
        path = REPO / source
        check(path.is_file() and not path.is_symlink(), f"Missing regular source: {source}")
        check(path.resolve().is_relative_to(REPO), f"External source: {source}")
        check("/home/pedro" not in path.read_text(), f"Hardcoded personal home: {source}")
        check(mode != "render" or "@CONFIG_HOME@" in path.read_text(), f"Missing render token: {source}")
        rows.append(fields)

    for profile in ("portable", "desktop"):
        targets = []
        for selected, mode, source, root, dest in rows:
            if selected not in {"all", profile}:
                continue
            # In the default XDG layout both roots share the same home.
            target = Path(".config") / dest if root == "config" else Path(dest)
            check(all(target != old and target not in old.parents and old not in target.parents for old in targets),
                  f"Duplicate or overlapping destination in {profile}: {dest}")
            targets.append(target)
        print(f"OK manifest {profile}: {len(targets)} destinations")

    sources = sorted({REPO / row[2] for row in rows})
    for path in sources:
        suffix = path.suffix
        if suffix == ".toml" or path.name.endswith(".toml.in"):
            tomllib.loads(path.read_text())
        elif suffix == ".json":
            json.loads(path.read_text())
        elif suffix in {".ini", ".in"}:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read_string(path.read_text())
    print("OK TOML, JSON and INI sources")

    for binary, extension, flags in (("luac", ".lua", ("-p",)),
                                      ("fish", ".fish", ("--no-config", "--no-execute"))):
        tool = shutil.which(binary)
        if not tool:
            print(f"SKIP {binary}: not installed")
            continue
        paths = [path for path in sources if path.suffix == extension]
        for path in paths:
            run(tool, *flags, str(path))
        print(f"OK {binary}: {len(paths)} files")
    run("bash", "-n", "home/.config/uwsm/env")

    ignored = [
        ".env", ".env.local", "local/hypr.lua", "private/token", "--help/residue",
        "infra/truenas/apps/example/ddns.env", "infra/truenas/apps/example/secrets/token",
        "infra/truenas/apps/example/credentials.txt", "infra/truenas/runtime/example",
        "infra/truenas/nas/__pycache__/prepare.pyc", "home/.config/fish/fish_variables",
        "home/.local/state/noctalia/settings.toml", "home/.config/wayvnc/tls/server.key",
        "home/.config/Code/User/settings.json", "home/.config/kitty/themes/noctalia.conf",
        "backup.bak.123", "history.sqlite3", "authkey.txt",
        "infra/truenas/README.md", "infra/truenas/apps/jellyfin/compose.yaml",
    ]
    allowed = [str(path.relative_to(REPO)) for path in sources] + [
        "script.sh", "README.md", "manifests/desktop.tsv", "tests/test-install.sh",
        "tests/validate-configs.py", ".env.example",
    ]
    for path in ignored + allowed:
        result = subprocess.run(["git", "-c", "core.excludesfile=/dev/null", "check-ignore",
                                 "--no-index", "-q", "--", path], cwd=REPO)
        check(result.returncode in {0, 1}, f"git check-ignore failed: {path}")
        check((result.returncode == 0) == (path in ignored), f"Unexpected ignore status: {path}")
    print(f"OK .gitignore: {len(ignored)} excluded / {len(allowed)} allowed")
    print("Static validation passed; runtime compatibility and visual appearance were not tested.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        sys.exit(1)
