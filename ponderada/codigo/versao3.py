"""
versao3.py: questão A4, versão 3. Semáforos com a ordem do produtor TROCADA.

Ponderada CC08 (Tato, a pulseira sensorial)
Autor: Lucas Michel Pereira (D1 = 5, D2 = 8, N = 6)

Igual à versão 2, com uma única diferença: o produtor faz wait(mutex) ANTES de
wait(vazio). O consumidor e os semáforos são importados da versão 2 sem nenhuma
alteração.

    sensor: wait(mutex); wait(vazio); escreve; ...    <- ordem trocada
    motor : wait(cheio); wait(mutex); lê; ...         <- igual à versão 2

Quando o buffer enche (vazio = 0), o sensor entra na região crítica, pega o
mutex e dorme em wait(vazio) segurando o mutex. O motor, que só liberaria uma
posição (signal(vazio)) depois de passar por wait(mutex), dorme esperando esse
mutex. Um espera o outro para sempre: deadlock. Como as duas threads estão
bloqueadas em semáforos, ninguém testa nada e o único jeito de perceber é por
fora: o watchdog de comum.py vê o motor 1 s sem receber e registra o
travamento.

Como rodar (dentro desta pasta):
    python versao3.py            # Windows
    python3 versao3.py           # Linux / macOS
Opções: --amostras, --execucoes, --posicoes, --limite, --log (veja --help).
"""

import time

from comum import EstadoCompartilhado, executar_versao
from versao2 import consumidor, preparar  # consumidor e semáforos idênticos aos da versão 2


def produtor(estado: EstadoCompartilhado) -> None:
    """Thread do sensor com a ordem errada: wait(mutex) antes de wait(vazio).

    Parâmetros:
        estado: memória compartilhada, já com os semáforos criados por ``preparar``.

    Retorno:
        Nenhum. Normalmente a thread nunca retorna: fica presa em wait(vazio)
        segurando o mutex assim que encontra o buffer cheio.

    Funcionamento:
        Pega o mutex e só então verifica se há posição livre. Com o buffer
        cheio, adormece em wait(vazio) sem soltar o mutex. É o "segura e espera"
        que, junto com a espera circular, fecha o deadlock (ver A5).
    """
    for amostra in range(estado.total):
        estado.marcar("sensor", "wait(mutex)")
        estado.mutex.acquire()                      # wait(mutex) PRIMEIRO (ordem trocada)
        estado.marcar("sensor", "wait(vazio), segurando o mutex")
        estado.vazio.acquire()                      # wait(vazio) com o mutex na mão: se cheio, deadlock
        estado.marcar("sensor", "região crítica")
        estado.buffer[estado.entrada] = amostra
        estado.entrada = (estado.entrada + 1) % estado.n
        lido = estado.contador                      # (1) lê o contador
        time.sleep(0)                               # (2) interrompida no pior momento
        estado.contador = lido + 1                  # (3) escreve
        estado.produzidas += 1
        estado.mutex.release()                      # signal(mutex)
        estado.cheio.release()                      # signal(cheio)
    estado.marcar("sensor", "terminou de produzir")


def main() -> None:
    """Ponto de entrada: roda a versão 3 e imprime a tabela de resultados.

    Parâmetros:
        Nenhum. As opções vêm da linha de comando (veja ``--help``); o padrão
        é 3 execuções de 20.000 amostras com N = 6.

    Retorno:
        Nenhum.

    Funcionamento:
        Usa o ``produtor`` desta versão (ordem trocada) com o ``consumidor`` e
        o ``preparar`` da versão 2, sem nenhuma alteração neles.
    """
    executar_versao(
        "Versão 3: semáforos com a ordem trocada no produtor",
        ["sensor: wait(mutex) → wait(vazio) → escreve, contador += 1 → signal(mutex) → signal(cheio)",
         "motor : wait(cheio) → wait(mutex) → lê,      contador -= 1 → signal(mutex) → signal(vazio)"],
        produtor, consumidor, preparar)


if __name__ == "__main__":
    main()
