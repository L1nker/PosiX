"""Interface gráfica inicial do PosiX."""

import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk, Pango

from posix_app.dbus_windows import PosiXContractError, PosiXDBusError, fetch_windows
from posix_app.storage import StorageError, save_window_position
from posix_app.window_identity import resolve_application


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
        self._records = []
        self._selected_record = None

        self._build_ui()

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
        self._show_empty_details()

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

        self._status_label.set_text(f"Posição salva com sucesso — ID {saved_id}")

    def refresh_windows(self):
        if self._loading:
            return

        self._loading = True
        self._selected_record = None
        self._list_box.unselect_all()
        self._refresh_button.set_sensitive(False)
        self._save_button.set_sensitive(False)
        self._status_label.set_text("Carregando janelas...")
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
        self._refresh_button.set_sensitive(True)
        self._save_button.set_sensitive(self._selected_record is not None)

        if error:
            self._status_label.set_text(error)
            return GLib.SOURCE_REMOVE

        self._records = records
        self._populate_window_list(records)
        self._list_box.unselect_all()
        self._selected_record = None
        self._save_button.set_sensitive(False)
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
            self._save_button.set_sensitive(False)
            self._show_empty_details()
            return

        self._selected_record = {
            "window": row.window_data,
            "application": row.application_info,
        }
        self._save_button.set_sensitive(not self._loading)
        self._show_details(row.window_data, row.application_info)

    def _show_empty_details(self):
        self._clear_details()

        title = Gtk.Label(label="Selecione uma janela", xalign=0)
        title.add_css_class("title-3")
        self._details_box.append(title)

        text = Gtk.Label(
            label="Os detalhes da janela selecionada aparecerão aqui.",
            xalign=0,
            wrap=True,
        )
        text.add_css_class("dim-label")
        self._details_box.append(text)

    def _show_details(self, window, app):
        self._clear_details()

        title = Gtk.Label(label="Detalhes da janela", xalign=0)
        title.add_css_class("title-3")
        self._details_box.append(title)

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
        self._details_box.append(grid)

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
        child = self._details_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._details_box.remove(child)
            child = next_child

    def _format_bool(self, value):
        return "Sim" if bool(value) else "Não"


def main(argv=None):
    app = PosiXApplication()
    return app.run(argv)
