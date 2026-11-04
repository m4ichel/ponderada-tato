"""
versao1.py: questão A4, versão 1. Buffer circular SEM sincronização.

Ponderada CC08 (Tato, a pulseira sensorial)
Autor: Lucas Michel Pereira (D1 = 5, D2 = 8, N = 6)

A thread do sensor (produtora) gera as amostras 0, 1, 2, ... e a thread do
motor (consumidora) as retira de um buffer circular de N = 6 posições. As duas
se coordenam só por um contador compartilhado de posições ocupadas e por espera
ocupada: laços que ficam testando o contador até o buffer ter vaga (produtor)
ou ter amostra (consumidor). É o exemplo clássico de Silberschatz.

O defeito: ``contador += 1`` e ``contador -= 1`` não são atômicos. Cada um é
"ler, calcular, escrever". O ``time.sleep(0)`` entre a leitura e a escrita
simula a thread sendo interrompida no pior momento. A outra thread altera o
contador nesse intervalo e uma das duas atualizações se perde:

* incremento perdido: o contador diz que há menos amostras do que há, então o
  produtor sobrescreve uma posição ainda não lida (amostra PERDIDA);
* decremento perdido: o contador diz que há mais amostras do que há, então o
  consumidor relê uma posição já lida (amostra DUPLICADA).

Se o consumidor ficar 1 s sem receber nada, a execução é encerrada e registrada
como travamento (o watchdog fica em comum.py). Para a espera ocupada não segurar
o GIL do CPython por 5 ms a cada volta, comum.py reduz o intervalo de troca de
threads do interpretador para 0,5 ms.

Como rodar (dentro desta pasta):
    python versao1.py            # Windows
    python3 versao1.py           # Linux / macOS
Opções: --amostras, --execucoes, --posicoes, --limite, --log (veja --help).
"""

import time

from comum import EstadoCompartilhado, executar_versao


def produtor(estado: EstadoCompartilhado) -> None:
    """Thread do sensor: coloca as amostras 0 .. total-1 no buffer, sem sincronização.

    Parâmetros:
        estado: memória compartilhada com o consumidor (buffer, contador, índices).

    Retorno:
        Nenhum. A thread termina depois de produzir todas as amostras, ou antes,
        se o watchdog pedir parada enquanto ela está em espera ocupada.

    Funcionamento:
        1. Espera ocupada enquanto ``contador == N`` (buffer cheio).
        2. Escreve a amostra em ``buffer[entrada]`` e avança ``entrada``.
        3. ``contador += 1`` em três passos: lê, cede a CPU (``sleep(0)``) e
           escreve. Os passos 1 a 3 formam a região crítica que ficou sem proteção.
    """
    for amostra in range(estado.total):
        estado.marcar("sensor", "espera ocupada: while contador == N")
        while estado.contador == estado.n:          # espera ocupada: buffer cheio
            if estado.parar.is_set():
                return
        estado.marcar("sensor", "região crítica (sem proteção)")
        estado.buffer[estado.entrada] = amostra
        estado.entrada = (estado.entrada + 1) % estado.n
        lido = estado.contador                      # (1) lê o contador
        time.sleep(0)                               # (2) "interrompida" no pior momento
        estado.contador = lido + 1                  # (3) escreve e apaga o que o motor fez em (2)
        estado.produzidas += 1
    estado.marcar("sensor", "terminou de produzir")


def consumidor(estado: EstadoCompartilhado) -> None:
    """Thread do motor: retira ``total`` amostras do buffer, sem sincronização.

    Parâmetros:
        estado: memória compartilhada com o produtor (buffer, contador, índices).

    Retorno:
        Nenhum. A thread termina depois de ``total`` leituras, ou quando o
        watchdog pede parada porque ela ficou 1 s sem receber nada.

    Funcionamento:
        1. Espera ocupada enquanto ``contador == 0`` (buffer vazio).
        2. Lê ``buffer[saida]`` e avança ``saida``.
        3. ``contador -= 1`` em três passos (lê, ``sleep(0)``, escreve).
        4. Entrega a amostra ao motor (``registrar_recebimento``).
    """
    for _ in range(estado.total):
        estado.marcar("motor", "espera ocupada: while contador == 0")
        while estado.contador == 0:                 # espera ocupada: buffer vazio
            if estado.parar.is_set():
                return
        estado.marcar("motor", "região crítica (sem proteção)")
        amostra = estado.buffer[estado.saida]
        estado.saida = (estado.saida + 1) % estado.n
        lido = estado.contador                      # (1) lê o contador
        time.sleep(0)                               # (2) "interrompida" no pior momento
        estado.contador = lido - 1                  # (3) escreve e apaga o que o sensor fez em (2)
        estado.registrar_recebimento(amostra)
    estado.marcar("motor", "terminou de consumir")


def main() -> None:
    """Ponto de entrada: roda a versão 1 e imprime a tabela de resultados.

    Parâmetros:
        Nenhum. As opções vêm da linha de comando (veja ``--help``); o padrão
        é 3 execuções de 20.000 amostras com N = 6.

    Retorno:
        Nenhum.

    Funcionamento:
        Entrega a ``comum.executar_versao`` o título, a descrição das operações
        e as funções ``produtor`` e ``consumidor`` desta versão (sem semáforos).
    """
    executar_versao(
        "Versão 1: sem sincronização (contador compartilhado + espera ocupada)",
        ["sensor: while contador == N: pass | buffer[entrada] = amostra | contador += 1 (com sleep(0))",
         "motor : while contador == 0: pass | amostra = buffer[saida]   | contador -= 1 (com sleep(0))"],
        produtor, consumidor)


if __name__ == "__main__":
    main()
