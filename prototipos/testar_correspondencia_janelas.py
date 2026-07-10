#!/usr/bin/env python3

import sys
from pathlib import Path


# Temporário até o empacotamento do aplicativo: permite importar src/ local.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from posix_app.dbus_windows import PosiXContractError, PosiXDBusError, fetch_windows
from posix_app.storage import StorageError, list_saved_positions
from posix_app.window_matching import WindowMatchingError, find_best_window_match


MAX_CANDIDATES = 5


def main():
    try:
        windows = fetch_windows()
        saved_positions = list_saved_positions()
    except (PosiXDBusError, PosiXContractError, StorageError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Erro inesperado: {error}", file=sys.stderr)
        return 1

    if not saved_positions:
        print("Nenhuma posição salva encontrada.")
        return 0

    if not windows:
        print("Nenhuma janela aberta encontrada.")
        return 0

    for index, saved_position in enumerate(saved_positions):
        if index:
            print()

        print_saved_position(saved_position)

        try:
            result = find_best_window_match(saved_position, windows)
        except WindowMatchingError as error:
            print("Resultado")
            print("---------")
            print("Status: erro")
            print(f"Mensagem: {error}")
            continue

        print_result(result)

    return 0


def print_saved_position(saved_position):
    print("Posição salva")
    print("--------------")
    print(f"ID: {saved_position.get('id', '')}")
    print(f"Nome: {saved_position.get('name', '')}")
    print(f"Aplicativo salvo: {saved_position.get('application') or 'Desconhecido'}")
    print(f"Título salvo: {saved_position.get('title') or ''}")
    print()


def print_result(result):
    print("Resultado")
    print("---------")
    print(f"Status: {result['status']}")
    print(f"Mensagem: {result['message']}")
    print()

    if result["status"] == "matched":
        best = result["best"]
        print("Correspondência sugerida:")
        print(f"{best['application']['resolved']} — {best['window'].get('title', '')}")
        print()
    elif result["status"] == "ambiguous":
        print("Correspondência ambígua — nenhuma janela foi escolhida automaticamente.")
        print()
    elif result["status"] == "not_found":
        print("Nenhuma correspondência segura encontrada.")
        print()

    print_candidates(result["candidates"][:MAX_CANDIDATES])


def print_candidates(candidates):
    print("Melhores candidatos")
    print("--------------------")

    if not candidates:
        print("Nenhum candidato disponível.")
        return

    for position, candidate in enumerate(candidates, start=1):
        window = candidate["window"]
        application = candidate["application"]
        print(f"{position}.")
        print(f"Pontuação: {candidate['score']}")
        print(f"Confiança: {candidate['confidence']}")
        print(f"Elegível: {yes_no(candidate['eligible'])}")
        print(f"Sequência atual: {window.get('stableSequence', '')}")
        print(f"Aplicativo atual: {application.get('resolved') or 'Desconhecido'}")
        print(f"Título atual: {window.get('title', '')}")
        print(f"Monitor: {window.get('monitorIndex', -1)}")
        print(f"Razões: {format_list(candidate['reasons'])}")
        print(f"Conflitos: {format_list(candidate['conflicts'])}")
        print()


def yes_no(value):
    return "Sim" if value else "Não"


def format_list(values):
    if not values:
        return "Nenhum"

    return "; ".join(values)


if __name__ == "__main__":
    sys.exit(main())
