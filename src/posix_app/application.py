"""Interface gráfica moderna do PosiX com posições universais e regras de janelas."""

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
from posix_app.rules_engine import plan_window_organization
from posix_app.storage import (
    StorageError,
    create_manual_preset,
    create_window_rule,
    delete_saved_position,
    delete_window_rule,
    list_saved_positions,
    list_window_rules,
    seed_default_presets_if_empty,
    toggle_window_rule,
    update_manual_preset,
    update_window_rule,
)
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


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="PosiX by Linker")
        self.set_default_size(840, 640)

        seed_default_presets_if_empty()

        self._presets = []
        self._rules = []

        self._build_ui()
        self.load_all()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        # HeaderBar principal
        header = Adw.HeaderBar()
        root.append(header)

        # Botão Mestre "⚡ Organizar Janelas" à esquerda
        self._organize_btn = Gtk.Button(
            label="⚡ Organizar Janelas",
            tooltip_text="Organiza e reposiciona todas as janelas abertas de acordo com as regras cadastradas",
        )
        self._organize_btn.add_css_class("suggested-action")
        self._organize_btn.connect("clicked", self._on_organize_all_clicked)
        header.pack_start(self._organize_btn)

        # Botão Capturar Janela à esquerda
        self._capture_btn = Gtk.Button(
            icon_name="camera-photo-symbolic",
            tooltip_text="Capturar dimensões de uma janela aberta",
        )
        self._capture_btn.connect("clicked", self._on_capture_clicked)
        header.pack_start(self._capture_btn)

        # Alternador de visualização central (Posições vs Regras)
        self._view_stack = Adw.ViewStack()
        view_switcher = Adw.ViewSwitcher(
            stack=self._view_stack,
            policy=Adw.ViewSwitcherPolicy.WIDE,
        )
        header.set_title_widget(view_switcher)

        # Botão Novo (+) à direita
        self._add_btn = Gtk.Button(
            label="+ Nova Posição",
            tooltip_text="Criar nova posição salva em pixels",
        )
        self._add_btn.connect("clicked", self._on_add_clicked)
        header.pack_end(self._add_btn)

        # Banner de aviso
        self._banner = Adw.Banner()
        self._banner.set_revealed(False)
        self._banner.set_title(
            "Extensão GNOME Shell desativada ou não encontrada. "
            "Ative a extensão 'posix@linker' no aplicativo Extensões para controlar as janelas."
        )
        root.append(self._banner)

        # Barra de status sutil
        self._status_label = Gtk.Label(
            label="Clique em qualquer posição para aplicá-la em uma janela aberta",
            xalign=0,
            margin_start=18,
            margin_end=18,
            margin_top=6,
            margin_bottom=4,
        )
        self._status_label.add_css_class("dim-label")
        root.append(self._status_label)

        # Conteúdo em abas via ViewStack
        self._view_stack.set_vexpand(True)
        root.append(self._view_stack)

        # -------------------------------------------------------------
        # ABA 1: POSIÇÕES SALVAS (Universais)
        # -------------------------------------------------------------
        presets_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            margin_start=18,
            margin_end=18,
            margin_top=8,
            margin_bottom=12,
            spacing=10,
        )

        presets_scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        presets_scroller.set_vexpand(True)
        presets_box.append(presets_scroller)

        self._presets_list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._presets_list_box.add_css_class("boxed-list")
        self._presets_list_box.connect("row-activated", self._on_preset_row_activated)
        presets_scroller.set_child(self._presets_list_box)

        # Rodapé da Aba de Posições (Apenas botão sutil de restaurar padrões)
        presets_footer = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10,
            margin_top=4,
        )
        presets_box.append(presets_footer)

        footer_hint = Gtk.Label(
            label="💡 Dica: Clique na posição para aplicar na janela. Use o lápis para editar ou a lixeira para excluir.",
            xalign=0,
        )
        footer_hint.add_css_class("dim-label")
        footer_hint.set_hexpand(True)
        presets_footer.append(footer_hint)

        load_defaults_btn = Gtk.Button(label="Restaurar Padrões")
        load_defaults_btn.connect("clicked", self._on_load_defaults_clicked)
        presets_footer.append(load_defaults_btn)

        page_presets = self._view_stack.add_titled(presets_box, "presets", "Posições")
        page_presets.set_icon_name("video-display-symbolic")

        # -------------------------------------------------------------
        # ABA 2: REGRAS DE JANELAS (Associações Automáticas)
        # -------------------------------------------------------------
        rules_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            margin_start=18,
            margin_end=18,
            margin_top=8,
            margin_bottom=12,
            spacing=10,
        )

        rules_scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        rules_scroller.set_vexpand(True)
        rules_box.append(rules_scroller)

        self._rules_list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._rules_list_box.add_css_class("boxed-list")
        rules_scroller.set_child(self._rules_list_box)

        # Rodapé da Aba de Regras
        rules_footer = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10,
            margin_top=4,
        )
        rules_box.append(rules_footer)

        rules_hint = Gtk.Label(
            label="💡 As regras associam programas e abas a posições salvas. Use '⚡ Organizar Janelas' para aplicar.",
            xalign=0,
        )
        rules_hint.add_css_class("dim-label")
        rules_hint.set_hexpand(True)
        rules_footer.append(rules_hint)

        new_rule_btn = Gtk.Button(label="+ Nova Regra")
        new_rule_btn.add_css_class("suggested-action")
        new_rule_btn.connect("clicked", self._on_add_rule_clicked)
        rules_footer.append(new_rule_btn)

        page_rules = self._view_stack.add_titled(rules_box, "rules", "Regras")
        page_rules.set_icon_name("view-grid-symbolic")

        # Alternar o botão + do cabeçalho de acordo com a aba visível
        self._view_stack.connect("notify::visible-child-name", self._on_tab_changed)

    def _on_tab_changed(self, stack, _param):
        name = stack.get_visible_child_name()
        if name == "rules":
            self._add_btn.set_label("+ Nova Regra")
            self._add_btn.set_tooltip_text("Criar nova regra de associação de janela")
            self._status_label.set_text("Gerencie suas regras de associação de janelas")
        else:
            self._add_btn.set_label("+ Nova Posição")
            self._add_btn.set_tooltip_text("Criar nova posição salva em pixels")
            self._status_label.set_text("Clique em qualquer posição para aplicá-la em uma janela aberta")

    def _on_add_clicked(self, _btn):
        name = self._view_stack.get_visible_child_name()
        if name == "rules":
            self._on_add_rule_clicked(None)
        else:
            self._on_add_preset_clicked(None)

    def load_all(self):
        self.load_presets()
        self.load_rules()

    # -------------------------------------------------------------
    # POSIÇÕES SALVAS
    # -------------------------------------------------------------
    def load_presets(self, select_id=None):
        try:
            self._presets = list_saved_positions()
        except StorageError as error:
            self._status_label.set_text(f"Erro ao carregar posições: {error}")
            self._presets = []

        # Limpar linhas atuais
        child = self._presets_list_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._presets_list_box.remove(child)
            child = next_child

        for preset in self._presets:
            row = Gtk.ListBoxRow()
            row.preset_data = preset
            row.set_child(self._create_preset_row_widget(preset))
            self._presets_list_box.append(row)

    def _create_preset_row_widget(self, preset):
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=14,
            margin_start=14,
            margin_end=14,
            margin_top=10,
            margin_bottom=10,
        )

        icon = Gtk.Image.new_from_icon_name("video-display-symbolic")
        icon.set_pixel_size(24)
        box.append(icon)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_hexpand(True)

        name_label = Gtk.Label(label=preset.get("name") or "Sem nome", xalign=0)
        name_label.add_css_class("heading")
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        text_box.append(name_label)

        width = preset.get("width")
        height = preset.get("height")
        gx = preset.get("global_x")
        gy = preset.get("global_y")
        mon = preset.get("monitor_index", 0)

        details = [f"{width} × {height} px"]
        if gx is not None and gy is not None:
            details.append(f"X: {gx}, Y: {gy}")
            details.append(f"Monitor {mon + 1}")  # <-- Contagem iniciando em 1!
        else:
            details.append("Posição livre (mantém onde estiver)")

        detail_label = Gtk.Label(label=" · ".join(details), xalign=0)
        detail_label.add_css_class("dim-label")
        text_box.append(detail_label)

        box.append(text_box)

        # Botões de Ação na Linha (Direita)
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)

        edit_btn = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Editar posição em pixels")
        edit_btn.add_css_class("flat")
        edit_btn.connect("clicked", lambda _b, p=preset: self._open_edit_preset(p))
        btn_box.append(edit_btn)

        del_btn = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Excluir posição")
        del_btn.add_css_class("flat")
        del_btn.add_css_class("destructive-action")
        del_btn.connect("clicked", lambda _b, p=preset: self._open_delete_preset(p))
        btn_box.append(del_btn)

        box.append(btn_box)
        return box

    def _on_preset_row_activated(self, _list_box, row):
        """Ao clicar na linha da posição, abre diretamente o seletor para aplicar na janela."""
        if not row or not hasattr(row, "preset_data"):
            return
        preset = row.preset_data
        dialog = ApplyWindowChooserDialog(self, preset, self._do_apply_geometry_to_window)
        dialog.present()

    def _open_edit_preset(self, preset):
        dialog = PresetEditorDialog(self, preset=preset, title="Editar Posição Salva")
        dialog.present()

    def _open_delete_preset(self, preset):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Excluir posição?",
            body=f"Deseja excluir a posição '{preset.get('name')}' ({preset.get('width')}×{preset.get('height')})?\nQuaisquer regras associadas a ela também serão removidas.",
        )
        dialog.add_response("cancelar", "Cancelar")
        dialog.add_response("excluir", "Excluir")
        dialog.set_default_response("cancelar")
        dialog.set_close_response("cancelar")
        dialog.set_response_appearance("excluir", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(_dlg, response):
            if response == "excluir":
                try:
                    delete_saved_position(preset["id"])
                    self.load_presets()
                    self.load_rules()
                    self._status_label.set_text(f"Posição '{preset.get('name')}' excluída.")
                except StorageError as error:
                    self._status_label.set_text(f"Erro ao excluir posição: {error}")

        dialog.connect("response", on_response)
        dialog.present()

    def _on_add_preset_clicked(self, _btn):
        dialog = PresetEditorDialog(self, title="Nova Posição Salva")
        dialog.present()

    def _do_apply_geometry_to_window(self, sequence, target_window, preset):
        width = preset["width"]
        height = preset["height"]

        if preset.get("global_x") is not None and preset.get("global_y") is not None:
            target_x = preset["global_x"]
            target_y = preset["global_y"]
        else:
            frame = target_window.get("frame", {})
            target_x = frame.get("x", 100)
            target_y = frame.get("y", 100)

        def worker():
            try:
                res = move_resize_window(sequence, target_x, target_y, width, height)
                GLib.idle_add(self._finish_apply, res, None)
            except (PosiXDBusError, PosiXContractError) as error:
                GLib.idle_add(self._finish_apply, None, str(error))
            except Exception as error:
                GLib.idle_add(self._finish_apply, None, f"Erro inesperado: {error}")

        self._status_label.set_text(f"Aplicando {width}×{height} na janela...")
        threading.Thread(target=worker, daemon=True).start()

    def _finish_apply(self, result, error):
        if error:
            self._status_label.set_text(f"Erro ao redimensionar: {error}")
            self._banner.set_revealed("D-Bus" in error or "posix@linker" in error)
            return GLib.SOURCE_REMOVE

        self._banner.set_revealed(False)
        if result and result.get("success"):
            self._status_label.set_text("Janela posicionada com sucesso!")
        else:
            msg = result.get("error") if result else "Falha ao aplicar"
            self._status_label.set_text(f"Aviso: {msg}")

        return GLib.SOURCE_REMOVE

    def _on_load_defaults_clicked(self, _btn):
        seed_default_presets_if_empty()
        self.load_presets()
        self._status_label.set_text("Posições padrão restauradas com sucesso!")

    # -------------------------------------------------------------
    # REGRAS DE JANELAS
    # -------------------------------------------------------------
    def load_rules(self, select_id=None):
        try:
            self._rules = list_window_rules()
        except StorageError as error:
            self._status_label.set_text(f"Erro ao carregar regras: {error}")
            self._rules = []

        child = self._rules_list_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._rules_list_box.remove(child)
            child = next_child

        for rule in self._rules:
            row = Gtk.ListBoxRow()
            row.rule_data = rule
            row.set_child(self._create_rule_row_widget(rule))
            self._rules_list_box.append(row)

    def _create_rule_row_widget(self, rule):
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=14,
            margin_start=14,
            margin_end=14,
            margin_top=10,
            margin_bottom=10,
        )

        icon = Gtk.Image.new_from_icon_name("view-grid-symbolic")
        icon.set_pixel_size(24)
        box.append(icon)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_hexpand(True)

        name_label = Gtk.Label(label=rule.get("name") or "Regra sem nome", xalign=0)
        name_label.add_css_class("heading")
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        text_box.append(name_label)

        pos_name = rule.get("position_name") or "Posição"
        w = rule.get("width")
        h = rule.get("height")
        target_info = f"➔ [{pos_name} ({w}×{h})]"

        filters = []
        if rule.get("match_title"):
            filters.append(f'Título: "{rule["match_title"]}"')
        if rule.get("match_app"):
            filters.append(f'App: "{rule["match_app"]}"')

        desc = " · ".join(filters) if filters else "Qualquer janela"
        detail_label = Gtk.Label(label=f"{desc}  {target_info}", xalign=0)
        detail_label.add_css_class("dim-label")
        detail_label.set_ellipsize(Pango.EllipsizeMode.END)
        text_box.append(detail_label)

        box.append(text_box)

        # Botões da linha de regra (Switch, Editar, Excluir)
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)

        switch = Gtk.Switch()
        switch.set_active(bool(rule.get("is_active", 1)))
        switch.set_valign(Gtk.Align.CENTER)
        switch.connect("state-set", lambda _s, state, r_id=rule["id"]: self._on_rule_toggle(r_id, state))
        action_box.append(switch)

        edit_btn = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Editar regra")
        edit_btn.add_css_class("flat")
        edit_btn.connect("clicked", lambda _b, r=rule: self._open_edit_rule(r))
        action_box.append(edit_btn)

        del_btn = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Excluir regra")
        del_btn.add_css_class("flat")
        del_btn.add_css_class("destructive-action")
        del_btn.connect("clicked", lambda _b, r=rule: self._open_delete_rule(r))
        action_box.append(del_btn)

        box.append(action_box)
        return box

    def _on_rule_toggle(self, rule_id, state):
        try:
            toggle_window_rule(rule_id, is_active=state)
            self._status_label.set_text("Regra atualizada.")
        except StorageError as error:
            self._status_label.set_text(f"Erro ao alternar regra: {error}")
        return False

    def _on_add_rule_clicked(self, _btn):
        if not self._presets:
            self._show_info_dialog("Nenhuma posição salva", "Crie ao menos uma Posição Salva antes de criar regras.")
            return
        dialog = RuleEditorDialog(self, presets=self._presets, title="Nova Regra de Janela")
        dialog.present()

    def _open_edit_rule(self, rule):
        dialog = RuleEditorDialog(
            self,
            rule=rule,
            presets=self._presets,
            title="Editar Regra de Janela",
        )
        dialog.present()

    def _open_delete_rule(self, rule):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Excluir regra?",
            body=f"Deseja excluir a regra '{rule.get('name')}'?",
        )
        dialog.add_response("cancelar", "Cancelar")
        dialog.add_response("excluir", "Excluir")
        dialog.set_default_response("cancelar")
        dialog.set_close_response("cancelar")
        dialog.set_response_appearance("excluir", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(_dlg, response):
            if response == "excluir":
                try:
                    delete_window_rule(rule["id"])
                    self.load_rules()
                    self._status_label.set_text(f"Regra '{rule.get('name')}' excluída.")
                except StorageError as error:
                    self._status_label.set_text(f"Erro ao excluir regra: {error}")

        dialog.connect("response", on_response)
        dialog.present()

    # -------------------------------------------------------------
    # ORGANIZAÇÃO GERAL DE JANELAS (Botão Mestre)
    # -------------------------------------------------------------
    def _on_organize_all_clicked(self, _btn):
        self._status_label.set_text("Escaneando janelas e organizando...")
        self._organize_btn.set_sensitive(False)

        def worker():
            try:
                windows = fetch_windows()
                rules = list_window_rules()
                positions = list_saved_positions()

                plan = plan_window_organization(windows, rules, positions)

                results = []
                for action in plan:
                    res = move_resize_window(
                        action["stable_sequence"],
                        action["target_x"],
                        action["target_y"],
                        action["target_width"],
                        action["target_height"],
                    )
                    results.append({"action": action, "result": res})

                GLib.idle_add(self._finish_organize_all, results, None)
            except Exception as e:
                GLib.idle_add(self._finish_organize_all, [], str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_organize_all(self, results, error):
        self._organize_btn.set_sensitive(True)

        if error:
            self._status_label.set_text(f"Erro ao organizar janelas: {error}")
            self._banner.set_revealed("D-Bus" in error or "posix@linker" in error)
            return GLib.SOURCE_REMOVE

        self._banner.set_revealed(False)
        count = len(results)

        if count == 0:
            self._status_label.set_text("Nenhuma janela aberta correspondeu às regras ativas.")
            self._show_info_dialog(
                "Organização de Janelas",
                "Nenhuma das janelas abertas no momento correspondeu aos títulos ou aplicativos das suas regras ativas.\n\nVerifique se os programas estão abertos e com as regras ativadas.",
            )
            return GLib.SOURCE_REMOVE

        summaries = [f"• {r['action']['summary']}" for r in results]
        body = f"{count} janela(s) reposicionada(s) com sucesso:\n\n" + "\n".join(summaries)
        self._status_label.set_text(f"⚡ {count} janela(s) organizada(s) com sucesso!")
        self._show_info_dialog("⚡ Janelas Organizadas!", body)

        return GLib.SOURCE_REMOVE

    # -------------------------------------------------------------
    # CAPTURA DE JANELA ABERTA
    # -------------------------------------------------------------
    def _on_capture_clicked(self, _btn):
        dialog = WindowCaptureDialog(self, self._on_window_captured)
        dialog.present()

    def _on_window_captured(self, window_data, app_data):
        dialog = PresetEditorDialog(
            self,
            captured_window=window_data,
            captured_app=app_data,
            title="Salvar Janela Capturada",
        )
        dialog.present()

    def _show_info_dialog(self, title, message):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=title,
            body=message,
        )
        dialog.add_response("ok", "OK")
        dialog.present()


class PresetEditorDialog(Adw.Window):
    """Diálogo modal para criação e edição de posições universais."""

    def __init__(
        self,
        parent,
        preset=None,
        captured_window=None,
        captured_app=None,
        title="Configurar Posição",
    ):
        super().__init__(transient_for=parent, modal=True, title=title)
        self.set_default_size(480, 480)

        self._parent_window = parent
        self._preset = preset
        self._captured_window = captured_window
        self._captured_app = captured_app

        self._build_ui()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        root.append(header)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.connect("clicked", lambda _b: self.close())
        header.pack_start(cancel_btn)

        save_btn = Gtk.Button(label="Salvar")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save_clicked)
        header.pack_end(save_btn)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_vexpand(True)
        root.append(scroller)

        clamp = Adw.Clamp(maximum_size=440)
        scroller.set_child(clamp)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_top=16,
            margin_bottom=24,
            margin_start=12,
            margin_end=12,
        )
        clamp.set_child(box)

        # Identificação
        group_id = Adw.PreferencesGroup(title="Identificação da Posição")
        box.append(group_id)

        self._name_row = Adw.EntryRow(title="Nome (Ex: 'Melhor Lugar', 'HD 16:9')")
        group_id.add(self._name_row)

        # Dimensões
        group_dims = Adw.PreferencesGroup(title="Tamanho da Janela (em Pixels)")
        box.append(group_dims)

        self._width_row = Adw.SpinRow.new_with_range(100, 7680, 10)
        self._width_row.set_title("Largura (px)")
        group_dims.add(self._width_row)

        self._height_row = Adw.SpinRow.new_with_range(100, 4320, 10)
        self._height_row.set_title("Altura (px)")
        group_dims.add(self._height_row)

        # Coordenadas
        group_pos = Adw.PreferencesGroup(title="Posicionamento na Tela")
        box.append(group_pos)

        self._fixed_pos_switch = Adw.SwitchRow(title="Fixar Posição em Coordenadas X / Y")
        self._fixed_pos_switch.set_subtitle("Se desativado, apenas o tamanho é alterado")
        self._fixed_pos_switch.connect("notify::active", self._on_fixed_pos_toggled)
        group_pos.add(self._fixed_pos_switch)

        self._x_row = Adw.SpinRow.new_with_range(-3840, 7680, 10)
        self._x_row.set_title("Posição Horizontal (X)")
        self._x_row.set_sensitive(False)
        group_pos.add(self._x_row)

        self._y_row = Adw.SpinRow.new_with_range(-2160, 4320, 10)
        self._y_row.set_title("Posição Vertical (Y)")
        self._y_row.set_sensitive(False)
        group_pos.add(self._y_row)

        # Monitor iniciando em 1 (1 = Principal, 2 = Secundário)
        self._monitor_row = Adw.SpinRow.new_with_range(1, 9, 1)
        self._monitor_row.set_title("Número do Monitor (1 = Principal)")
        self._monitor_row.set_sensitive(False)
        group_pos.add(self._monitor_row)

        self._populate_fields()

    def _populate_fields(self):
        if self._preset:
            p = self._preset
            self._name_row.set_text(p.get("name") or "")
            self._width_row.set_value(p.get("width") or 1280)
            self._height_row.set_value(p.get("height") or 720)

            has_coords = p.get("global_x") is not None and p.get("global_y") is not None
            self._fixed_pos_switch.set_active(has_coords)
            if has_coords:
                self._x_row.set_value(p.get("global_x") or 0)
                self._y_row.set_value(p.get("global_y") or 0)
                # No banco é salvo 0, 1... na tela exibimos 1, 2...
                self._monitor_row.set_value((p.get("monitor_index") or 0) + 1)

        elif self._captured_window:
            w = self._captured_window
            frame = w.get("frame", {})
            title = w.get("title") or "Janela Capturada"

            self._name_row.set_text(title)
            self._width_row.set_value(frame.get("width") or 1280)
            self._height_row.set_value(frame.get("height") or 720)

            self._fixed_pos_switch.set_active(True)
            self._x_row.set_value(frame.get("x") or 0)
            self._y_row.set_value(frame.get("y") or 0)
            self._monitor_row.set_value((w.get("monitorIndex") or 0) + 1)

        else:
            self._name_row.set_text("Melhor Lugar")
            self._width_row.set_value(1280)
            self._height_row.set_value(720)
            self._monitor_row.set_value(1)

    def _on_fixed_pos_toggled(self, row, _param):
        active = row.get_active()
        self._x_row.set_sensitive(active)
        self._y_row.set_sensitive(active)
        self._monitor_row.set_sensitive(active)

    def _on_save_clicked(self, _btn):
        name = self._name_row.get_text().strip()
        if not name:
            self._name_row.add_css_class("error")
            return

        width = int(self._width_row.get_value())
        height = int(self._height_row.get_value())

        fixed = self._fixed_pos_switch.get_active()
        gx = int(self._x_row.get_value()) if fixed else None
        gy = int(self._y_row.get_value()) if fixed else None
        # Subtrai 1 para salvar no banco como índice 0, 1...
        mon = max(0, int(self._monitor_row.get_value()) - 1) if fixed else 0

        try:
            if self._preset:
                update_manual_preset(
                    position_id=self._preset["id"],
                    name=name,
                    width=width,
                    height=height,
                    global_x=gx,
                    global_y=gy,
                    monitor_index=mon,
                    preset_type="universal",
                )
                pid = self._preset["id"]
            else:
                pid = create_manual_preset(
                    name=name,
                    width=width,
                    height=height,
                    global_x=gx,
                    global_y=gy,
                    monitor_index=mon,
                    preset_type="universal",
                )

            self._parent_window.load_presets(select_id=pid)
            self._parent_window.load_rules()
            self.close()
        except StorageError as error:
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading="Erro ao salvar",
                body=str(error),
            )
            dialog.add_response("ok", "OK")
            dialog.present()


