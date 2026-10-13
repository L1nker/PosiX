# Análise de Engenharia Reversa: Sizer 4.0 (Build 673)

**Arquivo analisado:** `docs/4.0.673.msi`  
**Autor original:** Brian Apps ([www.brianapps.net/sizer4](http://www.brianapps.net/sizer4))  
**Data da análise:** 13/10/2026  
**Ambiente de análise:** Zorin OS (Linux x86_64)

---

## 1. Visão Geral e Estrutura do Pacote

O instalador `4.0.673.msi` é um pacote Windows Installer gerado com o **WiX Toolset (v3.14)**. Dentro do arquivo interno `product.cab`, foram extraídos e analisados cinco componentes:

| Arquivo | Tamanho | Arquitetura | Propósito |
| :--- | :--- | :--- | :--- |
| `sizer.exe` | 221 KB | PE32 (x86 32-bit GUI) | Processo principal, interface de configuração, bandeja, hotkeys e motor de macros. |
| `hook32.dll` | 6 KB | PE32 (x86 DLL) | DLL de injeção global para interceptar eventos de janelas de 32 bits. |
| `hook64.dll` | 6 KB | PE32+ (x64 DLL) | DLL de injeção global para interceptar eventos de janelas de 64 bits. |
| `Stub64.dat` | 4.6 KB | PE32+ (x64 Executável) | Helper process de 64 bits responsável por carregar `hook64.dll` no ecossistema x64. |
| `ReadMe.txt` | 1.2 KB | Texto ASCII | Licença BSD-style do autor Brian Apps (1997–2020). |

---

## 2. Arquitetura de Interceptação de Janelas (Hooks & IPC)

O maior desafio técnico em sistemas Windows ao manipular janelas de outros programas é que processos de 32 bits não conseguem injetar código diretamente em processos de 64 bits. Brian Apps resolveu isso com extrema elegância:

```
[ sizer.exe (32-bit) ] 
       │ 
       ├──> Injeta hook32.dll via SetWindowsHookEx (em processos 32-bit)
       │ 
       └──> Dispara Stub64.dat (64-bit) passando HWND
                 │
                 └──> Injeta hook64.dll via SetWindowsHookEx (em processos 64-bit)
```

### Detalhes das DLLs de Gancho (`hook32.dll` e `hook64.dll`):
- **Funções Exportadas:**
  - `InstallHook(HWND hwndMaster)`
  - `RemoveHook()`
  - `GetSharedMessageEvent()`
  - `PopSharedMessage(MSG* msg)`
- **Tipos de Hook Utilizados:**
  1. `WH_CALLWNDPROC` (ID 4): Intercepta chamadas diretas de mensagens entre janelas.
  2. `WH_GETMESSAGE` (ID 3): Intercepta mensagens postadas na fila de eventos da aplicação.
- **Mensagens Monitoradas no Gancho:**
  - `WM_NCHITTEST` (`0x84`): Identifica a posição do mouse sobre bordas e quinas da janela (`HTLEFT`, `HTRIGHT`, `HTTOP`, `HTTOPLEFT`, `HTBOTTOMRIGHT`, etc.).
  - `WM_NCRBUTTONUP` (`0x00A5`): Disparado ao soltar o **botão direito do mouse** sobre a borda de redimensionamento ou barra de título.
  - `WM_SIZING` (`0x0214`): Monitora o redimensionamento em tempo real enquanto o usuário arrasta a janela.
  - `WM_ENTERSIZEMOVE` (`0x0231`) e `WM_EXITSIZEMOVE` (`0x0232`): Identificam início e término do reposicionamento.
- **Detecção de Cursor de Redimensionamento:**
  - O gancho verifica se o cursor atual é um cursor de dimensionamento (`IDC_SIZENWSE`, `IDC_SIZEWE`, etc.). Se for e o usuário clicar com o botão direito, o Sizer abre o menu instantaneamente!
- **Comunicação Inter-Processos (IPC):**
  - Objeto de memória compartilhada: `SIZER_SHARED_MEMORY`
  - Mutex de sincronização: `SIZER_SHARED_MUTEX`
  - Evento de sinalização de disparo: `SIZER_SHARED_EVENT`

---

## 3. Gatilhos de Interação do Usuário

O Sizer 4.0 oferece quatro formas distintas de acionamento:

1. **Clique de Botão Direito na Borda/Quina da Janela:**
   - Abre o menu flutuante exatamente onde o cursor está.
   - Aplica a opção `adjustOppositeEdge`: redimensiona mantendo a quina oposta ao cursor fixa no lugar.
2. **Atalho de Teclado Global (Hotkey):**
   - Padrão: `Ctrl + Win + Z` (configurável com modificadores Shift, Ctrl, Win, Alt).
   - Abre o menu de redimensionamento para a janela que estiver ativa no momento.
   - Cada preset ou macro individual pode ter seu próprio atalho exclusivo.
3. **Bandeja do Sistema (System Tray):**
   - Ícone na barra de tarefas para acesso rápido a presets e para abrir a janela de configurações (`-config`).
4. **Linha de Comando (CLI):**
   - `sizer.exe -config`: Abre a tela de configuração.
   - `sizer.exe -popup`: Abre o menu popup na posição atual do mouse.
   - `sizer.exe -execute "<nome>"`: Executa um preset ou macro diretamente via script ou terminal.

---

## 4. Sistema de Configuração (`sizer.xml`)

O Sizer 4.0 substituiu os antigos arquivos `.ini` por um formato XML limpo.

### Template XML Padrão Embutido:
```xml
<sizer>
  <options showIconInTray="1" adjustOppositeEdge="0" tooltipOption="1" hotKey="90" hotKeyModifiers="10" hotKeyExtended="0"/>
  <menu>
    <resize description="640×480" width="640" height="480" />
    <resize description="800×600" width="800" height="600" />
    <resize description="1024×768" width="1024" height="768" />
    <resize description="1152×864" width="1152" height="864" />
    <resize description="1280×960" width="1280" height="960" />
    <separator />
    <group description="4:3">
      <resize description="320×240" width="320" height="240" />
      <resize description="640×480" width="640" height="480" />
      <resize description="800×600" width="800" height="600" />
      <resize description="1024×768" width="1024" height="768" />
      <resize description="1152×864" width="1152" height="864" />
      <resize description="1280×960" width="1280" height="960" />
      <resize description="1400×1050" width="1400" height="1050" />
      <resize description="1600×1200" width="1600" height="1200" />
    </group>
    <group description="16:9">
      <resize description="852×480" width="852" height="480" />
      <resize description="1280×720" width="1280" height="720" />
      <resize description="1365×768" width="1365" height="768" />
      <resize description="1600×900" width="1600" height="900" />
      <resize description="1920×1080" width="1920" height="1080" />
    </group>
    <group description="16:10">
      <resize description="320×200" width="320" height="200" />
      <resize description="640×400" width="640" height="400" />
      <resize description="1280×800" width="1280" height="800" />
      <resize description="1440×900" width="1440" height="900" />
      <resize description="1680×1050" width="1680" height="1050" />
      <resize description="1920×1200" width="1920" height="1200" />
    </group>
    <group description="YouTube">
      <resize description="2160p" width="3840" height="2160" />
      <resize description="1440p" width="2560" height="1440" />
      <resize description="1080p" width="1920" height="1080" />
      <resize description="720p" width="1280" height="720" />
      <resize description="480p" width="854" height="480" />
      <resize description="360p" width="640" height="360" />
      <resize description="240p" width="426" height="240" />
    </group>    
    <separator />
    <template />
    <configDialog />
  </menu>
</sizer>
```

---

## 5. Linguagem de Macros e Filtros de Janelas (DSL Interna)

O Sizer 4.0 contém um **interpretador de scripts próprio** para macros:

### Sintaxe de Filtros de Janela:
- `win[cap="texto"]`: Filtro por título / caption da janela.
- `win[proc="executavel.exe"]`: Filtro pelo nome do executável/processo.
- `win[desktop=N]`: Filtro por área de trabalho virtual.
- `win[active]`, `win[last]`, `win[0]`, `win[1]`: Qualificadores ordinais de janela.

### Sintaxe de Coordenadas e Dimensões:
- Atribuições: `w = 1024`, `h = 768`, `l = 0`, `t = 0`.
- Referências:
  - `mon[active].workarea.w` (largura útil do monitor ativo sem a barra de tarefas).
  - `mon[primary].workarea` (monitor primário).
  - `win.client` (área interna útil da janela sem as bordas).
  - `win` (geometria total com decorações).
- Estados de Janela:
  - `maximize`, `restore`, `minimize`.
- Opções do Motor:
  - `option compensate_frame_effects on/off` (compensa bordas transparentes do DWM no Windows 10/11).
  - `option ignore_runtime_errors on/off`.

---

## 6. Feedback Visual em Tempo Real (Tooltip de Redimensionamento)

Quando o usuário arrasta qualquer borda com o mouse enquanto o Sizer está ativo, o Sizer intercepta `WM_SIZING` e cria uma janela temporária do tipo `tooltips_class32`:
- Exibe em tempo real o retângulo atual:
  `Pos: (X, Y)   Size: L × A`
- Esse feedback visual dá ao usuário a precisão exata de onde e como a janela está se comportando antes de soltar o clique.

---

## 7. Mapeamento & Inspirações para o PosiX no Linux (GNOME / Zorin OS)

| Recurso do Sizer 4.0 (Windows) | Equivalente Técnico no Linux / GNOME (PosiX) | Status no PosiX |
| :--- | :--- | :--- |
| **Menu de Contexto na Janela** | Monkey-patch no `WindowMenu` da extensão do GNOME Shell | ✅ Já implementado no PosiX |
| **Bandeja do Sistema (Tray)** | `PanelMenu.Button` na barra superior do GNOME | ✅ Já implementado no PosiX |
| **Linha de Comando (-config, etc.)** | `python3 -m posix_app` e chamadas D-Bus | ✅ Já implementado no PosiX |
| **Regras por Processo e Título** | `rules_engine.py` com matching inteligente | ✅ Já implementado no PosiX |
| **Grupos e Subpastas no Menu** | Suporte a categorias hierárquicas no `presets.json` | 💡 Oportunidade de expansão |
| **Tooltip com Dimensões em Tempo Real** | OSD / Clutter Actor no GNOME Shell ao redimensionar | 💡 Oportunidade de expansão |
| **Preset só de Posicionar ("Don't resize")**| Presets com largura/altura opcionais (apenas move X/Y) | 💡 Oportunidade de expansão |
| **Atalhos de Teclado Globais por Preset** | Keybindings D-Bus registrados no GNOME Shell | 💡 Oportunidade de expansão |
