#!/usr/bin/env python3
"""Lista janelas gerenciadas na sessao X11 e estima o monitor de cada uma."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class Monitor:
    name: str
    x: int
    y: int
    width: int
    height: int
    primary: bool = False


@dataclass
class Window:
    wid: str
    title: str
    wm_class: str
    pid: str
    x: int
    y: int
    width: int
    height: int
    monitor: str = "-"


def run_command(args: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        return 127, "", f"comando nao encontrado: {args[0]}"
    except Exception as exc:  # pragma: no cover - defesa para ambiente externo
        return 1, "", f"erro ao executar {' '.join(args)}: {exc}"

    return result.returncode, result.stdout, result.stderr


def is_x11_session() -> bool:
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    display = os.environ.get("DISPLAY", "")
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")

    print("Sessao:")
    print(f"  XDG_SESSION_TYPE={session_type or '-'}")
    print(f"  DISPLAY={display or '-'}")
    print(f"  WAYLAND_DISPLAY={wayland_display or '-'}")
    print()

    return session_type == "x11" and bool(display)


def parse_wmctrl() -> tuple[list[Window], list[str]]:
    code, stdout, stderr = run_command(["wmctrl", "-lGx"])
    errors: list[str] = []
    windows: list[Window] = []

    if code != 0:
        errors.append(f"wmctrl -lGx falhou: {stderr.strip() or stdout.strip() or code}")
        return windows, errors

    for line in stdout.splitlines():
        if not line.strip():
            continue

        parts = line.split(None, 8)
        if len(parts) < 8:
            errors.append(f"linha inesperada do wmctrl ignorada: {line}")
            continue

        wid = parts[0]
        title = parts[8] if len(parts) >= 9 else ""

        try:
            x = int(parts[2])
            y = int(parts[3])
            width = int(parts[4])
            height = int(parts[5])
        except ValueError:
            errors.append(f"geometria invalida do wmctrl ignorada: {line}")
            continue

        windows.append(
            Window(
                wid=wid,
                title=title,
                wm_class=parts[6],
                pid="-",
                x=x,
                y=y,
                width=width,
                height=height,
            )
        )

    return windows, errors


def clean_xprop_string(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def parse_xprop_strings(line: str) -> list[str]:
    return [match.group(1) for match in re.finditer(r'"([^"]*)"', line)]


def update_window_from_xprop(window: Window) -> str | None:
    code, stdout, stderr = run_command(
        ["xprop", "-id", window.wid, "WM_CLASS", "_NET_WM_PID", "_NET_WM_NAME", "WM_NAME"]
    )
    if code != 0:
        return f"xprop falhou para {window.wid}: {stderr.strip() or stdout.strip() or code}"

    for line in stdout.splitlines():
        if line.startswith("WM_CLASS("):
            values = parse_xprop_strings(line)
            if values:
                window.wm_class = ", ".join(values)
        elif line.startswith("_NET_WM_PID("):
            match = re.search(r"=\s*(\d+)", line)
            if match:
                window.pid = match.group(1)
        elif line.startswith("_NET_WM_NAME("):
            _, _, value = line.partition("=")
            value = clean_xprop_string(value)
            if value and "not found" not in value.lower():
                window.title = value
        elif line.startswith("WM_NAME(") and not window.title:
            _, _, value = line.partition("=")
            value = clean_xprop_string(value)
            if value and "not found" not in value.lower():
                window.title = value

    return None


def parse_xrandr() -> tuple[list[Monitor], list[str]]:
    code, stdout, stderr = run_command(["xrandr", "--query"])
    errors: list[str] = []
    monitors: list[Monitor] = []

    if code != 0:
        errors.append(f"xrandr --query falhou: {stderr.strip() or stdout.strip() or code}")
        return monitors, errors

    pattern = re.compile(
        r"^(?P<name>\S+) connected(?P<primary> primary)? "
        r"(?P<width>\d+)x(?P<height>\d+)\+(?P<x>-?\d+)\+(?P<y>-?\d+)"
    )

    for line in stdout.splitlines():
        match = pattern.match(line)
        if not match:
            continue

        monitors.append(
            Monitor(
                name=match.group("name"),
                x=int(match.group("x")),
                y=int(match.group("y")),
                width=int(match.group("width")),
                height=int(match.group("height")),
                primary=bool(match.group("primary")),
            )
        )

    return monitors, errors


def intersection_area(window: Window, monitor: Monitor) -> int:
    left = max(window.x, monitor.x)
    top = max(window.y, monitor.y)
    right = min(window.x + window.width, monitor.x + monitor.width)
    bottom = min(window.y + window.height, monitor.y + monitor.height)

    if right <= left or bottom <= top:
        return 0
    return (right - left) * (bottom - top)


def assign_monitors(windows: list[Window], monitors: list[Monitor]) -> None:
    for window in windows:
        best_monitor: Monitor | None = None
        best_area = 0

        for monitor in monitors:
            area = intersection_area(window, monitor)
            if area > best_area:
                best_area = area
                best_monitor = monitor

        if best_monitor is not None:
            window.monitor = best_monitor.name
        elif monitors:
            window.monitor = "fora dos monitores"


def shorten(value: str, max_len: int) -> str:
    value = value or "-"
    if len(value) <= max_len:
        return value
    if max_len <= 1:
        return value[:max_len]
    return value[: max_len - 1] + "..."


def print_monitors(monitors: list[Monitor]) -> None:
    print("Monitores ativos:")
    if not monitors:
        print("  nenhum monitor ativo detectado pelo xrandr")
        print()
        return

    for monitor in monitors:
        primary = "sim" if monitor.primary else "nao"
        print(
            f"  {monitor.name}: {monitor.width}x{monitor.height}+{monitor.x}+{monitor.y}, "
            f"principal={primary}"
        )
    print()


def print_windows(windows: list[Window]) -> None:
    columns = [
        ("ID", 10),
        ("PID", 7),
        ("X", 6),
        ("Y", 6),
        ("Larg", 6),
        ("Alt", 6),
        ("Monitor", 18),
        ("WM_CLASS", 34),
        ("Titulo", 60),
    ]

    header = " ".join(name.ljust(width) for name, width in columns)
    separator = " ".join("-" * width for _, width in columns)
    print("Janelas gerenciadas:")
    print(header)
    print(separator)

    if not windows:
        print("(nenhuma janela encontrada)")
        print()
        return

    for window in windows:
        values = [
            window.wid,
            window.pid,
            str(window.x),
            str(window.y),
            str(window.width),
            str(window.height),
            window.monitor,
            window.wm_class,
            window.title,
        ]
        print(
            " ".join(
                shorten(value, width).ljust(width)
                for value, (_, width) in zip(values, columns)
            )
        )
    print()


def main() -> int:
    if not is_x11_session():
        print("Erro: a sessao atual nao parece ser X11. Este prototipo requer X11.")
        return 1

    errors: list[str] = []
    windows, wmctrl_errors = parse_wmctrl()
    monitors, xrandr_errors = parse_xrandr()
    errors.extend(wmctrl_errors)
    errors.extend(xrandr_errors)

    for window in windows:
        error = update_window_from_xprop(window)
        if error:
            errors.append(error)

    assign_monitors(windows, monitors)
    print_monitors(monitors)
    print_windows(windows)

    if errors:
        print("Avisos/erros encontrados:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("Avisos/erros encontrados: nenhum")

    return 0


if __name__ == "__main__":
    sys.exit(main())
