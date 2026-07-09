#!/usr/bin/env python3

import json
import os
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


BUS_NAME = "io.github.L1nker.PosiX"
OBJECT_PATH = "/io/github/L1nker/PosiX"
INTERFACE_NAME = "io.github.L1nker.PosiX"
TIMEOUT_MS = 5000

REQUIRED_WINDOW_FIELDS = {
    "stableSequence",
    "title",
    "wmClass",
    "wmClassInstance",
    "pid",
    "appId",
    "appName",
    "monitorIndex",
    "frame",
    "relative",
}

REQUIRED_GEOMETRY_FIELDS = {"x", "y", "width", "height"}
REQUIRED_RELATIVE_FIELDS = {"x", "y"}

KNOWN_APPS = [
    (("brave", "brave-browser"), "Brave"),
    (("firefox",), "Firefox"),
    (("telegram-desktop", "telegram"), "Telegram"),
    (("discord",), "Discord"),
    (("gnome-terminal",), "Terminal"),
    (("gnome-text-editor",), "Editor de Texto"),
    (("nautilus",), "Arquivos"),
]


def describe_gio_error(error):
    message = str(error)

    if "org.freedesktop.DBus.Error.ServiceUnknown" in message:
        return (
            "Serviço D-Bus ausente. Verifique se a extensão posix@linker "
            "está instalada, habilitada e carregada."
        )

    if "org.freedesktop.DBus.Error.NameHasNoOwner" in message:
        return "Extensão não carregada: o nome D-Bus não possui dono na sessão atual."

    if (
        "org.freedesktop.DBus.Error.NoReply" in message
        or "Timeout" in message
        or "timed out" in message.lower()
    ):
        return "Timeout ao chamar ListWindows. O serviço não respondeu em até 5 segundos."

    return f"Erro GLib/Gio: {message}"


def call_list_windows():
    proxy = Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION,
        Gio.DBusProxyFlags.NONE,
        None,
        BUS_NAME,
        OBJECT_PATH,
        INTERFACE_NAME,
        None,
    )
    proxy.set_default_timeout(TIMEOUT_MS)

    result = proxy.call_sync(
        "ListWindows",
        None,
        Gio.DBusCallFlags.NONE,
        TIMEOUT_MS,
        None,
    )

    return result.unpack()[0]


def validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Contrato inválido: a resposta raiz não é um objeto JSON.")

    if payload.get("schemaVersion") != 1:
        raise ValueError("Contrato inválido: schemaVersion diferente de 1.")

    windows = payload.get("windows")
    if not isinstance(windows, list):
        raise ValueError("Contrato inválido: windows não é uma lista.")

    for index, window in enumerate(windows):
        validate_window(index, window)

    return windows


def validate_window(index, window):
    if not isinstance(window, dict):
        raise ValueError(f"Contrato inválido: janela {index} não é um objeto.")

    missing = sorted(REQUIRED_WINDOW_FIELDS - set(window))
    if missing:
        raise ValueError(
            f"Contrato inválido: janela {index} sem campos: {', '.join(missing)}."
        )

    validate_geometry(index, "frame", window["frame"], REQUIRED_GEOMETRY_FIELDS)
    validate_geometry(index, "relative", window["relative"], REQUIRED_RELATIVE_FIELDS)


def validate_geometry(index, field_name, value, required_fields):
    if not isinstance(value, dict):
        raise ValueError(f"Contrato inválido: {field_name} da janela {index} não é objeto.")

    missing = sorted(required_fields - set(value))
    if missing:
        raise ValueError(
            f"Contrato inválido: {field_name} da janela {index} sem campos: "
            f"{', '.join(missing)}."
        )


def gnome_app_label(window):
    return (
        window.get("appName")
        or window.get("appId")
        or window.get("wmClass")
        or "Desconhecido"
    )


def is_useful_gnome_value(value):
    text = str(value or "").strip()
    return bool(text) and text.lower() != "desconhecido"


def is_useful_app_id(value):
    text = str(value or "").strip()
    return is_useful_gnome_value(text) and not text.startswith("window:")


def useful_gnome_label(window):
    app_name = window.get("appName")
    app_id = window.get("appId")
    wm_class = window.get("wmClass")

    if is_useful_gnome_value(app_name):
        return app_name

    if is_useful_app_id(app_id):
        return app_id

    if is_useful_gnome_value(wm_class):
        return wm_class

    return ""


def needs_process_complement(window):
    app_name = window.get("appName") or ""
    app_id = window.get("appId") or ""
    wm_class = window.get("wmClass") or ""
    wm_class_instance = window.get("wmClassInstance") or ""

    return (
        not app_name
        or app_name == "Desconhecido"
        or not app_id
        or app_id.startswith("window:")
        or (not wm_class and not wm_class_instance)
    )


def read_text_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as file:
            return file.read().strip()
    except FileNotFoundError:
        return ""
    except ProcessLookupError:
        return ""
    except PermissionError:
        return ""
    except OSError:
        return ""


def read_bytes_file(path):
    try:
        with open(path, "rb") as file:
            return file.read()
    except FileNotFoundError:
        return b""
    except ProcessLookupError:
        return b""
    except PermissionError:
        return b""
    except OSError:
        return b""


