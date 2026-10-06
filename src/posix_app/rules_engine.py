"""Motor de correspondência de regras de janelas e organização automática do PosiX."""

import re


def match_window(window, rule):
    """Verifica se uma janela aberta corresponde aos critérios de uma regra cadastrada.

    - match_app: confere se o texto está contido no wmClass, appId ou appName (ex: 'firefox', 'brave').
    - match_title: suporta múltiplos termos separados por vírgula, ';' ou '|' (ex: 'WhatsApp, IXC').
    """
    if not isinstance(window, dict) or not isinstance(rule, dict):
        return False

    if not rule.get("is_active", True):
        return False

    match_app = str(rule.get("match_app") or "").strip().lower()
    match_title = str(rule.get("match_title") or "").strip().lower()

    if not match_app and not match_title:
        return False

    # 1. Verificação de aplicativo (se especificado)
    if match_app:
        app_id = str(window.get("appId") or "").lower()
        wm_class = str(window.get("wmClass") or "").lower()
        wm_instance = str(window.get("wmClassInstance") or "").lower()
        app_name = str(window.get("appName") or "").lower()

        app_tokens = [tok.strip() for tok in re.split(r"[,;|]", match_app) if tok.strip()]
        matched_any_app = any(
            tok in app_id or tok in wm_class or tok in wm_instance or tok in app_name
            for tok in app_tokens
        )
        if not matched_any_app:
            return False

    # 2. Verificação de título (se especificado)
    if match_title:
        window_title = str(window.get("title") or "").lower()
        title_tokens = [tok.strip() for tok in re.split(r"[,;|]", match_title) if tok.strip()]
        matched_any_title = any(tok in window_title for tok in title_tokens)
        if not matched_any_title:
            return False

    return True


def find_matching_rule_for_window(window, rules):
    """Encontra a regra de maior especificidade que coincide com a janela."""
    if not rules or not isinstance(rules, list):
        return None

    def rule_specificity(r):
        has_app = 1 if (r.get("match_app") or "").strip() else 0
        has_title = 1 if (r.get("match_title") or "").strip() else 0
        return (has_app + has_title, has_title, has_app)

    sorted_rules = sorted(rules, key=rule_specificity, reverse=True)

    for rule in sorted_rules:
        if match_window(window, rule):
            return rule

    return None


def plan_window_organization(windows, rules, positions=None):
    """Mapeia todas as janelas abertas para suas respectivas posições alvo com base nas regras ativas."""
    if not windows or not rules:
        return []

    positions_by_id = {}
    if positions:
        for p in positions:
            positions_by_id[p.get("id")] = p

    actions = []
    used_sequences = set()

    for win in windows:
        seq = str(win.get("stableSequence") or "")
        if not seq or seq in used_sequences:
            continue

        rule = find_matching_rule_for_window(win, rules)
        if not rule:
            continue

        pos_id = rule.get("position_id")
        pos_data = positions_by_id.get(pos_id) or rule

        target_width = pos_data.get("width")
        target_height = pos_data.get("height")
        if not target_width or not target_height:
            continue

        frame = win.get("frame") or {}
        gx = pos_data.get("global_x")
        gy = pos_data.get("global_y")

        target_x = gx if gx is not None else frame.get("x", 100)
        target_y = gy if gy is not None else frame.get("y", 100)

        used_sequences.add(seq)
        actions.append({
            "stable_sequence": seq,
            "window": win,
            "rule": rule,
            "position": pos_data,
            "target_x": int(target_x),
            "target_y": int(target_y),
            "target_width": int(target_width),
            "target_height": int(target_height),
            "summary": f"{win.get('title') or win.get('appName') or 'Janela'} ➔ {rule.get('name')} ({pos_data.get('position_name') or pos_data.get('name') or 'Posição'})",
        })

    return actions
