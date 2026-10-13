"""Persistência local de posições, regras e configurações do PosiX."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 3


class StorageError(Exception):
    """Erro ao acessar o armazenamento local do PosiX."""


DEFAULT_SETTINGS = {
    "tooltip_mode": "pos_size",  # 'pos_size', 'size', 'pos', 'none'
    "adjust_opposite_edge": "0",  # '0' ou '1'
    "compensate_frame_effects": "1",  # '0' ou '1'
    "global_hotkey": "Ctrl+Super+Z",
}


def save_window_position(
    window,
    application,
    name=None,
    preset_type="universal",
    group_name=None,
    dont_resize=False,
    dont_move=False,
):
    """Salva uma captura local da janela e retorna o ID criado."""
    if not isinstance(window, dict):
        raise StorageError("A janela informada não é um dicionário.")

    if not isinstance(application, dict):
        raise StorageError("A identificação da aplicação não é um dicionário.")

    try:
        database_path = get_database_path()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now(timezone.utc).isoformat()
        snapshot_json = json.dumps(
            {
                "window": window,
                "application": application,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            cursor = connection.execute(
                """
                INSERT INTO saved_positions (
                    name,
                    created_at,
                    stable_sequence,
                    application,
                    title,
                    app_id,
                    wm_class,
                    wm_class_instance,
                    pid,
                    monitor_index,
                    workspace_index,
                    global_x,
                    global_y,
                    relative_x,
                    relative_y,
                    width,
                    height,
                    snapshot_json,
                    preset_type,
                    group_name,
                    dont_resize,
                    dont_move,
                    sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name or _default_name(window, application),
                    created_at,
                    _text_or_none(window.get("stableSequence")),
                    _text_or_none(application.get("resolved")),
                    _text_or_none(window.get("title")),
                    _text_or_none(window.get("appId")),
                    _text_or_none(window.get("wmClass")),
                    _text_or_none(window.get("wmClassInstance")),
                    _int_or_none(window.get("pid")),
                    _int_or_none(window.get("monitorIndex")),
                    _int_or_none(window.get("workspaceIndex")),
                    None if dont_move else _int_or_none(_geometry(window, "frame").get("x")),
                    None if dont_move else _int_or_none(_geometry(window, "frame").get("y")),
                    None if dont_move else _int_or_none(_geometry(window, "relative").get("x")),
                    None if dont_move else _int_or_none(_geometry(window, "relative").get("y")),
                    None if dont_resize else _int_or_none(_geometry(window, "frame").get("width")),
                    None if dont_resize else _int_or_none(_geometry(window, "frame").get("height")),
                    snapshot_json,
                    preset_type or "universal",
                    _text_or_none(group_name),
                    1 if dont_resize else 0,
                    1 if dont_move else 0,
                    0,
                ),
            )
            new_id = cursor.lastrowid
            _sync_cache_files()
            return new_id
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao salvar posição: {error}") from error
    except OSError as error:
        raise StorageError(f"Erro de sistema ao salvar posição: {error}") from error


def list_saved_positions():
    """Retorna as posições salvas ordenadas pela ordem de exibição."""
    database_path = get_database_path()

    if not database_path.exists():
        return []

    try:
        with sqlite3.connect(database_path) as connection:
            connection.row_factory = sqlite3.Row
            _ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    created_at,
                    stable_sequence,
                    application,
                    title,
                    app_id,
                    wm_class,
                    wm_class_instance,
                    pid,
                    monitor_index,
                    workspace_index,
                    global_x,
                    global_y,
                    relative_x,
                    relative_y,
                    width,
                    height,
                    snapshot_json,
                    preset_type,
                    group_name,
                    dont_resize,
                    dont_move,
                    sort_order
                FROM saved_positions
                ORDER BY sort_order ASC, id DESC
                """
            ).fetchall()
            results = [dict(row) for row in rows]
            _sync_cache_files(positions=results)
            return results
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao listar posições: {error}") from error


def list_groups():
    """Retorna a lista de nomes de grupos/pastas customizados cadastrados."""
    database_path = get_database_path()
    if not database_path.exists():
        return []

    try:
        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT DISTINCT group_name
                FROM saved_positions
                WHERE group_name IS NOT NULL AND TRIM(group_name) != ''
                ORDER BY group_name COLLATE NOCASE ASC
                """
            ).fetchall()
            return [r[0] for r in rows if r[0]]
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao listar grupos: {error}") from error


