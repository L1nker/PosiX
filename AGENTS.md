# Instruções para agentes do projeto PosiX

Este arquivo registra regras permanentes para qualquer agente de programação que trabalhe no projeto.

## Identidade do projeto

- Nome oficial do aplicativo: PosiX.
- Nome de apresentação: PosiX by Linker.
- Foco principal: Zorin OS com GNOME.
- Português do Brasil é o idioma principal.
- Inglês será um idioma opcional.

## Ambiente atual de desenvolvimento

- Zorin OS 18.1.
- GNOME Shell 46.
- Mutter 46.
- Python 3.12.
- GTK 4.
- Libadwaita.
- GJS.
- Git.

## Diretrizes técnicas

- O aplicativo deverá funcionar em sessões X11 e Wayland.
- Não sacrificar integração com o Zorin para tentar oferecer compatibilidade genérica com todas as distribuições.
- A interface gráfica deverá usar GTK 4 e Libadwaita.
- A integração com o GNOME Shell deverá usar GJS.
- O controle de janelas deverá usar diretamente a API do Mutter por meio de uma extensão do GNOME Shell.
- `wmctrl`, `xdotool`, `xprop` e `xrandr` podem ser usados para diagnóstico e protótipos X11, mas não devem ser considerados fonte principal de geometria no aplicativo definitivo.
- A geometria oficial de uma janela deverá ser obtida por `Meta.Window.get_frame_rect()`.
- Não usar o buffer rect como posição visual da janela.
- O sistema deve aceitar coordenadas negativas.
- O sistema deve trabalhar com múltiplos monitores.
- A posição apresentada ao usuário deverá ser relativa ao monitor escolhido.
- Internamente poderão ser mantidas também coordenadas globais.
- O monitor não deve ser identificado somente pelo fato de estar marcado como principal.
- O sistema deverá considerar nome, fabricante, modelo, resolução, posição e outras propriedades disponíveis do monitor.
- Não usar `posix` como nome de módulo ou pacote Python, porque já existe um módulo interno com esse nome.

## Regras de segurança e manutenção

- Não instalar dependências nem alterar o sistema sem autorização explícita.
- Não apagar arquivos, reescrever histórico Git, usar force push ou modificar commits anteriores sem autorização.
- Preferir mudanças pequenas, testáveis e com commits claros.
- Antes de movimentar uma janela, validar cuidadosamente título, classe, aplicação e outros identificadores.
- Nunca testar movimentação em uma janela pessoal do usuário quando puder ser usada uma janela de teste controlada.
- Preservar os protótipos existentes como registro técnico, salvo autorização para alterá-los.

## Conclusões já comprovadas

- A extensão do GNOME Shell conseguiu identificar uma janela específica.
- `Meta.Window.move_resize_frame(true, ...)` conseguiu aplicar posição e tamanho exatos.
- Coordenadas negativas funcionaram.
- A restauração da posição e tamanho funcionou sem diferença.
- O frame rect de uma janela visualmente em um canto foi corretamente registrado como X=0 e Y=0.
- O `wmctrl` apresentou deslocamentos por trabalhar com geometria X11/buffer e não deverá ser usado como referência visual definitiva.
