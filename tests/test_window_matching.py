"""Testes unitários para o módulo de correspondência heurística (window_matching.py)."""

import json
import unittest

from posix_app.window_matching import (
    find_best_window_match,
    normalize_application_identity,
    normalize_title,
    rank_window_matches,
)


class TestWindowMatching(unittest.TestCase):
    def setUp(self):
        self.saved_position = {
            "id": 1,
            "name": "VS Code — main.py",
            "snapshot_json": json.dumps({
                "window": {
                    "stableSequence": "10",
                    "title": "main.py - Visual Studio Code",
                    "appId": "code.desktop",
                    "wmClass": "code",
                    "wmClassInstance": "code",
                    "monitorIndex": 0,
                    "frame": {"x": 50, "y": 50, "width": 1000, "height": 700},
                },
                "application": {
                    "gnome": "Code",
                    "resolved": "VS Code",
                    "origin": "GNOME",
                    "confidence": "alta",
                },
            }),
        }

    def test_normalize_title_removes_suffixes(self):
        self.assertEqual(
            normalize_title("GitHub - PosiX — Mozilla Firefox"),
            "github - posix",
        )
        self.assertEqual(
            normalize_title("Meu Dashboard — Brave"),
            "meu dashboard",
        )
        self.assertEqual(
            normalize_title("Pesquisa Google - Google Chrome"),
            "pesquisa google",
        )
        self.assertEqual(
            normalize_title("(3) Mensagens novas"),
            "mensagens novas",
        )

    def test_normalize_application_identity(self):
        self.assertEqual(normalize_application_identity("google-chrome.desktop"), "google-chrome")
        self.assertEqual(normalize_application_identity("Visual Studio Code"), "vscode")
        self.assertEqual(normalize_application_identity("code"), "vscode")
        self.assertEqual(normalize_application_identity("gnome-terminal"), "terminal")
        self.assertEqual(normalize_application_identity("gedit"), "editor-de-texto")

    def test_find_best_window_match_exact(self):
        current_windows = [
            {
                "stableSequence": "99",
                "title": "main.py - Visual Studio Code",
                "appId": "code.desktop",
                "wmClass": "code",
                "wmClassInstance": "code",
                "monitorIndex": 0,
                "frame": {"x": 60, "y": 60, "width": 1020, "height": 710},
            },
            {
                "stableSequence": "100",
                "title": "Terminal do Zorin",
                "appId": "org.gnome.Terminal.desktop",
                "wmClass": "gnome-terminal",
                "wmClassInstance": "gnome-terminal-server",
                "monitorIndex": 0,
                "frame": {"x": 200, "y": 200, "width": 800, "height": 600},
            },
        ]

        result = find_best_window_match(self.saved_position, current_windows)
        self.assertEqual(result["status"], "matched")
        self.assertIsNotNone(result["best"])
        self.assertEqual(result["best"]["window"]["stableSequence"], "99")
        self.assertGreaterEqual(result["best"]["score"], 100)

    def test_find_best_window_match_conflict_rejected(self):
        # Apenas janelas de aplicativos diferentes com appIds conflitantes
        current_windows = [
            {
                "stableSequence": "88",
                "title": "Configurações do Sistema",
                "appId": "gnome-control-center.desktop",
                "wmClass": "gnome-control-center",
                "wmClassInstance": "gnome-control-center",
                "monitorIndex": 0,
                "frame": {"x": 100, "y": 100, "width": 600, "height": 500},
            }
        ]

        result = find_best_window_match(self.saved_position, current_windows)
        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["best"])


if __name__ == "__main__":
    unittest.main()
