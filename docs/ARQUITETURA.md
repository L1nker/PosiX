# Arquitetura planejada do PosiX

Este documento descreve a arquitetura planejada para o PosiX. A implementação ainda está em fase inicial e algumas decisões serão validadas em provas de conceito futuras.

## Componentes principais

### Componente 1 - Aplicativo principal

O aplicativo principal será responsável pela experiência do usuário e pelo gerenciamento dos dados.

- Python 3.
- PyGObject.
- GTK 4.
- Libadwaita.
- Interface e gerenciamento de presets.
- Configurações.
- Traduções.
- Grupos de trabalho.
- Persistência de dados.

### Componente 2 - Extensão do GNOME Shell

A extensão será responsável pela integração direta com o GNOME Shell e com a API do Mutter.

- GJS.
- API do Mutter.
- Captura e movimentação de janelas.
- Leitura de frame rect.
- Indicador no painel.
- Suporte ao X11 e Wayland dentro do GNOME.

### Componente 3 - Comunicação

A comunicação entre aplicativo e extensão é planejada por D-Bus.

- O aplicativo envia comandos para a extensão.
- A extensão retorna janelas, geometrias e resultados.
- Os contratos de comunicação devem ser claros.
- Todos os dados recebidos devem ser validados antes de uso.
- Erros devem ser retornados de forma estruturada.

### Componente 4 - Persistência

A decisão definitiva entre JSON e SQLite ainda não deve ser fechada.

#### JSON

Vantagens:

- Simples de ler e inspecionar.
- Fácil de versionar em fases iniciais.
- Bom para protótipos e configurações pequenas.

Desvantagens:

- Mais frágil para alterações concorrentes.
- Consultas e filtros exigem leitura e processamento manual.
- Migrações podem ficar mais trabalhosas conforme o modelo crescer.

#### SQLite

Vantagens:

- Estrutura mais robusta para presets, grupos, monitores e histórico.
- Consultas e filtros mais confiáveis.
- Melhor caminho para migrações controladas.
- Boa opção para aplicação local sem servidor.

Desvantagens:

- Exige modelagem inicial mais cuidadosa.
- Menos transparente para edição manual.
- Pode ser excesso para protótipos muito pequenos.

Recomendação atual: usar SQLite na aplicação definitiva, mantendo a decisão aberta até a validação do núcleo de dados.

## Fluxo para capturar uma janela

1. Usuário solicita a captura pelo aplicativo.
2. Aplicativo envia comando para a extensão via D-Bus.
3. Extensão identifica a janela alvo de forma controlada.
4. Extensão coleta título, aplicação, classe, monitor e `Meta.Window.get_frame_rect()`.
5. Extensão retorna os dados ao aplicativo.
6. Aplicativo apresenta os dados ao usuário para revisão.
7. Usuário salva um novo preset ou atualiza um preset existente.

## Fluxo para restaurar um preset

1. Usuário escolhe um preset.
2. Aplicativo envia a regra de identificação e a geometria desejada para a extensão.
3. Extensão procura janelas correspondentes.
4. Extensão valida título, classe, aplicação e outros identificadores disponíveis.
5. Se nenhuma janela for encontrada, a extensão retorna erro informativo.
6. Se houver múltiplas correspondências, o aplicativo solicita desambiguação ou aplica uma regra previamente definida.
7. Extensão aplica a restauração com `Meta.Window.move_resize_frame(true, ...)`.
8. Extensão retorna sucesso, erro ou diferença encontrada.

## Fluxo para restaurar um grupo

1. Usuário escolhe um grupo pelo aplicativo ou, futuramente, pelo painel.
2. Aplicativo resolve a lista de presets do grupo.
3. Aplicativo envia comandos de restauração para a extensão.
4. Extensão processa cada preset e retorna resultados individuais.
5. Aplicativo apresenta um resumo com sucessos, janelas ausentes e conflitos.

## Estratégia para identificar janelas

A identificação de janelas deve combinar vários sinais, evitando depender de um único campo.

- Título exato.
- Título contendo texto.
- Título iniciando com texto.
- Expressão regular, em fase futura.
- Classe da janela.
- Aplicação associada.
- Identificadores disponibilizados pelo GNOME Shell ou Mutter.

Antes de mover uma janela, a extensão deve validar cuidadosamente os identificadores disponíveis. Quando houver risco de mover a janela errada, o sistema deve pedir confirmação ou bloquear a ação.

## Estratégia para identificar monitores

O monitor não deve ser identificado somente por estar marcado como principal.

Devem ser considerados:

- Nome.
- Fabricante.
- Modelo.
- Resolução.
- Posição no layout global.
- Escala, quando disponível.
- Outras propriedades expostas pelo GNOME Shell, Mutter ou APIs relacionadas.

Quando um monitor não estiver disponível, o sistema deve informar o problema e, futuramente, permitir escolher um monitor substituto.

## Coordenadas globais e relativas

Coordenadas globais representam a posição da janela no espaço total do desktop, considerando todos os monitores. Nesse espaço, coordenadas negativas podem existir quando um monitor está posicionado à esquerda ou acima do monitor de referência.

Coordenadas relativas representam a posição da janela dentro do monitor escolhido. Essa é a forma preferida para apresentar a posição ao usuário, porque faz mais sentido visualmente.

O PosiX pode manter os dois tipos internamente:

- Coordenadas globais para restauração precisa.
- Coordenadas relativas para exibição, edição e adaptação a mudanças de monitores.

## Tratamento de coordenadas negativas

Coordenadas negativas devem ser aceitas e preservadas. Elas não indicam erro por si só; podem representar um monitor posicionado à esquerda ou acima de outro monitor.

A validação deve distinguir coordenadas negativas válidas de geometrias impossíveis ou fora de qualquer monitor conhecido.

## Riscos técnicos

- Mudanças em APIs do GNOME Shell ou Mutter.
- Diferenças de comportamento entre X11 e Wayland.
- Identificação incorreta de janelas com títulos dinâmicos.
- Conflitos ao restaurar várias janelas ao mesmo tempo.
- Alterações no layout de monitores entre captura e restauração.
- Permissões e restrições de comunicação entre aplicativo e extensão.

## Limitações conhecidas

- O aplicativo gráfico final ainda não existe.
- A comunicação D-Bus ainda não foi implementada.
- A persistência definitiva ainda não foi escolhida.
- Os protótipos X11 usam ferramentas úteis para diagnóstico, mas não definem a geometria visual oficial.
- O comportamento completo em Wayland ainda precisa ser validado.

## Plano inicial de desenvolvimento por fases

### Fase 1 - Provas de conceito de geometria

Validar captura, leitura de frame rect, coordenadas negativas e restauração precisa com Mutter.

### Fase 2 - Comunicação D-Bus mínima

Criar um contrato inicial entre aplicativo e extensão para listar janelas e aplicar uma geometria.

### Fase 3 - Núcleo de dados e presets

Definir modelos de preset, janela, monitor e grupo. Validar persistência inicial.

### Fase 4 - Primeira interface GTK

Criar interface GTK 4 com Libadwaita para listar, salvar, editar e restaurar presets.

### Fase 5 - Grupos de trabalho e painel

Implementar grupos de trabalho e iniciar integração com indicador no painel.

### Fase 6 - Wayland e testes completos

Validar comportamento em Wayland, cobrir casos de múltiplos monitores e tratar falhas conhecidas.

### Fase 7 - Empacotamento e distribuição

Definir formato de empacotamento, documentar instalação e preparar distribuição inicial.
