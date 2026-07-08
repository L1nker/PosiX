import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const TITULO_ALVO = 'PosiX - Janela de Teste X11';
const WM_CLASS_ALVO = 'testar_movimento_x11.py';
const GEOMETRIA_SOLICITADA = {x: -180, y: 120, width: 900, height: 600};
const PREFIXO_LOG = '[PosiX Teste]';

function registrar(mensagem) {
    console.log(`${PREFIXO_LOG} ${mensagem}`);
}

function retanguloParaTexto(retangulo) {
    if (!retangulo)
        return '-';

    return `X=${retangulo.x} Y=${retangulo.y} L=${retangulo.width} A=${retangulo.height}`;
}

function diferencas(solicitada, obtida) {
    return {
        x: obtida.x - solicitada.x,
        y: obtida.y - solicitada.y,
        width: obtida.width - solicitada.width,
        height: obtida.height - solicitada.height,
    };
}

function diferencasParaTexto(diff) {
    return `dX=${diff.x}, dY=${diff.y}, dL=${diff.width}, dA=${diff.height}`;
}

function chamarRetangulo(janela, metodo) {
    if (typeof janela[metodo] !== 'function')
        return null;

    try {
        return janela[metodo]();
    } catch (erro) {
        registrar(`Erro ao chamar ${metodo}: ${erro.message}`);
        return null;
    }
}

function permiteParaTexto(valor) {
    if (valor === null)
        return 'indisponivel';

    return valor ? 'sim' : 'nao';
}

function chamarBooleano(janela, metodo) {
    if (typeof janela[metodo] !== 'function')
        return null;

    try {
        return janela[metodo]();
    } catch (erro) {
        registrar(`Erro ao chamar ${metodo}: ${erro.message}`);
        return null;
    }
}

function lerBooleano(janela, nome) {
    if (typeof janela[nome] === 'boolean')
        return janela[nome];

    return chamarBooleano(janela, nome);
}

function estadoMaximizadoParaTexto(janela) {
    if (typeof janela.get_maximized === 'function') {
        try {
            return String(janela.get_maximized());
        } catch (erro) {
            registrar(`Erro ao chamar get_maximized: ${erro.message}`);
        }
    }

    const horizontal = lerBooleano(janela, 'maximized_horizontally');
    const vertical = lerBooleano(janela, 'maximized_vertically');
    return `horizontal=${permiteParaTexto(horizontal)}, vertical=${permiteParaTexto(vertical)}`;
}

function registrarGeometriasDaJanela(janela, contexto) {
    const frame = chamarRetangulo(janela, 'get_frame_rect');
    const buffer = chamarRetangulo(janela, 'get_buffer_rect');
    const cliente = chamarRetangulo(janela, 'get_client_content_rect');
    const monitor = janela.get_monitor();
    let geometriaMonitor = null;
    let areaUtil = null;

    try {
        geometriaMonitor = global.display.get_monitor_geometry(monitor);
    } catch (erro) {
        registrar(`Erro ao obter geometria completa do monitor ${monitor}: ${erro.message}`);
    }

    try {
        areaUtil = janela.get_work_area_for_monitor(monitor);
    } catch (erro) {
        registrar(`Erro ao obter area util do monitor ${monitor}: ${erro.message}`);
    }

    registrar(`${contexto} - frame rect: ${retanguloParaTexto(frame)}`);
    registrar(`${contexto} - buffer rect: ${retanguloParaTexto(buffer)}`);
    registrar(`${contexto} - client content rect: ${retanguloParaTexto(cliente)}`);
    registrar(`${contexto} - monitor: ${monitor}`);
    registrar(`${contexto} - geometria completa do monitor: ${retanguloParaTexto(geometriaMonitor)}`);
    registrar(`${contexto} - area util do monitor: ${retanguloParaTexto(areaUtil)}`);

    return {frame, buffer, cliente, monitor, geometriaMonitor, areaUtil};
}

function contemClasseAlvo(janela) {
    const classe = janela.get_wm_class?.() ?? '';
    const instancia = janela.get_wm_class_instance?.() ?? '';

    return classe.includes(WM_CLASS_ALVO) || instancia.includes(WM_CLASS_ALVO);
}

