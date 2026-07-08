import Gio from 'gi://Gio';
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
}
