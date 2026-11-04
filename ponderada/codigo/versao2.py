"""
versao2.py: questão A4, versão 2. Buffer circular COM semáforos (solução correta).

Ponderada CC08 (Tato, a pulseira sensorial)
Autor: Lucas Michel Pereira (D1 = 5, D2 = 8, N = 6)

Mesmo produtor (sensor) e mesmo consumidor (motor) da versão 1, agora
coordenados por três semáforos, na ordem clássica:

    vazio = N   posições livres (o produtor espera nele quando o buffer enche)
    cheio = 0   posições ocupadas (o consumidor espera nele quando o buffer esvazia)
    mutex = 1   exclusão mútua: só uma thread por vez mexe no buffer e no contador

    sensor: wait(vazio); wait(mutex); escreve; contador += 1; signal(mutex); signal(cheio)
    motor : wait(cheio); wait(mutex); lê;      contador -= 1; signal(mutex); signal(vazio)

O ``time.sleep(0)`` entre ler e escrever o contador CONTINUA aqui, de propósito:
a thread ainda é "interrompida no pior momento", mas agora isso acontece com o
mutex na mão, e a outra thread não consegue entrar na região crítica. Não há
espera ocupada: quem espera fica bloqueado no semáforo e não gasta CPU.
Resultado esperado: 20.000 consumidas, 0 perdidas, 0 duplicadas, sem travar e
contador final 0.

Como rodar (dentro desta pasta):
    python versao2.py            # Windows
    python3 versao2.py           # Linux / macOS
Opções: --amostras, --execucoes, --posicoes, --limite, --log (veja --help).
"""

import threading
import time

from comum import EstadoCompartilhado, executar_versao


def preparar(estado: EstadoCompartilhado) -> None:
    """Cria os três semáforos de uma execução e os guarda no estado compartilhado.

    Parâmetros:
        estado: estado da execução; ganha os atributos ``vazio``, ``cheio`` e ``mutex``.

    Retorno:
        Nenhum.

    Funcionamento:
        ``vazio`` começa em N (todas as posições livres), ``cheio`` em 0 (nenhuma
        amostra) e ``mutex`` em 1 (região crítica livre). ``acquire()`` é o
        wait/P e ``release()`` é o signal/V.
    """
    estado.vazio = threading.Semaphore(estado.n)
    estado.cheio = threading.Semaphore(0)
    estado.mutex = threading.Semaphore(1)


def produtor(estado: EstadoCompartilhado) -> None:
    """Thread do sensor: produz as amostras 0 .. total-1 respeitando os semáforos.

    Parâmetros:
        estado: memória compartilhada, já com os semáforos criados por ``preparar``.

    Retorno:
        Nenhum. A thread termina depois de produzir todas as amostras.

    Funcionamento:
        wait(vazio) garante uma posição livre ANTES de pegar o mutex; dentro da
        região crítica escreve a amostra e faz ``contador += 1`` (com o mesmo
        ``sleep(0)`` da versão 1); depois signal(mutex) e signal(cheio), que
        avisa o consumidor que há uma amostra nova.
    """
    for amostra in range(estado.total):
        estado.marcar("sensor", "wait(vazio)")
        estado.vazio.acquire()                      # wait(vazio): dorme se o buffer está cheio
        estado.marcar("sensor", "wait(mutex)")
        estado.mutex.acquire()                      # wait(mutex): entra na região crítica
        estado.marcar("sensor", "região crítica")
        estado.buffer[estado.entrada] = amostra
        estado.entrada = (estado.entrada + 1) % estado.n
        lido = estado.contador                      # (1) lê o contador
        time.sleep(0)                               # (2) interrompida, mas com o mutex na mão
        estado.contador = lido + 1                  # (3) escreve: ninguém mexeu no meio
        estado.produzidas += 1
        estado.mutex.release()                      # signal(mutex): sai da região crítica
        estado.cheio.release()                      # signal(cheio): mais uma amostra disponível
    estado.marcar("sensor", "terminou de produzir")


def consumidor(estado: EstadoCompartilhado) -> None:
    """Thread do motor: consome ``total`` amostras respeitando os semáforos.

    Parâmetros:
        estado: memória compartilhada, já com os semáforos criados por ``preparar``.

    Retorno:
        Nenhum. A thread termina depois de receber ``total`` amostras.

    Funcionamento:
        wait(cheio) garante que há amostra ANTES de pegar o mutex; dentro da
        região crítica lê a amostra e faz ``contador -= 1``; depois signal(mutex)
        e signal(vazio), que devolve a posição ao produtor. Esta função também é
        usada, sem mudança, pela versão 3.
    """
    for _ in range(estado.total):
        estado.marcar("motor", "wait(cheio)")
        estado.cheio.acquire()                      # wait(cheio): dorme se o buffer está vazio
        estado.marcar("motor", "wait(mutex)")
        estado.mutex.acquire()                      # wait(mutex): entra na região crítica
        estado.marcar("motor", "região crítica")
        amostra = estado.buffer[estado.saida]
        estado.saida = (estado.saida + 1) % estado.n
        lido = estado.contador                      # (1) lê o contador
        time.sleep(0)                               # (2) interrompida, mas com o mutex na mão
        estado.contador = lido - 1                  # (3) escreve: ninguém mexeu no meio
        estado.mutex.release()                      # signal(mutex)
        estado.vazio.release()                      # signal(vazio): uma posição livre a mais
        estado.registrar_recebimento(amostra)
    estado.marcar("motor", "terminou de consumir")


def main() -> None:
    """Ponto de entrada: roda a versão 2 e imprime a tabela de resultados.

    Parâmetros:
        Nenhum. As opções vêm da linha de comando (veja ``--help``); o padrão
        é 3 execuções de 20.000 amostras com N = 6.

    Retorno:
        Nenhum.

    Funcionamento:
        Entrega a ``comum.executar_versao`` o título, a descrição das operações,
        as funções ``produtor`` e ``consumidor`` e a função ``preparar``, que
        cria os semáforos de cada execução.
    """
    executar_versao(
        "Versão 2: semáforos vazio (N), cheio (0) e mutex (1)",
        ["sensor: wait(vazio) → wait(mutex) → escreve, contador += 1 → signal(mutex) → signal(cheio)",
         "motor : wait(cheio) → wait(mutex) → lê,      contador -= 1 → signal(mutex) → signal(vazio)"],
        produtor, consumidor, preparar)


if __name__ == "__main__":
    main()
