# Ponderada CC08: do pipeline ao deadlock

**Autor:** Lucas Michel Pereira (D1 = 5, D2 = 8, N = 6)

Arquitetura, memória, pipeline, processos, semáforos e deadlock aplicados à pulseira sensorial Tato, com a decisão do CTO e o código da questão A4.

## Estrutura

```text
.
├── README.md
├── .gitignore
└── ponderada/
    ├── ponderada-tato.md     # Parte A (questões A1 a A5) e Parte B (memorando do CTO)
    ├── codigo/               # questão A4: produtor e consumidor com buffer circular
    │   ├── comum.py          # estado compartilhado, watchdog, análise e tabela (sem sincronização)
    │   ├── versao1.py        # versão 1: sem sincronização (contador + espera ocupada)
    │   ├── versao2.py        # versão 2: semáforos vazio (N), cheio (0) e mutex (1)
    │   └── versao3.py        # versão 3: ordem trocada no produtor (deadlock)
    └── img/                  # prints (caches da máquina e execuções da A4)
```

O relatório completo está em [`ponderada/ponderada-tato.md`](ponderada/ponderada-tato.md).

## Como rodar as três versões da A4

Requisito: **Python 3.7 ou mais novo**. Não há dependências externas, só a biblioteca padrão (`threading`).

Cada versão roda com **um único comando**, a partir da raiz do repositório (no Windows, troque `python3` por `python`):

```bash
python3 ponderada/codigo/versao1.py
```

```bash
python3 ponderada/codigo/versao2.py
```

```bash
python3 ponderada/codigo/versao3.py
```

Se preferir rodar de dentro da pasta do código, entre nela com `cd ponderada/codigo` e use `python3 versao1.py`, `python3 versao2.py` ou `python3 versao3.py`.

Cada comando faz sozinho as **3 execuções de 20.000 amostras** com buffer de **N = 6** posições e imprime uma tabela com amostras produzidas, consumidas, perdidas, duplicadas e se travou (motor 1 s sem receber nada). O que esperar:

| Versão | O que acontece | Tempo aproximado |
| :-- | :-- | :-- |
| 1: sem sincronização | perde e duplica amostras; costuma travar no fim | ~1 s por execução |
| 2: semáforos | 20.000 consumidas, 0 perdidas, 0 duplicadas, sem travar | ~0,2 s por execução |
| 3: ordem trocada | deadlock logo que o buffer enche; o watchdog encerra após 1 s | ~1 s por execução |

Opções (todas opcionais, iguais nas três versões):

| Opção | Padrão | Significado |
| :-- | :-- | :-- |
| `--amostras` | 20000 | amostras por execução |
| `--execucoes` | 3 | quantas execuções |
| `--posicoes` | 6 | posições do buffer (N) |
| `--limite` | 1.0 | segundos sem receber para declarar travamento |
| `--log ARQUIVO` | (nenhum) | também grava a saída num arquivo de texto |

Exemplo: `python3 ponderada/codigo/versao1.py --execucoes 5 --log saida-v1.txt`.
