"""Correspondência entre posições salvas e janelas abertas."""

import json
import re

from posix_app.window_identity import resolve_application


SCORE_APP_ID_EXACT = 60
SCORE_WM_CLASS_EXACT = 45
SCORE_WM_CLASS_INSTANCE_EXACT = 20
SCORE_RESOLVED_APP_EXACT = 35
SCORE_TITLE_EXACT = 80
SCORE_TITLE_CONTAINS = 30
SCORE_SAME_MONITOR = 5
SCORE_SIMILAR_SIZE = 5

PENALTY_APP_ID_CONFLICT = -100
PENALTY_WM_CLASS_CONFLICT = -70
PENALTY_RESOLVED_APP_CONFLICT = -60

MIN_ELIGIBLE_SCORE = 50
HIGH_CONFIDENCE_SCORE = 120
MEDIUM_CONFIDENCE_SCORE = 80
LOW_CONFIDENCE_SCORE = 50
AMBIGUOUS_SCORE_GAP = 20
MAX_SIZE_DIFFERENCE_RATIO = 0.10

STRONG_CONFLICTS = {
    "App IDs úteis diferentes",
    "WM_CLASS úteis diferentes",
}

BROWSER_TITLE_SUFFIXES = (
    " — Mozilla Firefox",
    " - Mozilla Firefox",
    " — Brave",
    " - Brave",
)

APP_IDENTITY_ALIASES = {
    "brave web browser": "brave",
    "brave": "brave",
    "brave browser": "brave",
    "firefox": "firefox",
    "mozilla firefox": "firefox",
    "telegram": "telegram",
    "telegram desktop": "telegram",
    "discord": "discord",
    "terminal": "terminal",
    "gnome terminal": "terminal",
    "editor de texto": "editor-de-texto",
    "gnome text editor": "editor-de-texto",
    "arquivos": "arquivos",
    "files": "arquivos",
    "nautilus": "arquivos",
}


class WindowMatchingError(Exception):
    """Erro ao comparar uma posição salva com janelas abertas."""


def rank_window_matches(saved_position, current_windows):
    """Retorna candidatos de janela ordenados por pontuação."""
    if not isinstance(current_windows, list):
        raise WindowMatchingError("A lista de janelas abertas é inválida.")

    snapshot = _load_snapshot(saved_position)
    saved_window = snapshot["window"]
    saved_application = snapshot["application"]

    candidates = []
    for window in current_windows:
        if not isinstance(window, dict):
            continue

        application = resolve_application(window)
        candidate = _score_candidate(
            saved_window,
            saved_application,
            window,
            application,
        )
        candidates.append(candidate)

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate["score"],
            candidate["eligible"],
            _text(candidate["window"].get("stableSequence")),
        ),
        reverse=True,
    )


def find_best_window_match(saved_position, current_windows):
    """Retorna a melhor correspondência segura, ambiguidade ou ausência."""
    candidates = rank_window_matches(saved_position, current_windows)
    eligible_candidates = [
        candidate for candidate in candidates
        if candidate["eligible"]
    ]

    if not eligible_candidates:
        return {
            "status": "not_found",
            "best": None,
            "candidates": candidates,
            "message": "Nenhuma janela aberta atingiu pontuação suficiente sem conflito forte.",
        }

    best = eligible_candidates[0]
    if len(eligible_candidates) > 1:
        second = eligible_candidates[1]
        if best["score"] - second["score"] < AMBIGUOUS_SCORE_GAP:
            return {
                "status": "ambiguous",
                "best": None,
                "candidates": candidates,
                "message": (
                    "Os dois melhores candidatos elegíveis ficaram próximos demais "
                    "para uma escolha automática segura."
                ),
            }

    return {
        "status": "matched",
        "best": best,
        "candidates": candidates,
        "message": "Uma janela aberta foi classificada como correspondência segura.",
    }


def _score_candidate(saved_window, saved_application, current_window, current_application):
    score = 0
    reasons = []
    conflicts = []

    score += _compare_exact_text(
        _useful_app_id(saved_window.get("appId")),
        _useful_app_id(current_window.get("appId")),
        SCORE_APP_ID_EXACT,
        PENALTY_APP_ID_CONFLICT,
        "App ID idêntico",
        "App IDs úteis diferentes",
        reasons,
        conflicts,
    )
    score += _compare_exact_text(
        _useful_value(saved_window.get("wmClass")),
        _useful_value(current_window.get("wmClass")),
        SCORE_WM_CLASS_EXACT,
        PENALTY_WM_CLASS_CONFLICT,
        "WM_CLASS idêntico",
        "WM_CLASS úteis diferentes",
        reasons,
        conflicts,
    )
    score += _compare_exact_text(
        _useful_value(saved_window.get("wmClassInstance")),
        _useful_value(current_window.get("wmClassInstance")),
        SCORE_WM_CLASS_INSTANCE_EXACT,
        0,
        "Instância idêntica",
        "",
        reasons,
        conflicts,
    )
    score += _compare_resolved_application(
        saved_application.get("resolved"),
        current_application.get("resolved"),
        reasons,
        conflicts,
    )

    title_score = _compare_titles(
        saved_window.get("title"),
        current_window.get("title"),
        reasons,
    )
    score += title_score

    if _safe_int(saved_window.get("monitorIndex")) == _safe_int(current_window.get("monitorIndex")):
        score += SCORE_SAME_MONITOR
        reasons.append("Mesmo monitor")

    if _has_similar_size(saved_window, current_window):
        score += SCORE_SIMILAR_SIZE
        reasons.append("Dimensões próximas")

    strong_conflict = any(conflict in STRONG_CONFLICTS for conflict in conflicts)
    eligible = score >= MIN_ELIGIBLE_SCORE and not strong_conflict

    return {
        "window": current_window,
        "application": current_application,
        "score": score,
        "confidence": _confidence(score),
        "reasons": reasons,
        "conflicts": conflicts,
        "eligible": eligible,
    }


