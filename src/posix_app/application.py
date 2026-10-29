"""Interface gráfica do PosiX inspirada na arquitetura visual do Sizer 4.0.

Contém abas estruturadas (Menu, Opções, Load/Save, Sobre), gerenciamento
de grupos/subpastas, botões verticais de ação, opções de OSD em tempo real,
suporte a presets 'Don't Resize' e exportação/importação de configurações.
"""

import json
import os
import threading
from pathlib import Path

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
    delete_group,
    delete_saved_position,
    delete_window_rule,
    export_configuration_json,
    get_all_settings,
    get_database_path,
    get_setting,
    import_configuration_json,
    list_groups,
    list_saved_positions,
    list_window_rules,
    rename_group,
    rename_saved_position,
    reorder_saved_position,
    seed_default_presets_if_empty,
    set_setting,
    toggle_window_rule,
    update_manual_preset,
    update_saved_position_geometry,
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
        self._ensure_extension_enabled()
        if self._window is None:
            self._window = MainWindow(self)

        self._window.present()

    def _ensure_extension_enabled(self):
        try:
            import subprocess

            res = subprocess.run(
                ["gnome-extensions", "info", "posix@linker"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if "Estado: INACTIVE" in res.stdout or "Habilitado: Não" in res.stdout:
                subprocess.run(["gnome-extensions", "enable", "posix@linker"], timeout=2)
        except Exception:
            pass


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="PosiX Configuration")
        self.set_default_size(780, 600)

        seed_default_presets_if_empty()

        self._selected_item = None
        self._presets = []
        self._rules = []
        self._groups = []

        self._build_ui()
        self.load_all()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        # HeaderBar estilo Sizer / GNOME moderno
        header = Adw.HeaderBar()
        root.append(header)

        # Alternador de Abas Superior (Menu, Options, Load/Save, About)
        self._view_stack = Adw.ViewStack()
        view_switcher = Adw.ViewSwitcher(
            stack=self._view_stack,
            policy=Adw.ViewSwitcherPolicy.WIDE,
        )
        header.set_title_widget(view_switcher)

        # Banner informativo de ações
        self._banner = Adw.Banner(button_label="OK")
        self._banner.connect("button-clicked", lambda _: self._banner.set_revealed(False))
        root.append(self._banner)

        # Conteúdo em Abas
        root.append(self._view_stack)
        self._view_stack.set_vexpand(True)

        # 1. ABA MENU (Principal)
        menu_page = self._build_menu_page()
        page1 = self._view_stack.add_titled(menu_page, "menu", "Menu")
        page1.set_icon_name("view-list-tree-symbolic")

        # 2. ABA OPTIONS (Configurações / Tooltip / Hotkeys)
        options_page = self._build_options_page()
        page2 = self._view_stack.add_titled(options_page, "options", "Opções")
        page2.set_icon_name("emblem-system-symbolic")

        # 3. ABA LOAD/SAVE (Import / Export / Padrões)
        load_save_page = self._build_load_save_page()
        page3 = self._view_stack.add_titled(load_save_page, "load_save", "Load/Save")
        page3.set_icon_name("document-save-symbolic")

        # 4. ABA ABOUT (Sobre)
        about_page = self._build_about_page()
        page4 = self._view_stack.add_titled(about_page, "about", "Sobre")
        page4.set_icon_name("help-about-symbolic")

        # Rodapé inferior
        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bottom_box.set_margin_top(8)
        bottom_box.set_margin_bottom(10)
        bottom_box.set_margin_start(16)
        bottom_box.set_margin_end(16)
        root.append(bottom_box)

        self._organize_btn = Gtk.Button(
            label="⚡ Organizar Janelas Agora",
            tooltip_text="Varre e organiza todas as janelas abertas de acordo com as regras cadastradas",
        )
        self._organize_btn.add_css_class("suggested-action")
        self._organize_btn.connect("clicked", self._on_organize_all_clicked)
        bottom_box.append(self._organize_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bottom_box.append(spacer)

        self._apply_btn = Gtk.Button(label="Aplicar na Janela...")
        self._apply_btn.connect("clicked", self._on_apply_selected_clicked)
        bottom_box.append(self._apply_btn)

        close_btn = Gtk.Button(label="Fechar Janela")
        close_btn.connect("clicked", lambda _: self.close())
        bottom_box.append(close_btn)

        quit_btn = Gtk.Button(label="🛑 Encerrar PosiX")
        quit_btn.add_css_class("destructive-action")
        quit_btn.set_tooltip_text("Fecha o PosiX e encerra completamente a extensão da bandeja")
        quit_btn.connect("clicked", self._on_quit_posix_clicked)
        bottom_box.append(quit_btn)

    def _on_quit_posix_clicked(self, _):
        try:
            import subprocess
            subprocess.run(["gnome-extensions", "disable", "posix@linker"], timeout=2)
        except Exception:
            pass
        self.get_application().quit()

    def _build_menu_page(self):
        """Constrói a aba Menu com layout em 2 colunas igual ao Sizer 4.0."""
        container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        container.set_margin_start(16)
        container.set_margin_end(16)
        container.set_margin_top(12)
        container.set_margin_bottom(8)

        # Coluna da Esquerda: Árvore / Lista Hierárquica com Scroll
        left_frame = Gtk.Frame()
        left_frame.set_hexpand(True)
        left_frame.set_vexpand(True)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        left_frame.set_child(scrolled)

        self._tree_list_box = Gtk.ListBox()
        self._tree_list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._tree_list_box.add_css_class("boxed-list")
        self._tree_list_box.connect("row-selected", self._on_tree_row_selected)
        scrolled.set_child(self._tree_list_box)

        container.append(left_frame)

        # Coluna da Direita: Botões Verticais de Ação (Move Up, Move Down, Edit, Add Size, Add Macro, Add Group, Delete)
        right_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right_panel.set_size_request(160, -1)

        self._btn_move_up = Gtk.Button(label="⬆ Mover para Cima")
        self._btn_move_up.connect("clicked", lambda _: self._on_reorder_clicked("up"))
        right_panel.append(self._btn_move_up)

        self._btn_move_down = Gtk.Button(label="⬇ Mover para Baixo")
        self._btn_move_down.connect("clicked", lambda _: self._on_reorder_clicked("down"))
        right_panel.append(self._btn_move_down)

        right_panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        self._btn_edit = Gtk.Button(label="✏️ Editar...")
        self._btn_edit.connect("clicked", self._on_edit_selected_clicked)
        right_panel.append(self._btn_edit)

        self._btn_add_size = Gtk.Button(label="➕ Novo Tamanho")
        self._btn_add_size.add_css_class("suggested-action")
        self._btn_add_size.connect("clicked", self._on_add_size_clicked)
        right_panel.append(self._btn_add_size)

        self._btn_add_rule = Gtk.Button(label="⚡ Nova Regra")
        self._btn_add_rule.connect("clicked", self._on_add_rule_clicked)
        right_panel.append(self._btn_add_rule)

        self._btn_add_group = Gtk.Button(label="📁 Novo Grupo...")
        self._btn_add_group.connect("clicked", self._on_add_group_clicked)
        right_panel.append(self._btn_add_group)

        right_panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        self._btn_delete = Gtk.Button(label="🗑️ Excluir")
        self._btn_delete.add_css_class("destructive-action")
        self._btn_delete.connect("clicked", self._on_delete_selected_clicked)
        right_panel.append(self._btn_delete)

        container.append(right_panel)
        return container

    def _build_options_page(self):
        """Constrói a aba Opções com configurações de OSD, comportamento e janelas."""
        clamp = Adw.Clamp(maximum_size=680)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        clamp.set_child(box)

        settings = get_all_settings()

        # Grupo: Comportamento de Janelas
        group_behavior = Adw.PreferencesGroup(title="Comportamento das Janelas")
        box.append(group_behavior)

        self._sw_compensate = Adw.SwitchRow(
            title="Compensar decorações e sombras",
            subtitle="Calcula o retângulo exato da janela descontando bordas invisíveis do compositor",
        )
        self._sw_compensate.set_active(settings.get("compensate_frame_effects", "1") == "1")
        self._sw_compensate.connect("notify::active", lambda sw, _: set_setting("compensate_frame_effects", "1" if sw.get_active() else "0"))
        group_behavior.add(self._sw_compensate)

        self._sw_opposite = Adw.SwitchRow(
            title="Ajustar quina/borda oposta ao cursor",
            subtitle="Ao redimensionar, trava a quina contrária ao ponto de clique do mouse",
        )
        self._sw_opposite.set_active(settings.get("adjust_opposite_edge", "0") == "1")
        self._sw_opposite.connect("notify::active", lambda sw, _: set_setting("adjust_opposite_edge", "1" if sw.get_active() else "0"))
        group_behavior.add(self._sw_opposite)

        # Grupo: Tooltip / OSD em Tempo Real
        group_tooltip = Adw.PreferencesGroup(
            title="Feedback em Tempo Real (Tooltip / OSD)",
            description="Exibe um indicador flutuante elegante na tela durante o arrasto ou redimensionamento da janela",
        )
        box.append(group_tooltip)

        self._combo_tooltip = Adw.ComboRow(title="Tooltip ao mover ou redimensionar:")
        tooltip_model = Gtk.StringList.new([
            "Posição e Tamanho (X, Y • Largura × Altura)",
            "Apenas Tamanho (Largura × Altura)",
            "Apenas Posição (X, Y)",
            "Desativado",
        ])
        self._combo_tooltip.set_model(tooltip_model)

        mode_map = {"pos_size": 0, "size": 1, "pos": 2, "none": 3}
        current_mode = settings.get("tooltip_mode", "pos_size")
        self._combo_tooltip.set_selected(mode_map.get(current_mode, 0))
        self._combo_tooltip.connect("notify::selected", self._on_tooltip_mode_changed)
        group_tooltip.add(self._combo_tooltip)

        # Grupo: Atalho Global
        group_hotkey = Adw.PreferencesGroup(title="Atalho de Teclado Global")
        box.append(group_hotkey)

        hotkey_row = Adw.ActionRow(
            title="Atalho de Acionamento Rápido",
            subtitle="Abre o menu do PosiX na janela atualmente em foco",
        )
        hotkey_badge = Gtk.Label(label="Ctrl + Super + Z")
        hotkey_badge.add_css_class("badge")
        hotkey_row.add_suffix(hotkey_badge)
        group_hotkey.add(hotkey_row)

        return clamp

    def _on_tooltip_mode_changed(self, combo, _):
        idx = combo.get_selected()
        rev_map = {0: "pos_size", 1: "size", 2: "pos", 3: "none"}
        set_setting("tooltip_mode", rev_map.get(idx, "pos_size"))

    def _build_load_save_page(self):
        """Constrói a aba Load/Save para backup, exportação e importação."""
        clamp = Adw.Clamp(maximum_size=680)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        clamp.set_child(box)

        group_storage = Adw.PreferencesGroup(title="Armazenamento de Configurações")
        box.append(group_storage)

        db_path = str(get_database_path())
        path_row = Adw.ActionRow(
            title="Arquivo de Banco de Dados Local",
            subtitle=db_path,
        )
        group_storage.add(path_row)

        group_backup = Adw.PreferencesGroup(title="Backup e Sincronização")
        box.append(group_backup)

        export_row = Adw.ActionRow(
            title="Exportar Configurações",
            subtitle="Gera um arquivo JSON contendo todos os tamanhos, regras e preferências",
        )
        btn_export = Gtk.Button(label="Exportar para Arquivo...")
        btn_export.connect("clicked", self._on_export_clicked)
        export_row.add_suffix(btn_export)
        group_backup.add(export_row)

        import_row = Adw.ActionRow(
            title="Importar Configurações",
            subtitle="Restaura tamanhos e preferências a partir de um backup JSON",
        )
        btn_import = Gtk.Button(label="Importar de Arquivo...")
        btn_import.connect("clicked", self._on_import_clicked)
        import_row.add_suffix(btn_import)
        group_backup.add(import_row)

        group_defaults = Adw.PreferencesGroup(title="Restauração de Fábrica")
        box.append(group_defaults)

        reset_row = Adw.ActionRow(
            title="Restaurar Predefinições Originais",
            subtitle="Recria os grupos de resolução clássicos (4:3, 16:9, YouTube)",
        )
        btn_reset = Gtk.Button(label="Restaurar Padrões")
        btn_reset.connect("clicked", self._on_reset_defaults_clicked)
        reset_row.add_suffix(btn_reset)
        group_defaults.add(reset_row)

        return clamp

    def _build_about_page(self):
        """Constrói a aba Sobre com créditos e informações."""
        clamp = Adw.Clamp(maximum_size=580)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(32)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        clamp.set_child(box)

        icon = Gtk.Image.new_from_icon_name("focus-windows-symbolic")
        icon.set_pixel_size(72)
        box.append(icon)

        title = Gtk.Label(label="PosiX 4.0")
        title.add_css_class("title-1")
        box.append(title)

        subtitle = Gtk.Label(label="Gerenciador e Restaurador de Janelas para Linux")
        subtitle.add_css_class("dim-label")
        box.append(subtitle)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        info_box.set_margin_top(12)

        desc = Gtk.Label(
            label="Inspirado na arquitetura do utilitário clássico Sizer de Brian Apps.\n"
                  "Integração nativa com compositor GNOME Mutter via D-Bus e GJS Extension.\n"
                  "Desenvolvido sob direção de criação de Linker."
        )
        desc.set_justify(Gtk.Justification.CENTER)
        info_box.append(desc)

        link_btn = Gtk.LinkButton(
            uri="https://github.com/L1nker/PosiX",
            label="Ver Repositório no GitHub (L1nker/PosiX)",
        )
        info_box.append(link_btn)

        box.append(info_box)
        return clamp

    def load_all(self):
        """Recarrega posições, regras e grupos montando a lista hierárquica."""
        self._presets = list_saved_positions()
        self._rules = list_window_rules()
        self._groups = list_groups()
        self._selected_item = None

        # Limpa árvore
        while True:
            child = self._tree_list_box.get_first_child()
            if child is None:
                break
            self._tree_list_box.remove(child)

        # Cabeçalho Raiz "PosiX Menu"
        root_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root_header.set_margin_top(6)
        root_header.set_margin_bottom(6)
        root_header.set_margin_start(10)
        root_header.set_margin_end(10)
        icon_root = Gtk.Image.new_from_icon_name("focus-windows-symbolic")
        root_header.append(icon_root)
        lbl_root = Gtk.Label(label="PosiX Menu")
        lbl_root.add_css_class("heading")
        root_header.append(lbl_root)
        self._tree_list_box.append(root_header)

        # 1. Presets na Raiz (sem grupo)
        root_presets = [p for p in self._presets if not p.get("group_name")]
        for p in root_presets:
            row = self._create_preset_row(p, is_nested=False)
            self._tree_list_box.append(row)

        # 2. Grupos / Pastas e seus Presets
        for g_name in self._groups:
            group_header = self._create_group_header_row(g_name)
            self._tree_list_box.append(group_header)

            group_items = [p for p in self._presets if p.get("group_name") == g_name]
            for p in group_items:
                row = self._create_preset_row(p, is_nested=True)
                self._tree_list_box.append(row)

        # 3. Seção Regras / Automações (se houver)
        if self._rules:
            rules_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            rules_header.set_margin_top(12)
            rules_header.set_margin_bottom(4)
            rules_header.set_margin_start(10)
            rules_header.set_margin_end(10)
            icon_r = Gtk.Image.new_from_icon_name("system-run-symbolic")
            rules_header.append(icon_r)
            lbl_r = Gtk.Label(label="Regras de Janelas (Automações)")
            lbl_r.add_css_class("heading")
            rules_header.append(lbl_r)
            self._tree_list_box.append(rules_header)

            for r in self._rules:
                row = self._create_rule_row(r)
                self._tree_list_box.append(row)

    def _create_preset_row(self, p, is_nested=False):
        row = Adw.ActionRow()
        row.item_data = {"type": "preset", "data": p}

        name = p.get("name") or "Sem nome"
        dont_resize = bool(p.get("dont_resize"))
        dont_move = bool(p.get("dont_move"))
        w = p.get("width")
        h = p.get("height")
        gx = p.get("global_x")
        gy = p.get("global_y")
        mon = (p.get("monitor_index") or 0) + 1

        prefix_indent = "     ↳ " if is_nested else ""
        row.set_title(f"{prefix_indent}{name}")

        subparts = []
        if dont_resize:
            subparts.append("Apenas Mover")
        elif w and h:
            subparts.append(f"{w} × {h} px")

        if dont_move:
            subparts.append("Sem Mover")
        elif gx is not None and gy is not None:
            subparts.append(f"X: {gx}, Y: {gy}")

        subparts.append(f"Monitor {mon}")
        row.set_subtitle(" • ".join(subparts))

        icon_name = "view-restore-symbolic" if dont_resize else "view-fullscreen-symbolic"
        icon = Gtk.Image.new_from_icon_name(icon_name)
        row.add_prefix(icon)

        return row

    def _create_group_header_row(self, group_name):
        row = Adw.ActionRow()
        row.item_data = {"type": "group", "data": group_name}
        row.set_title(f"📁 {group_name}")
        row.set_subtitle("Grupo de Resoluções")
        icon = Gtk.Image.new_from_icon_name("folder-symbolic")
        row.add_prefix(icon)
        return row

    def _create_rule_row(self, r):
        row = Adw.ActionRow()
        row.item_data = {"type": "rule", "data": r}
        name = r.get("name") or "Regra"
        row.set_title(name)

        pos_name = r.get("position_name") or "Posição"
        criteria = []
        if r.get("match_app"):
            criteria.append(f"App: {r.get('match_app')}")
        if r.get("match_title"):
            criteria.append(f"Título: {r.get('match_title')}")

        crit_str = " | ".join(criteria) if criteria else "Qualquer"
        row.set_subtitle(f"{crit_str} ➔ {pos_name}")

        icon = Gtk.Image.new_from_icon_name("emblem-default-symbolic" if r.get("is_active") else "dialog-error-symbolic")
        row.add_prefix(icon)

        # Switch ativar/desativar
        sw = Gtk.Switch()
        sw.set_active(bool(r.get("is_active")))
        sw.set_valign(Gtk.Align.CENTER)
        sw.connect("notify::active", lambda s, _, rid=r["id"]: toggle_window_rule(rid, s.get_active()))
        row.add_suffix(sw)

        return row

    def _on_tree_row_selected(self, _, row):
        if row and hasattr(row, "item_data"):
            self._selected_item = row.item_data
        else:
            self._selected_item = None

    def _on_reorder_clicked(self, direction):
        if not self._selected_item or self._selected_item["type"] != "preset":
            self._show_banner("Selecione um tamanho/preset para mover.")
            return

        p_id = self._selected_item["data"]["id"]
        reorder_saved_position(p_id, direction)
        self.load_all()

    def _on_edit_selected_clicked(self, _):
        if not self._selected_item:
            self._show_banner("Selecione um item para editar.")
            return

        item_type = self._selected_item["type"]
        if item_type == "preset":
            dialog = PresetEditorDialog(self, preset=self._selected_item["data"])
            dialog.present()
        elif item_type == "group":
            dialog = GroupEditorDialog(self, group_name=self._selected_item["data"])
            dialog.present()
        elif item_type == "rule":
            dialog = RuleEditorDialog(self, rule=self._selected_item["data"])
            dialog.present()

    def _on_add_size_clicked(self, _):
        dialog = PresetEditorDialog(self)
        dialog.present()

    def _on_add_rule_clicked(self, _):
        dialog = RuleEditorDialog(self)
        dialog.present()

    def _on_add_group_clicked(self, _):
        dialog = GroupEditorDialog(self)
        dialog.present()

    def _on_delete_selected_clicked(self, _):
        if not self._selected_item:
            self._show_banner("Selecione um item para excluir.")
            return

        item_type = self._selected_item["type"]
        if item_type == "preset":
            p = self._selected_item["data"]
            delete_saved_position(p["id"])
            self._show_banner(f"Tamanho '{p.get('name')}' excluído.")
            self.load_all()
        elif item_type == "group":
            g_name = self._selected_item["data"]
            delete_group(g_name, remove_items=False)
            self._show_banner(f"Grupo '{g_name}' excluído (itens movidos para a raiz).")
            self.load_all()
        elif item_type == "rule":
            r = self._selected_item["data"]
            delete_window_rule(r["id"])
            self._show_banner(f"Regra '{r.get('name')}' excluída.")
            self.load_all()

    def _on_apply_selected_clicked(self, _):
        if not self._selected_item or self._selected_item["type"] != "preset":
            self._show_banner("Selecione uma posição/tamanho para aplicar.")
            return

        dialog = ApplyWindowChooserDialog(self, self._selected_item["data"])
        dialog.present()

    def _on_organize_all_clicked(self, _):
        def worker():
            try:
                windows = fetch_windows()
                rules = list_window_rules()
                positions = list_saved_positions()
                plan = plan_window_organization(windows, rules, positions)
                for action in plan:
                    move_resize_window(
                        action["stable_sequence"],
                        action["target_x"],
                        action["target_y"],
                        action["target_width"],
                        action["target_height"],
                    )
                GLib.idle_add(lambda: self._show_banner(f"⚡ {len(plan)} janela(s) organizada(s) com sucesso!"))
            except Exception as e:
                GLib.idle_add(lambda: self._show_banner(f"Erro ao organizar: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_export_clicked(self, _):
        dialog = Gtk.FileDialog(title="Salvar Backup do PosiX")
        dialog.set_initial_name("PosiX_Backup.json")

        def on_save_finish(_, result):
            try:
                gfile = dialog.save_finish(result)
                if gfile:
                    content = export_configuration_json()
                    path = gfile.get_path()
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                    self._show_banner(f"Configurações exportadas para: {Path(path).name}")
            except Exception as e:
                self._show_banner(f"Erro ao exportar: {e}")

        dialog.save(self, None, on_save_finish)

    def _on_import_clicked(self, _):
        dialog = Gtk.FileDialog(title="Selecionar Backup do PosiX")

        def on_open_finish(_, result):
            try:
                gfile = dialog.open_finish(result)
                if gfile:
                    path = gfile.get_path()
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    import_configuration_json(content)
                    self.load_all()
                    self._show_banner("Configurações importadas com sucesso!")
            except Exception as e:
                self._show_banner(f"Erro ao importar: {e}")

        dialog.open(self, None, on_open_finish)

    def _on_reset_defaults_clicked(self, _):
        seed_default_presets_if_empty()
        self.load_all()
        self._show_banner("Predefinições padrão restauradas.")

    def _show_banner(self, text):
        self._banner.set_title(text)
        self._banner.set_revealed(True)


class PresetEditorDialog(Adw.Window):
    """Diálogo completo de criação e edição de tamanho/posição."""

    def __init__(self, parent, preset=None):
        super().__init__(modal=True, transient_for=parent)
        self._parent = parent
        self._preset = preset

        title_text = "Editar Posição" if preset else "Novo Tamanho / Posição"
        self.set_title(title_text)
        self.set_default_size(520, 560)

        self._build_ui()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)

        btn_cancel = Gtk.Button(label="Cancelar")
        btn_cancel.connect("clicked", lambda _: self.close())
        header.pack_start(btn_cancel)

        btn_save = Gtk.Button(label="Salvar")
        btn_save.add_css_class("suggested-action")
        btn_save.connect("clicked", self._on_save_clicked)
        header.pack_end(btn_save)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        root.append(scrolled)
        scrolled.set_vexpand(True)

        clamp = Adw.Clamp(maximum_size=480)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        clamp.set_child(box)
        scrolled.set_child(clamp)

        # Grupo: Identificação
        group_ident = Adw.PreferencesGroup(title="Identificação")
        box.append(group_ident)

        self._name_row = Adw.EntryRow(title="Nome / Descrição")
        if self._preset:
            self._name_row.set_text(self._preset.get("name") or "")
        group_ident.add(self._name_row)

        # Grupo / Pasta
        self._group_row = Adw.EntryRow(title="Grupo / Pasta (opcional)")
        if self._preset and self._preset.get("group_name"):
            self._group_row.set_text(self._preset.get("group_name"))
        group_ident.add(self._group_row)

        # Grupo: Modos de Redimensionamento e Movimento (Sizer Features)
        group_modes = Adw.PreferencesGroup(title="Opções de Aplicação")
        box.append(group_modes)

        self._sw_dont_resize = Adw.SwitchRow(
            title="Não redimensionar janela",
            subtitle="Apenas move para a coordenada X/Y mantendo o tamanho atual da janela",
        )
        self._sw_dont_resize.set_active(bool(self._preset.get("dont_resize")) if self._preset else False)
        self._sw_dont_resize.connect("notify::active", self._on_mode_switches_changed)
        group_modes.add(self._sw_dont_resize)

        self._sw_dont_move = Adw.SwitchRow(
            title="Não mover janela",
            subtitle="Apenas redimensiona para a largura e altura mantendo onde ela estiver",
        )
        self._sw_dont_move.set_active(bool(self._preset.get("dont_move")) if self._preset else False)
        self._sw_dont_move.connect("notify::active", self._on_mode_switches_changed)
        group_modes.add(self._sw_dont_move)

        # Grupo: Dimensões
        self._group_dims = Adw.PreferencesGroup(title="Dimensões (Largura × Altura)")
        box.append(self._group_dims)

        self._width_row = Adw.SpinRow.new_with_range(100, 7680, 10)
        self._width_row.set_title("Largura (px)")
        self._width_row.set_value(self._preset.get("width") or 1280 if self._preset else 1280)
        self._group_dims.add(self._width_row)

        self._height_row = Adw.SpinRow.new_with_range(100, 4320, 10)
        self._height_row.set_title("Altura (px)")
        self._height_row.set_value(self._preset.get("height") or 720 if self._preset else 720)
        self._group_dims.add(self._height_row)

        # Grupo: Posição na Tela
        self._group_pos = Adw.PreferencesGroup(title="Posição na Tela e Monitor")
        box.append(self._group_pos)

        self._x_row = Adw.SpinRow.new_with_range(-10000, 20000, 10)
        self._x_row.set_title("Posição X (px)")
        self._x_row.set_value(self._preset.get("global_x") or 0 if self._preset else 0)
        self._group_pos.add(self._x_row)

        self._y_row = Adw.SpinRow.new_with_range(-10000, 20000, 10)
        self._y_row.set_title("Posição Y (px)")
        self._y_row.set_value(self._preset.get("global_y") or 0 if self._preset else 0)
        self._group_pos.add(self._y_row)

        self._mon_row = Adw.SpinRow.new_with_range(1, 9, 1)
        self._mon_row.set_title("Monitor")
        current_mon = (self._preset.get("monitor_index") or 0) + 1 if self._preset else 1
        self._mon_row.set_value(current_mon)
        self._group_pos.add(self._mon_row)

        # Botão Capturar Janela
        btn_capture = Gtk.Button(label="📸 Capturar de Janela Aberta...")
        btn_capture.connect("clicked", self._on_capture_clicked)
        box.append(btn_capture)

        self._on_mode_switches_changed(None, None)

    def _on_mode_switches_changed(self, _, __):
        dont_res = self._sw_dont_resize.get_active()
        dont_mov = self._sw_dont_move.get_active()

        self._group_dims.set_sensitive(not dont_res)
        self._group_pos.set_sensitive(not dont_mov)

    def _on_capture_clicked(self, _):
        dialog = CaptureWindowChooserDialog(self, callback=self._fill_from_window)
        dialog.present()

    def _fill_from_window(self, win):
        frame = win.get("frame") or {}
        title = win.get("title") or win.get("appName") or "Janela Capturada"
        self._name_row.set_text(title)
        self._width_row.set_value(frame.get("width", 1280))
        self._height_row.set_value(frame.get("height", 720))
        self._x_row.set_value(frame.get("x", 0))
        self._y_row.set_value(frame.get("y", 0))
        self._mon_row.set_value((win.get("monitorIndex") or 0) + 1)

    def _on_save_clicked(self, _):
        name = self._name_row.get_text().strip()
        if not name:
            self._parent._show_banner("Por favor, preencha o nome da posição.")
            return

        group = self._group_row.get_text().strip() or None
        dont_res = self._sw_dont_resize.get_active()
        dont_mov = self._sw_dont_move.get_active()

        w = None if dont_res else int(self._width_row.get_value())
        h = None if dont_res else int(self._height_row.get_value())
        x = None if dont_mov else int(self._x_row.get_value())
        y = None if dont_mov else int(self._y_row.get_value())
        mon = max(0, int(self._mon_row.get_value()) - 1)

        try:
            if self._preset:
                update_manual_preset(
                    position_id=self._preset["id"],
                    name=name,
                    width=w,
                    height=h,
                    global_x=x,
                    global_y=y,
                    monitor_index=mon,
                    group_name=group,
                    dont_resize=dont_res,
                    dont_move=dont_mov,
                )
            else:
                create_manual_preset(
                    name=name,
                    width=w,
                    height=h,
                    global_x=x,
                    global_y=y,
                    monitor_index=mon,
                    group_name=group,
                    dont_resize=dont_res,
                    dont_move=dont_mov,
                )
            self._parent.load_all()
            self.close()
        except Exception as e:
            self._parent._show_banner(f"Erro ao salvar: {e}")


class GroupEditorDialog(Adw.Window):
    """Diálogo para criar ou renomear um grupo de resoluções."""

    def __init__(self, parent, group_name=None):
        super().__init__(modal=True, transient_for=parent)
        self._parent = parent
        self._old_name = group_name

        self.set_title("Editar Grupo" if group_name else "Novo Grupo / Pasta")
        self.set_default_size(380, 220)

        self._build_ui()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)

        btn_cancel = Gtk.Button(label="Cancelar")
        btn_cancel.connect("clicked", lambda _: self.close())
        header.pack_start(btn_cancel)

        btn_save = Gtk.Button(label="Salvar")
        btn_save.add_css_class("suggested-action")
        btn_save.connect("clicked", self._on_save_clicked)
        header.pack_end(btn_save)

        clamp = Adw.Clamp(maximum_size=340)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_start(16)
        box.set_margin_end(16)
        clamp.set_child(box)
        root.append(clamp)

        group_pref = Adw.PreferencesGroup(title="Nome da Pasta")
        box.append(group_pref)

        self._entry = Adw.EntryRow(title="Nome do Grupo")
        if self._old_name:
            self._entry.set_text(self._old_name)
        group_pref.add(self._entry)

    def _on_save_clicked(self, _):
        new_name = self._entry.get_text().strip()
        if not new_name:
            return

        try:
            if self._old_name:
                rename_group(self._old_name, new_name)
            else:
                # Cria um preset exemplo no grupo
                create_manual_preset(
                    name=f"Preset de Exemplo",
                    width=1280,
                    height=720,
                    group_name=new_name,
                )
            self._parent.load_all()
            self.close()
        except Exception as e:
            self._parent._show_banner(f"Erro no grupo: {e}")


class RuleEditorDialog(Adw.Window):
    """Diálogo para cadastrar regras de automação de janelas."""

    def __init__(self, parent, rule=None):
        super().__init__(modal=True, transient_for=parent)
        self._parent = parent
        self._rule = rule

        self.set_title("Editar Regra" if rule else "Nova Regra de Janela")
        self.set_default_size(480, 460)

        self._build_ui()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)

        btn_cancel = Gtk.Button(label="Cancelar")
        btn_cancel.connect("clicked", lambda _: self.close())
        header.pack_start(btn_cancel)

        btn_save = Gtk.Button(label="Salvar")
        btn_save.add_css_class("suggested-action")
        btn_save.connect("clicked", self._on_save_clicked)
        header.pack_end(btn_save)

        clamp = Adw.Clamp(maximum_size=420)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        clamp.set_child(box)
        root.append(clamp)

        group_ident = Adw.PreferencesGroup(title="Definição da Regra")
        box.append(group_ident)

        self._name_row = Adw.EntryRow(title="Nome da Regra")
        if self._rule:
            self._name_row.set_text(self._rule.get("name") or "")
        group_ident.add(self._name_row)

        # Seletor de Posição
        self._pos_combo = Adw.ComboRow(title="Posição Associada")
        presets = list_saved_positions()
        self._preset_ids = [p["id"] for p in presets]
        preset_labels = [f"{p.get('name')} (Mon {(p.get('monitor_index') or 0) + 1})" for p in presets]

        model = Gtk.StringList.new(preset_labels if preset_labels else ["Nenhuma posição cadastrada"])
        self._pos_combo.set_model(model)

        if self._rule and self._rule.get("position_id") in self._preset_ids:
            idx = self._preset_ids.index(self._rule.get("position_id"))
            self._pos_combo.set_selected(idx)
        else:
            self._pos_combo.set_selected(0)

        group_ident.add(self._pos_combo)

        # Critérios de Matching
        group_criteria = Adw.PreferencesGroup(
            title="Critérios de Correspondência",
            description="A regra será disparada quando a janela coincidir com o aplicativo ou com os termos no título",
        )
        box.append(group_criteria)

        self._app_row = Adw.EntryRow(title="Aplicativo (ex: firefox, brave, code)")
        if self._rule and self._rule.get("match_app"):
            self._app_row.set_text(self._rule.get("match_app"))
        group_criteria.add(self._app_row)

        self._title_row = Adw.EntryRow(title="Título da Janela (ex: WhatsApp, IXC)")
        if self._rule and self._rule.get("match_title"):
            self._title_row.set_text(self._rule.get("match_title"))
        group_criteria.add(self._title_row)

        self._sw_active = Adw.SwitchRow(title="Regra Ativa")
        self._sw_active.set_active(bool(self._rule.get("is_active", 1)) if self._rule else True)
        box.append(self._sw_active)

    def _on_save_clicked(self, _):
        name = self._name_row.get_text().strip()
        if not name:
            self._parent._show_banner("Por favor, preencha o nome da regra.")
            return

        if not self._preset_ids:
            self._parent._show_banner("Cadastre ao menos uma posição antes de criar regras.")
            return

        sel_idx = self._pos_combo.get_selected()
        pos_id = self._preset_ids[sel_idx if sel_idx < len(self._preset_ids) else 0]
        match_app = self._app_row.get_text().strip() or None
        match_title = self._title_row.get_text().strip() or None
        is_active = self._sw_active.get_active()

        if not match_app and not match_title:
            self._parent._show_banner("Preencha ao menos um critério (Aplicativo ou Título).")
            return

        try:
            if self._rule:
                update_window_rule(self._rule["id"], name, pos_id, match_title, match_app, is_active)
            else:
                create_window_rule(name, pos_id, match_title, match_app, is_active)
            self._parent.load_all()
            self.close()
        except Exception as e:
            self._parent._show_banner(f"Erro ao salvar regra: {e}")


class ApplyWindowChooserDialog(Adw.Window):
    """Diálogo para escolher em qual janela aberta aplicar um preset."""

    def __init__(self, parent, preset):
        super().__init__(modal=True, transient_for=parent)
        self._parent = parent
        self._preset = preset

        self.set_title(f"Aplicar '{preset.get('name')}'")
        self.set_default_size(460, 420)

        self._build_ui()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)

        btn_cancel = Gtk.Button(label="Cancelar")
        btn_cancel.connect("clicked", lambda _: self.close())
        header.pack_start(btn_cancel)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        root.append(scrolled)

        self._list_box = Gtk.ListBox()
        self._list_box.add_css_class("boxed-list")
        self._list_box.set_margin_top(12)
        self._list_box.set_margin_bottom(12)
        self._list_box.set_margin_start(16)
        self._list_box.set_margin_end(16)
        scrolled.set_child(self._list_box)

        # Carrega janelas abertas
        try:
            windows = fetch_windows()
            if not windows:
                row = Adw.ActionRow(title="Nenhuma janela aberta identificada.")
                self._list_box.append(row)
            else:
                for win in windows:
                    row = Adw.ActionRow()
                    title = win.get("title") or "Sem título"
                    app = win.get("appName") or win.get("wmClass") or "Aplicação"
                    frame = win.get("frame") or {}
                    mon = (win.get("monitorIndex") or 0) + 1

                    row.set_title(title)
                    row.set_subtitle(f"{app} • {frame.get('width', 0)}×{frame.get('height', 0)} px • Monitor {mon}")

                    btn = Gtk.Button(label="Aplicar")
                    btn.add_css_class("suggested-action")
                    btn.connect("clicked", lambda _, w=win: self._apply_to_window(w))
                    row.add_suffix(btn)
                    self._list_box.append(row)
        except Exception as e:
            row = Adw.ActionRow(title=f"Erro ao buscar janelas: {e}")
            self._list_box.append(row)

    def _apply_to_window(self, win):
        seq = str(win.get("stableSequence") or "")
        frame = win.get("frame") or {}

        dont_res = bool(self._preset.get("dont_resize"))
        dont_mov = bool(self._preset.get("dont_move"))

        target_w = frame.get("width", 800) if dont_res else (self._preset.get("width") or frame.get("width", 800))
        target_h = frame.get("height", 600) if dont_res else (self._preset.get("height") or frame.get("height", 600))
        target_x = frame.get("x", 100) if dont_mov else (self._preset.get("global_x") if self._preset.get("global_x") is not None else frame.get("x", 100))
        target_y = frame.get("y", 100) if dont_mov else (self._preset.get("global_y") if self._preset.get("global_y") is not None else frame.get("y", 100))

        try:
            move_resize_window(seq, target_x, target_y, target_w, target_h)
            self._parent._show_banner(f"Posição aplicada na janela '{win.get('title')}'!")
            self.close()
        except Exception as e:
            self._parent._show_banner(f"Erro ao aplicar: {e}")


