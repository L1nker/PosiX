"""Persistência local de posições capturadas pelo PosiX."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1


class StorageError(Exception):
    """Erro ao acessar o armazenamento local do PosiX."""


def save_window_position(window, application, name=None):
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
                    snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    _int_or_none(_geometry(window, "frame").get("x")),
                    _int_or_none(_geometry(window, "frame").get("y")),
                    _int_or_none(_geometry(window, "relative").get("x")),
                    _int_or_none(_geometry(window, "relative").get("y")),
                    _int_or_none(_geometry(window, "frame").get("width")),
                    _int_or_none(_geometry(window, "frame").get("height")),
                    snapshot_json,
                ),
            )
            return cursor.lastrowid
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao salvar posição: {error}") from error
    except OSError as error:
        raise StorageError(f"Erro de sistema ao salvar posição: {error}") from error


def list_saved_positions():
    """Retorna as posições salvas da mais recente para a mais antiga."""
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
                    snapshot_json
                FROM saved_positions
                ORDER BY id DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as error:
        raise StorageError(f"Erro SQLite ao listar posições: {error}") from error


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
            snapshot_json TEXT NOT NULL
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

