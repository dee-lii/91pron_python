#!/usr/bin/env python3
"""ADB helpers for the Redmi G Pro 27U monitor.

The monitor runs HyperOS/Android on its smart side. This tool uses normal ADB
commands for screenshot, UI dump, key events, and volume control. It does not
depend on any Python packages.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import http.server
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Sequence


DEFAULT_HOST = os.environ.get("REDMI_GPRO27U_HOST", "192.168.31.52")
DEFAULT_PORT = int(os.environ.get("REDMI_GPRO27U_PORT", "5555"))
ADB_CANDIDATES = [
    pathlib.Path("~/Library/Android/sdk/platform-tools/adb").expanduser(),
    pathlib.Path("~/Android/platform-tools/adb").expanduser(),
    pathlib.Path("/opt/homebrew/bin/adb"),
    pathlib.Path("/usr/local/bin/adb"),
]

KEYCODES = {
    "back": 4,
    "home": 3,
    "menu": 82,
    "power": 26,
    "up": 19,
    "down": 20,
    "left": 21,
    "right": 22,
    "ok": 23,
    "enter": 23,
    "volume_up": 24,
    "vol_up": 24,
    "volume_down": 25,
    "vol_down": 25,
    "mute": 164,
    "play_pause": 85,
}

COMMON_PORTS = [
    22,
    80,
    443,
    5554,
    5555,
    7000,
    7001,
    8008,
    8009,
    8010,
    8080,
    9080,
    9081,
    9090,
    9999,
]


class ToolError(RuntimeError):
    pass


def find_adb() -> str | None:
    for path in ADB_CANDIDATES:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


class Adb:
    def __init__(self, host: str, port: int, adb_path: str | None = None) -> None:
        self.host = host
        self.port = port
        self.endpoint = f"{host}:{port}"
        self.adb_path = adb_path or os.environ.get("ADB") or shutil.which("adb") or find_adb()

    def require(self) -> str:
        if not self.adb_path:
            raise ToolError(
                "adb was not found. Install Android platform-tools first.\n"
                "macOS: brew install android-platform-tools\n"
                "Then run: adb connect %s" % self.endpoint
            )
        return self.adb_path

    def run(
        self,
        args: Sequence[str],
        *,
        check: bool = True,
        text: bool = True,
        timeout: float | None = 30,
        device: bool = True,
    ) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
        adb = self.require()
        cmd: list[str] = [adb]
        if device:
            cmd.extend(["-s", self.endpoint])
        cmd.extend(args)
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            timeout=timeout,
        )
        if check and proc.returncode != 0:
            stderr = proc.stderr if isinstance(proc.stderr, str) else proc.stderr.decode("utf-8", "replace")
            stdout = proc.stdout if isinstance(proc.stdout, str) else proc.stdout.decode("utf-8", "replace")
            raise ToolError(f"Command failed: {' '.join(cmd)}\n{stderr or stdout}".rstrip())
        return proc

    def connect(self) -> str:
        adb = self.require()
        proc = subprocess.run(
            [adb, "connect", self.endpoint],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0:
            raise ToolError(output or f"adb connect {self.endpoint} failed")
        lowered = output.lower()
        if "failed to authenticate" in lowered or "unauthorized" in lowered:
            raise ToolError(
                output
                + "\nAuthorize this computer on the monitor, then run the command again."
            )
        if "connected" not in lowered and "already connected" not in lowered:
            raise ToolError(output or f"Could not connect to {self.endpoint}")
        return output

    def shell(self, command: Sequence[str], *, timeout: float | None = 30, check: bool = True) -> str:
        proc = self.run(["shell", *command], timeout=timeout, check=check)
        assert isinstance(proc.stdout, str)
        if not check and proc.stderr:
            return proc.stdout + proc.stderr
        return proc.stdout

    def screenshot_png(self) -> bytes:
        proc = self.run(["exec-out", "screencap", "-p"], text=False, timeout=20)
        assert isinstance(proc.stdout, bytes)
        data = proc.stdout
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            preview = data[:200].decode("utf-8", "replace")
            raise ToolError("screencap did not return a PNG. Output begins with:\n" + preview)
        return data


def print_err(message: str) -> None:
    print(message, file=sys.stderr)


def connect_adb(args: argparse.Namespace) -> Adb:
    adb = Adb(args.host, args.port, args.adb)
    if not getattr(args, "no_connect", False):
        message = adb.connect()
        if getattr(args, "verbose", False):
            print(message, file=sys.stderr)
    return adb


def command_doctor(args: argparse.Namespace) -> int:
    adb = Adb(args.host, args.port, args.adb)
    print(f"target: {adb.endpoint}")
    print(f"adb: {adb.adb_path or 'not found'}")
    if not adb.adb_path:
        print()
        print(
            "adb was not found. Install Android platform-tools first.\n"
            "macOS: brew install android-platform-tools\n"
            f"Then run: adb connect {adb.endpoint}"
        )
        return 2

    version = adb.run(["version"], device=False).stdout
    print(str(version).strip())
    try:
        print(adb.connect())
        state = adb.run(["get-state"]).stdout
        print(f"state: {str(state).strip()}")
        props = {
            "model": ["getprop", "ro.product.model"],
            "brand": ["getprop", "ro.product.brand"],
            "android": ["getprop", "ro.build.version.release"],
            "sdk": ["getprop", "ro.build.version.sdk"],
            "build": ["getprop", "ro.build.display.id"],
        }
        for label, cmd in props.items():
            value = adb.shell(cmd).strip()
            if value:
                print(f"{label}: {value}")
    except ToolError as exc:
        print_err(str(exc))
        return 1
    return 0


def default_capture_path(directory: pathlib.Path) -> pathlib.Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return directory / f"redmi-gpro27u-{stamp}.png"


def command_screenshot(args: argparse.Namespace) -> int:
    adb = connect_adb(args)
    data = adb.screenshot_png()
    if args.output == "-":
        sys.stdout.buffer.write(data)
        return 0

    output = pathlib.Path(args.output) if args.output else default_capture_path(pathlib.Path("captures"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    print(output.resolve())
    return 0


def command_ui(args: argparse.Namespace) -> int:
    adb = connect_adb(args)
    adb.shell(["uiautomator", "dump", "/sdcard/window.xml"], timeout=20)
    proc = adb.run(["exec-out", "cat", "/sdcard/window.xml"], timeout=20)
    xml = str(proc.stdout)
    if args.output:
        output = pathlib.Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(xml, encoding="utf-8")
        print(output.resolve())
    else:
        print(xml, end="" if xml.endswith("\n") else "\n")
    return 0


def extract_music_volume(dumpsys_audio: str) -> int | None:
    stream_music = False
    for line in dumpsys_audio.splitlines():
        stripped = line.strip()
        if stripped.startswith("- STREAM_"):
            stream_music = stripped.startswith("- STREAM_MUSIC:")
            continue
        if stream_music:
            match = re.search(r"\bstreamVolume:(\d+)\b", stripped)
            if match:
                return int(match.group(1))
    return None


def get_music_volume(adb: Adb) -> int | None:
    return extract_music_volume(adb.shell(["dumpsys", "audio"], timeout=20, check=False))


def command_volume(args: argparse.Namespace) -> int:
    adb = connect_adb(args)
    action = args.action
    if action == "up":
        adb.shell(["input", "keyevent", "24"])
    elif action == "down":
        adb.shell(["input", "keyevent", "25"])
    elif action == "mute":
        adb.shell(["input", "keyevent", "164"])
    elif action == "set":
        current = get_music_volume(adb)
        if current is None:
            raise ToolError("Could not read STREAM_MUSIC volume from dumpsys audio.")
        delta = args.level - current
        keycode = "24" if delta > 0 else "25"
        for _ in range(abs(delta)):
            adb.shell(["input", "keyevent", keycode])
            time.sleep(args.delay)
        actual = get_music_volume(adb)
        print(f"STREAM_MUSIC volume: {current} -> {actual}")
        if actual != args.level:
            raise ToolError(f"Requested {args.level}, but device reported {actual}.")
    elif action == "get":
        data = adb.shell(["dumpsys", "audio"], timeout=20, check=False)
        current = extract_music_volume(data)
        if current is not None:
            print(f"STREAM_MUSIC volume: {current}")
        elif args.raw:
            print(data[:4000])
        else:
            raise ToolError("Could not read STREAM_MUSIC volume from dumpsys audio.")
    return 0


def parse_key(value: str) -> str:
    lowered = value.strip().lower()
    if lowered.isdigit():
        return lowered
    if lowered.startswith("keycode_"):
        lowered = lowered[8:]
    if lowered not in KEYCODES:
        known = ", ".join(sorted(KEYCODES))
        raise ToolError(f"Unknown key '{value}'. Use a number or one of: {known}")
    return str(KEYCODES[lowered])


def command_key(args: argparse.Namespace) -> int:
    code = parse_key(args.key)
    adb = connect_adb(args)
    adb.shell(["input", "keyevent", code])
    return 0


def command_shell(args: argparse.Namespace) -> int:
    adb = connect_adb(args)
    output = adb.shell(args.shell_command, timeout=args.timeout, check=False)
    print(output, end="" if output.endswith("\n") else "\n")
    return 0


def probe_tcp(host: str, port: int, timeout: float) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def parse_ports(raw: str | None) -> list[int]:
    if not raw or raw == "common":
        return COMMON_PORTS
    ports: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            ports.update(range(start, end + 1))
        else:
            ports.add(int(part))
    return sorted(ports)


def command_probe_ports(args: argparse.Namespace) -> int:
    ports = parse_ports(args.ports)
    open_ports: list[int] = []
    lock = threading.Lock()

    def worker(port: int) -> None:
        try:
            is_open = probe_tcp(args.host, port, args.timeout)
        except OSError:
            is_open = False
        if is_open:
            with lock:
                open_ports.append(port)

    worker_count = max(1, min(args.workers, len(ports)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(worker, port) for port in ports]
        for future in as_completed(futures):
            future.result()

    for port in sorted(open_ports):
        print(port)
    if not open_ports:
        print("No open TCP ports found in the requested set.", file=sys.stderr)
        return 1
    return 0


class ScreenHandler(http.server.BaseHTTPRequestHandler):
    adb: Adb
    interval: float

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", file=sys.stderr)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/shot.png"):
            try:
                data = self.adb.screenshot_png()
            except Exception as exc:  # noqa: BLE001
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(str(exc).encode("utf-8", "replace"))
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        escaped_endpoint = html.escape(self.adb.endpoint)
        interval_ms = max(250, int(self.interval * 1000))
        body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Redmi G Pro 27U Screen</title>
  <style>
    html, body {{ margin: 0; height: 100%; background: #111; color: #eee; font-family: system-ui, sans-serif; }}
    main {{ min-height: 100%; display: grid; grid-template-rows: auto 1fr; }}
    header {{ display: flex; gap: 12px; align-items: center; padding: 10px 14px; background: #1c1c1c; }}
    img {{ display: block; max-width: 100vw; max-height: calc(100vh - 48px); margin: auto; object-fit: contain; }}
    button {{ font: inherit; padding: 5px 10px; }}
  </style>
</head>
<body>
  <main>
    <header>
      <strong>{escaped_endpoint}</strong>
      <span id="stamp"></span>
      <button id="pause">Pause</button>
    </header>
    <img id="screen" alt="screen">
  </main>
  <script>
    const img = document.getElementById('screen');
    const stamp = document.getElementById('stamp');
    const pause = document.getElementById('pause');
    let paused = false;
    async function refresh() {{
      if (paused) return;
      img.src = '/shot.png?t=' + Date.now();
      stamp.textContent = new Date().toLocaleTimeString();
    }}
    pause.onclick = () => {{
      paused = !paused;
      pause.textContent = paused ? 'Resume' : 'Pause';
      if (!paused) refresh();
    }};
    refresh();
    setInterval(refresh, {interval_ms});
  </script>
</body>
</html>
"""
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def command_view(args: argparse.Namespace) -> int:
    adb = connect_adb(args)

    class Handler(ScreenHandler):
        pass

    Handler.adb = adb
    Handler.interval = args.interval

    server = http.server.ThreadingHTTPServer((args.bind, args.listen), Handler)
    url = f"http://{args.bind}:{args.listen}/"
    print(f"Serving {adb.endpoint} screenshots at {url}")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


