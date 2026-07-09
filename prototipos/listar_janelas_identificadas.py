#!/usr/bin/env python3

import sys
from pathlib import Path


# Temporário até o empacotamento do aplicativo: permite importar src/ local.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from posix_app.dbus_windows import PosiXContractError, PosiXDBusError, fetch_windows
from posix_app.window_identity import resolve_application


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
        windows = fetch_windows()
    except (PosiXDBusError, PosiXContractError) as error:
        print(str(error), file=sys.stderr)
        return 1

    print_table(windows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
