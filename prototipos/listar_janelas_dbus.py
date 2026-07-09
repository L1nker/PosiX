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
    "pid",
    "appName",
    "monitorIndex",
    "frame",
    "relative",
}


def describe_gio_error(error):
    message = str(error)

    if "org.freedesktop.DBus.Error.ServiceUnknown" in message:
        return (
            "Serviço D-Bus inexistente. Verifique se a extensão posix@linker "
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
        raise ValueError("Contrato inesperado: resposta raiz não é um objeto JSON.")

    if payload.get("schemaVersion") != 1:
        raise ValueError("Contrato inesperado: schemaVersion diferente de 1.")

    windows = payload.get("windows")
    if not isinstance(windows, list):
        raise ValueError("Contrato inesperado: windows não é uma lista.")

    for index, window in enumerate(windows):
        if not isinstance(window, dict):
            raise ValueError(f"Contrato inesperado: janela {index} não é um objeto.")

        missing = sorted(REQUIRED_WINDOW_FIELDS - set(window))
        if missing:
            fields = ", ".join(missing)
            raise ValueError(f"Contrato inesperado: janela {index} sem campos: {fields}.")

        for geometry_field in ("frame", "relative"):
            if not isinstance(window[geometry_field], dict):
                raise ValueError(
                    f"Contrato inesperado: {geometry_field} da janela {index} não é objeto."
                )

    return windows


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
        "X global",
        "Y global",
        "Largura",
        "Altura",
        "Aplicativo",
        "Título",
    ]
    rows = []

    for window in windows:
        frame = window["frame"]
        relative = window["relative"]
        rows.append([
            window["stableSequence"],
            window["pid"],
            window["monitorIndex"],
            relative.get("x", 0),
            relative.get("y", 0),
            frame.get("x", 0),
            frame.get("y", 0),
            frame.get("width", 0),
            frame.get("height", 0),
            truncate(window.get("appName") or window.get("appId") or "", 24),
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