function classeParaTexto(janela) {
    const classe = janela.get_wm_class?.() ?? '-';
    const instancia = janela.get_wm_class_instance?.() ?? '-';

    if (classe === instancia)
        return classe;

    return `${instancia}, ${classe}`;
}

function monitorParaTexto(janela) {
    const indice = janela.get_monitor();
    let geometria = null;

    try {
        geometria = global.display.get_monitor_geometry(indice);
    } catch (erro) {
        registrar(`Nao foi possivel obter geometria do monitor ${indice}: ${erro.message}`);
    }

    if (!geometria)
        return `monitor ${indice}`;

    return `monitor ${indice} (${retanguloParaTexto(geometria)})`;
}

const IndicadorPosiX = GObject.registerClass(
class IndicadorPosiX extends PanelMenu.Button {
    _init(extensao) {
        super._init(0.0, 'PosiX Teste');
        this._extensao = extensao;

        const box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        box.add_child(new St.Label({text: 'PosiX Teste'}));
        this.add_child(box);

        this.menu.addAction('Executar teste na janela PosiX', () => {
            this._extensao.executarTeste();
        });
        this.menu.addAction('Restaurar janela', () => {
            this._extensao.restaurarAgora();
        });
        this.menu.addAction('Mostrar último resultado', () => {
            this._extensao.mostrarUltimoResultado();
        });
    }
});

export default class PosiXTesteExtension extends Extension {
    enable() {
        this._indicador = new IndicadorPosiX(this);
        this._geometriaOriginal = null;
        this._janelaAlvo = null;
        this._ultimoResultado = 'Nenhum teste executado ainda.';
        this._timeoutConfirmarMovimento = 0;
        this._timeoutRestaurar = 0;
        this._timeoutConfirmarRestauracao = 0;

        Main.panel.addToStatusArea(this.uuid, this._indicador);
        registrar('Extensao habilitada.');
    }

    disable() {
        this._removerTimeouts();

        if (this._indicador) {
            this._indicador.destroy();
            this._indicador = null;
        }

        this._janelaAlvo = null;
        registrar('Extensao desabilitada.');
    }

    _notificar(mensagem) {
        this._ultimoResultado = mensagem;
        registrar(mensagem);
        Main.notify('PosiX Teste', mensagem);
    }

    _removerTimeouts() {
        for (const id of [
            this._timeoutConfirmarMovimento,
            this._timeoutRestaurar,
            this._timeoutConfirmarRestauracao,
        ]) {
            if (id)
                GLib.source_remove(id);
        }

        this._timeoutConfirmarMovimento = 0;
        this._timeoutRestaurar = 0;
        this._timeoutConfirmarRestauracao = 0;
    }

    _localizarJanelaAlvo() {
        const candidatas = global.get_window_actors()
            .map(ator => ator.meta_window)
            .filter(janela => janela && !(janela.is_override_redirect?.() ?? false))
            .filter(janela => janela.get_title() === TITULO_ALVO)
            .filter(janela => contemClasseAlvo(janela));

        if (candidatas.length !== 1) {
            const mensagem = candidatas.length === 0
                ? 'Teste abortado: nenhuma janela PosiX com titulo e WM_CLASS esperados foi encontrada.'
                : `Teste abortado: ${candidatas.length} janelas PosiX candidatas foram encontradas.`;
            this._notificar(mensagem);
            return null;
        }

        return candidatas[0];
    }

