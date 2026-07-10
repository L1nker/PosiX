#!/usr/bin/env python3

import sys
from pathlib import Path


# Temporário até o empacotamento do aplicativo: permite importar src/ local.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from posix_app.dbus_windows import (
    PosiXContractError,
    PosiXDBusError,
    fetch_windows,
    move_resize_window,
)
from posix_app.storage import StorageError, list_saved_positions
from posix_app.window_identity import resolve_application


def main():
    try:
        windows = fetch_windows()
        saved_positions = list_saved_positions()
    except (PosiXDBusError, PosiXContractError, StorageError) as error:
        print(f"Erro técnico: {error}", file=sys.stderr)
        return 1

    if not windows:
        print("Nenhuma janela aberta foi retornada pelo D-Bus.")
        return 0

    if not saved_positions:
        print("Nenhuma posição salva encontrada.")
        return 0

    window = select_open_window(windows)
    if window is None:
        return 0

    saved_position = select_saved_position(saved_positions)
    if saved_position is None:
        return 0

    if not has_saved_geometry(saved_position):
        print("A posição salva não possui geometria global e dimensão válidas.", file=sys.stderr)
        return 1

    print_comparison(window, saved_position)

    confirmation = input("Digite RESTAURAR para confirmar ou Q para cancelar: ").strip()
    if confirmation.lower() == "q":
        print("Restauração cancelada.")
        return 0

    if confirmation != "RESTAURAR":
        print("Confirmação inválida. Nenhuma restauração foi executada.")
        return 0

    try:
        result = move_resize_window(
            window.get("stableSequence", ""),
            saved_position["global_x"],
            saved_position["global_y"],
            saved_position["width"],
            saved_position["height"],
        )
    except (PosiXDBusError, PosiXContractError) as error:
        print(f"Erro técnico: {error}", file=sys.stderr)
        return 1

    print_result(result)
    return 0 if result.get("success") else 1


def select_open_window(windows):
    print("Janelas abertas")
    print("---------------")
    for index, window in enumerate(windows, start=1):
        app = resolve_application(window)
        frame = window.get("frame", {})
        print(
            f"[{index}] {app.get('resolved', '')} — "
            f"{window.get('title', '')} — "
            f"Seq {window.get('stableSequence', '')} — "
            f"Monitor {window.get('monitorIndex', -1)} — "
            f"X={frame.get('x', 0)} Y={frame.get('y', 0)} — "
            f"{frame.get('width', 0)}x{frame.get('height', 0)}"
        )

    return select_from_list(windows, "Selecione a janela aberta ou Q para cancelar: ")


def select_saved_position(saved_positions):
    print()
    print("Posições salvas")
    print("---------------")
    for index, position in enumerate(saved_positions, start=1):
        print(
            f"[{index}] ID {position.get('id')} — "
            f"{position.get('name') or ''} — "
            f"Monitor {position.get('monitor_index')} — "
            f"Global X={position.get('global_x')} Y={position.get('global_y')} — "
            f"Relativa X={position.get('relative_x')} Y={position.get('relative_y')} — "
            f"{position.get('width')}x{position.get('height')}"
        )

    return select_from_list(saved_positions, "Selecione a posição salva ou Q para cancelar: ")


def select_from_list(items, prompt):
    while True:
        choice = input(prompt).strip()

        if choice.lower() == "q":
            print("Operação cancelada.")
            return None

        if not choice:
            print("Entrada vazia. Digite um número da lista ou Q para cancelar.")
            continue

        if not choice.isdigit():
            print("Entrada inválida. Digite um número da lista ou Q para cancelar.")
            continue

        selected_index = int(choice)
        if selected_index < 1 or selected_index > len(items):
            print("Número fora da lista. Tente novamente.")
            continue

        return items[selected_index - 1]


def has_saved_geometry(position):
    return all(
        isinstance(position.get(key), int)
        for key in ("global_x", "global_y", "width", "height")
    ) and position["width"] > 0 and position["height"] > 0


def print_comparison(window, position):
    frame = window.get("frame", {})
    requested = {
        "x": position["global_x"],
        "y": position["global_y"],
        "width": position["width"],
        "height": position["height"],
    }

    print()
    print("Janela atual")
    print("------------")
    print(f"Sequência: {window.get('stableSequence', '')}")
    print(f"Título: {window.get('title', '')}")
    print(format_geometry("Geometria atual", frame))

    print()
    print("Posição salva")
    print("-------------")
    print(f"ID: {position.get('id')}")
    print(f"Nome: {position.get('name') or ''}")
    print(format_geometry("Geometria salva", requested))
    print(
        "Posição relativa salva: "
        f"X={position.get('relative_x')} Y={position.get('relative_y')}"
    )

    print()
    print("Alteração solicitada")
    print("--------------------")
    print(format_geometry("Destino global", requested))


def print_result(result):
    print()
    print("Resultado da restauração")
    print("------------------------")
    print(f"Sucesso: {format_bool(result.get('success', False))}")
    print(f"Sequência: {result.get('stableSequence', '')}")
    print(format_geometry("Geometria anterior", result.get("before")))
    print(format_geometry("Geometria solicitada", result.get("requested")))
    print(format_geometry("Geometria obtida", result.get("after")))
    print(format_geometry("Diferenças", result.get("difference")))
    print(f"Restauração exata: {format_bool(result.get('exact', False))}")

    if result.get("error"):
        print(f"Mensagem de erro: {result['error']}")


def format_geometry(label, geometry):
    if geometry is None:
        return f"{label}: n/a"

    return (
        f"{label}: "
        f"X={geometry.get('x')} Y={geometry.get('y')} "
        f"{geometry.get('width')}x{geometry.get('height')}"
    )


def format_bool(value):
    return "Sim" if bool(value) else "Não"


if __name__ == "__main__":
    raise SystemExit(main())
