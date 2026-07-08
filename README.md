# PosiX by Linker

PosiX by Linker é um aplicativo em desenvolvimento para salvar e restaurar posições e dimensões de janelas no Zorin OS com GNOME.

O problema que o PosiX pretende resolver é simples: quem trabalha com muitas janelas, vários monitores ou layouts repetidos perde tempo reorganizando o ambiente manualmente. A proposta é permitir que o usuário salve a posição e o tamanho de janelas importantes e restaure esse arranjo depois, com precisão.

O público-alvo são usuários que trabalham com várias janelas e monitores, especialmente em fluxos de trabalho nos quais o mesmo conjunto de aplicativos precisa voltar sempre para os mesmos lugares.

## Estado atual

O projeto está em fase de prova de conceito. Ainda não existe aplicativo gráfico final, instalador ou fluxo de uso definitivo.

O repositório está em desenvolvimento inicial. As APIs, formatos de dados, interface e organização interna ainda podem mudar.

## Funcionalidades planejadas

- Capturar janelas abertas e registrar título, aplicação, classe, posição, tamanho e monitor.
- Salvar presets de posição e dimensão.
- Restaurar uma janela individual.
- Restaurar vários presets de uma vez.
- Criar grupos de trabalho para diferentes arranjos de janelas.
- Trabalhar com múltiplos monitores.
- Aceitar coordenadas negativas.
- Exibir uma interface simples em português do Brasil.
- Oferecer inglês como idioma opcional.
- Disponibilizar indicador no painel do GNOME para ações rápidas.

## Tecnologias planejadas

- Python 3.12.
- PyGObject.
- GTK 4.
- Libadwaita.
- GJS.
- GNOME Shell Extension.
- API do Mutter.
- D-Bus para comunicação entre aplicativo e extensão.
- Git.

## Estrutura atual das pastas

```text
.
├── gnome-extension/
│   └── posix-teste@linker/
│       ├── extension.js
│       └── metadata.json
├── prototipos/
│   ├── listar_janelas_x11.py
│   └── testar_movimento_x11.py
├── docs/
│   ├── ARQUITETURA.md
│   └── REQUISITOS.md
├── AGENTS.md
└── README.md
```

## Resultados já validados

Os testes com Mutter e a extensão do GNOME Shell validaram pontos essenciais para o projeto:

- A extensão conseguiu identificar uma janela específica.
- `Meta.Window.get_frame_rect()` registrou corretamente a posição visual da janela.
- Uma janela visualmente posicionada no canto foi registrada com X=0 e Y=0.
- `Meta.Window.move_resize_frame(true, ...)` aplicou posição e tamanho exatos.
- Coordenadas negativas funcionaram.
- A restauração de posição e tamanho funcionou sem diferença observada.
- O `wmctrl` apresentou deslocamentos por usar geometria X11/buffer, portanto não deve ser usado como referência visual definitiva no aplicativo final.

## Executando os protótipos atuais

Os protótipos atuais são registros técnicos da investigação inicial. Eles não representam o aplicativo final.

Para listar janelas em uma sessão X11:

```bash
python3 prototipos/listar_janelas_x11.py
```

Para testar movimentação de janela em uma sessão X11:

```bash
python3 prototipos/testar_movimento_x11.py
```

Use uma janela de teste controlada sempre que possível. Não use janelas pessoais ou com trabalho importante para testes de movimentação.