    executarTeste() {
        this._removerTimeouts();

        const janela = this._localizarJanelaAlvo();
        if (!janela)
            return;

        this._janelaAlvo = janela;
        this._geometriaOriginal = janela.get_frame_rect();

        const titulo = janela.get_title();
        const classe = classeParaTexto(janela);
        const pid = janela.get_pid();
        const monitor = monitorParaTexto(janela);
        const maximizada = estadoMaximizadoParaTexto(janela);
        const permiteMover = chamarBooleano(janela, 'allows_move');
        const permiteRedimensionar = chamarBooleano(janela, 'allows_resize');

        registrar(`Titulo: ${titulo}`);
        registrar(`WM_CLASS: ${classe}`);
        registrar(`PID: ${pid}`);
        registrar(`Monitor: ${monitor}`);
        registrar(`Estado maximizado: ${maximizada}`);
        registrar(`Permite movimento: ${permiteParaTexto(permiteMover)}`);
        registrar(`Permite redimensionamento: ${permiteParaTexto(permiteRedimensionar)}`);
        registrarGeometriasDaJanela(janela, 'Antes do movimento');
        registrar(`Geometria original capturada: ${retanguloParaTexto(this._geometriaOriginal)}`);
        registrar(`Geometria solicitada: ${retanguloParaTexto(GEOMETRIA_SOLICITADA)}`);

        janela.move_resize_frame(
            true,
            GEOMETRIA_SOLICITADA.x,
            GEOMETRIA_SOLICITADA.y,
            GEOMETRIA_SOLICITADA.width,
            GEOMETRIA_SOLICITADA.height
        );

        this._notificar('Teste iniciado: geometria solicitada via Mutter.');

        this._timeoutConfirmarMovimento = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 700, () => {
            this._timeoutConfirmarMovimento = 0;
            this._confirmarMovimento();
            return GLib.SOURCE_REMOVE;
        });
    }

    _confirmarMovimento() {
        if (!this._janelaAlvo) {
            this._notificar('Nao foi possivel confirmar o movimento: janela alvo ausente.');
            return;
        }

        const geometrias = registrarGeometriasDaJanela(this._janelaAlvo, 'Depois do movimento');
        const obtida = geometrias.frame;
        if (!obtida) {
            this._notificar('Nao foi possivel obter frame rect depois do movimento.');
            return;
        }

        const diff = diferencas(GEOMETRIA_SOLICITADA, obtida);

        registrar(`Frame rect realmente obtido: ${retanguloParaTexto(obtida)}`);
        registrar(`Diferencas solicitada/frame obtido: ${diferencasParaTexto(diff)}`);

        this._notificar(
            `Frame obtido: ${retanguloParaTexto(obtida)} | ${diferencasParaTexto(diff)}`
        );

        this._timeoutRestaurar = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
            this._timeoutRestaurar = 0;
            this._restaurarJanela('automatica');
            return GLib.SOURCE_REMOVE;
        });
    }

    restaurarAgora() {
        this._restaurarJanela('manual');
    }

    _restaurarJanela(origem) {
        if (!this._janelaAlvo || !this._geometriaOriginal) {
            this._notificar('Nao ha geometria original capturada para restaurar.');
            return;
        }

        if (this._timeoutRestaurar) {
            GLib.source_remove(this._timeoutRestaurar);
            this._timeoutRestaurar = 0;
        }

        registrar(`Restauracao ${origem}: ${retanguloParaTexto(this._geometriaOriginal)}`);
        this._janelaAlvo.move_resize_frame(
            true,
            this._geometriaOriginal.x,
            this._geometriaOriginal.y,
            this._geometriaOriginal.width,
            this._geometriaOriginal.height
        );

        this._timeoutConfirmarRestauracao = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 700, () => {
            this._timeoutConfirmarRestauracao = 0;
            this._confirmarRestauracao();
            return GLib.SOURCE_REMOVE;
        });
    }

    _confirmarRestauracao() {
        if (!this._janelaAlvo || !this._geometriaOriginal) {
            this._notificar('Nao foi possivel confirmar a restauracao: janela alvo ausente.');
            return;
        }

        const restaurada = this._janelaAlvo.get_frame_rect();
        const diff = diferencas(this._geometriaOriginal, restaurada);

        registrar(`Geometria restaurada: ${retanguloParaTexto(restaurada)}`);
        registrar(`Diferencas original/restaurada: ${diferencasParaTexto(diff)}`);

        this._notificar(
            `Restaurada: ${retanguloParaTexto(restaurada)} | ${diferencasParaTexto(diff)}`
        );
    }

    mostrarUltimoResultado() {
        this._notificar(this._ultimoResultado);
    }
}
