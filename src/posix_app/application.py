"""Interface gráfica inicial do PosiX."""

import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk, Pango

from posix_app.dbus_windows import (
    PosiXContractError,
    PosiXDBusError,
    fetch_windows,
    move_resize_window,
)
from posix_app.storage import StorageError, list_saved_positions, save_window_position
from posix_app.window_identity import resolve_application
from posix_app.window_matching import WindowMatchingError, find_best_window_match


APPLICATION_ID = "io.github.L1nker.PosiX.App"


class PosiXApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APPLICATION_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._window = None

    def do_activate(self):
        if self._window is None:
            self._window = MainWindow(self)

        self._window.present()
        self._window.refresh_windows()


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="PosiX by Linker")
        self.set_default_size(1100, 700)

        self._loading = False
        self._restoring = False
        self._records = []
        self._selected_record = None
        self._saved_positions = []
        self._selected_saved_position = None
        self._suggested_match = None
        self._status_after_refresh = None

        self._build_ui()
        self._load_saved_positions()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title="PosiX",
            subtitle="Gerenciador de posições de janelas",
        ))
        root.append(header)

        self._refresh_button = Gtk.Button(label="Atualizar")
        self._refresh_button.connect("clicked", self._on_refresh_clicked)
        header.pack_end(self._refresh_button)

        self._save_button = Gtk.Button(label="Salvar posição")
        self._save_button.set_sensitive(False)
        self._save_button.connect("clicked", self._on_save_clicked)
        header.pack_end(self._save_button)

        self._status_label = Gtk.Label(
            label="Carregando janelas...",
            xalign=0,
            margin_start=16,
            margin_end=16,
            margin_top=10,
            margin_bottom=10,
        )
        self._status_label.add_css_class("dim-label")
        root.append(self._status_label)

        paned = Gtk.Paned(
            orientation=Gtk.Orientation.HORIZONTAL,
            wide_handle=True,
            margin_start=12,
            margin_end=12,
            margin_bottom=12,
        )
        root.append(paned)

        list_scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            min_content_width=430,
        )
        list_scroller.set_vexpand(True)
        paned.set_start_child(list_scroller)
        paned.set_resize_start_child(True)
        paned.set_shrink_start_child(False)

        self._list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.connect("row-selected", self._on_row_selected)
        list_scroller.set_child(self._list_box)

        details_scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            min_content_width=450,
        )
        details_scroller.set_vexpand(True)
        paned.set_end_child(details_scroller)
        paned.set_resize_end_child(True)
        paned.set_shrink_end_child(False)

        self._details_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin_start=18,
            margin_end=18,
            margin_top=12,
            margin_bottom=18,
        )
        details_scroller.set_child(self._details_box)

        self._window_details_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
        )
        self._details_box.append(self._window_details_box)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(8)
        separator.set_margin_bottom(8)
        self._details_box.append(separator)

        self._build_restore_section()
        self._show_empty_details()

    def _build_restore_section(self):
        restore_title = Gtk.Label(label="Restaurar posição salva", xalign=0)
        restore_title.add_css_class("title-3")
        self._details_box.append(restore_title)

        self._saved_positions_model = Gtk.StringList.new(["Selecione uma posição salva"])
        self._saved_positions_dropdown = Gtk.DropDown.new(self._saved_positions_model, None)
        self._saved_positions_dropdown.set_selected(0)
        self._saved_positions_dropdown.connect(
            "notify::selected",
            self._on_saved_position_selected,
        )
        self._details_box.append(self._saved_positions_dropdown)

        self._saved_position_summary = Gtk.Label(
            label="Nenhuma posição salva",
            xalign=0,
            wrap=True,
        )
        self._saved_position_summary.add_css_class("dim-label")
        self._details_box.append(self._saved_position_summary)

        self._match_suggestion_label = Gtk.Label(
            label="Selecione uma posição salva para procurar a janela correspondente.",
            xalign=0,
            wrap=True,
        )
        self._match_suggestion_label.add_css_class("dim-label")
        self._details_box.append(self._match_suggestion_label)

        self._select_suggested_button = Gtk.Button(label="Selecionar janela sugerida")
        self._select_suggested_button.set_sensitive(False)
        self._select_suggested_button.connect("clicked", self._on_select_suggested_clicked)
        self._details_box.append(self._select_suggested_button)

        self._restore_button = Gtk.Button(label="Restaurar posição")
        self._restore_button.set_sensitive(False)
        self._restore_button.connect("clicked", self._on_restore_clicked)
        self._details_box.append(self._restore_button)

    def _on_refresh_clicked(self, _button):
        self.refresh_windows()

    def _on_save_clicked(self, _button):
        if self._selected_record is None or self._loading:
            return

        try:
            saved_id = save_window_position(
                self._selected_record["window"],
                self._selected_record["application"],
            )
        except StorageError as error:
            self._status_label.set_text(f"Não foi possível salvar a posição: {error}")
            return

        self._load_saved_positions(select_id=saved_id)
        self._status_label.set_text(f"Posição salva com sucesso — ID {saved_id}")

    def _on_restore_clicked(self, _button):
        if not self._can_restore():
            return

        self._show_restore_confirmation()

    def refresh_windows(self):
        if self._loading:
            return

        self._loading = True
        self._selected_record = None
        self._clear_match_suggestion()
        self._list_box.unselect_all()
        self._update_action_sensitivity()
        self._status_label.set_text("Carregando janelas...")
        self._update_match_suggestion()
        self._show_empty_details()

        thread = threading.Thread(target=self._load_windows_worker, daemon=True)
        thread.start()

    def _load_windows_worker(self):
        try:
            windows = fetch_windows()
            records = [
                {
                    "window": window,
                    "application": resolve_application(window),
                }
                for window in windows
            ]
            GLib.idle_add(self._finish_loading, records, None)
        except (PosiXDBusError, PosiXContractError) as error:
            GLib.idle_add(self._finish_loading, None, str(error))
        except Exception as error:
            GLib.idle_add(
                self._finish_loading,
                None,
                f"Erro inesperado ao carregar janelas: {error}",
            )

    def _finish_loading(self, records, error):
        self._loading = False
        self._update_action_sensitivity()

        if error:
            self._status_label.set_text(error)
            return GLib.SOURCE_REMOVE

        self._records = records
        self._populate_window_list(records)
        self._list_box.unselect_all()
        self._selected_record = None
        self._clear_match_suggestion()
        self._update_match_suggestion()
        self._update_action_sensitivity()
        if self._status_after_refresh:
            self._status_label.set_text(self._status_after_refresh)
            self._status_after_refresh = None
        else:
            self._status_label.set_text(f"{len(records)} janelas encontradas")
        self._show_empty_details()
        return GLib.SOURCE_REMOVE

    def _populate_window_list(self, records):
        self._clear_list()

        for record in records:
            row = Gtk.ListBoxRow()
            row.window_data = record["window"]
            row.application_info = record["application"]
            row.set_child(self._create_window_row(record))
            self._list_box.append(row)

    def _create_window_row(self, record):
        window = record["window"]
        app = record["application"]
        frame = window["frame"]
        relative = window["relative"]

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            margin_start=12,
            margin_end=12,
            margin_top=10,
            margin_bottom=10,
        )

        app_label = Gtk.Label(label=app["resolved"], xalign=0)
        app_label.add_css_class("heading")
        app_label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(app_label)

        title_label = Gtk.Label(label=window.get("title", ""), xalign=0)
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(title_label)

        geometry_label = Gtk.Label(
            label=(
                f"Monitor {window.get('monitorIndex', -1)} · "
                f"X {relative.get('x', 0)} · Y {relative.get('y', 0)} · "
                f"{frame.get('width', 0)} × {frame.get('height', 0)}"
            ),
            xalign=0,
        )
        geometry_label.add_css_class("dim-label")
        box.append(geometry_label)

        return box

    def _on_row_selected(self, _list_box, row):
        if row is None:
            self._selected_record = None
            self._update_action_sensitivity()
            self._show_empty_details()
            return

        self._selected_record = {
            "window": row.window_data,
            "application": row.application_info,
        }
        self._update_action_sensitivity()
        self._show_details(row.window_data, row.application_info)

    def _show_empty_details(self):
        self._clear_details()

        title = Gtk.Label(label="Selecione uma janela", xalign=0)
        title.add_css_class("title-3")
        self._window_details_box.append(title)

        text = Gtk.Label(
            label="Os detalhes da janela selecionada aparecerão aqui.",
            xalign=0,
            wrap=True,
        )
        text.add_css_class("dim-label")
        self._window_details_box.append(text)

    def _show_details(self, window, app):
        self._clear_details()

        title = Gtk.Label(label="Detalhes da janela", xalign=0)
        title.add_css_class("title-3")
        self._window_details_box.append(title)

        frame = window.get("frame", {})
        relative = window.get("relative", {})
        state = window.get("state", {})

        rows = [
            ("Sequência", window.get("stableSequence", "")),
            ("Aplicativo GNOME", app.get("gnome", "")),
            ("Aplicativo resolvido", app.get("resolved", "")),
            ("Origem", app.get("origin", "")),
            ("Confiança", app.get("confidence", "")),
            ("Título completo", window.get("title", "")),
            ("App ID", window.get("appId", "")),
            ("WM_CLASS", window.get("wmClass", "")),
            ("Instância", window.get("wmClassInstance", "")),
            ("PID", window.get("pid", -1)),
            ("Monitor", window.get("monitorIndex", -1)),
            ("Workspace", window.get("workspaceIndex", -1)),
            ("Posição global", f"X={frame.get('x', 0)} Y={frame.get('y', 0)}"),
            ("Posição relativa", f"X={relative.get('x', 0)} Y={relative.get('y', 0)}"),
            ("Dimensão", f"{frame.get('width', 0)} × {frame.get('height', 0)}"),
            ("Maximizada", self._format_bool(state.get("maximized", False))),
            ("Tela cheia", self._format_bool(state.get("fullscreen", False))),
            ("Minimizada", self._format_bool(state.get("minimized", False))),
            ("Permite mover", self._format_bool(state.get("allowsMove", False))),
            ("Permite redimensionar", self._format_bool(state.get("allowsResize", False))),
            ("Skip taskbar", self._format_bool(state.get("skipTaskbar", False))),
        ]

        grid = Gtk.Grid(column_spacing=16, row_spacing=8)
        self._window_details_box.append(grid)

        for index, (label, value) in enumerate(rows):
            key_label = Gtk.Label(label=f"{label}:", xalign=0)
            key_label.add_css_class("dim-label")
            value_label = Gtk.Label(label=str(value), xalign=0, wrap=True, selectable=True)
            grid.attach(key_label, 0, index, 1, 1)
            grid.attach(value_label, 1, index, 1, 1)

    def _clear_list(self):
        child = self._list_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._list_box.remove(child)
            child = next_child

    def _clear_details(self):
        child = self._window_details_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._window_details_box.remove(child)
            child = next_child

    def _format_bool(self, value):
        return "Sim" if bool(value) else "Não"

    def _load_saved_positions(self, select_id=None):
        try:
            self._saved_positions = list_saved_positions()
        except StorageError as error:
            self._saved_positions = []
            self._selected_saved_position = None
            self._status_label.set_text(f"Erro ao carregar posições salvas: {error}")
            self._refresh_saved_positions_dropdown()
            return

        self._refresh_saved_positions_dropdown(select_id=select_id)

    def _refresh_saved_positions_dropdown(self, select_id=None):
        items = ["Selecione uma posição salva"]
        items.extend(
            f"ID {position.get('id')} — {position.get('name') or 'Posição sem nome'}"
            for position in self._saved_positions
        )
        self._saved_positions_model.splice(
            0,
            self._saved_positions_model.get_n_items(),
            items,
        )

        selected_index = 0
        if select_id is not None:
            for index, position in enumerate(self._saved_positions, start=1):
                if position.get("id") == select_id:
                    selected_index = index
                    break

        self._saved_positions_dropdown.set_selected(selected_index)
        self._set_selected_saved_position_by_index(selected_index)

        if not self._saved_positions:
            self._saved_position_summary.set_text("Nenhuma posição salva")
            self._saved_positions_dropdown.set_sensitive(False)
        else:
            self._saved_positions_dropdown.set_sensitive(not self._restoring)

        self._update_match_suggestion()
        self._update_action_sensitivity()

    def _on_saved_position_selected(self, dropdown, _param):
        self._set_selected_saved_position_by_index(dropdown.get_selected())
        self._update_match_suggestion()
        self._update_action_sensitivity()

    def _set_selected_saved_position_by_index(self, selected_index):
        if selected_index == 0 or selected_index > len(self._saved_positions):
            self._selected_saved_position = None
            if self._saved_positions:
                self._saved_position_summary.set_text("Selecione uma posição salva")
            else:
                self._saved_position_summary.set_text("Nenhuma posição salva")
            self._clear_match_suggestion()
            return

        self._selected_saved_position = self._saved_positions[selected_index - 1]
        self._saved_position_summary.set_text(
            self._format_saved_position_summary(self._selected_saved_position)
        )

    def _format_saved_position_summary(self, position):
        return (
            f"Monitor {position.get('monitor_index')} · "
            f"X global {position.get('global_x')} · "
            f"Y global {position.get('global_y')} · "
            f"{position.get('width')} × {position.get('height')}"
        )

    def _update_action_sensitivity(self):
        busy = self._loading or self._restoring
        self._refresh_button.set_sensitive(not busy)
        self._save_button.set_sensitive(self._selected_record is not None and not busy)
        self._restore_button.set_sensitive(self._can_restore())
        self._select_suggested_button.set_sensitive(self._can_select_suggested_window())
        self._saved_positions_dropdown.set_sensitive(
            bool(self._saved_positions) and not self._restoring
        )

    def _can_restore(self):
        return (
            self._selected_record is not None
            and self._selected_saved_position is not None
            and not self._loading
            and not self._restoring
            and self._has_valid_restore_target()
        )

    def _can_select_suggested_window(self):
        return (
            self._suggested_match is not None
            and self._selected_saved_position is not None
            and not self._loading
            and not self._restoring
        )

    def _has_valid_restore_target(self):
        if self._selected_record is None:
            return False

        sequence = str(self._selected_record["window"].get("stableSequence", "")).strip()
        if not sequence:
            return False

        position = self._selected_saved_position
        if position is None:
            return False

        return all(
            isinstance(position.get(key), int)
            for key in ("global_x", "global_y", "width", "height")
        ) and position["width"] > 0 and position["height"] > 0

    def _show_restore_confirmation(self):
        window = self._selected_record["window"]
        app = self._selected_record["application"]
        position = self._selected_saved_position
        frame = window.get("frame", {})
        body = "\n".join([
            f"Janela aberta: {app.get('resolved', '')} — {window.get('title', '')}",
            f"Posição salva: ID {position.get('id')} — {position.get('name') or ''}",
            (
                "Geometria atual: "
                f"X={frame.get('x', 0)} Y={frame.get('y', 0)} "
                f"{frame.get('width', 0)} × {frame.get('height', 0)}"
            ),
            (
                "Será aplicada: "
                f"X={position.get('global_x')} Y={position.get('global_y')} "
                f"{position.get('width')} × {position.get('height')}"
            ),
        ])

        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Confirmar restauração",
            body=body,
        )
        dialog.add_response("cancelar", "Cancelar")
        dialog.add_response("restaurar", "Restaurar")
        dialog.set_default_response("cancelar")
        dialog.set_close_response("cancelar")
        dialog.set_response_appearance("restaurar", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_restore_dialog_response)
        dialog.present()

    def _update_match_suggestion(self):
        self._clear_match_suggestion()

        if self._selected_saved_position is None:
            self._match_suggestion_label.set_text(
                "Selecione uma posição salva para procurar a janela correspondente."
            )
            self._update_action_sensitivity()
            return

        if self._loading:
            self._match_suggestion_label.set_text("Aguardando o carregamento das janelas...")
            self._update_action_sensitivity()
            return

        if not self._records:
            self._match_suggestion_label.set_text(
                "Nenhuma janela aberta disponível para correspondência."
            )
            self._update_action_sensitivity()
            return

        try:
            result = find_best_window_match(
                self._selected_saved_position,
                [record["window"] for record in self._records],
            )
        except WindowMatchingError as error:
            self._match_suggestion_label.set_text(
                f"Não foi possível analisar a correspondência: {error}"
            )
            self._update_action_sensitivity()
            return
        except Exception as error:
            self._match_suggestion_label.set_text(
                f"Erro ao analisar a correspondência: {error}"
            )
            self._update_action_sensitivity()
            return

        status = result.get("status")
        if status == "matched":
            candidate = result["best"]
            window = candidate["window"]
            app = candidate["application"]
            self._suggested_match = candidate
            self._match_suggestion_label.set_text(
                "Janela sugerida: "
                f"{app.get('resolved', '')} — {window.get('title', '')} · "
                f"confiança {candidate.get('confidence', '')} · "
                f"{candidate.get('score', 0)} pontos"
            )
        elif status == "ambiguous":
            self._match_suggestion_label.set_text(
                "Correspondência ambígua: os melhores candidatos estão próximos demais."
            )
        elif status == "not_found":
            self._match_suggestion_label.set_text("Nenhuma correspondência segura encontrada.")
        else:
            self._match_suggestion_label.set_text(
                "Erro ao analisar a correspondência: status desconhecido."
            )

        self._update_action_sensitivity()

    def _clear_match_suggestion(self):
        self._suggested_match = None
        if hasattr(self, "_select_suggested_button"):
            self._select_suggested_button.set_sensitive(False)

    def _on_select_suggested_clicked(self, _button):
        if not self._can_select_suggested_window():
            return

        suggested_sequence = str(
            self._suggested_match["window"].get("stableSequence", "")
        ).strip()
        if not suggested_sequence:
            self._handle_missing_suggested_window()
            return

        row = self._find_window_row_by_stable_sequence(suggested_sequence)
        if row is None:
            self._handle_missing_suggested_window()
            return

        self._list_box.select_row(row)

    def _find_window_row_by_stable_sequence(self, stable_sequence):
        row = self._list_box.get_first_child()
        while row is not None:
            current_sequence = str(row.window_data.get("stableSequence", "")).strip()
            if current_sequence == stable_sequence:
                return row
            row = row.get_next_sibling()

        return None

    def _handle_missing_suggested_window(self):
        self._clear_match_suggestion()
        self._match_suggestion_label.set_text(
            "A janela sugerida não está mais disponível. Atualize a lista."
        )
        self._update_action_sensitivity()

    def _on_restore_dialog_response(self, _dialog, response):
        if response != "restaurar":
            return

        self._start_restore()

    def _start_restore(self):
        if not self._can_restore():
            self._status_label.set_text("Não foi possível restaurar: seleção inválida.")
            return

        self._restoring = True
        self._update_action_sensitivity()
        self._status_label.set_text("Restaurando posição...")

        window = self._selected_record["window"]
        position = self._selected_saved_position
        thread = threading.Thread(
            target=self._restore_worker,
            args=(
                str(window.get("stableSequence", "")).strip(),
                position["global_x"],
                position["global_y"],
                position["width"],
                position["height"],
            ),
            daemon=True,
        )
        thread.start()

    def _restore_worker(self, stable_sequence, x, y, width, height):
        try:
            result = move_resize_window(stable_sequence, x, y, width, height)
            GLib.idle_add(self._finish_restore, result, None)
        except (PosiXDBusError, PosiXContractError) as error:
            GLib.idle_add(self._finish_restore, None, str(error))
        except Exception as error:
            GLib.idle_add(self._finish_restore, None, f"Erro inesperado: {error}")

    def _finish_restore(self, result, error):
        self._restoring = False

        if error:
            self._status_label.set_text(f"Erro ao restaurar a posição: {error}")
            self._update_action_sensitivity()
            return GLib.SOURCE_REMOVE

        if not result.get("success"):
            self._status_label.set_text(
                f"Não foi possível restaurar a posição: {result.get('error', '')}"
            )
            self._update_action_sensitivity()
            return GLib.SOURCE_REMOVE

        if result.get("exact"):
            message = "Posição restaurada com sucesso — geometria exata"
        else:
            difference = result.get("difference") or {}
            message = (
                "Posição restaurada com diferenças: "
                f"X={difference.get('x', 0)} "
                f"Y={difference.get('y', 0)} "
                f"L={difference.get('width', 0)} "
                f"A={difference.get('height', 0)}"
            )

        self._status_after_refresh = message
        self.refresh_windows()
        return GLib.SOURCE_REMOVE


def main(argv=None):
    app = PosiXApplication()
    return app.run(argv)
