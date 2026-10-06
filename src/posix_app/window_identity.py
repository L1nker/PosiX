"""Identificação complementar de janelas por metadados do GNOME e /proc."""

import os


KNOWN_APPS = [
    (("brave", "brave-browser"), "Brave"),
    (("firefox",), "Firefox"),
    (("google-chrome", "chrome"), "Google Chrome"),
    (("chromium", "chromium-browser"), "Chromium"),
    (("telegram-desktop", "telegram"), "Telegram"),
    (("discord",), "Discord"),
    (("code", "code-oss", "visual-studio-code"), "VS Code"),
    (("cursor",), "Cursor"),
    (("spotify",), "Spotify"),
    (("slack",), "Slack"),
    (("obsidian",), "Obsidian"),
    (("gnome-terminal",), "Terminal"),
    (("gnome-text-editor",), "Editor de Texto"),
    (("nautilus",), "Arquivos"),
    (("vlc",), "VLC"),
    (("gimp",), "GIMP"),
    (("soffice.bin", "libreoffice"), "LibreOffice"),
    (("gnome-calculator", "calculator"), "Calculadora"),
    (("gnome-system-monitor",), "Monitor do Sistema"),
]


def resolve_application(window):
    """Resolve o aplicativo preservando identificações úteis do GNOME."""
    gnome_label = gnome_app_label(window)
    useful_gnome = useful_gnome_label(window)

    if not needs_process_complement(window):
        return {
            "gnome": gnome_label,
            "resolved": useful_gnome or gnome_label,
            "origin": "GNOME",
            "confidence": "alta",
        }

    process_info = read_process_info(safe_int(window.get("pid"), -1))
    resolved, origin, confidence = suggest_application(process_info)

    if useful_gnome:
        return {
            "gnome": gnome_label,
            "resolved": useful_gnome,
            "origin": "GNOME",
            "confidence": "alta",
        }

    return {
        "gnome": gnome_label,
        "resolved": resolved,
        "origin": origin,
        "confidence": confidence,
    }


def gnome_app_label(window):
    return (
        window.get("appName")
        or window.get("appId")
        or window.get("wmClass")
        or "Desconhecido"
    )


def is_useful_gnome_value(value):
    text = str(value or "").strip()
    return bool(text) and text.lower() != "desconhecido"


def is_useful_app_id(value):
    text = str(value or "").strip()
    return is_useful_gnome_value(text) and not text.startswith("window:")


def useful_gnome_label(window):
    app_name = window.get("appName")
    app_id = window.get("appId")
    wm_class = window.get("wmClass")

    if is_useful_gnome_value(app_name):
        return app_name

    if is_useful_app_id(app_id):
        return app_id

    if is_useful_gnome_value(wm_class):
        return wm_class

    return ""


def needs_process_complement(window):
    app_name = window.get("appName") or ""
    app_id = window.get("appId") or ""
    wm_class = window.get("wmClass") or ""
    wm_class_instance = window.get("wmClassInstance") or ""

    return (
        not app_name
        or app_name == "Desconhecido"
        or not app_id
        or app_id.startswith("window:")
        or (not wm_class and not wm_class_instance)
    )


def read_process_info(pid):
    if pid <= 0:
        return empty_process_info()

    proc_dir = f"/proc/{pid}"
    comm = read_text_file(f"{proc_dir}/comm")
    status = parse_status(read_text_file(f"{proc_dir}/status"))
    cmdline = parse_cmdline(read_bytes_file(f"{proc_dir}/cmdline"))
    executable = read_symlink(f"{proc_dir}/exe")
    ppid = safe_int(status.get("PPid"), -1)
    parent_name = read_parent_process_name(ppid)

    return {
        "comm": comm,
        "statusName": status.get("Name", ""),
        "executable": executable,
        "executableBase": os.path.basename(executable) if executable else "",
        "cmdline": cmdline,
        "ppid": ppid,
        "parentName": parent_name,
    }


def read_parent_process_name(ppid):
    if ppid <= 0:
        return ""

    parent_comm = read_text_file(f"/proc/{ppid}/comm")
    if parent_comm:
        return parent_comm

    parent_status = parse_status(read_text_file(f"/proc/{ppid}/status"))
    return parent_status.get("Name", "")


def read_text_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as file:
            return file.read().strip()
    except FileNotFoundError:
        return ""
    except ProcessLookupError:
        return ""
    except PermissionError:
        return ""
    except OSError:
        return ""


def read_bytes_file(path):
    try:
        with open(path, "rb") as file:
            return file.read()
    except FileNotFoundError:
        return b""
    except ProcessLookupError:
        return b""
    except PermissionError:
        return b""
    except OSError:
        return b""


def read_symlink(path):
    try:
        return os.readlink(path)
    except FileNotFoundError:
        return ""
    except ProcessLookupError:
        return ""
    except PermissionError:
        return ""
    except OSError:
        return ""


def parse_status(status_text):
    fields = {}

    for line in status_text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()

    return fields


def parse_cmdline(cmdline_bytes):
    if not cmdline_bytes:
        return ""

    parts = [
        part.decode("utf-8", errors="replace")
        for part in cmdline_bytes.split(b"\0")
        if part
    ]
    return " ".join(parts)


def empty_process_info():
    return {
        "comm": "",
        "statusName": "",
        "executable": "",
        "executableBase": "",
        "cmdline": "",
        "ppid": -1,
        "parentName": "",
    }


def normalize(value):
    return str(value or "").lower()


def match_known_app(text):
    normalized = normalize(text)
    if not normalized:
        return None

    for aliases, app_name in KNOWN_APPS:
        for alias in aliases:
            if alias in normalized:
                return app_name

    return None


def suggest_application(process_info):
    executable_match = match_known_app(process_info["executableBase"])
    if executable_match:
        return executable_match, "Processo", "alta"

    for field_name in ("cmdline", "parentName"):
        match = match_known_app(process_info[field_name])
        if match:
            return match, "Processo", "média"

    for field_name in ("comm", "statusName"):
        match = match_known_app(process_info[field_name])
        if match:
            return match, "Processo", "baixa"

    return "Desconhecido", "Processo", "desconhecida"


def safe_int(value, fallback=-1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

