import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as WindowMenu from 'resource:///org/gnome/shell/ui/windowMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'io.github.L1nker.PosiX';
const OBJECT_PATH = '/io/github/L1nker/PosiX';
const LOG_PREFIX = '[PosiX D-Bus]';

const INTERFACE_XML = `
<node>
  <interface name="io.github.L1nker.PosiX">
    <method name="Ping">
      <arg type="s" name="mensagem" direction="in"/>
      <arg type="s" name="resposta" direction="out"/>
    </method>
    <method name="ListWindows">
      <arg type="s" name="json" direction="out"/>
    </method>
    <method name="MoveResizeWindow">
      <arg type="s" name="stableSequence" direction="in"/>
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
      <arg type="i" name="width" direction="in"/>
      <arg type="i" name="height" direction="in"/>
      <arg type="s" name="json" direction="out"/>
    </method>
    <method name="OrganizeWindows">
      <arg type="s" name="json" direction="out"/>
    </method>
  </interface>
</node>`;

export default class PosiXExtension extends Extension {
    enable() {
        this._ownerId = 0;
        this._dbusObject = null;
        this._connection = null;
        this._origBuildMenu = null;
        this._indicator = null;

        this._osdBin = null;
        this._osdLabel = null;
        this._activeGrabWindow = null;
        this._windowMoveId = 0;
        this._windowSizeId = 0;
        this._grabBeginId = 0;
        this._grabEndId = 0;

        this._log('extensão habilitada');

        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            this._onBusAcquired.bind(this),
            this._onNameAcquired.bind(this),
            this._onNameLost.bind(this)
        );

