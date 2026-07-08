# Requisitos do PosiX

Este documento organiza os requisitos iniciais do PosiX por categoria e prioridade.

## Classificação

- Essencial para a primeira versão: necessário para que o primeiro uso real do aplicativo seja viável.
- Importante: desejável para melhorar a experiência, a confiabilidade ou o fluxo de trabalho.
- Futuro: previsto para etapas posteriores, sem compromisso com a primeira versão.

## 1. Captura de janelas

| Requisito | Classificação |
| --- | --- |
| Selecionar uma janela. | Essencial para a primeira versão |
| Ler título, aplicativo, classe, posição, tamanho e monitor. | Essencial para a primeira versão |
| Diferenciar várias janelas do mesmo aplicativo. | Essencial para a primeira versão |
| Permitir regra por título exato. | Essencial para a primeira versão |
| Permitir regra por título que contém um texto. | Importante |
| Permitir regra por título que começa com um texto. | Importante |
| Permitir regra por expressão regular. | Futuro |

## 2. Presets

| Requisito | Classificação |
| --- | --- |
| Salvar posição e dimensão. | Essencial para a primeira versão |
| Atribuir nome ao preset. | Essencial para a primeira versão |
| Editar preset. | Essencial para a primeira versão |
| Atualizar preset usando a posição atual da janela. | Importante |
| Excluir preset. | Essencial para a primeira versão |
| Duplicar preset. | Importante |

## 3. Restauração

| Requisito | Classificação |
| --- | --- |
| Restaurar uma janela individual. | Essencial para a primeira versão |
| Restaurar todas as janelas configuradas. | Importante |
| Usar coordenadas negativas. | Essencial para a primeira versão |
| Respeitar múltiplos monitores. | Essencial para a primeira versão |
| Tratar janelas maximizadas. | Importante |
| Tratar janelas em tela cheia. | Importante |
| Informar quando nenhuma janela correspondente for encontrada. | Essencial para a primeira versão |
| Tratar múltiplas correspondências. | Essencial para a primeira versão |

## 4. Grupos de trabalho

| Requisito | Classificação |
| --- | --- |
| Criar grupos. | Importante |
| Copiar presets para grupos. | Importante |
| Vincular presets a grupos. | Futuro |
| Restaurar um grupo pelo aplicativo. | Importante |
| Restaurar um grupo pelo painel. | Futuro |

## 5. Monitores

| Requisito | Classificação |
| --- | --- |
| Reconhecer monitor. | Essencial para a primeira versão |
| Armazenar posição relativa ao monitor. | Essencial para a primeira versão |
| Lidar com mudança na ordem dos monitores. | Importante |
| Lidar com monitor desconectado. | Importante |
| Permitir escolher um monitor substituto. | Futuro |

## 6. Interface

| Requisito | Classificação |
| --- | --- |
| Usar português como idioma padrão. | Essencial para a primeira versão |
| Oferecer inglês como idioma opcional. | Futuro |
| Usar GTK 4 e Libadwaita. | Essencial para a primeira versão |
| Manter interface simples. | Essencial para a primeira versão |
| Oferecer pesquisa e filtros. | Importante |
| Permitir edição de presets. | Essencial para a primeira versão |
| Permitir exclusão de presets. | Essencial para a primeira versão |

## 7. Integração com o sistema

| Requisito | Classificação |
| --- | --- |
| Iniciar com o sistema. | Importante |
| Ter indicador no painel. | Importante |
| Oferecer menu rápido. | Importante |
| Restaurar grupos sem abrir a janela principal. | Futuro |

## 8. Segurança

| Requisito | Classificação |
| --- | --- |
| Confirmar a janela correta antes de mover. | Essencial para a primeira versão |
| Evitar movimentar janela errada. | Essencial para a primeira versão |
| Registrar erros. | Essencial para a primeira versão |
| Oferecer restauração ou desfazer quando possível. | Futuro |

## 9. Requisitos futuros

| Requisito | Classificação |
| --- | --- |
| Atalhos de teclado. | Futuro |
| Importação e exportação. | Futuro |
| Restauração automática. | Futuro |
| Perfis de configuração de monitores. | Futuro |
| Easter egg, ainda a definir. | Futuro |