def rename_group(old_name, new_name):
    """Renomeia um grupo/pasta em todas as posições associadas."""
    clean_old = _clean_text(old_name)
    clean_new = _clean_text(new_name)
    if not clean_old or not clean_new:
        raise StorageError("Os nomes dos grupos não podem ser vazios.")

    try:
        database_path = get_database_path()
        if not database_path.exists():
            return False

        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            cursor = connection.execute(
                "UPDATE saved_positions SET group_name = ? WHERE group_name = ?",
                (clean_new, clean_old),
            )
            connection.commit()
            updated = cursor.rowcount > 0
            if updated:
                _sync_cache_files()
            return updated
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao renomear grupo: {error}") from error


def delete_group(group_name, remove_items=False):
    """Exclui um grupo. Se remove_items for False, move os itens para a raiz."""
    clean_name = _clean_text(group_name)
    if not clean_name:
        return False

    try:
        database_path = get_database_path()
        if not database_path.exists():
            return False

        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            if remove_items:
                # Remove regras dependentes primeiro
                connection.execute(
                    "DELETE FROM window_rules WHERE position_id IN (SELECT id FROM saved_positions WHERE group_name = ?)",
                    (clean_name,),
                )
                cursor = connection.execute(
                    "DELETE FROM saved_positions WHERE group_name = ?",
                    (clean_name,),
                )
            else:
                cursor = connection.execute(
                    "UPDATE saved_positions SET group_name = NULL WHERE group_name = ?",
                    (clean_name,),
                )
            connection.commit()
            affected = cursor.rowcount > 0
            if affected:
                _sync_cache_files()
            return affected
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao excluir grupo: {error}") from error


def reorder_saved_position(position_id, direction="up"):
    """Move uma posição para cima ou para baixo na ordem de exibição."""
    val_id = _validate_position_id(position_id)
    try:
        database_path = get_database_path()
        if not database_path.exists():
            return False

        with sqlite3.connect(database_path) as connection:
            connection.row_factory = sqlite3.Row
            _ensure_schema(connection)
            items = connection.execute(
                "SELECT id, sort_order FROM saved_positions ORDER BY sort_order ASC, id DESC"
            ).fetchall()
            ids = [r["id"] for r in items]
            if val_id not in ids:
                return False

            idx = ids.index(val_id)
            if direction == "up" and idx > 0:
                swap_idx = idx - 1
            elif direction == "down" and idx < len(ids) - 1:
                swap_idx = idx + 1
            else:
                return False

            ids[idx], ids[swap_idx] = ids[swap_idx], ids[idx]
            for order, item_id in enumerate(ids):
                connection.execute(
                    "UPDATE saved_positions SET sort_order = ? WHERE id = ?",
                    (order, item_id),
                )
            connection.commit()
            _sync_cache_files()
            return True
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao reordenar posição: {error}") from error


def get_setting(key, default=None):
    """Recupera uma configuração persistida do aplicativo."""
    database_path = get_database_path()
    if not database_path.exists():
        return DEFAULT_SETTINGS.get(key, default)

    try:
        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            row = connection.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
            if row:
                return row[0]
            return DEFAULT_SETTINGS.get(key, default)
    except sqlite3.Error:
        return DEFAULT_SETTINGS.get(key, default)


def set_setting(key, value):
    """Define e persiste uma configuração do aplicativo."""
    database_path = get_database_path()
    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            connection.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(key), str(value)),
            )
            connection.commit()
            _sync_cache_files()
            return True
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao salvar configuração: {error}") from error


def get_all_settings():
    """Retorna um dicionário com todas as configurações ativas."""
    settings = dict(DEFAULT_SETTINGS)
    database_path = get_database_path()
    if not database_path.exists():
        return settings

    try:
        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            rows = connection.execute("SELECT key, value FROM app_settings").fetchall()
            for k, v in rows:
                settings[k] = v
            return settings
    except sqlite3.Error:
        return settings