        this._patchWindowMenu();
        this._initIndicator();
        this._initOsd();
    }

    disable() {
        this._unpatchWindowMenu();
        this._destroyIndicator();
        this._destroyOsd();

        if (this._dbusObject) {
            this._dbusObject.flush();
            this._dbusObject.unexport();
            this._dbusObject = null;
        }

        if (this._ownerId) {
            Gio.bus_unown_name(this._ownerId);
            this._ownerId = 0;
        }

        this._connection = null;
        this._log('extensão desabilitada');
    }

    _initOsd() {
        try {
            this._grabBeginId = global.display.connect('grab-op-begin', (_display, window, _op) => {
                this._onGrabBegin(window);
            });
            this._grabEndId = global.display.connect('grab-op-end', (_display, _window, _op) => {
                this._onGrabEnd();
            });
        } catch (err) {
            this._log(`Aviso ao conectar sinais de grab-op: ${err.message}`);
        }
    }

    _destroyOsd() {
        try {
            if (this._grabBeginId) {
                global.display.disconnect(this._grabBeginId);
                this._grabBeginId = 0;
            }
            if (this._grabEndId) {
                global.display.disconnect(this._grabEndId);
                this._grabEndId = 0;
            }
            this._onGrabEnd();
        } catch (_) {}
    }

    _onGrabBegin(window) {
        try {
            const settings = this._loadSettings();
            const mode = settings.tooltip_mode || 'pos_size';
            if (mode === 'none' || !window || typeof window.get_frame_rect !== 'function')
                return;

            this._activeGrabWindow = window;
            this._updateOsd(window, mode);

            this._windowMoveId = window.connect('position-changed', () => {
                this._updateOsd(window, mode);
            });
            this._windowSizeId = window.connect('size-changed', () => {
                this._updateOsd(window, mode);
            });
        } catch (err) {
            this._log(`Erro em _onGrabBegin: ${err.message}`);
        }
    }

    _onGrabEnd() {
        try {
            if (this._activeGrabWindow) {
                if (this._windowMoveId) {
                    this._activeGrabWindow.disconnect(this._windowMoveId);
                    this._windowMoveId = 0;
                }
                if (this._windowSizeId) {
                    this._activeGrabWindow.disconnect(this._windowSizeId);
                    this._windowSizeId = 0;
                }
                this._activeGrabWindow = null;
            }

            if (this._osdBin) {
                this._osdBin.destroy();
                this._osdBin = null;
                this._osdLabel = null;
            }
        } catch (err) {
            this._log(`Erro em _onGrabEnd: ${err.message}`);
        }
    }

    _updateOsd(window, mode) {
        try {
            if (!this._osdBin) {
                this._osdBin = new St.Bin({
                    style_class: 'posix-osd-panel',
                    style: 'background-color: rgba(20, 20, 24, 0.92); color: #ffffff; border: 1px solid rgba(255, 255, 255, 0.22); border-radius: 10px; padding: 6px 14px; box-shadow: 0 4px 16px rgba(0,0,0,0.55);',
                    reactive: false,
                    can_focus: false,
                });
                this._osdLabel = new St.Label({
                    style: 'color: #ffffff; font-size: 13px; font-weight: 700; font-family: sans-serif;',
                    text: '',
                });
                this._osdBin.set_child(this._osdLabel);
                Main.uiGroup.add_child(this._osdBin);
            }

            const frame = window.get_frame_rect();
            const mon = window.get_monitor();
            let msg = '';
            if (mode === 'size') {
                msg = `📐 ${frame.width} × ${frame.height} px`;
            } else if (mode === 'pos') {
                msg = `📍 X: ${frame.x}, Y: ${frame.y}  (Monitor ${mon + 1})`;
            } else {
                msg = `📍 X: ${frame.x}, Y: ${frame.y}   •   📐 ${frame.width} × ${frame.height} px   •   Monitor ${mon + 1}`;
            }
            this._osdLabel.set_text(msg);

            const monitor = Main.layoutManager.monitors[mon] || Main.layoutManager.primaryMonitor;
            const [, natW] = this._osdBin.get_preferred_width(-1);
            const osdW = natW || 260;
            this._osdBin.set_position(
                monitor.x + Math.max(20, Math.round((monitor.width - osdW) / 2)),
                monitor.y + 40
            );
            this._osdBin.show();
        } catch (_) {}
    }

    _patchWindowMenu() {
        if (this._origBuildMenu)
            return;

        const extension = this;
        this._origBuildMenu = WindowMenu.WindowMenu.prototype._buildMenu;
        WindowMenu.WindowMenu.prototype._buildMenu = function(window) {
            try {
                extension._origBuildMenu.call(this, window);
            } catch (err) {
                console.error(`[PosiX] Erro no _buildMenu original: ${err.message}`);
            }

            try {
                extension._injectPosiXWindowMenu(this, window);
            } catch (err) {
                console.error(`[PosiX] Erro protegido ao injetar menu da janela: ${err.message}`);
            }
        };
    }

    _unpatchWindowMenu() {
        if (this._origBuildMenu) {
            WindowMenu.WindowMenu.prototype._buildMenu = this._origBuildMenu;
            this._origBuildMenu = null;
        }
    }

    _injectPosiXWindowMenu(menu, window) {
        try {
            if (!menu || typeof menu.addMenuItem !== 'function')
                return;

            if (!window || typeof window.get_frame_rect !== 'function')
                return;

            const data = this._loadPresetsData();
            const presets = data.presets || [];

            menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

            const subMenu = new PopupMenu.PopupSubMenuMenuItem('PosiX');

            // 1. Organizar Todas as Janelas
            const organizeItem = new PopupMenu.PopupMenuItem('⚡ Organizar Todas as Janelas');
            organizeItem.connect('activate', () => {
                try {
                    menu.close();
                } catch (_) {}
                GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                    try {
                        this._organizeAllWindows();
                    } catch (e) {
                        this._log(`Erro ao organizar: ${e.message}`);
                    }
                    return GLib.SOURCE_REMOVE;
                });
            });
            subMenu.menu.addMenuItem(organizeItem);

            // 2. Salvar Posição Desta Janela
            const saveCurrentItem = new PopupMenu.PopupMenuItem('💾 Salvar Posição Desta Janela...');
            saveCurrentItem.connect('activate', () => {
                try {
                    menu.close();
                } catch (_) {}
                GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                    try {
                        this._saveWindowAsPreset(window);
                    } catch (e) {
                        this._log(`Erro ao salvar: ${e.message}`);
                    }
                    return GLib.SOURCE_REMOVE;
                });
            });
            subMenu.menu.addMenuItem(saveCurrentItem);

            if (presets.length > 0) {
                subMenu.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
                this._populateMenuWithPresets(subMenu.menu, data, window, menu);
            }

            menu.addMenuItem(subMenu);
        } catch (error) {
            this._log(`Erro protegido ao injetar menu da janela: ${error.message}`);
        }
    }

    _populateMenuWithPresets(menuTarget, data, targetWindow, parentMenuToClose = null) {
        const presets = data.presets || [];
        const groups = data.groups || [];

        // Itens soltos (sem grupo)
        const rootPresets = presets.filter(p => !p.group);
        // Itens agrupados por pasta
        const groupedMap = {};
        for (const g of groups) {
            groupedMap[g] = [];
        }
        for (const p of presets) {
            if (p.group) {
                if (!groupedMap[p.group])
                    groupedMap[p.group] = [];
                groupedMap[p.group].push(p);
            }
        }

        const createItem = (preset) => {
            let label = preset.name || 'Posição';
            if (preset.dont_resize) {
                label = `${label} (Apenas Mover)`;
            } else if (preset.dont_move) {
                label = `${label} (${preset.width}×${preset.height} - Fixo)`;
            } else if (preset.width && preset.height) {
                label = `${label} (${preset.width}×${preset.height})`;
            }

            const item = new PopupMenu.PopupMenuItem(label);
            item.connect('activate', () => {
                if (parentMenuToClose) {
                    try { parentMenuToClose.close(); } catch (_) {}
                }
                GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                    try {
                        if (targetWindow) {
                            this._applyPresetToWindow(targetWindow, preset);
                        } else {
                            this._applyPresetToActiveWindow(preset);
                        }
                    } catch (e) {
                        this._log(`Erro ao aplicar preset: ${e.message}`);
                    }
                    return GLib.SOURCE_REMOVE;
                });
            });
            return item;
        };

        // Adiciona itens soltos da raiz
        for (const p of rootPresets) {
            menuTarget.addMenuItem(createItem(p));
        }

        // Adiciona grupos como submenus
        const groupNames = Object.keys(groupedMap).sort();
        if (groupNames.length > 0 && rootPresets.length > 0) {
            menuTarget.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        }

        for (const gName of groupNames) {
            const list = groupedMap[gName];
            if (!list || list.length === 0) continue;

            const groupSub = new PopupMenu.PopupSubMenuMenuItem(`📁 ${gName}`);
            for (const p of list) {
                groupSub.menu.addMenuItem(createItem(p));
            }
            menuTarget.addMenuItem(groupSub);
        }
    }

    _loadPresetsData() {
        try {
            const dataDir = GLib.get_user_data_dir();
            const filePath = `${dataDir}/posix/presets.json`;
            const file = Gio.File.new_for_path(filePath);
            if (!file.query_exists(null))
                return {presets: this._fallbackPresets(), groups: [], settings: {}};

            const [, contents] = file.load_contents(null);
            const decoder = new TextDecoder('utf-8');
            const jsonText = decoder.decode(contents);
            const data = JSON.parse(jsonText);

            if (Array.isArray(data))
                return {presets: data, groups: [], settings: {}};

            if (data && Array.isArray(data.presets))
                return data;

            return {presets: this._fallbackPresets(), groups: [], settings: {}};
        } catch (_error) {
            return {presets: this._fallbackPresets(), groups: [], settings: {}};
        }
    }

    _loadSettings() {
        try {
            const data = this._loadPresetsData();
            return data.settings || {};
        } catch (_) {
            return {};
        }
    }

    _fallbackPresets() {
        return [
            {name: '640 × 480 (VGA 4:3)', width: 640, height: 480},
            {name: '1280 × 720 (HD 16:9)', width: 1280, height: 720},
            {name: '1920 × 1080 (Full HD 16:9)', width: 1920, height: 1080},
        ];
    }

    _initIndicator() {
        try {
            this._indicator = new PanelMenu.Button(0.0, 'PosiX', false);
            const icon = new St.Icon({
                icon_name: 'focus-windows-symbolic',
                style_class: 'system-status-icon',
            });
            this._indicator.add_child(icon);

            this._indicator.menu.connect('open-state-changed', (_menu, open) => {
                if (open)
                    this._refreshIndicatorMenu();
            });

            this._refreshIndicatorMenu();
            Main.panel.addToStatusArea('posix-indicator', this._indicator);
        } catch (error) {
            this._log(`Erro ao inicializar indicador na bandeja: ${error.message}`);
        }
    }

    _destroyIndicator() {
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }

    _refreshIndicatorMenu() {
        if (!this._indicator) return;

        this._indicator.menu.removeAll();

        // 1. Abrir PosiX
        const openAppItem = new PopupMenu.PopupMenuItem('⚙️ Painel PosiX...');
        openAppItem.connect('activate', () => {
            this._launchApp();
        });
        this._indicator.menu.addMenuItem(openAppItem);

        // 2. Organizar Todas as Janelas
        const organizeItem = new PopupMenu.PopupMenuItem('⚡ Organizar Janelas Agora');
        organizeItem.connect('activate', () => {
            this._organizeAllWindows();
        });
        this._indicator.menu.addMenuItem(organizeItem);

        // 3. Salvar Janela Ativa
        const saveFocusItem = new PopupMenu.PopupMenuItem('💾 Salvar Janela em Foco...');
        saveFocusItem.connect('activate', () => {
            const focusWin = global.display.focus_window;
            if (focusWin) {
                this._saveWindowAsPreset(focusWin);
            } else {
                Main.notify('PosiX', 'Nenhuma janela ativa em foco para salvar.');
            }
        });
        this._indicator.menu.addMenuItem(saveFocusItem);

        const data = this._loadPresetsData();
        const presets = data.presets || [];

        if (presets.length > 0) {
            this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            this._populateMenuWithPresets(this._indicator.menu, data, null, null);
        }
    }

    _launchApp() {
        try {
            const proc = new Gio.Subprocess({
                argv: ['bash', '-c', 'PYTHONPATH=/home/linker/AG_Local/PosiX/src python3 -m posix_app'],
                flags: Gio.SubprocessFlags.NONE,
            });
            proc.init(null);
        } catch (e) {
            this._log(`Erro ao abrir PosiX: ${e.message}`);
        }
    }

    _applyPresetToWindow(win, preset) {
        try {
            if (!win) return;

            if (win.is_fullscreen())
                win.unmake_fullscreen();

            if (win.get_maximized() !== 0)
                win.unmaximize(Meta.MaximizeFlags.BOTH);

            const frame = win.get_frame_rect();
            const targetX = preset.dont_move
                ? frame.x
                : ((preset.global_x !== null && preset.global_x !== undefined) ? preset.global_x : frame.x);
            const targetY = preset.dont_move
                ? frame.y
                : ((preset.global_y !== null && preset.global_y !== undefined) ? preset.global_y : frame.y);
            const targetW = preset.dont_resize
                ? frame.width
                : ((preset.width !== null && preset.width !== undefined) ? preset.width : frame.width);
            const targetH = preset.dont_resize
                ? frame.height
                : ((preset.height !== null && preset.height !== undefined) ? preset.height : frame.height);

            // Descola com user_op = false para janelas restritas como PiP
            try {
                win.move_frame(false, targetX, targetY);
            } catch (_) {}

            win.move_resize_frame(false, targetX, targetY, targetW, targetH);
        } catch (e) {
            this._log(`Erro ao redimensionar janela: ${e.message}`);
        }
    }

    _applyPresetToActiveWindow(preset) {
        const focusWindow = global.display.focus_window;
        if (!focusWindow) {
            this._log('Nenhuma janela em foco para redimensionar');
            return;
        }
        this._applyPresetToWindow(focusWindow, preset);
    }

    _saveWindowAsPreset(win) {
        try {
            if (!win || typeof win.get_frame_rect !== 'function')
                return;

            const frame = win.get_frame_rect();
            const rawTitle = win.get_title() || 'Janela Capturada';
            const escapedTitle = rawTitle.replace(/'/g, "\\'");
            const monitor = win.get_monitor();

            const cmd = `PYTHONPATH=/home/linker/AG_Local/PosiX/src python3 -c "from posix_app.storage import create_manual_preset; create_manual_preset('${escapedTitle}', ${frame.width}, ${frame.height}, ${frame.x}, ${frame.y}, ${monitor})"`;

            const proc = new Gio.Subprocess({
                argv: ['bash', '-c', cmd],
                flags: Gio.SubprocessFlags.NONE,
            });
            proc.init(null);
            proc.wait_async(null, () => {
                Main.notify('PosiX', `Posição salva: "${rawTitle}" (${frame.width}×${frame.height})`);
                this._refreshIndicatorMenu();
            });
        } catch (e) {
            this._log(`Erro ao salvar posição da janela: ${e.message}`);
        }
    }

    _organizeAllWindows() {
        try {
            const cmd = `PYTHONPATH=/home/linker/AG_Local/PosiX/src python3 -c '
import json
from posix_app.storage import list_window_rules, list_saved_positions
from posix_app.rules_engine import plan_window_organization
from posix_app.dbus_windows import fetch_windows, move_resize_window

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

print(len(plan))
'`;
            const proc = new Gio.Subprocess({
                argv: ['bash', '-c', cmd],
                flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
            });
            proc.init(null);
            proc.communicate_utf8_async(null, null, (_proc, res) => {
                try {
                    const [, stdout] = proc.communicate_utf8_finish(res);
                    const count = parseInt((stdout || '').trim(), 10) || 0;
                    if (count > 0) {
                        Main.notify('PosiX', `⚡ ${count} janela(s) organizada(s) com sucesso!`);
                    } else {
                        Main.notify('PosiX', 'Nenhuma janela aberta correspondeu às regras ativas.');
                    }
                } catch (_) {
                    Main.notify('PosiX', 'Janelas verificadas.');
                }
            });
        } catch (e) {
            this._log(`Erro ao organizar janelas: ${e.message}`);
        }
    }

    Ping(mensagem) {
        this._log(`chamada Ping recebida: ${mensagem}`);
        return `PosiX respondeu: ${mensagem}`;
    }

    ListWindows() {
        const windows = this._listWindows();
        this._log(`ListWindows chamado: ${windows.length} janelas retornadas`);

        return JSON.stringify({
            schemaVersion: 1,
            windows,
        });
    }

    MoveResizeWindow(stableSequence, x, y, width, height) {
        this._log(
            `MoveResizeWindow solicitado: sequência ${stableSequence}, ${x} ${y} ${width} ${height}`
        );

        try {
            const result = this._moveResizeWindow(stableSequence, x, y, width, height);
            if (result.success)
                this._log(`MoveResizeWindow concluído: exact=${result.exact}`);
            else
                this._log(`MoveResizeWindow falhou: ${result.error}`);
            return JSON.stringify(result);
        } catch (error) {
            const requested = this._requestedGeometry(x, y, width, height);
            const result = this._moveResizeFailure(
                String(stableSequence ?? ''),
                requested,
                error.message
            );
            this._log(`MoveResizeWindow falhou: ${error.message}`);
            return JSON.stringify(result);
        }
    }

    OrganizeWindows() {
        this._log('OrganizeWindows chamado via D-Bus');
        this._organizeAllWindows();
        return JSON.stringify({
            success: true,
            message: 'Organização disparada com sucesso',
        });
    }

    _onBusAcquired(connection, _name) {
        this._connection = connection;
        this._log('conexão com o barramento obtida');

        if (this._dbusObject) {
            this._dbusObject.flush();
            this._dbusObject.unexport();
            this._dbusObject = null;
        }

        this._dbusObject = Gio.DBusExportedObject.wrapJSObject(INTERFACE_XML, this);
        this._dbusObject.export(connection, OBJECT_PATH);
    }

    _onNameAcquired(_connection, name) {
        this._log(`nome adquirido: ${name}`);
    }

    _onNameLost(_connection, name) {
        this._log(`nome perdido: ${name}`);

        if (this._dbusObject) {
            this._dbusObject.flush();
            this._dbusObject.unexport();
            this._dbusObject = null;
        }

        this._connection = null;
    }

    _log(message) {
        console.log(`${LOG_PREFIX} ${message}`);
    }

    _listWindows() {
        const result = [];
        const seen = new Set();
        const actors = this._safeCall(() => global.get_window_actors(), []);

        for (const actor of actors) {
            try {
                const metaWindow = this._safeCall(() => actor.get_meta_window(), null);

                if (!metaWindow)
                    continue;

                if (this._safeCall(() => metaWindow.is_override_redirect(), false))
                    continue;

                const stableSequence = String(this._safeCall(
                    () => metaWindow.get_stable_sequence(),
                    result.length
                ));

                if (seen.has(stableSequence))
                    continue;

                seen.add(stableSequence);
                result.push(this._serializeWindow(metaWindow, stableSequence));
            } catch (error) {
                this._log(`janela ignorada por erro: ${error.message}`);
            }
        }

        result.sort((a, b) => {
            if (a.monitorIndex !== b.monitorIndex)
                return a.monitorIndex - b.monitorIndex;

            return Number(a.stableSequence) - Number(b.stableSequence);
        });

        return result;
    }

    _moveResizeWindow(stableSequence, x, y, width, height) {
        const sequence = String(stableSequence ?? '').trim();
        const requested = this._requestedGeometry(x, y, width, height);

        this._validateMoveResizeRequest(sequence, requested);

        const metaWindow = this._findWindowByStableSequence(sequence);
        if (!metaWindow) {
            return this._moveResizeFailure(
                sequence,
                requested,
                'Janela não encontrada para a stable sequence informada.'
            );
        }

        if (this._safeCall(() => metaWindow.is_fullscreen(), false)) {
            this._safeCall(() => metaWindow.unmake_fullscreen(), null);
        }

        if (this._safeCall(() => metaWindow.get_maximized(), 0) !== 0) {
            this._safeCall(() => metaWindow.unmaximize(Meta.MaximizeFlags.BOTH), null);
        }

        const before = this._geometryFromRect(this._safeCall(
            () => metaWindow.get_frame_rect(),
            null
        ));

        try {
            metaWindow.move_frame(false, requested.x, requested.y);
        } catch (_) {}

        metaWindow.move_resize_frame(
            false,
            requested.x,
            requested.y,
            requested.width,
            requested.height
        );

        const after = this._geometryFromRect(this._safeCall(
            () => metaWindow.get_frame_rect(),
            null
        ));

        const exact = (
            after.x === requested.x &&
            after.y === requested.y &&
            after.width === requested.width &&
            after.height === requested.height
        );

        return {
            success: true,
            stableSequence: sequence,
            title: this._safeCall(() => metaWindow.get_title(), ''),
            requested,
            before,
            after,
            exact,
            error: null,
        };
    }

    _serializeWindow(metaWindow, stableSequence) {
        const frameRect = this._safeCall(() => metaWindow.get_frame_rect(), null);
        const bufferRect = this._safeCall(() => metaWindow.get_buffer_rect(), null);
        const monitorIndex = this._safeCall(() => metaWindow.get_monitor(), 0);
        const workspaceIndex = this._safeCall(
            () => metaWindow.get_workspace()?.index() ?? 0,
            0
        );

        const frame = this._geometryFromRect(frameRect);
        const buffer = this._geometryFromRect(bufferRect);

        return {
            stableSequence,
            title: this._safeCall(() => metaWindow.get_title(), ''),
            wmClass: this._safeCall(() => metaWindow.get_wm_class(), ''),
            wmClassInstance: this._safeCall(() => metaWindow.get_wm_class_instance(), ''),
            pid: this._safeCall(() => metaWindow.get_pid(), 0),
            appId: this._safeCall(() => metaWindow.get_gtk_application_id(), ''),
            appName: this._resolveAppName(metaWindow),
            monitorIndex,
            workspaceIndex,
            frame,
            buffer,
            relative: {
                x: frame.x,
                y: frame.y,
            },
            isMaximized: this._safeCall(() => metaWindow.get_maximized() !== 0, false),
            isFullscreen: this._safeCall(() => metaWindow.is_fullscreen(), false),
            isActive: this._safeCall(() => metaWindow.has_focus(), false),
        };
    }

    _resolveAppName(metaWindow) {
        const tracker = Shell.WindowTracker.get_default();
        const app = this._safeCall(() => tracker.get_window_app(metaWindow), null);

        if (!app)
            return '';

        return this._safeCall(() => app.get_name(), '');
    }

    _findWindowByStableSequence(stableSequence) {
        const targetSequence = String(stableSequence ?? '').trim();
        const actors = this._safeCall(() => global.get_window_actors(), []);

        for (const actor of actors) {
            const metaWindow = this._safeCall(() => actor.get_meta_window(), null);
            if (!metaWindow)
                continue;

            const currentSequence = String(this._safeCall(
                () => metaWindow.get_stable_sequence(),
                ''
            )).trim();

            if (currentSequence === targetSequence)
                return metaWindow;
        }

        return null;
    }

    _validateMoveResizeRequest(stableSequence, requested) {
        if (!stableSequence)
            throw new Error('A stableSequence da janela deve ser informada.');

        if (!Number.isInteger(requested.x) || !Number.isInteger(requested.y))
            throw new Error('As coordenadas x e y devem ser números inteiros.');

        if (!Number.isInteger(requested.width) || !Number.isInteger(requested.height))
            throw new Error('A largura e altura devem ser números inteiros.');

        if (requested.width <= 0 || requested.height <= 0)
            throw new Error('A largura e altura devem ser maiores que zero.');
    }

    _requestedGeometry(x, y, width, height) {
        return {
            x: Number(x),
            y: Number(y),
            width: Number(width),
            height: Number(height),
        };
    }

    _geometryFromRect(rect) {
        if (!rect) {
            return {
                x: 0,
                y: 0,
                width: 0,
                height: 0,
            };
        }

        return {
            x: Number(rect.x ?? 0),
            y: Number(rect.y ?? 0),
            width: Number(rect.width ?? 0),
            height: Number(rect.height ?? 0),
        };
    }

    _moveResizeFailure(stableSequence, requested, errorMessage) {
        return {
            success: false,
            stableSequence,
            title: '',
            requested,
            before: this._geometryFromRect(null),
            after: this._geometryFromRect(null),
            exact: false,
            error: errorMessage,
        };
    }

    _safeCall(action, fallbackValue) {
        try {
            return action();
        } catch (_error) {
            return fallbackValue;
        }
    }
}
