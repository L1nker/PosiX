"""Cliente D-Bus para obter janelas pela extensão GNOME do PosiX."""

import json

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


BUS_NAME = "io.github.L1nker.PosiX"
OBJECT_PATH = "/io/github/L1nker/PosiX"
INTERFACE_NAME = "io.github.L1nker.PosiX"
DEFAULT_TIMEOUT_MS = 5000

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


class PosiXDBusError(Exception):
    """Erro ao comunicar com o serviço D-Bus do PosiX."""


class PosiXContractError(Exception):
    """Erro no contrato JSON retornado pela extensão."""


def fetch_windows(timeout_ms=DEFAULT_TIMEOUT_MS):
    """Retorna a lista de janelas validada pelo contrato ListWindows."""
    response = _call_list_windows(timeout_ms)

    try:
        payload = json.loads(response)
    except json.JSONDecodeError as error:
        raise PosiXContractError(f"JSON inválido retornado pela extensão: {error}") from error

    return _validate_payload(payload)


def _call_list_windows(timeout_ms):
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            None,
            BUS_NAME,
            OBJECT_PATH,
            INTERFACE_NAME,
            None,
        )
        proxy.set_default_timeout(timeout_ms)

        result = proxy.call_sync(
            "ListWindows",
            None,
            Gio.DBusCallFlags.NONE,
            timeout_ms,
            None,
        )
    except GLib.Error as error:
        raise PosiXDBusError(_describe_gio_error(error)) from error

    return result.unpack()[0]


def _describe_gio_error(error):
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


def _validate_payload(payload):
    if not isinstance(payload, dict):
        raise PosiXContractError("Contrato inválido: a resposta raiz não é um objeto JSON.")

    if payload.get("schemaVersion") != 1:
        raise PosiXContractError("Contrato inválido: schemaVersion diferente de 1.")

    windows = payload.get("windows")
    if not isinstance(windows, list):
        raise PosiXContractError("Contrato inválido: windows não é uma lista.")

    for index, window in enumerate(windows):
        _validate_window(index, window)

    return windows


def _validate_window(index, window):
    if not isinstance(window, dict):
        raise PosiXContractError(f"Contrato inválido: janela {index} não é um objeto.")

    missing = sorted(REQUIRED_WINDOW_FIELDS - set(window))
    if missing:
        raise PosiXContractError(
            f"Contrato inválido: janela {index} sem campos: {', '.join(missing)}."
        )

    _validate_geometry(index, "frame", window["frame"], REQUIRED_GEOMETRY_FIELDS)
    _validate_geometry(index, "relative", window["relative"], REQUIRED_RELATIVE_FIELDS)


def _validate_geometry(index, field_name, value, required_fields):
    if not isinstance(value, dict):
        raise PosiXContractError(
            f"Contrato inválido: {field_name} da janela {index} não é objeto."
        )

    missing = sorted(required_fields - set(value))
    if missing:
        raise PosiXContractError(
            f"Contrato inválido: {field_name} da janela {index} sem campos: "
            f"{', '.join(missing)}."
        )