class CaptureWindowChooserDialog(Adw.Window):
    """Diálogo para capturar os dados de uma janela aberta."""

    def __init__(self, parent, callback):
        super().__init__(modal=True, transient_for=parent)
        self._callback = callback

        self.set_title("Capturar Dimensões de Janela")
        self.set_default_size(440, 380)

        self._build_ui()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)

        btn_cancel = Gtk.Button(label="Cancelar")
        btn_cancel.connect("clicked", lambda _: self.close())
        header.pack_start(btn_cancel)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        root.append(scrolled)

        list_box = Gtk.ListBox()
        list_box.add_css_class("boxed-list")
        list_box.set_margin_top(12)
        list_box.set_margin_bottom(12)
        list_box.set_margin_start(16)
        list_box.set_margin_end(16)
        scrolled.set_child(list_box)

        try:
            windows = fetch_windows()
            for win in windows:
                row = Adw.ActionRow()
                title = win.get("title") or "Sem título"
                app = win.get("appName") or win.get("wmClass") or "Aplicação"
                frame = win.get("frame") or {}

                row.set_title(title)
                row.set_subtitle(f"{app} • {frame.get('width', 0)}×{frame.get('height', 0)} px")

                btn = Gtk.Button(label="Capturar")
                btn.connect("clicked", lambda _, w=win: self._on_select(w))
                row.add_suffix(btn)
                list_box.append(row)
        except Exception as e:
            row = Adw.ActionRow(title=f"Erro ao buscar janelas: {e}")
            list_box.append(row)

    def _on_select(self, win):
        self._callback(win)
        self.close()


def main():
    app = PosiXApplication()
    return app.run(None)


if __name__ == "__main__":
    main()
