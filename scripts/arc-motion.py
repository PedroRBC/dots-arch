#!/usr/bin/env python3
"""Opt-in ARC Motion, session-only wallpaper and independent recovery."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import tomllib

REPO = Path(__file__).resolve().parents[1]
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
ROOT = STATE / "dots-arch/motion"
BACKUPS = ROOT / "backups"
RUNTIME = ROOT / "runtime.json"
SOURCE = REPO / "home/.config/hypr/config/animations.lua"
LINK = CONFIG / "hypr/config/animations.lua"
SETTINGS = STATE / "noctalia/settings.toml"
UNIT = "arc-motion.service"
LEAVES = {"global", "windows", "workspaces", "specialWorkspaceIn", "specialWorkspaceOut"}
RELOAD = 'package.loaded["config.animations"]=nil; require("config.animations")'

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("arc_static", REPO / "scripts/hyper-tech.py")
static = importlib.util.module_from_spec(spec)
spec.loader.exec_module(static)


def command(*args, timeout=30):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError(f"{args[0]}: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def noctalia(*args):
    return command(static.noctalia_binary(), *args)


@contextmanager
def scoped_edit():
    option = command("hyprctl", "getoption", "misc:disable_autoreload")
    match = re.search(r"^bool: (true|false)$", option, re.MULTILINE)
    if not match:
        raise ValueError("Não foi possível conferir misc.disable_autoreload.")
    disabled = match[1] == "true"
    if not disabled:
        command("hyprctl", "eval", 'hl.config({misc={disable_autoreload=true}})')
    try:
        yield
    finally:
        if not disabled:
            command("hyprctl", "eval", 'hl.config({misc={disable_autoreload=false}})')


def private_dir(path):
    if path.is_symlink():
        raise ValueError(f"Diretório simbólico inesperado: {path}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def write_json(path, data):
    if path.is_symlink():
        raise ValueError(f"Journal simbólico inesperado: {path}")
    atomic_write(path, (json.dumps(data, indent=2) + "\n").encode(), 0o600)


def atomic_write(path, content, mode, expected=None):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"Arquivo irregular: {path}")
    if expected is not None and path.read_bytes() != expected:
        raise ValueError(f"Alteração concorrente: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=".arc-motion-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if expected is not None and path.read_bytes() != expected:
            raise ValueError(f"Alteração concorrente: {path}")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fingerprint(path):
    return static.fingerprint(path)


def geometry():
    keys = ("name", "width", "height", "x", "y", "scale", "transform", "refreshRate")
    return sorted(({key: item[key] for key in keys}
                   for item in json.loads(command("hyprctl", "-j", "monitors"))), key=lambda m: m["name"])


def nonvisual_hash():
    data = tomllib.loads(SETTINGS.read_text())
    for key in ("wallpaper", "theme"):
        data.pop(key, None)
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def check_link():
    if not SOURCE.is_file() or SOURCE.is_symlink() or not LINK.is_symlink() or LINK.resolve() != SOURCE:
        raise ValueError("O módulo animations.lua deve ser o link deste clone.")


def make_backup():
    check_link()
    if RUNTIME.exists():
        raise ValueError("Encerre o wallpaper Motion antes de capturar outro baseline.")
    nodes = json.loads(command("hyprctl", "-j", "animations"))[0]
    if not LEAVES <= {node["name"] for node in nodes if node["overridden"]}:
        raise ValueError("Baseline de animações diferente do esperado; revise antes de aplicar.")
    snapshot = {"version": 1, "repo": str(REPO), "source": fingerprint(SOURCE),
                "link": fingerprint(LINK), "mode": SOURCE.stat().st_mode & 0o777,
                "animations": nodes, "geometry": geometry(), "nonvisual": nonvisual_hash(),
                "sealed": False}
    private_dir(BACKUPS)
    directory = BACKUPS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}-motion")
    private_dir(directory)
    atomic_write(directory / "animations.lua", SOURCE.read_bytes(), 0o600)
    write_json(directory / "backup.json", snapshot)
    print(f"Backup ARC Motion: {directory.name}")
    return directory, snapshot


def load_backup(identifier):
    if not identifier or Path(identifier).name != identifier or identifier in {".", ".."}:
        raise ValueError("Use somente o ID do backup Motion.")
    directory = BACKUPS / identifier
    if directory.is_symlink() or directory.resolve().parent != BACKUPS.resolve():
        raise ValueError("Backup fora do diretório privado.")
    journal = directory / "backup.json"
    saved = directory / "animations.lua"
    if journal.is_symlink() or saved.is_symlink():
        raise ValueError("Backup simbólico inválido.")
    data = json.loads(journal.read_text())
    if (not isinstance(data, dict) or data.get("version") != 1 or data.get("repo") != str(REPO)
            or not isinstance(data.get("source"), dict) or not isinstance(data.get("link"), dict)
            or not isinstance(data.get("animations"), list) or type(data.get("sealed")) is not bool):
        raise ValueError("Backup Motion incompatível.")
    if fingerprint(saved) != {"sha256": data["source"].get("sha256"), "link": None}:
        raise ValueError("Cópia de animações corrompida.")
    if type(data.get("mode")) is not int or not 0 <= data["mode"] <= 0o777:
        raise ValueError("Permissões inválidas no backup.")
    return directory, data


def animation_nodes():
    return {item["name"]: item for item in json.loads(command("hyprctl", "-j", "animations"))[0]}


def same_nodes(before, after):
    return {name: node for name, node in before.items()} == {name: node for name, node in after.items()}


def seal(directory, data):
    data.update(after=fingerprint(SOURCE), after_link=fingerprint(LINK),
                after_animations=animation_nodes(), sealed=True)
    write_json(directory / "backup.json", data)


def apply_interactions(directory, data):
    if data.get("sealed"):
        raise ValueError("Backup já utilizado; não sobrescreva seu ponto de recuperação.")
    check_link()
    if fingerprint(LINK)["link"] != data["link"]["link"]:
        raise ValueError("Link de animações alterado.")
    old = {item["name"]: item for item in data["animations"]}
    command("luac", "-p", str(SOURCE))
    try:
        command("hyprctl", "eval", RELOAD)
        errors = command("hyprctl", "configerrors")
        if errors:
            raise ValueError(errors)
        now = animation_nodes()
        changed = {name for name in old if old[name] != now.get(name)}
        if not changed <= LEAVES or geometry() != data["geometry"] or nonvisual_hash() != data["nonvisual"]:
            raise ValueError("A aplicação alterou algo fora dos cinco nós de animação.")
        seal(directory, data)
    except (ValueError, OSError, subprocess.SubprocessError):
        with scoped_edit():
            SOURCE.write_bytes((directory / "animations.lua").read_bytes())
            command("hyprctl", "eval", RELOAD)
        raise
    print(f"Interações ARC Motion aplicadas. Recuperação: --restore {directory.name} --apply")


def restore(directory, data, apply):
    if not data.get("sealed"):
        raise ValueError("Backup ainda não finalizado.")
    check_link()
    if fingerprint(SOURCE) != data.get("after") or fingerprint(LINK) != data.get("after_link"):
        raise ValueError("Restauração recusada: alterações posteriores em animations.lua.")
    if not same_nodes(data.get("after_animations", {}), animation_nodes()):
        raise ValueError("Restauração recusada: animações runtime alteradas posteriormente.")
    print("Restaurar somente animações; encerrar o wallpaper Motion se ativo.")
    if not apply:
        return
    stop()
    with scoped_edit():
        SOURCE.write_bytes((directory / "animations.lua").read_bytes())
        SOURCE.chmod(data["mode"])
        command("hyprctl", "eval", RELOAD)
    old = {item["name"]: item for item in data["animations"]}
    if not same_nodes(old, animation_nodes()):
        raise ValueError("Runtime não corresponde ao baseline; confira o backup privado.")
    print("ARC estático restaurado; paleta e imagens não foram substituídas.")


def enabled_value(blob):
    value = tomllib.loads(blob.decode()).get("wallpaper", {}).get("enabled")
    if value is not None and not isinstance(value, bool):
        raise ValueError("wallpaper.enabled não é booleano.")
    return value


def patch_enabled(blob, value):
    # Only a plain table/key is supported. Refuse exotic valid TOML rather than reserialize mixed state.
    enabled_value(blob)
    text = blob.decode()
    lines = text.splitlines(keepends=True)
    sections = [i for i, line in enumerate(lines) if re.fullmatch(r"\s*\[wallpaper\]\s*(?:#.*)?\n?", line)]
    if len(sections) != 1:
        raise ValueError("Esperada uma única tabela [wallpaper] simples no estado local.")
    start = sections[0] + 1
    end = next((i for i in range(start, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    keys = [i for i in range(start, end) if re.match(r"\s*enabled\s*=", lines[i])]
    if len(keys) > 1 or (enabled_value(blob) is not None and not keys):
        raise ValueError("Formato de wallpaper.enabled não suportado.")
    if keys:
        del lines[keys[0]]
    if value is not None:
        lines.insert(start, f"enabled = {'true' if value else 'false'}\n")
    result = "".join(lines).encode()
    before, after = tomllib.loads(blob.decode()), tomllib.loads(result.decode())
    before["wallpaper"].pop("enabled", None)
    after["wallpaper"].pop("enabled", None)
    if before != after or enabled_value(result) != value:
        raise ValueError("Patch recusado: alteração fora do campo de enable.")
    return result


def set_enabled(expected, value):
    if SETTINGS.is_symlink() or SETTINGS.parent.is_symlink() or not SETTINGS.is_file():
        raise ValueError("Estado Noctalia deve ser um arquivo local regular.")
    blob = SETTINGS.read_bytes()
    if enabled_value(blob) != expected:
        raise ValueError("wallpaper.enabled foi alterado por outro processo.")
    atomic_write(SETTINGS, patch_enabled(blob, value), SETTINGS.stat().st_mode & 0o777, blob)
    noctalia("msg", "config-reload")
    merged = tomllib.loads(noctalia("config", "export", "merged"))
    if merged.get("wallpaper", {}).get("enabled", True) != (True if value is None else value):
        raise ValueError("Noctalia não confirmou o renderizador solicitado.")


def runtime_data(token=None):
    if RUNTIME.is_symlink():
        raise ValueError("Journal runtime simbólico recusado.")
    data = json.loads(RUNTIME.read_text())
    if (not isinstance(data, dict) or data.get("version") != 1 or data.get("repo") != str(REPO)
            or data.get("unit") != UNIT or not isinstance(data.get("token"), str)
            or not re.fullmatch(r"[a-f0-9]{32}", data["token"])
            or not isinstance(data.get("pending"), bool) or "before_enabled" not in data
            or (data["before_enabled"] is not None and type(data["before_enabled"]) is not bool)):
        raise ValueError("Journal runtime inválido.")
    if token is not None and data["token"] != token:
        raise ValueError("Ownership de runtime diferente; nenhuma alteração feita.")
    return data


def cleanup(token):
    if not RUNTIME.exists():
        return
    data = runtime_data(token)
    if data["pending"]:
        current = enabled_value(SETTINGS.read_bytes())
        if current is False or current == data["before_enabled"]:
            set_enabled(current, data["before_enabled"])
        else:
            print("Enable alterado posteriormente; preservado.", file=sys.stderr)
    RUNTIME.unlink()


def stop():
    if not RUNTIME.exists():
        print("Wallpaper Motion já está parado.")
        return
    data = runtime_data()
    active = command("systemctl", "--user", "show", UNIT, "--property=LoadState", "--value")
    if active != "not-found":
        description = command("systemctl", "--user", "show", UNIT, "--property=Description", "--value")
        if description != "ARC Motion " + data["token"]:
            raise ValueError("Unidade não pertence a este journal; não será encerrada.")
        command("systemctl", "--user", "stop", UNIT)
    cleanup(data["token"])
    print("Fundo nativo restaurado; nenhuma imagem escolhida foi sobrescrita.")


def groups(monitors):
    result = {"landscape": [], "portrait": []}
    for monitor in monitors:
        width, height = monitor["width"], monitor["height"]
        if monitor["transform"] % 2:
            width, height = height, width
        name = monitor["name"]
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", name):
            raise ValueError("Nome de output não suportado.")
        result["portrait" if height > width else "landscape"].append(name)
    return {kind: names for kind, names in result.items() if names}


def videos():
    return {kind: CACHE / f"dots-arch/arc-motion/arc-motion-{kind}.mp4" for kind in ("landscape", "portrait")}


def check_wallpaper():
    for executable in ("mpvpaper", "ffprobe", "systemd-run", "systemctl"):
        if not shutil.which(executable):
            raise ValueError(f"Dependência ausente: {executable}. Nenhuma troca de fundo realizada.")
    for kind, path in videos().items():
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Gere o vídeo {kind} primeiro: {path}")
        probe = json.loads(command("ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)))
        streams = probe["streams"]
        expected = (1920, 1080) if kind == "landscape" else (768, 1366)
        if (len(streams) != 1 or streams[0].get("codec_type") != "video"
                or streams[0].get("codec_name") != "h264"
                or (streams[0].get("width"), streams[0].get("height")) != expected
                or streams[0].get("avg_frame_rate") != "24/1"
                or int(streams[0].get("nb_frames", 0)) != 1440
                or abs(float(probe["format"]["duration"]) - 60) > 0.1):
            raise ValueError(f"Vídeo fora do contrato: {path}")
    if command("systemctl", "--user", "is-active", "graphical-session.target") != "active":
        raise ValueError("Sessão gráfica systemd indisponível.")


def start():
    check_wallpaper()
    private_dir(ROOT)
    with (ROOT / "operation.lock").open("a") as lock:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if RUNTIME.exists():
            raise ValueError("Há um journal Motion ativo; use --status/--stop primeiro.")
        if command("systemctl", "--user", "show", UNIT, "--property=LoadState", "--value") != "not-found":
            raise ValueError("Já existe uma unidade arc-motion; nenhuma unidade foi substituída.")
        before = enabled_value(SETTINGS.read_bytes())
        if before is False:
            raise ValueError("Wallpaper nativo já está desabilitado; não assumir propriedade de outro renderer.")
        token = secrets.token_hex(16)
        data = {"version": 1, "repo": str(REPO), "unit": UNIT, "token": token,
                "before_enabled": before, "pending": False, "geometry": geometry(),
                "session": os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"), "ready": False}
        groups(data["geometry"])
        write_json(RUNTIME, data)
        args = [sys.executable, "-I", str(Path(__file__).resolve())]
        import shlex
        post = shlex.join(args + ["--cleanup", token]).replace("%", "%%").replace("$", "$$")
        try:
            command("systemd-run", "--user", "--collect", "--unit=" + UNIT,
                    "--description=ARC Motion " + token, "--property=PartOf=graphical-session.target",
                    "--property=After=graphical-session.target",
                    "--property=KillMode=control-group", "--property=TimeoutStopSec=15",
                    "--property=Restart=no", "--property=ExecStopPost=" + post,
                    *args, "--supervise", token)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if not RUNTIME.exists():
                    raise ValueError("O renderer falhou; consulte journalctl --user -u arc-motion.")
                if runtime_data(token).get("ready"):
                    print("Wallpaper ARC Motion ativo somente nesta sessão. Retorno: --stop --apply")
                    return
                time.sleep(0.2)
            raise ValueError("Timeout iniciando o renderer.")
        except (ValueError, OSError, subprocess.SubprocessError):
            stop()
            raise


def mpv_request(path, name):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(1)
        client.connect(str(path))
        client.sendall((json.dumps({"command": ["get_property", name], "request_id": 1}) + "\n").encode())
        stream = client.makefile("rb")
        for _ in range(30):
            data = json.loads(stream.readline(65536))
            if data.get("request_id") == 1:
                if data.get("error") != "success":
                    raise ValueError(data.get("error"))
                return data.get("data")
        raise ValueError("Resposta mpv não recebida.")


def supervise(token):
    data = runtime_data(token)
    players = []
    stopping = False

    def terminate(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    with tempfile.TemporaryDirectory(prefix="arc-motion-", dir=runtime) as directory:
        try:
            for kind, names in groups(data["geometry"]).items():
                ipc = Path(directory) / (kind + ".sock")
                options = ("no-config=yes loop-file=inf audio=no input-default-bindings=no "
                           "input-vo-keyboard=no input-terminal=no terminal=no hwdec=auto-safe "
                           "vd-lavc-threads=2 cache=no panscan=0 "
                           f"input-ipc-server={ipc}")
                player = subprocess.Popen(["mpvpaper", "-o", options, " ".join(names), str(videos()[kind])])
                players.append((player, ipc))
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline and not stopping:
                if any(player.poll() is not None for player, _ in players):
                    raise ValueError("Um player encerrou antes de carregar o vídeo.")
                try:
                    if all(mpv_request(ipc, "video-params") for _, ipc in players):
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(0.2)
            else:
                raise ValueError("Players não confirmaram o carregamento.")
            data["pending"] = True
            write_json(RUNTIME, data)
            set_enabled(data["before_enabled"], False)
            data["ready"] = True
            write_json(RUNTIME, data)
            last_check = 0
            while not stopping:
                if any(player.poll() is not None for player, _ in players):
                    raise ValueError("Player encerrou; retornando ao fundo estático.")
                if time.monotonic() - last_check > 3:
                    if geometry() != data["geometry"]:
                        raise ValueError("Outputs alterados; retornando ao fundo estático.")
                    last_check = time.monotonic()
                time.sleep(0.5)
        finally:
            for player, _ in players:
                if player.poll() is None:
                    player.terminate()
            for player, _ in players:
                try:
                    player.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    player.kill()
                    player.wait()
            # ExecStopPost independently repeats cleanup if this process is killed.
            cleanup(token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--backup", action="store_true")
    action.add_argument("--restore", metavar="ID")
    action.add_argument("--stop", action="store_true")
    action.add_argument("--status", action="store_true")
    action.add_argument("--wallpaper", action="store_true", help="Ativar somente o fundo, sem retocar animações")
    action.add_argument("--interactions", action="store_true", help="Aplicar somente animações, sem dependência de mpvpaper")
    action.add_argument("--supervise", help=argparse.SUPPRESS)
    action.add_argument("--cleanup", help=argparse.SUPPRESS)
    parser.add_argument("--from-backup", metavar="ID")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.supervise:
        supervise(args.supervise)
    elif args.cleanup:
        cleanup(args.cleanup)
    elif args.backup:
        make_backup()
    elif args.status:
        if not RUNTIME.exists():
            print("Wallpaper ARC Motion parado; nenhuma escrita realizada.")
        else:
            data = runtime_data()
            print(f"Wallpaper ARC Motion: {'ativo' if data.get('ready') else 'iniciando/recuperação pendente'}")
    elif args.restore:
        restore(*load_backup(args.restore), args.apply)
    elif args.stop:
        if args.apply:
            stop()
        else:
            print("DRY-RUN: parar somente a unidade ARC Motion e restaurar o enable nativo.")
    elif args.apply:
        if not args.interactions:
            check_wallpaper()
        if not args.wallpaper:
            if not args.from_backup:
                raise ValueError("Capture --backup antes de editar o Lua e forneça --from-backup ID.")
            apply_interactions(*load_backup(args.from_backup))
        if not args.interactions:
            start()
    else:
        print("DRY-RUN: animações ARC + wallpaper opcional via mpvpaper; nenhuma escrita ou IPC setter.")
        print("Capture --backup antes de editar o Lua. Gere vídeos com render-arc-motion.py --apply.")
        print("Ative: --from-backup ID --apply. Fundo separado: --wallpaper --apply. Retorno: --stop --apply.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