class RuleEditorDialog(Adw.Window):
    """Diálogo modal para vincular títulos e aplicativos a uma posição salva."""

    def __init__(self, parent, presets, rule=None, title="Configurar Regra"):
        super().__init__(transient_for=parent, modal=True, title=title)
        self.set_default_size(500, 480)

        self._parent_window = parent
        self._presets = presets or []
        self._rule = rule

        self._build_ui()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        root.append(header)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.connect("clicked", lambda _b: self.close())
        header.pack_start(cancel_btn)

        save_btn = Gtk.Button(label="Salvar Regra")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save_clicked)
        header.pack_end(save_btn)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_vexpand(True)
        root.append(scroller)

        clamp = Adw.Clamp(maximum_size=460)
        scroller.set_child(clamp)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_top=16,
            margin_bottom=24,
            margin_start=12,
            margin_end=12,
        )
        clamp.set_child(box)

        # Identificação da Regra
        group_id = Adw.PreferencesGroup(title="Identificação da Regra")
        box.append(group_id)

        self._name_row = Adw.EntryRow(title="Nome da Regra")
        group_id.add(self._name_row)

        # Critérios de Correspondência
        group_match = Adw.PreferencesGroup(
            title="Critérios da Janela",
            description="Preencha o título da janela, o aplicativo ou ambos:",
        )
        box.append(group_match)

        self._title_row = Adw.EntryRow(title="Título da Janela contém")
        self._title_row.set_tooltip_text("Ex: WhatsApp, IXC ou Picture-in-picture (separe múltiplos termos por vírgula)")
        group_match.add(self._title_row)

        self._app_row = Adw.EntryRow(title="Aplicativo (Opcional)")
        self._app_row.set_tooltip_text("Ex: firefox, brave, code (ou deixe vazio para qualquer programa)")
        group_match.add(self._app_row)

        # Destino: Posição Salva
        group_pos = Adw.PreferencesGroup(title="Posição Salva Vinculada")
        box.append(group_pos)

        self._pos_combo = Adw.ComboRow(title="Posição Alvo")
        pos_names = [f"{p.get('name')} ({p.get('width')}×{p.get('height')})" for p in self._presets]
        self._pos_combo.set_model(Gtk.StringList.new(pos_names))
        group_pos.add(self._pos_combo)

        # Estado Ativo
        group_active = Adw.PreferencesGroup()
        box.append(group_active)

        self._active_switch = Adw.SwitchRow(title="Regra Ativa")
        self._active_switch.set_active(True)
        group_active.add(self._active_switch)

        self._populate_fields()

    def _populate_fields(self):
        if self._rule:
            r = self._rule
            self._name_row.set_text(r.get("name") or "")
            self._title_row.set_text(r.get("match_title") or "")
            self._app_row.set_text(r.get("match_app") or "")
            self._active_switch.set_active(bool(r.get("is_active", 1)))

            target_pos_id = r.get("position_id")
            for idx, p in enumerate(self._presets):
                if p.get("id") == target_pos_id:
                    self._pos_combo.set_selected(idx)
                    break
        else:
            self._name_row.set_text("Nova Regra")
            if len(self._presets) > 0:
                self._pos_combo.set_selected(0)

    def _on_save_clicked(self, _btn):
        name = self._name_row.get_text().strip()
        if not name:
            self._show_error("Nome Obrigatório", "Por favor, digite um nome para a regra.")
            return

        title_match = self._title_row.get_text().strip()
        app_match = self._app_row.get_text().strip()

        if not title_match and not app_match:
            self._show_error(
                "Critério Obrigatório",
                "Informe ao menos um critério para identificar a janela:\n\n• O que deve conter no Título (ex: 'WhatsApp, IXC' ou 'Picture-in-picture')\nOU\n• O nome do Aplicativo (ex: 'firefox' ou 'brave').",
            )
            return

        if len(self._presets) == 0:
            self._show_error("Nenhuma Posição", "Não há posições salvas disponíveis. Crie ao menos uma posição salva antes.")
            return

        selected_pos_idx = self._pos_combo.get_selected()
        if selected_pos_idx < 0 or selected_pos_idx >= len(self._presets):
            selected_pos_idx = 0

        position_id = self._presets[selected_pos_idx]["id"]
        is_active = self._active_switch.get_active()

        try:
            if self._rule:
                update_window_rule(
                    rule_id=self._rule["id"],
                    name=name,
                    position_id=position_id,
                    match_title=title_match or None,
                    match_app=app_match or None,
                    is_active=is_active,
                )
                rid = self._rule["id"]
            else:
                rid = create_window_rule(
                    name=name,
                    position_id=position_id,
                    match_title=title_match or None,
                    match_app=app_match or None,
                    is_active=is_active,
                )

            self._parent_window.load_rules(select_id=rid)
            self._parent_window.load_presets()
            self.close()
        except StorageError as error:
            self._show_error("Erro ao salvar regra", str(error))

    def _show_error(self, heading, body):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=heading,
            body=body,
        )
        dialog.add_response("ok", "OK")
        dialog.present()


