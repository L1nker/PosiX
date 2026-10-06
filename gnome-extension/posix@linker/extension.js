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
    }

    disable() {
        this._unpatchWindowMenu();
        this._destroyIndicator();

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

            const presets = this._loadPresets();
            if (!Array.isArray(presets))
                return;

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
            const saveCurrentItem = new PopupMenu.PopupMenuItem('💾 Salvar Posição Desta Janela');
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

                for (const preset of presets) {
                    if (!preset || !preset.width || !preset.height) continue;
                    const label = `${preset.name || 'Tamanho'} (${preset.width}×${preset.height})`;
                    const item = new PopupMenu.PopupMenuItem(label);
                    item.connect('activate', () => {
                        try {
                            menu.close();
                        } catch (_) {}
                        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                            try {
                                this._applyPresetToWindow(window, preset);
                            } catch (e) {
                                this._log(`Erro ao aplicar preset: ${e.message}`);
                            }
                            return GLib.SOURCE_REMOVE;
                        });
                    });
                    subMenu.menu.addMenuItem(item);
                }
            }

            menu.addMenuItem(subMenu);
        } catch (error) {
            this._log(`Erro protegido ao injetar menu da janela: ${error.message}`);
        }
    }

    _loadPresets() {
        try {
            const dataDir = GLib.get_user_data_dir();
            const filePath = `${dataDir}/posix/presets.json`;
            const file = Gio.File.new_for_path(filePath);
            if (!file.query_exists(null))
                return this._fallbackPresets();

            const [, contents] = file.load_contents(null);
            const decoder = new TextDecoder('utf-8');
            const jsonText = decoder.decode(contents);
            const data = JSON.parse(jsonText);

            if (Array.isArray(data))
                return data;

            if (data && Array.isArray(data.presets))
                return data.presets;

            return this._fallbackPresets();
        } catch (_error) {
            return this._fallbackPresets();
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
        if (!this._indicator || !this._indicator.menu)
            return;

        this._indicator.menu.removeAll();

        // 1. Organizar Janelas (Destaque Principal)
        const organizeItem = new PopupMenu.PopupMenuItem('⚡ Organizar Janelas');
        organizeItem.connect('activate', () => {
            GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                this._organizeAllWindows();
                return GLib.SOURCE_REMOVE;
            });
        });
        this._indicator.menu.addMenuItem(organizeItem);

        // 2. Salvar Posição da Janela Ativa
        const saveActiveItem = new PopupMenu.PopupMenuItem('💾 Salvar Posição da Janela Ativa');
        saveActiveItem.connect('activate', () => {
            const focusWindow = global.display.focus_window;
            if (focusWindow) {
                GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                    this._saveWindowAsPreset(focusWindow);
                    return GLib.SOURCE_REMOVE;
                });
            } else {
                Main.notify('PosiX', 'Nenhuma janela em foco para capturar.');
            }
        });
        this._indicator.menu.addMenuItem(saveActiveItem);

        // 3. Abrir App PosiX
        const openItem = new PopupMenu.PopupMenuItem('Abrir Painel PosiX');
        openItem.connect('activate', () => {
            this._launchApp();
        });
        this._indicator.menu.addMenuItem(openItem);

        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const sectionHeader = new PopupMenu.PopupMenuItem('Redimensionar Janela Ativa:', {reactive: false});
        this._indicator.menu.addMenuItem(sectionHeader);

        const presets = this._loadPresets();
        for (const preset of presets) {
            const label = `  ${preset.name || 'Tamanho'} (${preset.width}×${preset.height})`;
            const item = new PopupMenu.PopupMenuItem(label);
            item.connect('activate', () => {
                this._applyPresetToActiveWindow(preset);
            });
            this._indicator.menu.addMenuItem(item);
        }
    }

    _launchApp() {
        try {
            const proc = new Gio.Subprocess({
                argv: ['bash', '-c', 'PYTHONPATH=/home/linker/GoogleDrive/AG_Projects/PosiX/src python3 -m posix_app'],
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
            const targetX = (preset.global_x !== null && preset.global_x !== undefined) ? preset.global_x : frame.x;
            const targetY = (preset.global_y !== null && preset.global_y !== undefined) ? preset.global_y : frame.y;

            // Descola com user_op = false para janelas restritas como PiP
            try {
                win.move_frame(false, targetX, targetY);
            } catch (_) {}

            win.move_resize_frame(false, targetX, targetY, preset.width, preset.height);
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

            const cmd = `PYTHONPATH=/home/linker/GoogleDrive/AG_Projects/PosiX/src python3 -c "from posix_app.storage import create_manual_preset; create_manual_preset('${escapedTitle}', ${frame.width}, ${frame.height}, ${frame.x}, ${frame.y}, ${monitor})"`;

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
            const cmd = `PYTHONPATH=/home/linker/GoogleDrive/AG_Projects/PosiX/src python3 -c '
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
        const difference = {
            x: after.x - requested.x,
            y: after.y - requested.y,
            width: after.width - requested.width,
            height: after.height - requested.height,
        };
        const exact = (
            difference.x === 0 &&
            difference.y === 0 &&
            difference.width === 0 &&
            difference.height === 0
        );

        return {
            success: true,
            stableSequence: sequence,
            before,
            requested,
            after,
            difference,
            exact,
            error: '',
        };
    }

    _findWindowByStableSequence(stableSequence) {
        const actors = this._safeCall(() => global.get_window_actors(), []);

        for (const actor of actors) {
            const metaWindow = this._safeCall(() => actor.get_meta_window(), null);
            if (!metaWindow)
                continue;

            const currentSequence = String(this._safeCall(
                () => metaWindow.get_stable_sequence(),
                ''
            ));
            if (currentSequence === stableSequence)
                return metaWindow;
        }

        return null;
    }

    _validateMoveResizeRequest(stableSequence, requested) {
        if (!stableSequence)
            throw new Error('stableSequence não pode ser vazia.');

        for (const key of ['x', 'y', 'width', 'height']) {
            if (!Number.isFinite(requested[key]) || !Number.isInteger(requested[key]))
                throw new Error(`Valor inválido para ${key}.`);
        }

        if (requested.width <= 0)
            throw new Error('width deve ser maior que zero.');

        if (requested.height <= 0)
            throw new Error('height deve ser maior que zero.');
    }

    _requestedGeometry(x, y, width, height) {
        return {
            x: Number(x),
            y: Number(y),
            width: Number(width),
            height: Number(height),
        };
    }

    _moveResizeFailure(stableSequence, requested, error) {
        return {
            success: false,
            stableSequence,
            before: null,
            requested,
            after: null,
            difference: null,
            exact: false,
            error,
        };
    }

    _serializeWindow(metaWindow, stableSequence) {
        const monitorIndex = this._safeCall(() => metaWindow.get_monitor(), -1);
        const frame = this._geometryFromRect(this._safeCall(
            () => metaWindow.get_frame_rect(),
            null
        ));
        const monitor = this._getMonitorGeometry(monitorIndex);
        const workArea = this._getWorkArea(metaWindow, monitorIndex);
        const app = this._getWindowApp(metaWindow);

        return {
            stableSequence,
            title: this._safeCall(() => metaWindow.get_title(), ''),
            wmClass: this._safeCall(() => metaWindow.get_wm_class(), ''),
            wmClassInstance: this._safeCall(() => metaWindow.get_wm_class_instance(), ''),
            pid: this._safeCall(() => metaWindow.get_pid(), -1),
            appId: app.id,
            appName: app.name,
            monitorIndex,
            workspaceIndex: this._getWorkspaceIndex(metaWindow),
            frame,
            monitor,
            workArea,
            relative: {
                x: frame.x - monitor.x,
                y: frame.y - monitor.y,
            },
            state: {
                maximized: this._safeCall(() => metaWindow.get_maximized(), 0) !== 0,
                fullscreen: this._safeCall(() => metaWindow.is_fullscreen(), false),
                minimized: this._safeCall(() => metaWindow.minimized, false),
                allowsMove: this._safeCall(() => metaWindow.allows_move(), false),
                allowsResize: this._safeCall(() => metaWindow.allows_resize(), false),
                skipTaskbar: this._safeCall(() => metaWindow.is_skip_taskbar(), false),
            },
            windowType: this._safeCall(() => metaWindow.get_window_type(), -1),
        };
    }

    _getWindowApp(metaWindow) {
        const tracker = this._safeCall(() => Shell.WindowTracker.get_default(), null);
        const app = tracker ? this._safeCall(() => tracker.get_window_app(metaWindow), null) : null;

        return {
            id: app ? this._safeCall(() => app.get_id(), '') : '',
            name: app ? this._safeCall(() => app.get_name(), '') : '',
        };
    }

    _getWorkspaceIndex(metaWindow) {
        const workspace = this._safeCall(() => metaWindow.get_workspace(), null);

        if (!workspace)
            return -1;

        return this._safeCall(() => workspace.index(), -1);
    }

    _getMonitorGeometry(monitorIndex) {
        if (monitorIndex < 0)
            return this._emptyGeometry();

        return this._geometryFromRect(this._safeCall(
            () => global.display.get_monitor_geometry(monitorIndex),
            null
        ));
    }

    _getWorkArea(metaWindow, monitorIndex) {
        if (monitorIndex < 0)
            return this._emptyGeometry();

        const workspace = this._safeCall(() => metaWindow.get_workspace(), null);

        if (workspace && typeof workspace.get_work_area_for_monitor === 'function') {
            return this._geometryFromRect(this._safeCall(
                () => workspace.get_work_area_for_monitor(monitorIndex),
                null
            ));
        }

        return this._emptyGeometry();
    }

    _geometryFromRect(rect) {
        if (!rect)
            return this._emptyGeometry();

        return {
            x: Number(rect.x ?? 0),
            y: Number(rect.y ?? 0),
            width: Number(rect.width ?? 0),
            height: Number(rect.height ?? 0),
        };
    }

    _emptyGeometry() {
        return {
            x: 0,
            y: 0,
            width: 0,
            height: 0,
        };
    }

    _safeCall(callback, fallback) {
        try {
            const value = callback();
            return value ?? fallback;
        } catch (_error) {
            return fallback;
        }
    }
}
