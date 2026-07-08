#!/usr/bin/env python3
"""Prova de conceito segura para mover e redimensionar a propria janela X11."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402


WINDOW_TITLE = "PosiX - Janela de Teste X11"
REQUESTED_GEOMETRY = (-180, 120, 900, 600)


@dataclass
class Geometry:
    x: int
    y: int
    width: int
    height: int


@dataclass
class ManagedWindow:
    wid: str
    pid: str
    wm_class: str
    title: str
    geometry: Geometry


@dataclass
class Monitor:
    name: str
    x: int
    y: int
    width: int
    height: int
    primary: bool


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
    except Exception as exc:  # pragma: no cover - protecao contra falhas externas
        return 1, "", f"erro ao executar {' '.join(args)}: {exc}"

    return result.returncode, result.stdout, result.stderr


def log_terminal(message: str) -> None:
    print(message, flush=True)


def is_x11_session() -> bool:
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    display = os.environ.get("DISPLAY", "")
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")

    log_terminal("Sessao:")
    log_terminal(f"  XDG_SESSION_TYPE={session_type or '-'}")
    log_terminal(f"  DISPLAY={display or '-'}")
    log_terminal(f"  WAYLAND_DISPLAY={wayland_display or '-'}")

    return session_type == "x11" and bool(display)


def parse_wmctrl_line(line: str) -> ManagedWindow | None:
    parts = line.split(None, 8)
    if len(parts) < 9:
        return None

    try:
        geometry = Geometry(
            x=int(parts[2]),
            y=int(parts[3]),
            width=int(parts[4]),
            height=int(parts[5]),
        )
    except ValueError:
        return None

    return ManagedWindow(
        wid=parts[0],
        pid="-",
        wm_class=parts[6],
        title=parts[8],
        geometry=geometry,
    )


def parse_xprop_pid(output: str) -> str:
    match = re.search(r"_NET_WM_PID\([^)]+\)\s*=\s*(\d+)", output)
    return match.group(1) if match else "-"


def parse_xprop_class(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("WM_CLASS("):
            values = re.findall(r'"([^"]*)"', line)
            if values:
                return ", ".join(values)
    return "-"


def read_xprop(wid: str, properties: list[str]) -> tuple[dict[str, str], str | None]:
    code, stdout, stderr = run_command(["xprop", "-id", wid, *properties])
    if code != 0:
        return {}, stderr.strip() or stdout.strip() or str(code)

    values: dict[str, str] = {}
    for line in stdout.splitlines():
        name = line.split("(", 1)[0].strip()
        values[name] = line.strip()
    return values, None


def list_matching_windows() -> tuple[list[ManagedWindow], list[str]]:
    code, stdout, stderr = run_command(["wmctrl", "-lGx"])
    if code != 0:
        return [], [f"wmctrl -lGx falhou: {stderr.strip() or stdout.strip() or code}"]

    windows: list[ManagedWindow] = []
    warnings: list[str] = []

    for line in stdout.splitlines():
        window = parse_wmctrl_line(line)
        if window is None or window.title != WINDOW_TITLE:
            continue

        props, error = read_xprop(window.wid, ["_NET_WM_PID", "WM_CLASS"])
        if error:
            warnings.append(f"xprop falhou para {window.wid}: {error}")
        else:
            raw = "\n".join(props.values())
            window.pid = parse_xprop_pid(raw)
            window.wm_class = parse_xprop_class(raw)

        windows.append(window)

    return windows, warnings


def locate_own_window() -> tuple[ManagedWindow | None, list[str]]:
    windows, warnings = list_matching_windows()
    current_pid = str(os.getpid())
    pid_matches = [window for window in windows if window.pid == current_pid]

    if len(pid_matches) == 1:
        return pid_matches[0], warnings
    if len(pid_matches) > 1:
        warnings.append(
            f"seguranca: {len(pid_matches)} janelas com titulo e PID atuais; teste abortado"
        )
        return None, warnings
    if len(windows) == 1:
        warnings.append(
            "PID da janela nao confirmou o processo atual; usando a unica janela com titulo exato"
        )
        return windows[0], warnings
    if not windows:
        warnings.append("nenhuma janela com o titulo exato foi encontrada")
    else:
        warnings.append(
            f"seguranca: {len(windows)} janelas com o mesmo titulo e sem PID unico; teste abortado"
        )
    return None, warnings


def get_window_by_id(wid: str) -> ManagedWindow | None:
    code, stdout, _stderr = run_command(["wmctrl", "-lGx"])
    if code != 0:
        return None

    for line in stdout.splitlines():
        window = parse_wmctrl_line(line)
        if window is not None and window.wid.lower() == wid.lower():
            props, _error = read_xprop(window.wid, ["_NET_WM_PID", "WM_CLASS"])
            raw = "\n".join(props.values())
            window.pid = parse_xprop_pid(raw)
            window.wm_class = parse_xprop_class(raw)
            return window
    return None


def parse_monitors() -> list[Monitor]:
    code, stdout, _stderr = run_command(["xrandr", "--query"])
    if code != 0:
        return []

    pattern = re.compile(
        r"^(?P<name>\S+) connected(?P<primary> primary)? "
        r"(?P<width>\d+)x(?P<height>\d+)\+(?P<x>-?\d+)\+(?P<y>-?\d+)"
    )
    monitors: list[Monitor] = []
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
    return monitors


def intersection_area(geometry: Geometry, monitor: Monitor) -> int:
    left = max(geometry.x, monitor.x)
    top = max(geometry.y, monitor.y)
    right = min(geometry.x + geometry.width, monitor.x + monitor.width)
    bottom = min(geometry.y + geometry.height, monitor.y + monitor.height)
    if right <= left or bottom <= top:
        return 0
    return (right - left) * (bottom - top)


def estimate_monitor(geometry: Geometry) -> str:
    best_name = "-"
    best_area = 0
    monitors = parse_monitors()
    for monitor in monitors:
        area = intersection_area(geometry, monitor)
        if area > best_area:
            best_area = area
            best_name = monitor.name
    if best_area == 0 and monitors:
        return "fora dos monitores"
    return best_name


def format_geometry(geometry: Geometry | None) -> str:
    if geometry is None:
        return "-"
    return f"X={geometry.x} Y={geometry.y} L={geometry.width} A={geometry.height}"


def diff_geometry(requested: Geometry, actual: Geometry) -> str:
    return (
        f"dX={actual.x - requested.x}, "
        f"dY={actual.y - requested.y}, "
        f"dL={actual.width - requested.width}, "
        f"dA={actual.height - requested.height}"
    )


def move_resize(wid: str, geometry: Geometry) -> tuple[bool, str]:
    spec = f"0,{geometry.x},{geometry.y},{geometry.width},{geometry.height}"
    code, stdout, stderr = run_command(["wmctrl", "-ir", wid, "-e", spec])
    if code != 0:
        return False, stderr.strip() or stdout.strip() or str(code)
    return True, spec


class TestWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title=WINDOW_TITLE)
        self.set_default_size(620, 420)

        self.window_id = "-"
        self.original_geometry: Geometry | None = None
        self.last_geometry: Geometry | None = None
        self.restore_source_id: int | None = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)
        self.set_child(root)

        self.position_label = Gtk.Label(xalign=0)
        self.size_label = Gtk.Label(xalign=0)
        self.id_label = Gtk.Label(xalign=0)
        self.monitor_label = Gtk.Label(xalign=0)

        root.append(self.position_label)
        root.append(self.size_label)
        root.append(self.id_label)
        root.append(self.monitor_label)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.append(buttons)

        self.start_button = Gtk.Button(label="Iniciar teste de movimento")
        self.start_button.connect("clicked", self.on_start_clicked)
        buttons.append(self.start_button)

        self.restore_button = Gtk.Button(label="Restaurar agora")
        self.restore_button.connect("clicked", self.on_restore_clicked)
        buttons.append(self.restore_button)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        root.append(scroller)

        self.messages = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.buffer = self.messages.get_buffer()
        scroller.set_child(self.messages)

        self.add_message("Janela criada. Clique em 'Iniciar teste de movimento'.")
        GLib.timeout_add(500, self.refresh_status)

    def add_message(self, message: str) -> None:
        log_terminal(message)
        end = self.buffer.get_end_iter()
        self.buffer.insert(end, message + "\n")

    def refresh_status(self) -> bool:
        own, warnings = locate_own_window()
        for warning in warnings:
            if "nenhuma janela" not in warning:
                self.add_message(f"Aviso: {warning}")

        if own is not None:
            self.window_id = own.wid
            self.last_geometry = own.geometry
            self.position_label.set_text(f"posicao atual: X={own.geometry.x} Y={own.geometry.y}")
            self.size_label.set_text(
                f"largura e altura atuais: {own.geometry.width}x{own.geometry.height}"
            )
            self.id_label.set_text(f"ID X11 encontrado: {own.wid}")
            self.monitor_label.set_text(f"monitor provavel: {estimate_monitor(own.geometry)}")
        else:
            self.position_label.set_text("posicao atual: -")
            self.size_label.set_text("largura e altura atuais: -")
            self.id_label.set_text("ID X11 encontrado: -")
            self.monitor_label.set_text("monitor provavel: -")
        return True

    def on_start_clicked(self, _button: Gtk.Button) -> None:
        self.start_button.set_sensitive(False)
        self.add_message("Iniciando teste.")

        own, warnings = locate_own_window()
        for warning in warnings:
            self.add_message(f"Aviso: {warning}")

        if own is None:
            self.add_message("Teste abortado: nao foi possivel localizar somente esta janela.")
            self.start_button.set_sensitive(True)
            return

        self.window_id = own.wid
        self.original_geometry = own.geometry
        requested = Geometry(*REQUESTED_GEOMETRY)

        props, error = read_xprop(own.wid, ["_GTK_FRAME_EXTENTS", "_NET_FRAME_EXTENTS"])
        gtk_extents = props.get("_GTK_FRAME_EXTENTS", "_GTK_FRAME_EXTENTS: nao encontrado")
        net_extents = props.get("_NET_FRAME_EXTENTS", "_NET_FRAME_EXTENTS: nao encontrado")
        if error:
            self.add_message(f"Aviso ao consultar extents: {error}")

        self.add_message(f"ID X11 selecionado: {own.wid}")
        self.add_message(f"PID esperado: {os.getpid()} | PID encontrado: {own.pid}")
        self.add_message(f"Geometria original: {format_geometry(self.original_geometry)}")
        self.add_message(f"Valores de _GTK_FRAME_EXTENTS: {gtk_extents}")
        self.add_message(f"Valores de _NET_FRAME_EXTENTS: {net_extents}")
        self.add_message(f"Geometria solicitada: {format_geometry(requested)}")

        ok, detail = move_resize(own.wid, requested)
        if not ok:
            self.add_message(f"Falha ao mover/redimensionar: {detail}")
            self.start_button.set_sensitive(True)
            return

        self.add_message(f"wmctrl aplicado: {detail}")
        GLib.timeout_add(700, self.confirm_after_move, own.wid, requested)

    def confirm_after_move(self, wid: str, requested: Geometry) -> bool:
        current = get_window_by_id(wid)
        if current is None:
            self.add_message("Nao foi possivel confirmar geometria apos movimento.")
            self.start_button.set_sensitive(True)
            return False

        self.add_message(f"Geometria realmente obtida: {format_geometry(current.geometry)}")
        self.add_message(f"Diferencas solicitada/obtida: {diff_geometry(requested, current.geometry)}")
        self.add_message("Mantendo a janela na posicao solicitada por 5 segundos.")

        if self.restore_source_id is not None:
            GLib.source_remove(self.restore_source_id)
        self.restore_source_id = GLib.timeout_add_seconds(5, self.restore_original)
        return False

    def on_restore_clicked(self, _button: Gtk.Button) -> None:
        self.add_message("Restauracao manual solicitada.")
        self.restore_original()

    def restore_original(self) -> bool:
        self.restore_source_id = None
        if self.original_geometry is None:
            self.add_message("Nao ha geometria original capturada para restaurar.")
            self.start_button.set_sensitive(True)
            return False
        if self.window_id == "-":
            self.add_message("Nao ha ID X11 capturado para restaurar.")
            self.start_button.set_sensitive(True)
            return False

        ok, detail = move_resize(self.window_id, self.original_geometry)
        if not ok:
            self.add_message(f"Falha ao restaurar geometria original: {detail}")
            self.start_button.set_sensitive(True)
            return False

        self.add_message(f"Restauracao solicitada: {detail}")
        GLib.timeout_add(700, self.confirm_after_restore, self.window_id)
        return False

    def confirm_after_restore(self, wid: str) -> bool:
        current = get_window_by_id(wid)
        if current is None:
            self.add_message("Nao foi possivel confirmar geometria apos restauracao.")
        else:
            self.add_message(f"Geometria apos a restauracao: {format_geometry(current.geometry)}")
            if self.original_geometry is not None:
                self.add_message(
                    "Diferencas original/restaurada: "
                    f"{diff_geometry(self.original_geometry, current.geometry)}"
                )
        self.start_button.set_sensitive(True)
        return False


class App(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="local.posix_poc.testar_movimento_x11")

    def do_activate(self) -> None:
        window = TestWindow(self)
        window.present()


def main() -> int:
    if not is_x11_session():
        log_terminal("Erro: este prototipo requer uma sessao X11.")
        return 1

    app = App()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
