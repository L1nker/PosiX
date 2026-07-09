#!/usr/bin/env python3

import json
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
    "state",
}

REQUIRED_GEOMETRY_FIELDS = {"x", "y", "width", "height"}
REQUIRED_RELATIVE_FIELDS = {"x", "y"}
REQUIRED_STATE_FIELDS = {
    "maximized",
    "fullscreen",
    "minimized",
    "allowsMove",
    "allowsResize",
    "skipTaskbar",
}


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
    validate_state(index, window["state"])


def validate_geometry(index, field_name, value, required_fields):
    if not isinstance(value, dict):
        raise ValueError(f"Contrato inválido: {field_name} da janela {index} não é objeto.")

    missing = sorted(required_fields - set(value))
    if missing:
        raise ValueError(
            f"Contrato inválido: {field_name} da janela {index} sem campos: "
            f"{', '.join(missing)}."
        )


def validate_state(index, state):
    if not isinstance(state, dict):
        raise ValueError(f"Contrato inválido: state da janela {index} não é objeto.")

    missing = sorted(REQUIRED_STATE_FIELDS - set(state))
    if missing:
        raise ValueError(
            f"Contrato inválido: state da janela {index} sem campos: {', '.join(missing)}."
        )


def app_label(window):
    return (
        window.get("appName")
        or window.get("appId")
        or window.get("wmClass")
        or "Aplicativo desconhecido"
    )


def truncate(value, limit):
    text = str(value)
    if len(text) <= limit:
        return text

    return f"{text[:limit - 1]}…"


def format_bool(value):
    return "Sim" if bool(value) else "Não"


def print_window_list(windows):
    for index, window in enumerate(windows, start=1):
        relative = window["relative"]
        frame = window["frame"]
        print(
            f"[{index}] {truncate(app_label(window), 32)} — "
            f"{truncate(window.get('title', ''), 70)} — "
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


def print_selected_window(window):
    frame = window["frame"]
    relative = window["relative"]
    state = window["state"]

    print()
    print("Janela selecionada")
    print("------------------")
    print(f"Sequência: {window.get('stableSequence', '')}")
    print(f"Aplicativo: {app_label(window)}")
    print(f"App ID: {window.get('appId', '')}")
    print(f"Título: {window.get('title', '')}")
    print(f"WM_CLASS: {window.get('wmClass', '')}")
    print(f"Instância: {window.get('wmClassInstance', '')}")
    print(f"PID: {window.get('pid', -1)}")
    print(f"Monitor: {window.get('monitorIndex', -1)}")
    print(f"Workspace: {window.get('workspaceIndex', -1)}")
    print(f"Posição global: X={frame.get('x', 0)} Y={frame.get('y', 0)}")
    print(f"Posição relativa: X={relative.get('x', 0)} Y={relative.get('y', 0)}")
    print(f"Dimensão: {frame.get('width', 0)}x{frame.get('height', 0)}")
    print(f"Maximizada: {format_bool(state.get('maximized', False))}")
    print(f"Tela cheia: {format_bool(state.get('fullscreen', False))}")
    print(f"Minimizada: {format_bool(state.get('minimized', False))}")
    print(f"Permite mover: {format_bool(state.get('allowsMove', False))}")
    print(f"Permite redimensionar: {format_bool(state.get('allowsResize', False))}")
    print(f"Ignorada pela barra de tarefas: {format_bool(state.get('skipTaskbar', False))}")


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
    if selected is not None:
        print_selected_window(selected)

    return 0


if __name__ == "__main__":
    sys.exit(main())
