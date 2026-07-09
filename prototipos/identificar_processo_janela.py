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
    "workspaceIndex",
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


def known_app_label(window):
    return (
        window.get("appName")
        or window.get("appId")
        or window.get("wmClass")
        or "Desconhecido"
    )


def truncate(value, limit):
    text = str(value)
    if len(text) <= limit:
        return text

    return f"{text[:limit - 1]}…"


def print_window_list(windows):
    for index, window in enumerate(windows, start=1):
        relative = window["relative"]
        frame = window["frame"]
        print(
            f"[{index}] {truncate(known_app_label(window), 32)} — "
            f"{truncate(window.get('title', ''), 70)} — "
            f"PID {window.get('pid', -1)} — "
            f"Monitor {window.get('monitorIndex', -1)} — "
            f"X={relative.get('x', 0)} Y={relative.get('y', 0)} — "
            f"{frame.get('width', 0)}x{frame.get('height', 0)}"
        )


def select_window(windows):
    if not windows:
        print("Nenhuma janela foi retornada pelo serviço D-Bus.")
        return None

    print_window_list(windows)

    while True:
        choice = input("Digite o número da janela ou Q para cancelar: ").strip()

        if choice.lower() == "q":
            print("Seleção cancelada.")
            return None

        if not choice:
            print("Entrada vazia. Digite um número da lista ou Q para cancelar.")
            continue

        if not choice.isdigit():
            print("Entrada inválida. Digite um número da lista ou Q para cancelar.")
            continue

        selected_index = int(choice)
        if selected_index < 1 or selected_index > len(windows):
            print("Número fora da lista. Tente novamente.")
            continue

        return windows[selected_index - 1]


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


def parse_ppid_from_stat(stat_text):
    if not stat_text:
        return -1

    close_paren = stat_text.rfind(")")
    if close_paren == -1:
        return -1

    remainder = stat_text[close_paren + 1 :].strip().split()
    if len(remainder) < 2:
        return -1

    try:
        return int(remainder[1])
    except ValueError:
        return -1


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
    status_text = read_text_file(f"{proc_dir}/status")
    status = parse_status(status_text)
    cmdline = parse_cmdline(read_bytes_file(f"{proc_dir}/cmdline"))
    executable = read_symlink(f"{proc_dir}/exe")
    stat_text = read_text_file(f"{proc_dir}/stat")
    ppid = parse_ppid_from_stat(stat_text)
    status_ppid = safe_int(status.get("PPid"), -1)

    if ppid <= 0 and status_ppid > 0:
        ppid = status_ppid

    parent = read_parent_process_info(ppid)

    return {
        "comm": comm,
        "statusName": status.get("Name", ""),
        "executable": executable,
        "executableBase": os.path.basename(executable) if executable else "",
        "cmdline": cmdline,
        "ppid": ppid,
        "parentName": parent,
    }


def read_parent_process_info(ppid):
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
        return None, None

    for aliases, app_name in KNOWN_APPS:
        for alias in aliases:
            if alias in normalized:
                return app_name, alias

    return None, None


def suggest_application(process_info):
    executable_base = process_info["executableBase"]
    app_name, evidence = match_known_app(executable_base)
    if app_name:
        return app_name, f"nome do executável: {evidence}", "alta"

    for field_name, label in (
        ("cmdline", "linha de comando"),
        ("parentName", "processo pai"),
    ):
        app_name, evidence = match_known_app(process_info[field_name])
        if app_name:
            return app_name, f"{label}: {evidence}", "média"

    for field_name, label in (
        ("comm", "/proc/comm"),
        ("statusName", "/proc/status"),
    ):
        app_name, evidence = match_known_app(process_info[field_name])
        if app_name:
            return app_name, f"{label}: {evidence}", "baixa"

    return "Desconhecido", "Nenhuma evidência suficiente", "baixa"


def print_identification(window, process_info):
    suggested_app, evidence, confidence = suggest_application(process_info)

    print()
    print("Identificação da janela")
    print("-----------------------")
    print(f"Sequência: {window.get('stableSequence', '')}")
    print(f"Título: {window.get('title', '')}")
    print(f"Aplicativo informado pelo GNOME: {window.get('appName', '')}")
    print(f"App ID informado pelo GNOME: {window.get('appId', '')}")
    print(f"WM_CLASS: {window.get('wmClass', '')}")
    print(f"Instância: {window.get('wmClassInstance', '')}")
    print(f"PID: {window.get('pid', -1)}")

    print()
    print("Identificação pelo processo")
    print("---------------------------")
    print(f"Nome em /proc/comm: {process_info['comm']}")
    print(f"Nome em /proc/status: {process_info['statusName']}")
    print(f"Executável: {process_info['executable']}")
    print(f"Nome do executável: {process_info['executableBase']}")
    print(f"Linha de comando: {process_info['cmdline']}")
    print(f"PID pai: {process_info['ppid']}")
    print(f"Processo pai: {process_info['parentName']}")

    print()
    print(f"Aplicativo sugerido: {suggested_app}")
    print(f"Evidência utilizada: {evidence}")
    print(f"Confiança: {confidence}")


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

    selected = select_window(windows)
    if selected is None:
        return 0

    pid = safe_int(selected.get("pid"), -1)
    process_info = read_process_info(pid)
    print_identification(selected, process_info)

    return 0


if __name__ == "__main__":
    sys.exit(main())