class WindowCaptureDialog(Adw.Window):
    """Diálogo modal para listar janelas abertas e capturar suas dimensões."""

    def __init__(self, parent, on_captured_callback):
        super().__init__(transient_for=parent, modal=True, title="Capturar Janela Aberta")
        self.set_default_size(560, 460)

        self._on_captured = on_captured_callback
        self._records = []
        self._selected_record = None

        self._build_ui()
        self._load_windows()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.connect("clicked", lambda _b: self.close())
        header.pack_start(cancel_btn)

        self._capture_btn = Gtk.Button(label="Usar Dimensões")
        self._capture_btn.add_css_class("suggested-action")
        self._capture_btn.set_sensitive(False)
        self._capture_btn.connect("clicked", self._on_capture_confirmed)
        header.pack_end(self._capture_btn)

        self._spinner = Gtk.Spinner(spinning=True)
        self._spinner.set_margin_top(20)
        self._spinner.set_margin_bottom(20)
        root.append(self._spinner)

        self._info_label = Gtk.Label(
            label="Selecione uma das janelas abertas para capturar sua posição e tamanho:",
            xalign=0,
            margin_start=16,
            margin_end=16,
            margin_top=8,
            margin_bottom=8,
        )
        self._info_label.add_css_class("dim-label")
        root.append(self._info_label)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_vexpand(True)
        root.append(scroller)

        self._list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.set_margin_start(16)
        self._list_box.set_margin_end(16)
        self._list_box.set_margin_bottom(16)
        self._list_box.connect("row-selected", self._on_row_selected)
        self._list_box.connect("row-activated", lambda _l, _r: self._on_capture_confirmed(None))
        scroller.set_child(self._list_box)

    def _load_windows(self):
        def worker():
            try:
                wins = fetch_windows()
                records = [
                    {"window": w, "application": resolve_application(w)}
                    for w in wins
                ]
                GLib.idle_add(self._finish_load, records, None)
            except Exception as e:
                GLib.idle_add(self._finish_load, None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_load(self, records, error):
        self._spinner.set_spinning(False)
        self._spinner.set_visible(False)

        if error:
            self._info_label.set_text(f"Não foi possível listar as janelas: {error}")
            return GLib.SOURCE_REMOVE

        self._records = records
        self._info_label.set_text(f"{len(records)} janelas encontradas. Escolha uma:")

        for rec in records:
            w = rec["window"]
            app = rec["application"]
            frame = w.get("frame", {})

            row = Gtk.ListBoxRow()
            row.record_data = rec

            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=3,
                margin_start=12,
                margin_end=12,
                margin_top=8,
                margin_bottom=8,
            )

            title_l = Gtk.Label(label=f"{app.get('resolved', 'App')} — {w.get('title', '')}", xalign=0)
            title_l.add_css_class("heading")
            title_l.set_ellipsize(Pango.EllipsizeMode.END)
            box.append(title_l)

            dims_l = Gtk.Label(
                label=f"{frame.get('width', 0)} × {frame.get('height', 0)} px  ·  Posição X: {frame.get('x', 0)}, Y: {frame.get('y', 0)}",
                xalign=0,
            )
            dims_l.add_css_class("dim-label")
            box.append(dims_l)

            row.set_child(box)
            self._list_box.append(row)

        return GLib.SOURCE_REMOVE

    def _on_row_selected(self, _l, row):
        if row:
            self._selected_record = row.record_data
            self._capture_btn.set_sensitive(True)
        else:
            self._selected_record = None
            self._capture_btn.set_sensitive(False)

    def _on_capture_confirmed(self, _btn):
        if not self._selected_record:
            return
        rec = self._selected_record
        self.close()
        self._on_captured(rec["window"], rec["application"])


