import Gio from 'gi://Gio';
import Shell from 'gi://Shell';
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
  </interface>
</node>`;

export default class PosiXExtension extends Extension {
    enable() {
        this._ownerId = 0;
        this._dbusObject = null;
        this._connection = null;

        this._log('extensão habilitada');

        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            this._onBusAcquired.bind(this),
            this._onNameAcquired.bind(this),
            this._onNameLost.bind(this)
        );
    }

    disable() {
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
