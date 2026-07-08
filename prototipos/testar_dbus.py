#!/usr/bin/env python3

import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


BUS_NAME = "io.github.L1nker.PosiX"
OBJECT_PATH = "/io/github/L1nker/PosiX"
INTERFACE_NAME = "io.github.L1nker.PosiX"
MESSAGE = "Teste do aplicativo Python"
EXPECTED_RESPONSE = f"PosiX respondeu: {MESSAGE}"
TIMEOUT_MS = 5000


def describe_gio_error(error):
    message = str(error)

    if "org.freedesktop.DBus.Error.ServiceUnknown" in message:
        return (
            "Nome D-Bus inexistente. Verifique se a extensão posix@linker "
            "está instalada, habilitada e carregada na sessão atual."
        )

    if "org.freedesktop.DBus.Error.NameHasNoOwner" in message:
        return (
            "A extensão não parece estar carregada. O nome D-Bus existe na "
            "chamada, mas não possui dono na sessão atual."
        )

    if (
        "org.freedesktop.DBus.Error.NoReply" in message
        or "Timeout" in message
        or "timed out" in message.lower()
    ):
        return "Timeout ao chamar Ping. O serviço não respondeu em até 5 segundos."

    return f"Erro GLib/Gio: {message}"


def main():
    print("Conectando ao serviço D-Bus do PosiX...")

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
        proxy.set_default_timeout(TIMEOUT_MS)

        print(f"Mensagem enviada: {MESSAGE}")
        result = proxy.call_sync(
            "Ping",
            GLib.Variant("(s)", (MESSAGE,)),
            Gio.DBusCallFlags.NONE,
            TIMEOUT_MS,
            None,
        )

        response = result.unpack()[0]

        if response != EXPECTED_RESPONSE:
            print(f"Resposta inesperada: {response}", file=sys.stderr)
            print(f"Resposta esperada: {EXPECTED_RESPONSE}", file=sys.stderr)
            return 1

        print(f"Resposta recebida: {response}")
        print("Teste D-Bus concluído com sucesso.")
        return 0

    except GLib.Error as error:
        print(describe_gio_error(error), file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Erro inesperado: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