def read_symlink(path):
    try:
        return os.readlink(path)
    except FileNotFoundError:
        return ""
    except ProcessLookupError:
        return ""
    except PermissionError:
        return ""
    except OSError:
        return ""


def parse_status(status_text):
    fields = {}

    for line in status_text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()

    return fields


def parse_cmdline(cmdline_bytes):
    if not cmdline_bytes:
        return ""

    parts = [
        part.decode("utf-8", errors="replace")
        for part in cmdline_bytes.split(b"\0")
        if part
    ]
    return " ".join(parts)


def safe_int(value, fallback=-1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def read_process_info(pid):
    if pid <= 0:
        return empty_process_info()

    proc_dir = f"/proc/{pid}"
    comm = read_text_file(f"{proc_dir}/comm")
    status = parse_status(read_text_file(f"{proc_dir}/status"))
    cmdline = parse_cmdline(read_bytes_file(f"{proc_dir}/cmdline"))
    executable = read_symlink(f"{proc_dir}/exe")
    ppid = safe_int(status.get("PPid"), -1)
    parent_name = read_parent_process_name(ppid)

    return {
        "comm": comm,
        "statusName": status.get("Name", ""),
        "executable": executable,
        "executableBase": os.path.basename(executable) if executable else "",
        "cmdline": cmdline,
        "ppid": ppid,
        "parentName": parent_name,
    }


def read_parent_process_name(ppid):
    if ppid <= 0:
        return ""

    parent_comm = read_text_file(f"/proc/{ppid}/comm")
    if parent_comm:
        return parent_comm

    parent_status = parse_status(read_text_file(f"/proc/{ppid}/status"))
    return parent_status.get("Name", "")


def empty_process_info():
    return {
        "comm": "",
        "statusName": "",
        "executable": "",
        "executableBase": "",
        "cmdline": "",
        "ppid": -1,
        "parentName": "",
    }


def normalize(value):
    return str(value or "").lower()


def match_known_app(text):
    normalized = normalize(text)
    if not normalized:
        return None

    for aliases, app_name in KNOWN_APPS:
        for alias in aliases:
            if alias in normalized:
                return app_name

    return None


def suggest_application(process_info):
    executable_match = match_known_app(process_info["executableBase"])
    if executable_match:
        return executable_match, "Processo", "alta"

    for field_name in ("cmdline", "parentName"):
        match = match_known_app(process_info[field_name])
        if match:
            return match, "Processo", "média"

    for field_name in ("comm", "statusName"):
        match = match_known_app(process_info[field_name])
        if match:
            return match, "Processo", "baixa"

    return "Desconhecido", "Processo", "desconhecida"


def resolve_application(window):
    gnome_label = gnome_app_label(window)
    useful_gnome = useful_gnome_label(window)

    if not needs_process_complement(window):
        return {
            "gnome": gnome_label,
            "resolved": useful_gnome or gnome_label,
            "origin": "GNOME",
            "confidence": "alta",
        }

    process_info = read_process_info(safe_int(window.get("pid"), -1))
    resolved, origin, confidence = suggest_application(process_info)

    if useful_gnome:
        return {
            "gnome": gnome_label,
            "resolved": useful_gnome,
            "origin": "GNOME",
            "confidence": "alta",
        }

    return {
        "gnome": gnome_label,
        "resolved": resolved,
        "origin": origin,
        "confidence": confidence,
    }


def truncate(value, limit):
    text = str(value)
    if len(text) <= limit:
        return text

    return f"{text[:limit - 1]}…"


def print_table(windows):
    headers = [
        "Sequência",
        "PID",
        "Monitor",
        "X relativo",
        "Y relativo",
        "Largura",
        "Altura",
        "Aplicativo GNOME",
        "Aplicativo resolvido",
        "Origem",
        "Confiança",
        "Título",
    ]
    rows = []

    for window in windows:
        frame = window["frame"]
        relative = window["relative"]
        app = resolve_application(window)
        rows.append([
            window.get("stableSequence", ""),
            window.get("pid", -1),
            window.get("monitorIndex", -1),
            relative.get("x", 0),
            relative.get("y", 0),
            frame.get("width", 0),
            frame.get("height", 0),
            truncate(app["gnome"], 24),
            truncate(app["resolved"], 24),
            app["origin"],
            app["confidence"],
            truncate(window.get("title", ""), 60),
        ])

    widths = [
        max(len(str(row[index])) for row in [headers, *rows])
        for index in range(len(headers))
    ]

    print(f"Quantidade de janelas: {len(windows)}")
    print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))

    for row in rows:
        print(" | ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))


def main():
    try:
        response = call_list_windows()
    except GLib.Error as error:
        print(describe_gio_error(error), file=sys.stderr)
        return 1

    try:
        payload = json.loads(response)
    except json.JSONDecodeError as error:
        print(f"JSON inválido retornado pela extensão: {error}", file=sys.stderr)
        return 1

    try:
        windows = validate_payload(payload)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1

    print_table(windows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