class ApplyWindowChooserDialog(Adw.Window):
    """Diálogo modal rápido para escolher em qual janela aberta aplicar a posição."""

    def __init__(self, parent, preset, on_window_chosen_callback):
        super().__init__(
            transient_for=parent,
            modal=True,
            title=f"Aplicar: {preset.get('name')}",
        )
        self.set_default_size(520, 420)

        self._preset = preset
        self._on_chosen = on_window_chosen_callback
        self._selected_sequence = None
        self._selected_window = None

        self._build_ui()
        self._load_windows()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.connect("clicked", lambda _b: self.close())
        header.pack_start(cancel_btn)

        self._apply_btn = Gtk.Button(label="Posicionar")
        self._apply_btn.add_css_class("suggested-action")
        self._apply_btn.set_sensitive(False)
        self._apply_btn.connect("clicked", self._on_apply_confirmed)
        header.pack_end(self._apply_btn)

        p = self._preset
        info_banner = Gtk.Label(
            label=f"Selecione a janela para aplicar {p.get('width')} × {p.get('height')} px:",
            xalign=0,
            margin_start=16,
            margin_end=16,
            margin_top=8,
            margin_bottom=8,
        )
        info_banner.add_css_class("dim-label")
        root.append(info_banner)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_vexpand(True)
        root.append(scroller)

        self._list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.set_margin_start(16)
        self._list_box.set_margin_end(16)
        self._list_box.set_margin_bottom(16)
        self._list_box.connect("row-selected", self._on_row_selected)
        self._list_box.connect("row-activated", lambda _l, _r: self._on_apply_confirmed(None))
        scroller.set_child(self._list_box)

    def _load_windows(self):
        def worker():
            try:
                wins = fetch_windows()
                records = [
                    {"window": w, "application": resolve_application(w)}
                    for w in wins
                ]
                GLib.idle_add(self._finish_load, records)
            except Exception:
                GLib.idle_add(self._finish_load, [])

        threading.Thread(target=worker, daemon=True).start()

    def _finish_load(self, records):
        for rec in records:
            w = rec["window"]
            app = rec["application"]
            frame = w.get("frame", {})

            row = Gtk.ListBoxRow()
            row.window_obj = w
            row.sequence = str(w.get("stableSequence", "")).strip()

            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=2,
                margin_start=12,
                margin_end=12,
                margin_top=8,
                margin_bottom=8,
            )

            title_l = Gtk.Label(label=f"{app.get('resolved', 'App')} — {w.get('title', '')}", xalign=0)
            title_l.add_css_class("heading")
            title_l.set_ellipsize(Pango.EllipsizeMode.END)
            box.append(title_l)

            dims_l = Gtk.Label(
                label=f"Atual: {frame.get('width', 0)} × {frame.get('height', 0)} px  (X: {frame.get('x', 0)}, Y: {frame.get('y', 0)})",
                xalign=0,
            )
            dims_l.add_css_class("dim-label")
            box.append(dims_l)

            row.set_child(box)
            self._list_box.append(row)

        return GLib.SOURCE_REMOVE

    def _on_row_selected(self, _l, row):
        if row:
            self._selected_sequence = row.sequence
            self._selected_window = row.window_obj
            self._apply_btn.set_sensitive(True)
        else:
            self._selected_sequence = None
            self._selected_window = None
            self._apply_btn.set_sensitive(False)

    def _on_apply_confirmed(self, _btn):
        if not self._selected_sequence:
            return
        seq = self._selected_sequence
        target_win = self._selected_window
        self.close()
        self._on_chosen(seq, target_win, self._preset)


def main(argv=None):
    app = PosiXApplication()
    return app.run(argv)