def _load_snapshot(saved_position):
    if not isinstance(saved_position, dict):
        raise WindowMatchingError("A posição salva não é um dicionário.")

    snapshot_json = saved_position.get("snapshot_json")
    if not snapshot_json:
        raise WindowMatchingError("A posição salva não possui snapshot_json.")

    try:
        snapshot = json.loads(snapshot_json)
    except json.JSONDecodeError as error:
        raise WindowMatchingError(f"snapshot_json inválido: {error}") from error

    if not isinstance(snapshot, dict):
        raise WindowMatchingError("snapshot_json inválido: a raiz não é um objeto.")

    window = snapshot.get("window")
    if not isinstance(window, dict):
        raise WindowMatchingError("snapshot_json inválido: window ausente ou inválido.")

    application = snapshot.get("application")
    if not isinstance(application, dict):
        raise WindowMatchingError("snapshot_json inválido: application ausente ou inválida.")

    return snapshot


def _compare_exact_text(
    saved_value,
    current_value,
    match_score,
    conflict_penalty,
    reason,
    conflict,
    reasons,
    conflicts,
):
    if not saved_value or not current_value:
        return 0

    if saved_value == current_value:
        reasons.append(reason)
        return match_score

    if conflict_penalty and conflict:
        conflicts.append(conflict)
        return conflict_penalty

    return 0


def _compare_resolved_application(saved_value, current_value, reasons, conflicts):
    saved_text = _useful_value(saved_value)
    current_text = _useful_value(current_value)

    if not saved_text or not current_text:
        return 0

    if saved_text == current_text:
        reasons.append("Aplicativo resolvido idêntico")
        return SCORE_RESOLVED_APP_EXACT

    saved_identity = normalize_application_identity(saved_value)
    current_identity = normalize_application_identity(current_value)

    if saved_identity and current_identity and saved_identity == current_identity:
        reasons.append(
            "Aplicativos equivalentes: "
            f"{_text(saved_value)} e {_text(current_value)}"
        )
        return SCORE_RESOLVED_APP_EXACT

    conflicts.append("Aplicativos resolvidos úteis diferentes")
    return PENALTY_RESOLVED_APP_CONFLICT


def _compare_titles(saved_title, current_title, reasons):
    saved_normalized = normalize_title(saved_title)
    current_normalized = normalize_title(current_title)

    if not saved_normalized or not current_normalized:
        return 0

    if saved_normalized == current_normalized:
        reasons.append("Título normalizado idêntico")
        return SCORE_TITLE_EXACT

    if saved_normalized in current_normalized or current_normalized in saved_normalized:
        reasons.append("Um título normalizado contém o outro")
        return SCORE_TITLE_CONTAINS

    return 0


def normalize_title(value):
    """Normaliza título apenas para comparação de identidade."""
    text = _collapse_spaces(_text(value))
    text = re.sub(r"^\(\d+\)\s+", "", text)

    for suffix in BROWSER_TITLE_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break

    return _collapse_spaces(text).casefold()


def normalize_application_identity(value):
    """Normaliza nomes equivalentes de aplicativos para comparação de identidade."""
    text = normalize_text(value)
    if not text or text == "desconhecido":
        return ""

    if text.endswith(".desktop"):
        text = text[: -len(".desktop")]

    text = re.sub(r"[-_]+", " ", text)
    text = _collapse_spaces(text)

    return APP_IDENTITY_ALIASES.get(text, text)


def _has_similar_size(saved_window, current_window):
    saved_frame = _frame(saved_window)
    current_frame = _frame(current_window)

    return (
        _within_ratio(saved_frame.get("width"), current_frame.get("width"))
        and _within_ratio(saved_frame.get("height"), current_frame.get("height"))
    )


def _within_ratio(saved_value, current_value):
    saved_number = _safe_int(saved_value)
    current_number = _safe_int(current_value)

    if saved_number <= 0 or current_number <= 0:
        return False

    allowed_difference = max(saved_number * MAX_SIZE_DIFFERENCE_RATIO, 1)
    return abs(saved_number - current_number) <= allowed_difference


def _frame(window):
    frame = window.get("frame")
    if isinstance(frame, dict):
        return frame

    return {}


def _confidence(score):
    if score >= HIGH_CONFIDENCE_SCORE:
        return "alta"

    if score >= MEDIUM_CONFIDENCE_SCORE:
        return "média"

    if score >= LOW_CONFIDENCE_SCORE:
        return "baixa"

    return "insuficiente"


def _useful_app_id(value):
    text = _useful_value(value)
    if text.startswith("window:"):
        return ""

    return text


def _useful_value(value):
    text = normalize_text(value)
    if not text or text == "desconhecido":
        return ""

    return text


def normalize_text(value):
    return _collapse_spaces(_text(value)).casefold()


def _collapse_spaces(value):
    return re.sub(r"\s+", " ", value).strip()


def _text(value):
    return str(value or "").strip()


def _safe_int(value, fallback=-1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