def add_common_target_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"monitor IP, default: {DEFAULT_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"ADB TCP port, default: {DEFAULT_PORT}")
    parser.add_argument("--adb", help="path to adb; defaults to $ADB or PATH lookup")
    parser.add_argument("--no-connect", action="store_true", help="skip adb connect before running the command")
    parser.add_argument("-v", "--verbose", action="store_true", help="print adb connect output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control and inspect a Redmi G Pro 27U monitor over ADB.",
    )
    add_common_target_args(parser)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    doctor = sub.add_parser("doctor", help="check adb and print device properties")
    doctor.set_defaults(func=command_doctor)

    screenshot = sub.add_parser("screenshot", help="capture a PNG screenshot")
    screenshot.add_argument("output", nargs="?", help="output PNG path, or '-' for stdout")
    screenshot.set_defaults(func=command_screenshot)

    ui = sub.add_parser("ui", help="dump current Android UI hierarchy XML")
    ui.add_argument("-o", "--output", help="write XML to this path instead of stdout")
    ui.set_defaults(func=command_ui)

    view = sub.add_parser("view", help="serve a local auto-refreshing screenshot page")
    view.add_argument("--bind", default="127.0.0.1", help="local bind address")
    view.add_argument("--listen", type=int, default=8765, help="local HTTP port")
    view.add_argument("--interval", type=float, default=1.0, help="refresh interval in seconds")
    view.set_defaults(func=command_view)

    volume = sub.add_parser("volume", help="control monitor Android volume")
    volume_sub = volume.add_subparsers(dest="action", required=True)
    for name in ("up", "down", "mute", "get"):
        item = volume_sub.add_parser(name)
        if name == "get":
            item.add_argument("--raw", action="store_true", help="print raw dumpsys audio if parsing fails")
        item.set_defaults(func=command_volume)
    set_parser = volume_sub.add_parser("set")
    set_parser.add_argument("level", type=int)
    set_parser.add_argument("--delay", type=float, default=0.08, help="delay between key events")
    set_parser.set_defaults(func=command_volume)

    key = sub.add_parser("key", help="send an Android key event")
    key.add_argument("key", help="key name or numeric keycode")
    key.set_defaults(func=command_key)

    shell = sub.add_parser("shell", help="run an adb shell command")
    shell.add_argument("--timeout", type=float, default=30)
    shell.add_argument("shell_command", nargs=argparse.REMAINDER)
    shell.set_defaults(func=command_shell)

    ports = sub.add_parser("probe-ports", help="probe TCP ports without adb")
    ports.add_argument("--ports", default="common", help="common, comma list, or range such as 1-10000")
    ports.add_argument("--timeout", type=float, default=0.35)
    ports.add_argument("--workers", type=int, default=128)
    ports.set_defaults(func=command_probe_ports)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.subcommand == "shell" and not args.shell_command:
            raise ToolError("Provide a shell command after 'shell'.")
        return int(args.func(args))
    except KeyboardInterrupt:
        print_err("Interrupted.")
        return 130
    except (ToolError, subprocess.TimeoutExpired, OSError) as exc:
        print_err(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
