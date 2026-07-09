#!/usr/bin/env python3

import sys
from pathlib import Path


# Temporário até o empacotamento do aplicativo: permite importar src/ local.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from posix_app.storage import StorageError, list_saved_positions


def main():
    try:
        positions = list_saved_positions()
    except StorageError as error:
        print(f"Não foi possível listar posições salvas: {error}", file=sys.stderr)
        return 1

    print(f"Quantidade de posições salvas: {len(positions)}")

    if not positions:
        print("Nenhuma posição salva encontrada.")
        return 0

    for position in positions:
        print()
        print(f"ID: {position.get('id')}")
        print(f"Nome: {position.get('name') or ''}")
        print(f"Data: {position.get('created_at') or ''}")
        print(f"Aplicativo: {position.get('application') or ''}")
        print(f"Título: {position.get('title') or ''}")
        print(f"Monitor: {position.get('monitor_index')}")
        print(
            "Posição global: "
            f"X={position.get('global_x')} Y={position.get('global_y')}"
        )
        print(
            "Posição relativa: "
            f"X={position.get('relative_x')} Y={position.get('relative_y')}"
        )
        print(f"Dimensão: {position.get('width')}x{position.get('height')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

