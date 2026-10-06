"""Testes unitários para o motor de regras e organização de janelas (rules_engine.py)."""

import unittest

from posix_app.rules_engine import (
    find_matching_rule_for_window,
    match_window,
    plan_window_organization,
)


class TestRulesEngine(unittest.TestCase):
    def setUp(self):
        self.firefox_whatsapp = {
            "stableSequence": "101",
            "title": "(5) WhatsApp - Mozilla Firefox",
            "wmClass": "firefox",
            "appId": "firefox.desktop",
            "appName": "Firefox Web Browser",
            "frame": {"x": 50, "y": 50, "width": 800, "height": 600},
        }

        self.firefox_ixc = {
            "stableSequence": "102",
            "title": "IXC Provedor :: Central do Assinante - Mozilla Firefox",
            "wmClass": "firefox",
            "appId": "firefox.desktop",
            "appName": "Firefox Web Browser",
            "frame": {"x": 100, "y": 100, "width": 900, "height": 700},
        }

        self.brave_pip = {
            "stableSequence": "205",
            "title": "Picture-in-picture",
            "wmClass": "",
            "appId": "brave-browser.desktop",
            "appName": "Brave Web Browser",
            "frame": {"x": 1400, "y": 800, "width": 480, "height": 270},
        }

        self.rule_whatsapp_ixc = {
            "id": 1,
            "name": "Firefox Comunicação / Gestão",
            "position_id": 10,
            "match_title": "WhatsApp, IXC",
            "match_app": "firefox",
            "is_active": True,
            "position_name": "Melhor Lugar",
            "width": 1280,
            "height": 720,
            "global_x": 200,
            "global_y": 150,
        }

        self.rule_pip = {
            "id": 2,
            "name": "YouTube PiP Canto",
            "position_id": 11,
            "match_title": "Picture-in-picture",
            "match_app": "brave",
            "is_active": True,
            "position_name": "PiP Inferior",
            "width": 540,
            "height": 304,
            "global_x": 1360,
            "global_y": 720,
        }

    def test_match_window_whatsapp_and_ixc(self):
        # Janela do WhatsApp deve bater
        self.assertTrue(match_window(self.firefox_whatsapp, self.rule_whatsapp_ixc))

        # Janela do IXC deve bater na mesma regra
        self.assertTrue(match_window(self.firefox_ixc, self.rule_whatsapp_ixc))

        # Outra janela sem os termos não deve bater
        firefox_random = dict(self.firefox_whatsapp, title="Google Search - Mozilla Firefox")
        self.assertFalse(match_window(firefox_random, self.rule_whatsapp_ixc))

    def test_match_window_brave_pip(self):
        # Brave PiP tem wmClass vazio, mas appId é 'brave-browser.desktop' e título é 'Picture-in-picture'
        self.assertTrue(match_window(self.brave_pip, self.rule_pip))

    def test_inactive_rule_does_not_match(self):
        inactive_rule = dict(self.rule_whatsapp_ixc, is_active=False)
        self.assertFalse(match_window(self.firefox_whatsapp, inactive_rule))

    def test_plan_window_organization(self):
        windows = [self.firefox_whatsapp, self.brave_pip]
        rules = [self.rule_whatsapp_ixc, self.rule_pip]

        plan = plan_window_organization(windows, rules)
        self.assertEqual(len(plan), 2)

        # Primeiro item planejado: Firefox WhatsApp
        self.assertEqual(plan[0]["stable_sequence"], "101")
        self.assertEqual(plan[0]["target_width"], 1280)
        self.assertEqual(plan[0]["target_height"], 720)
        self.assertEqual(plan[0]["target_x"], 200)
        self.assertEqual(plan[0]["target_y"], 150)

        # Segundo item planejado: Brave PiP
        self.assertEqual(plan[1]["stable_sequence"], "205")
        self.assertEqual(plan[1]["target_width"], 540)
        self.assertEqual(plan[1]["target_height"], 304)
        self.assertEqual(plan[1]["target_x"], 1360)
        self.assertEqual(plan[1]["target_y"], 720)


if __name__ == "__main__":
    unittest.main()