def _sync_cache_files(positions=None, rules=None):
    """Sincroniza presets.json para consumo instantâneo pela extensão GNOME Shell."""
    try:
        db_path = get_database_path()
        if positions is None:
            if not db_path.exists():
                positions = []
            else:
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    _ensure_schema(conn)
                    rows = conn.execute("SELECT * FROM saved_positions ORDER BY sort_order ASC, id DESC").fetchall()
                    positions = [dict(r) for r in rows]

        if rules is None:
            if not db_path.exists():
                rules = []
            else:
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    _ensure_schema(conn)
                    rows = conn.execute(
                        """
                        SELECT r.*, p.name AS position_name, p.width, p.height, p.global_x, p.global_y,
                               p.monitor_index, p.dont_resize, p.dont_move
                        FROM window_rules r
                        JOIN saved_positions p ON r.position_id = p.id
                        ORDER BY r.id DESC
                        """
                    ).fetchall()
                    rules = [dict(r) for r in rows]

        cache_path = db_path.parent / "presets.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        presets_data = [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "group": p.get("group_name") or None,
                "width": p.get("width"),
                "height": p.get("height"),
                "global_x": p.get("global_x"),
                "global_y": p.get("global_y"),
                "monitor_index": p.get("monitor_index", 0),
                "dont_resize": bool(p.get("dont_resize")),
                "dont_move": bool(p.get("dont_move")),
                "preset_type": p.get("preset_type") or "universal",
                "application": p.get("application") or "",
                "sort_order": p.get("sort_order", 0),
            }
            for p in positions
        ]

        rules_data = [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "position_id": r.get("position_id"),
                "position_name": r.get("position_name"),
                "match_title": r.get("match_title") or "",
                "match_app": r.get("match_app") or "",
                "is_active": bool(r.get("is_active", 1)),
                "width": r.get("width"),
                "height": r.get("height"),
                "global_x": r.get("global_x"),
                "global_y": r.get("global_y"),
                "monitor_index": r.get("monitor_index", 0),
                "dont_resize": bool(r.get("dont_resize")),
                "dont_move": bool(r.get("dont_move")),
            }
            for r in rules
        ]

        # Extrai grupos únicos
        groups = sorted(list({p["group"] for p in presets_data if p["group"]}))

        payload = {
            "version": 3,
            "settings": get_all_settings(),
            "groups": groups,
            "presets": presets_data,
            "rules": rules_data,
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _sync_presets_json_cache(positions=None):
    """Compatibilidade com chamadas existentes de sincronização."""
    _sync_cache_files(positions=positions)


def delete_saved_position(position_id):
    """Remove uma posição salva pelo ID e informa se uma linha foi excluída."""
    validated_id = _validate_position_id(position_id)

    try:
        database_path = get_database_path()
        if not database_path.exists():
            return False

        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            connection.execute("DELETE FROM window_rules WHERE position_id = ?", (validated_id,))
            cursor = connection.execute(
                "DELETE FROM saved_positions WHERE id = ?",
                (validated_id,),
            )
            connection.commit()
            deleted = cursor.rowcount == 1
            if deleted:
                _sync_cache_files()
            return deleted
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao excluir posição: {error}") from error


def create_window_rule(name, position_id, match_title=None, match_app=None, is_active=True):
    """Cria uma nova regra vinculando critérios de janela a uma posição salva."""
    clean_name = _clean_text(name)
    if not clean_name:
        raise StorageError("O nome da regra não pode ser vazio.")

    val_pos_id = _validate_position_id(position_id)
    clean_title = _clean_text(match_title)
    clean_app = _clean_text(match_app)

    if not clean_title and not clean_app:
        raise StorageError("A regra precisa de ao menos um critério (título ou aplicativo).")

    created_at = datetime.now(timezone.utc).isoformat()
    active_int = 1 if is_active else 0

    try:
        database_path = get_database_path()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            pos = connection.execute("SELECT id FROM saved_positions WHERE id = ?", (val_pos_id,)).fetchone()
            if not pos:
                raise StorageError(f"Posição com ID {val_pos_id} não existe.")

            cursor = connection.execute(
                """
                INSERT INTO window_rules (name, position_id, match_title, match_app, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clean_name, val_pos_id, clean_title or None, clean_app or None, active_int, created_at),
            )
            connection.commit()
            rule_id = cursor.lastrowid
            _sync_cache_files()
            return rule_id
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao criar regra de janela: {error}") from error


def list_window_rules():
    """Lista todas as regras cadastradas com informações da posição associada."""
    database_path = get_database_path()
    if not database_path.exists():
        return []

    try:
        with sqlite3.connect(database_path) as connection:
            connection.row_factory = sqlite3.Row
            _ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT
                    r.id,
                    r.name,
                    r.position_id,
                    r.match_title,
                    r.match_app,
                    r.is_active,
                    r.created_at,
                    p.name AS position_name,
                    p.width,
                    p.height,
                    p.global_x,
                    p.global_y,
                    p.monitor_index,
                    p.dont_resize,
                    p.dont_move,
                    p.group_name
                FROM window_rules r
                JOIN saved_positions p ON r.position_id = p.id
                ORDER BY r.id DESC
                """
            ).fetchall()
            results = [dict(row) for row in rows]
            _sync_cache_files(rules=results)
            return results
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao listar regras de janela: {error}") from error


def update_window_rule(rule_id, name, position_id, match_title=None, match_app=None, is_active=True):
    """Atualiza as informações de uma regra de janela existente."""
    val_rule_id = _validate_position_id(rule_id)
    clean_name = _clean_text(name)
    if not clean_name:
        raise StorageError("O nome da regra não pode ser vazio.")

    val_pos_id = _validate_position_id(position_id)
    clean_title = _clean_text(match_title)
    clean_app = _clean_text(match_app)

    if not clean_title and not clean_app:
        raise StorageError("A regra precisa de ao menos um critério (título ou aplicativo).")

    active_int = 1 if is_active else 0

    try:
        database_path = get_database_path()
        if not database_path.exists():
            return False

        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            pos = connection.execute("SELECT id FROM saved_positions WHERE id = ?", (val_pos_id,)).fetchone()
            if not pos:
                raise StorageError(f"Posição com ID {val_pos_id} não existe.")

            cursor = connection.execute(
                """
                UPDATE window_rules
                SET name = ?, position_id = ?, match_title = ?, match_app = ?, is_active = ?
                WHERE id = ?
                """,
                (clean_name, val_pos_id, clean_title or None, clean_app or None, active_int, val_rule_id),
            )
            connection.commit()
            updated = cursor.rowcount == 1
            if updated:
                _sync_cache_files()
            return updated
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao atualizar regra de janela: {error}") from error


def toggle_window_rule(rule_id, is_active=None):
    """Ativa ou desativa uma regra de janela."""
    val_rule_id = _validate_position_id(rule_id)

    try:
        database_path = get_database_path()
        if not database_path.exists():
            return False

        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            if is_active is None:
                row = connection.execute("SELECT is_active FROM window_rules WHERE id = ?", (val_rule_id,)).fetchone()
                if not row:
                    return False
                new_state = 0 if row[0] == 1 else 1
            else:
                new_state = 1 if is_active else 0

            cursor = connection.execute(
                "UPDATE window_rules SET is_active = ? WHERE id = ?",
                (new_state, val_rule_id),
            )
            connection.commit()
            updated = cursor.rowcount == 1
            if updated:
                _sync_cache_files()
            return updated
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao alternar estado da regra: {error}") from error


def delete_window_rule(rule_id):
    """Remove uma regra de janela pelo ID."""
    val_rule_id = _validate_position_id(rule_id)

    try:
        database_path = get_database_path()
        if not database_path.exists():
            return False

        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            cursor = connection.execute(
                "DELETE FROM window_rules WHERE id = ?",
                (val_rule_id,),
            )
            connection.commit()
            deleted = cursor.rowcount == 1
            if deleted:
                _sync_cache_files()
            return deleted
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao excluir regra de janela: {error}") from error


def rename_saved_position(position_id, new_name):
    """Altera o nome de uma posição salva pelo ID."""
    validated_id = _validate_position_id(position_id)
    clean_name = _clean_text(new_name)
    if not clean_name:
        raise StorageError("O novo nome da posição não pode ser vazio.")

    try:
        database_path = get_database_path()
        if not database_path.exists():
            return False

        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            cursor = connection.execute(
                "UPDATE saved_positions SET name = ? WHERE id = ?",
                (clean_name, validated_id),
            )
            connection.commit()
            renamed = cursor.rowcount == 1
            if renamed:
                _sync_cache_files()
            return renamed
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao renomear posição: {error}") from error


def update_saved_position_geometry(position_id, window, application):
    """Atualiza a geometria e snapshot de uma posição salva pelo ID mantendo o nome."""
    validated_id = _validate_position_id(position_id)

    if not isinstance(window, dict):
        raise StorageError("A janela informada não é um dicionário.")

    if not isinstance(application, dict):
        raise StorageError("A identificação da aplicação não é um dicionário.")

    try:
        database_path = get_database_path()
        if not database_path.exists():
            return False

        snapshot_json = json.dumps(
            {
                "window": window,
                "application": application,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            cursor = connection.execute(
                """
                UPDATE saved_positions
                SET
                    stable_sequence = ?,
                    application = ?,
                    title = ?,
                    app_id = ?,
                    wm_class = ?,
                    wm_class_instance = ?,
                    pid = ?,
                    monitor_index = ?,
                    workspace_index = ?,
                    global_x = ?,
                    global_y = ?,
                    relative_x = ?,
                    relative_y = ?,
                    width = ?,
                    height = ?,
                    snapshot_json = ?
                WHERE id = ?
                """,
                (
                    _text_or_none(window.get("stableSequence")),
                    _text_or_none(application.get("resolved")),
                    _text_or_none(window.get("title")),
                    _text_or_none(window.get("appId")),
                    _text_or_none(window.get("wmClass")),
                    _text_or_none(window.get("wmClassInstance")),
                    _int_or_none(window.get("pid")),
                    _int_or_none(window.get("monitorIndex")),
                    _int_or_none(window.get("workspaceIndex")),
                    _int_or_none(_geometry(window, "frame").get("x")),
                    _int_or_none(_geometry(window, "frame").get("y")),
                    _int_or_none(_geometry(window, "relative").get("x")),
                    _int_or_none(_geometry(window, "relative").get("y")),
                    _int_or_none(_geometry(window, "frame").get("width")),
                    _int_or_none(_geometry(window, "frame").get("height")),
                    snapshot_json,
                    validated_id,
                ),
            )
            connection.commit()
            updated = cursor.rowcount == 1
            if updated:
                _sync_cache_files()
            return updated
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao atualizar geometria da posição: {error}") from error


def create_manual_preset(
    name,
    width=None,
    height=None,
    global_x=None,
    global_y=None,
    monitor_index=0,
    preset_type="universal",
    application_name=None,
    group_name=None,
    dont_resize=False,
    dont_move=False,
):
    """Cria um preset com dimensões ou posicionamento em pixels."""
    clean_name = _clean_text(name)
    if not clean_name:
        raise StorageError("O nome do preset não pode ser vazio.")

    width_val = None
    height_val = None
    if not dont_resize:
        width_val = _int_or_none(width)
        height_val = _int_or_none(height)
        if not width_val or width_val <= 0 or not height_val or height_val <= 0:
            raise StorageError("Largura e altura devem ser números inteiros maiores que zero.")

    created_at = datetime.now(timezone.utc).isoformat()
    clean_type = "universal"
    clean_app = _clean_text(application_name)
    clean_group = _text_or_none(group_name)

    snapshot = {
        "window": {
            "title": clean_name,
            "monitorIndex": monitor_index or 0,
            "frame": {
                "x": None if dont_move else (global_x if global_x is not None else 0),
                "y": None if dont_move else (global_y if global_y is not None else 0),
                "width": width_val,
                "height": height_val,
            },
            "relative": {
                "x": None if dont_move else (global_x if global_x is not None else 0),
                "y": None if dont_move else (global_y if global_y is not None else 0),
            },
        },
        "application": {
            "resolved": clean_app or "Universal",
        },
    }
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)

    try:
        database_path = get_database_path()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            cursor = connection.execute(
                """
                INSERT INTO saved_positions (
                    name,
                    created_at,
                    application,
                    title,
                    monitor_index,
                    global_x,
                    global_y,
                    relative_x,
                    relative_y,
                    width,
                    height,
                    snapshot_json,
                    preset_type,
                    group_name,
                    dont_resize,
                    dont_move,
                    sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_name,
                    created_at,
                    clean_app or None,
                    clean_name,
                    monitor_index or 0,
                    None if dont_move else _int_or_none(global_x),
                    None if dont_move else _int_or_none(global_y),
                    None if dont_move else _int_or_none(global_x),
                    None if dont_move else _int_or_none(global_y),
                    width_val,
                    height_val,
                    snapshot_json,
                    clean_type,
                    clean_group,
                    1 if dont_resize else 0,
                    1 if dont_move else 0,
                    0,
                ),
            )
            connection.commit()
            new_id = cursor.lastrowid
            _sync_cache_files()
            return new_id
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao criar preset manual: {error}") from error


def update_manual_preset(
    position_id,
    name,
    width=None,
    height=None,
    global_x=None,
    global_y=None,
    monitor_index=0,
    preset_type="universal",
    application_name=None,
    group_name=None,
    dont_resize=False,
    dont_move=False,
):
    """Atualiza as informações manuais de um preset."""
    validated_id = _validate_position_id(position_id)
    clean_name = _clean_text(name)
    if not clean_name:
        raise StorageError("O nome do preset não pode ser vazio.")

    width_val = None
    height_val = None
    if not dont_resize:
        width_val = _int_or_none(width)
        height_val = _int_or_none(height)
        if not width_val or width_val <= 0 or not height_val or height_val <= 0:
            raise StorageError("Largura e altura devem ser números inteiros maiores que zero.")

    clean_type = "universal"
    clean_app = _clean_text(application_name)
    clean_group = _text_or_none(group_name)

    snapshot = {
        "window": {
            "title": clean_name,
            "monitorIndex": monitor_index or 0,
            "frame": {
                "x": None if dont_move else (global_x if global_x is not None else 0),
                "y": None if dont_move else (global_y if global_y is not None else 0),
                "width": width_val,
                "height": height_val,
            },
            "relative": {
                "x": None if dont_move else (global_x if global_x is not None else 0),
                "y": None if dont_move else (global_y if global_y is not None else 0),
            },
        },
        "application": {
            "resolved": clean_app or "Universal",
        },
    }
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)

    try:
        database_path = get_database_path()
        if not database_path.exists():
            return False

        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            cursor = connection.execute(
                """
                UPDATE saved_positions
                SET
                    name = ?,
                    application = ?,
                    title = ?,
                    monitor_index = ?,
                    global_x = ?,
                    global_y = ?,
                    relative_x = ?,
                    relative_y = ?,
                    width = ?,
                    height = ?,
                    snapshot_json = ?,
                    preset_type = ?,
                    group_name = ?,
                    dont_resize = ?,
                    dont_move = ?
                WHERE id = ?
                """,
                (
                    clean_name,
                    clean_app or None,
                    clean_name,
                    monitor_index or 0,
                    None if dont_move else _int_or_none(global_x),
                    None if dont_move else _int_or_none(global_y),
                    None if dont_move else _int_or_none(global_x),
                    None if dont_move else _int_or_none(global_y),
                    width_val,
                    height_val,
                    snapshot_json,
                    clean_type,
                    clean_group,
                    1 if dont_resize else 0,
                    1 if dont_move else 0,
                    validated_id,
                ),
            )
            connection.commit()
            updated = cursor.rowcount == 1
            if updated:
                _sync_cache_files()
            return updated
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao atualizar preset manual: {error}") from error


def export_configuration_json():
    """Exporta todas as posições, regras e configurações para uma string JSON formatada."""
    positions = list_saved_positions()
    rules = list_window_rules()
    settings = get_all_settings()

    data = {
        "version": 3,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "settings": settings,
        "positions": positions,
        "rules": rules,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def import_configuration_json(json_content):
    """Importa posições, regras e configurações a partir de uma string JSON."""
    if not json_content:
        raise StorageError("O conteúdo JSON está vazio.")

    try:
        data = json.loads(json_content)
    except Exception as err:
        raise StorageError(f"JSON inválido: {err}") from err

    if not isinstance(data, dict):
        raise StorageError("O formato do arquivo JSON de backup é inválido.")

    # Importa configurações
    settings = data.get("settings", {})
    if isinstance(settings, dict):
        for k, v in settings.items():
            set_setting(k, v)

    positions = data.get("positions", [])
    if isinstance(positions, list):
        for p in positions:
            name = p.get("name")
            if not name:
                continue
            create_manual_preset(
                name=name,
                width=p.get("width"),
                height=p.get("height"),
                global_x=p.get("global_x"),
                global_y=p.get("global_y"),
                monitor_index=p.get("monitor_index", 0),
                group_name=p.get("group_name"),
                dont_resize=bool(p.get("dont_resize")),
                dont_move=bool(p.get("dont_move")),
            )
    _sync_cache_files()
    return True


def seed_default_presets_if_empty():
    """Gera presets clássicos iniciais caso a base esteja vazia."""
    database_path = get_database_path()
    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            _ensure_schema(connection)
            count = connection.execute("SELECT count(*) FROM saved_positions").fetchone()[0]
            if count == 0:
                defaults = [
                    # Itens avulsos populares
                    ("HD 720p (16:9)", 1280, 720, None),
                    ("Full HD 1080p (16:9)", 1920, 1080, None),
                    # Grupo 4:3
                    ("640 × 480 (VGA)", 640, 480, "4:3"),
                    ("800 × 600 (SVGA)", 800, 600, "4:3"),
                    ("1024 × 768 (XGA)", 1024, 768, "4:3"),
                    # Grupo YouTube
                    ("YouTube 480p", 854, 480, "YouTube"),
                    ("YouTube 720p", 1280, 720, "YouTube"),
                    ("YouTube 1080p", 1920, 1080, "YouTube"),
                ]
                for name, width, height, grp in defaults:
                    create_manual_preset(name, width, height, group_name=grp)
    except Exception:
        pass


def get_database_path():
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        base_dir = Path(data_home).expanduser()
    else:
        base_dir = Path.home() / ".local" / "share"

    return base_dir / "posix" / "posix.db"


def _ensure_schema(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            stable_sequence TEXT,
            application TEXT,
            title TEXT,
            app_id TEXT,
            wm_class TEXT,
            wm_class_instance TEXT,
            pid INTEGER,
            monitor_index INTEGER,
            workspace_index INTEGER,
            global_x INTEGER,
            global_y INTEGER,
            relative_x INTEGER,
            relative_y INTEGER,
            width INTEGER,
            height INTEGER,
            snapshot_json TEXT NOT NULL,
            preset_type TEXT DEFAULT 'universal',
            group_name TEXT DEFAULT NULL,
            dont_resize INTEGER DEFAULT 0,
            dont_move INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0
        )
        """
    )
    columns = [row[1] for row in connection.execute("PRAGMA table_info(saved_positions)").fetchall()]
    if "preset_type" not in columns:
        connection.execute("ALTER TABLE saved_positions ADD COLUMN preset_type TEXT DEFAULT 'universal'")
    if "group_name" not in columns:
        connection.execute("ALTER TABLE saved_positions ADD COLUMN group_name TEXT DEFAULT NULL")
    if "dont_resize" not in columns:
        connection.execute("ALTER TABLE saved_positions ADD COLUMN dont_resize INTEGER DEFAULT 0")
    if "dont_move" not in columns:
        connection.execute("ALTER TABLE saved_positions ADD COLUMN dont_move INTEGER DEFAULT 0")
    if "sort_order" not in columns:
        connection.execute("ALTER TABLE saved_positions ADD COLUMN sort_order INTEGER DEFAULT 0")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS window_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            position_id INTEGER NOT NULL,
            match_title TEXT,
            match_app TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (position_id) REFERENCES saved_positions(id) ON DELETE CASCADE
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _default_name(window, application):
    app_name = _clean_text(application.get("resolved"))
    title = _clean_text(window.get("title"))

    if app_name and title:
        return f"{app_name} — {title}"

    return app_name or title or "Posição sem nome"


def _geometry(window, key):
    value = window.get(key)
    if isinstance(value, dict):
        return value

    return {}


def _clean_text(value):
    text = str(value or "").strip()
    return text


def _text_or_none(value):
    text = _clean_text(value)
    return text or None


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_position_id(position_id):
    if isinstance(position_id, bool) or not isinstance(position_id, int):
        raise StorageError("O ID da posição deve ser um inteiro positivo.")

    if position_id <= 0:
        raise StorageError("O ID da posição deve ser um inteiro positivo.")

    return position_id
