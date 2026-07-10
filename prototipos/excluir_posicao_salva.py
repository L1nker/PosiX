#!/usr/bin/env python3

import sys
from pathlib import Path


# Temporário até o empacotamento do aplicativo: permite importar src/ local.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from posix_app.storage import StorageError, delete_saved_position, list_saved_positions


def main():
    try:
        positions = list_saved_positions()
    except StorageError as error:
        print(f"Erro ao listar posições salvas: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Erro inesperado: {error}", file=sys.stderr)
        return 1

    if not positions:
        print("Nenhuma posição salva encontrada.")
        return 0

    print_positions(positions)
    selected_id = ask_position_id()
    if selected_id is None:
        print("Operação cancelada.")
        return 0

    selected_position = find_position(positions, selected_id)
    if selected_position is None:
        print("Posição inexistente.")
        return 0

    print()
    print_position_details(selected_position)

    confirmation = input("Digite EXCLUIR para confirmar ou Q para cancelar: ").strip()
    if confirmation.upper() == "Q":
        print("Operação cancelada.")
        return 0

    if confirmation != "EXCLUIR":
        print("Confirmação inválida. Nenhuma posição foi excluída.")
        return 0

    try:
        deleted = delete_saved_position(selected_id)
    except StorageError as error:
        print(f"Erro ao excluir posição salva: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Erro inesperado: {error}", file=sys.stderr)
        return 1

    if deleted:
        print("Posição excluída com sucesso.")
    else:
        print("A posição não existe mais.")

    return 0


def print_positions(positions):
    print("Posições salvas")
    print("---------------")
    for position in positions:
        print(
            f"[{position.get('id')}] "
            f"{position.get('name') or 'Posição sem nome'} — "
            f"{position.get('application') or 'Aplicativo desconhecido'} — "
            f"{position.get('title') or ''} — "
            f"Monitor {position.get('monitor_index')} — "
            f"X={position.get('global_x')} Y={position.get('global_y')} — "
            f"{position.get('width')} x {position.get('height')}"
        )


def ask_position_id():
    value = input("Digite o ID da posição ou Q para cancelar: ").strip()
    if value.upper() == "Q":
        return None

    try:
        position_id = int(value)
    except ValueError:
        print("ID inválido.")
        return None

    if position_id <= 0:
        print("ID inválido.")
        return None

    return position_id


def find_position(positions, position_id):
    for position in positions:
        if position.get("id") == position_id:
            return position

    return None


def print_position_details(position):
    print("Posição escolhida")
    print("-----------------")
    print(f"ID: {position.get('id')}")
    print(f"Nome: {position.get('name') or ''}")
    print(f"Data: {position.get('created_at') or ''}")
    print(f"Aplicativo: {position.get('application') or ''}")
    print(f"Título: {position.get('title') or ''}")
    print(f"App ID: {position.get('app_id') or ''}")
    print(f"WM_CLASS: {position.get('wm_class') or ''}")
    print(f"Instância: {position.get('wm_class_instance') or ''}")
    print(f"PID capturado: {position.get('pid')}")
    print(f"Monitor: {position.get('monitor_index')}")
    print(f"Workspace: {position.get('workspace_index')}")
    print(
        "Posição global: "
        f"X={position.get('global_x')} Y={position.get('global_y')}"
    )
    print(
        "Posição relativa: "
        f"X={position.get('relative_x')} Y={position.get('relative_y')}"
    )
    print(f"Dimensão: {position.get('width')} x {position.get('height')}")


if __name__ == "__main__":
    sys.exit(main())
