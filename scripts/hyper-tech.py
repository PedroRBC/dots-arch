#!/usr/bin/env python3
"""Opt-in ARC activation and conflict-aware recovery; dry-run unless explicit."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib

REPO = Path(__file__).resolve().parents[1]
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
STATE = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
DATA = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
BACKUPS = STATE / "dots-arch/themes"
SOURCES = (
    "home/.config/noctalia/config.toml", "home/.config/hypr/config/colors.lua",
    "home/.config/hypr/config/decorations.lua", "home/.config/kitty/kitty.conf",
    "seeds/.config/alacritty/alacritty.toml.in",
)
BUILTINS = {"kitty", "alacritty", "btop", "gtk3", "gtk4", "qt", "kcolorscheme"}
COMMUNITY = {"claude-code", "vscode"}


def noctalia_binary():
    # An upgraded package can coexist with an older, still-running shell. Its CLI
    # must not migrate settings to a schema the active daemon cannot save.
    matches = []
    for process in Path("/proc").glob("[0-9]*"):
        try:
            if process.stat().st_uid == os.getuid() and (process / "comm").read_text().strip() == "noctalia":
                matches.append(str(process / "exe"))
        except OSError:
            continue
    if len(matches) > 1:
        raise ValueError("Mais de um processo Noctalia; confira a sessão antes de aplicar.")
    return matches[0] if matches else "noctalia"


def command(*args):
    if args[0] == "noctalia":
        args = (noctalia_binary(), *args[1:])
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.PIPE, timeout=30).strip()
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.output or str(error)).strip()
        raise ValueError(f"{args[0]}: {detail}") from error


def msg(*args):
    return command("noctalia", "msg", *args)


def fingerprint(path):
    if not path.exists() and not path.is_symlink():
        return None
    if not path.is_file():
        raise ValueError(f"Não é um arquivo: {path}")
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "link": os.readlink(path) if path.is_symlink() else None}


def managed_paths():
    paths = [REPO / source for source in SOURCES]
    paths.extend(CONFIG / relative for relative in (
        "noctalia/config.toml", "hypr/config/colors.lua", "hypr/config/decorations.lua",
        "kitty/kitty.conf", "kitty/themes/noctalia.conf", "alacritty/alacritty.toml",
        "alacritty/themes/noctalia.toml", "btop/btop.conf", "btop/themes/noctalia.theme",
        "gtk-3.0/gtk.css", "gtk-3.0/noctalia.css", "gtk-4.0/gtk.css", "gtk-4.0/noctalia.css",
        "qt5ct/colors/noctalia.conf", "qt6ct/colors/noctalia.conf", "kdeglobals",
    ))
    paths.append(STATE / "noctalia/settings.toml")
    paths.append(DATA / "color-schemes/noctalia.colors")
    for relative in (
        ".claude/themes/noctalia.json",
        ".vscode/extensions/noctalia.noctaliatheme-0.0.5/themes/NoctaliaTheme-color-theme.json",
        ".vscode-oss/extensions/noctalia.noctaliatheme-0.0.5-universal/themes/NoctaliaTheme-color-theme.json",
        ".vscode-oss/extensions/noctalia.noctaliatheme-0.0.5/themes/NoctaliaTheme-color-theme.json",
        ".antigravity-ide/extensions/noctalia.noctaliatheme-0.0.5-universal/themes/NoctaliaTheme-color-theme.json",
    ):
        paths.append(Path.home() / relative)
    return list(dict.fromkeys(paths))


def check_templates():
    config = tomllib.loads(command("noctalia", "config", "export", "merged"))
    templates = config.get("theme", {}).get("templates", {})
    unknown = set(templates.get("builtin_ids", [])) - BUILTINS
    unknown |= set(templates.get("community_ids", [])) - COMMUNITY
    if unknown or any(key not in {"builtin_ids", "community_ids", "enable_builtin_templates",
                                  "enable_community_templates"} for key in templates):
        raise ValueError("Templates extras precisam de revisão antes da aplicação: " + str(sorted(unknown)))
    # Community hooks are executable user code; only the audited output-only formats are supported.
    for name in templates.get("community_ids", []):
        manifest = STATE / "noctalia/community-templates" / name / "template.toml"
        data = tomllib.loads(manifest.read_text())
        expected = {str(p) for p in managed_paths()}
        for item in data.get("templates", {}).values():
            if set(item) - {"input_path", "output_path", "requires_path"}:
                raise ValueError(f"Hook não auditado em {manifest}")
            outputs = item.get("output_path", [])
            for output in [outputs] if isinstance(outputs, str) else outputs:
                if str(Path(output).expanduser()) not in expected:
                    raise ValueError(f"Saída não auditada: {output}")
    return config


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")
    path.chmod(0o600)


def make_backup():
    check_templates()
    directory = BACKUPS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}-arc")
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o700)
    files = []
    for index, path in enumerate(managed_paths()):
        before = fingerprint(path)
        item = {"path": str(path), "before": before, "copy": str(index)}
        if before is not None:
            shutil.copyfile(path, directory / str(index))
            (directory / str(index)).chmod(0o600)
            item["mode"] = path.stat().st_mode & 0o777
        files.append(item)
    monitors = json.loads(command("hyprctl", "-j", "monitors"))
    settings = {}
    if shutil.which("gsettings"):
        for key in ("gtk-theme", "color-scheme"):
            settings[key] = command("gsettings", "get", "org.gnome.desktop.interface", key)
    data = {"version": 1, "repo": str(REPO), "files": files, "palette": msg("color-scheme-get"),
            "mode": msg("theme-mode-get"), "wallpaper": msg("wallpaper-get"),
            "wallpapers": {m["name"]: msg("wallpaper-get", m["name"]) for m in monitors},
            "gsettings": settings}
    write_json(directory / "backup.json", data)
    print(f"Backup ARC: {directory.name}")
    return directory, data


def load_backup(identifier):
    if not identifier or Path(identifier).name != identifier or identifier in {".", ".."}:
        raise ValueError("Use somente o ID do backup, não um caminho.")
    directory = BACKUPS / identifier
    if directory.is_symlink() or directory.resolve().parent != BACKUPS.resolve():
        raise ValueError("Backup fora do diretório privado.")
    data = json.loads((directory / "backup.json").read_text())
    if data.get("version") != 1 or data.get("repo") != str(REPO):
        raise ValueError("Backup incompatível com este clone.")
    allowed = {str(p) for p in managed_paths()}
    files = data.get("files")
    if not isinstance(files, list) or {item.get("path") for item in files} != allowed:
        raise ValueError("Backup incompleto ou com destinos inválidos.")
    if len(files) != len(allowed):
        raise ValueError("Backup contém destinos repetidos.")
    for item in files:
        if not isinstance(item.get("copy"), str) or not item["copy"].isascii() or not item["copy"].isdigit():
            raise ValueError("Backup contém cópia inválida.")
        if "before" not in item or (data.get("sealed") and "after" not in item):
            raise ValueError("Backup sem fingerprints completos.")
        if item["before"] is not None:
            copy = directory / item["copy"]
            saved = fingerprint(copy)
            if copy.is_symlink() or saved is None or saved["sha256"] != item["before"].get("sha256"):
                raise ValueError("Conteúdo de backup inválido.")
            if not isinstance(item.get("mode"), int) or not 0 <= item["mode"] <= 0o777:
                raise ValueError("Permissões de backup inválidas.")
    return directory, data


def seal(directory, data):
    for item in data["files"]:
        item["after"] = fingerprint(Path(item["path"]))
    data["gsettings_after"] = {key: command("gsettings", "get", "org.gnome.desktop.interface", key)
                               for key in data.get("gsettings", {})}
    data["sealed"] = True
    write_json(directory / "backup.json", data)


def restore(directory, data, apply):
    if not data.get("sealed"):
        raise ValueError("Backup ainda não finalizado; confira as cópias privadas manualmente.")
    conflicts = [item["path"] for item in data["files"]
                 if fingerprint(Path(item["path"])) != item["after"]]
    for key, value in data.get("gsettings_after", {}).items():
        if command("gsettings", "get", "org.gnome.desktop.interface", key) != value:
            conflicts.append("gsettings:" + key)
    if conflicts:
        raise ValueError("Restauração recusada; preserve/revise alterações posteriores: " + ", ".join(conflicts))
    print("Restaurar cores, fontes de configuração e saídas geradas; sem apagar ajustes posteriores.")
    if not apply:
        return
    # Source files first, then local files. Keep symlinks as symlinks.
    for item in data["files"]:
        path = Path(item["path"])
        if path == STATE / "noctalia/settings.toml":
            # Restore only appearance through IPC; never replace mixed runtime state
            # or reintroduce a newer schema marker into an older running daemon.
            continue
        if item["before"] is None:
            if path.exists() or path.is_symlink():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if item["before"]["link"] is not None:
                if not path.is_symlink() or os.readlink(path) != item["before"]["link"]:
                    raise ValueError(f"Link mudou: {path}")
            path.write_bytes((directory / item["copy"]).read_bytes())
            path.chmod(item["mode"])
    command("hyprctl", "eval", 'package.loaded["config.colors"]=nil; '
            'package.loaded["config.decorations"]=nil; require("config.colors"); require("config.decorations")')
    msg("config-reload")
    msg("theme-mode-set", data["mode"])
    msg("color-scheme-set", *data["palette"].split(maxsplit=1))
    msg("wallpaper-set", data["wallpaper"])
    for monitor, wallpaper in data["wallpapers"].items():
        msg("wallpaper-set", monitor, wallpaper)
    for key, value in data.get("gsettings", {}).items():
        command("gsettings", "set", "org.gnome.desktop.interface", key, value)
    print("Configurações anteriores restauradas. Nenhuma sessão foi encerrada.")


def activate(directory, data):
    check_templates()
    palette = CONFIG / "noctalia/palettes/Arc.json"
    wallpapers = CONFIG / "noctalia/wallpapers"
    if not palette.is_file() or not all((wallpapers / f"arc-{kind}.png").is_file()
                                      for kind in ("landscape", "portrait")):
        raise ValueError("Instale os assets pelo script.sh antes de aplicar o tema.")
    command("noctalia", "config", "validate")
    monitors = json.loads(command("hyprctl", "-j", "monitors"))
    try:
        msg("config-reload")
        msg("theme-mode-set", "dark")
        msg("color-scheme-set", "custom", "Arc")
        msg("wallpaper-set", str(wallpapers / "arc-landscape.png"))
        for monitor in monitors:
            width, height = monitor["width"], monitor["height"]
            if monitor.get("transform", 0) % 2:
                width, height = height, width
            kind = "portrait" if height > width else "landscape"
            msg("wallpaper-set", monitor["name"], str(wallpapers / f"arc-{kind}.png"))
        msg("config-reload")
        msg("templates-apply")
        command("hyprctl", "eval", 'package.loaded["config.colors"]=nil; '
            'package.loaded["config.decorations"]=nil; require("config.colors"); require("config.decorations")')
        # The daemon queues template jobs. Require the token and stable managed outputs.
        output = CONFIG / "kitty/themes/noctalia.conf"
        previous, stable = None, 0
        for _ in range(80):
            current = [fingerprint(path) for path in managed_paths()]
            stable = stable + 1 if current == previous else 0
            if stable >= 4 and output.is_file() and "#57d9ff" in output.read_text().lower():
                break
            previous = current
            time.sleep(0.25)
        else:
            raise ValueError("O daemon não confirmou saídas estáveis da paleta ARC.")
        if msg("color-scheme-get") != "custom Arc":
            raise ValueError("A paleta ativa não corresponde a ARC.")
        seal(directory, data)
        print(f"ARC aplicado. Rollback: python3 -I scripts/hyper-tech.py --restore {directory.name} --apply")
    except (ValueError, OSError, subprocess.SubprocessError):
        seal(directory, data)
        print(f"Falha na aplicação; restaurando backup {directory.name}.", file=sys.stderr)
        restore(directory, data, True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--backup", action="store_true", help="Capture antes de editar fontes já linkadas")
    action.add_argument("--restore", metavar="ID", help="Confira rollback; exige --apply para restaurar")
    action.add_argument("--seal", metavar="ID", help="Finalize fingerprints após mudanças e validação")
    parser.add_argument("--from-backup", metavar="ID", help="Use o backup anterior às edições")
    parser.add_argument("--apply", action="store_true", help="Autorize alterações na sessão atual")
    args = parser.parse_args()
    if args.backup:
        make_backup()
    elif args.restore:
        restore(*load_backup(args.restore), args.apply)
    elif args.seal:
        if not args.apply:
            raise ValueError("Finalizar o journal exige --apply.")
        seal(*load_backup(args.seal))
    elif args.apply:
        directory, data = load_backup(args.from_backup) if args.from_backup else make_backup()
        if data.get("sealed"):
            raise ValueError("Backup já usado; crie outro antes de reaplicar.")
        activate(directory, data)
    else:
        print("DRY-RUN: selecionar Arc dark, wallpapers por orientação e templates existentes.")
        print("Sem mudar atalhos, barra, monitores, plugins ou serviços. Nenhum arquivo foi escrito.")
        print("Antes das edições: --backup. Para ativar: --from-backup ID --apply.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
