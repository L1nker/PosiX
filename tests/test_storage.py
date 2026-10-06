"""Testes unitários para o módulo de armazenamento local (storage.py)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from posix_app.storage import (
    StorageError,
    create_manual_preset,
    create_window_rule,
    delete_saved_position,
    delete_window_rule,
    list_saved_positions,
    list_window_rules,
    rename_saved_position,
    save_window_position,
    toggle_window_rule,
    update_manual_preset,
    update_saved_position_geometry,
    update_window_rule,
)


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "posix_test.db"
        self.patcher = patch("posix_app.storage.get_database_path", return_value=self.db_path)
        self.patcher.start()

        self.sample_window = {
            "stableSequence": "42",
            "title": "Projeto Alpha - Editor",
            "wmClass": "code",
            "wmClassInstance": "code",
            "pid": 12345,
            "appId": "code.desktop",
            "appName": "VS Code",
            "monitorIndex": 0,
            "workspaceIndex": 1,
            "frame": {"x": 100, "y": 200, "width": 1200, "height": 800},
            "relative": {"x": 100, "y": 200},
        }
        self.sample_app = {
            "gnome": "VS Code",
            "resolved": "VS Code",
            "origin": "GNOME",
            "confidence": "alta",
        }

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_save_and_list_positions(self):
        # Salva com nome padrão
        id1 = save_window_position(self.sample_window, self.sample_app)
        self.assertIsInstance(id1, int)
        self.assertGreater(id1, 0)

        # Salva com nome personalizado
        id2 = save_window_position(self.sample_window, self.sample_app, name="Meu Workspace Principal")
        self.assertEqual(id2, id1 + 1)

        positions = list_saved_positions()
        self.assertEqual(len(positions), 2)
        self.assertEqual(positions[0]["id"], id2)
        self.assertEqual(positions[0]["name"], "Meu Workspace Principal")
        self.assertEqual(positions[1]["id"], id1)
        self.assertIn("VS Code", positions[1]["name"])

    def test_rename_saved_position(self):
        saved_id = save_window_position(self.sample_window, self.sample_app, name="Nome Antigo")
        
        # Renomeação com sucesso
        success = rename_saved_position(saved_id, "Nome Novo e Melhor")
        self.assertTrue(success)

        positions = list_saved_positions()
        self.assertEqual(positions[0]["name"], "Nome Novo e Melhor")

        # Falha com nome vazio
        with self.assertRaises(StorageError):
            rename_saved_position(saved_id, "   ")

        # ID inexistente
        not_found = rename_saved_position(9999, "Tentativa Inexistente")
        self.assertFalse(not_found)

    def test_update_saved_position_geometry(self):
        saved_id = save_window_position(self.sample_window, self.sample_app, name="Layout Fixo")

        updated_window = dict(self.sample_window)
        updated_window["frame"] = {"x": 300, "y": 400, "width": 1600, "height": 900}
        updated_window["relative"] = {"x": 300, "y": 400}
        updated_window["title"] = "Projeto Alpha - Modificado"

        success = update_saved_position_geometry(saved_id, updated_window, self.sample_app)
        self.assertTrue(success)

        positions = list_saved_positions()
        self.assertEqual(len(positions), 1)
        pos = positions[0]
        self.assertEqual(pos["name"], "Layout Fixo")  # Nome deve se manter
        self.assertEqual(pos["global_x"], 300)
        self.assertEqual(pos["global_y"], 400)
        self.assertEqual(pos["width"], 1600)
        self.assertEqual(pos["height"], 900)
        self.assertEqual(pos["title"], "Projeto Alpha - Modificado")

    def test_delete_saved_position(self):
        saved_id = save_window_position(self.sample_window, self.sample_app)
        self.assertEqual(len(list_saved_positions()), 1)

        deleted = delete_saved_position(saved_id)
        self.assertTrue(deleted)
        self.assertEqual(len(list_saved_positions()), 0)

        # Deletar novamente deve retornar False
        deleted_again = delete_saved_position(saved_id)
        self.assertFalse(deleted_again)

    def test_create_and_update_manual_preset(self):
        # Cria preset manual universal
        preset_id = create_manual_preset(
            name="1280 × 720 (HD)",
            width=1280,
            height=720,
            global_x=100,
            global_y=150,
            preset_type="universal",
        )
        self.assertIsInstance(preset_id, int)
        self.assertGreater(preset_id, 0)

        positions = list_saved_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["name"], "1280 × 720 (HD)")
        self.assertEqual(positions[0]["width"], 1280)
        self.assertEqual(positions[0]["height"], 720)

        # Atualiza o preset manual
        updated = update_manual_preset(
            position_id=preset_id,
            name="1280 × 720 (Custom)",
            width=1280,
            height=800,
            global_x=50,
            global_y=50,
        )
        self.assertTrue(updated)

        positions = list_saved_positions()
        self.assertEqual(positions[0]["name"], "1280 × 720 (Custom)")
        self.assertEqual(positions[0]["height"], 800)

    def test_window_rules_crud(self):
        pos_id = create_manual_preset("Melhor Lugar", 1280, 720, global_x=200, global_y=150)

        # Criação de regra com múltiplos títulos
        rule_id = create_window_rule(
            name="WhatsApp e IXC",
            position_id=pos_id,
            match_title="WhatsApp, IXC",
            match_app="firefox",
        )
        self.assertIsInstance(rule_id, int)

        rules = list_window_rules()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["id"], rule_id)
        self.assertEqual(rules[0]["name"], "WhatsApp e IXC")
        self.assertEqual(rules[0]["match_title"], "WhatsApp, IXC")
        self.assertEqual(rules[0]["position_name"], "Melhor Lugar")
        self.assertEqual(rules[0]["width"], 1280)

        # Toggle de regra
        self.assertTrue(rules[0]["is_active"])
        toggle_window_rule(rule_id, is_active=False)
        rules = list_window_rules()
        self.assertFalse(rules[0]["is_active"])

        # Atualização de regra
        update_window_rule(rule_id, "WhatsApp e IXC - Atualizado", pos_id, match_title="WhatsApp, IXC, Telegram", is_active=True)
        rules = list_window_rules()
        self.assertEqual(rules[0]["name"], "WhatsApp e IXC - Atualizado")
        self.assertEqual(rules[0]["match_title"], "WhatsApp, IXC, Telegram")
        self.assertTrue(rules[0]["is_active"])

        # Exclusão da posição deve remover as regras associadas
        delete_saved_position(pos_id)
        rules_after_pos_delete = list_window_rules()
        self.assertEqual(len(rules_after_pos_delete), 0)


if __name__ == "__main__":
    unittest.main()
