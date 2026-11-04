"""
comum.py: infraestrutura compartilhada pelas três versões da questão A4.

Ponderada CC08 (Tato, a pulseira sensorial)
Autor: Lucas Michel Pereira (D1 = 5, D2 = 8, N = 6)

Este módulo guarda o que as versões 1, 2 e 3 têm em comum e que NÃO é a
sincronização entre as threads:

* os parâmetros do experimento: buffer de N = 3 + (D2 mod 5) = 6 posições,
  20.000 amostras por execução, 3 execuções por versão e o critério de
  travamento (consumidor 1 s sem receber nada);
* ``EstadoCompartilhado``: a memória que a thread do sensor (produtora) e a
  thread do motor (consumidora) dividem, ou seja, o buffer circular, o contador
  de posições ocupadas e os índices de escrita e de leitura;
* ``executar_versao``: roda as execuções, faz o papel de cão de guarda
  (watchdog) que detecta o travamento e imprime a tabela de resultados;
* ``analisar``: conta as amostras consumidas, perdidas e duplicadas.

Cada versão só define COMO o produtor e o consumidor acessam o buffer. Assim,
a única diferença entre os três programas é justamente o que a questão compara.
Este arquivo não é executado sozinho: ele é importado por versao1.py,
versao2.py e versao3.py. Requer Python 3.7 ou mais novo, sem bibliotecas externas.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Parâmetros individuais e do experimento
# ---------------------------------------------------------------------------
D1 = 5                          # letras de "Lucas"
D2 = 8                          # último dígito das 18 letras de "Lucas Michel Pereira"
N_POSICOES = 3 + (D2 % 5)       # N = 3 + (8 mod 5) = 6 posições
TOTAL_AMOSTRAS = 20_000         # amostras por execução (enunciado)
EXECUCOES = 3                   # execuções por versão (enunciado)
LIMITE_SEM_RECEBER_S = 1.0      # 1 s sem receber nada = travamento (enunciado)
POSICAO_NUNCA_ESCRITA = -1      # valor inicial das posições do buffer

# O CPython só tira o GIL à força de uma thread a cada 5 ms (sys.getswitchinterval()).
# Uma espera ocupada nunca solta o GIL por conta própria, então cada volta dela
# seguraria a CPU por até 5 ms e a versão 1 levaria uns 3 min por execução. Com
# 0,5 ms o interpretador preempta as threads com mais frequência, como faria o
# escalonador de um SO. A mesma configuração vale para as três versões.
INTERVALO_TROCA_S = 0.0005

#: Assinatura das funções de thread de cada versão: recebem o estado e não retornam nada.
FuncaoThread = Callable[["EstadoCompartilhado"], None]


class EstadoCompartilhado:
    """Memória dividida entre a thread do sensor e a thread do motor.

    Atributos:
        n (int): número de posições do buffer circular (N).
        total (int): quantas amostras o produtor deve gerar (0 até total - 1).
        buffer (list[int]): as N posições; começam com ``POSICAO_NUNCA_ESCRITA``.
        contador (int): posições ocupadas segundo as threads. Na versão 1 ele
            pode "mentir", porque as atualizações concorrentes se perdem.
        entrada (int): próxima posição que o produtor escreve (só ele altera).
        saida (int): próxima posição que o consumidor lê (só ele altera).
        produzidas (int): amostras que o produtor já colocou no buffer.
        recebidas (list[int]): tudo o que o consumidor tirou do buffer, em ordem.
        ultimo_recebimento (float): instante (``time.monotonic``) da última
            amostra recebida; é o que o watchdog vigia.
        parar (threading.Event): pedido de parada enviado pelo watchdog. Só as
            threads em espera ocupada (versão 1) conseguem atendê-lo; threads
            bloqueadas num semáforo não testam nada, e é isso que caracteriza
            o deadlock da versão 3.
        onde (dict[str, str]): última etapa anunciada por cada thread, usada
            para mostrar onde cada uma estava quando houve travamento.

    As versões 2 e 3 acrescentam, em ``preparar``, os semáforos ``vazio``,
    ``cheio`` e ``mutex``.
    """

    def __init__(self, n: int, total: int) -> None:
        """Cria o buffer vazio e zera contadores e índices.

        Parâmetros:
            n: número de posições do buffer circular (N).
            total: número de amostras que o produtor vai gerar.

        Retorno:
            Nenhum (construtor).
        """
        self.n = n
        self.total = total
        self.buffer: List[int] = [POSICAO_NUNCA_ESCRITA] * n
        self.contador = 0
        self.entrada = 0
        self.saida = 0
        self.produzidas = 0
        self.recebidas: List[int] = []
        self.ultimo_recebimento = time.monotonic()
        self.parar = threading.Event()
        self.onde = {"sensor": "não iniciou", "motor": "não iniciou"}

    def marcar(self, papel: str, etapa: str) -> None:
        """Anota em que etapa uma thread está (só para o diagnóstico de travamento).

        Parâmetros:
            papel: ``"sensor"`` (produtor) ou ``"motor"`` (consumidor).
            etapa: texto curto, por exemplo ``"wait(vazio)"``.

        Retorno:
            Nenhum. Cada thread só escreve na própria chave do dicionário, então
            esta anotação não cria uma nova condição de corrida.
        """
        self.onde[papel] = etapa

    def registrar_recebimento(self, amostra: int) -> None:
        """Guarda uma amostra que o consumidor acabou de tirar do buffer.

        Parâmetros:
            amostra: número da amostra lida da posição ``saida``.

        Retorno:
            Nenhum. Também atualiza ``ultimo_recebimento``, que o watchdog usa
            para decidir se o consumidor travou.
        """
        self.recebidas.append(amostra)
        self.ultimo_recebimento = time.monotonic()


@dataclass
class Resultado:
    """Resumo de uma execução: uma linha da tabela pedida na questão A4.

    Atributos:
        execucao: número da execução (1, 2, 3, ...).
        produzidas: amostras que o produtor chegou a colocar no buffer.
        consumidas: leituras feitas pelo consumidor (inclui repetições).
        perdidas: amostras de 0 a total-1 que o motor nunca recebeu.
        duplicadas: leituras de uma amostra que o motor já tinha recebido.
        invalidas: leituras de uma posição que nunca tinha sido escrita.
        travou: True se o consumidor ficou ``limite`` segundos sem receber nada.
        contador_final: valor do contador compartilhado ao final.
        duracao_s: duração da execução em segundos, até o veredito do watchdog.
        onde_sensor: última etapa anunciada pelo produtor.
        onde_motor: última etapa anunciada pelo consumidor.
    """

    execucao: int
    produzidas: int
    consumidas: int
    perdidas: int
    duplicadas: int
    invalidas: int
    travou: bool
    contador_final: int
    duracao_s: float
    onde_sensor: str
    onde_motor: str


def analisar(estado: EstadoCompartilhado, execucao: int, travou: bool,
             duracao_s: float) -> Resultado:
    """Compara o que o motor recebeu com o que o sensor deveria ter entregue.

    Parâmetros:
        estado: estado compartilhado ao fim da execução.
        execucao: número da execução, só para identificar a linha.
        travou: veredito do watchdog.
        duracao_s: tempo da execução, em segundos.

    Retorno:
        Um ``Resultado``. As contas são:
        perdidas = total - (amostras distintas recebidas);
        duplicadas = (leituras válidas) - (amostras distintas recebidas);
        inválidas = leituras de posição nunca escrita.
        Logo, consumidas = (total - perdidas) + duplicadas + inválidas.
    """
    recebidas = list(estado.recebidas)
    validas = [a for a in recebidas if 0 <= a < estado.total]
    distintas = len(set(validas))
    return Resultado(
        execucao=execucao,
        produzidas=estado.produzidas,
        consumidas=len(recebidas),
        perdidas=estado.total - distintas,
        duplicadas=len(validas) - distintas,
        invalidas=len(recebidas) - len(validas),
        travou=travou,
        contador_final=estado.contador,
        duracao_s=duracao_s,
        onde_sensor=estado.onde["sensor"],
        onde_motor=estado.onde["motor"],
    )


def vigiar(estado: EstadoCompartilhado, motor: threading.Thread,
           limite_s: float) -> bool:
    """Cão de guarda (watchdog): espera o consumidor terminar ou travar.

    Parâmetros:
        estado: estado compartilhado, de onde vem ``ultimo_recebimento``.
        motor: a thread consumidora.
        limite_s: tempo máximo sem receber amostra antes de declarar travamento.

    Retorno:
        True se o consumidor ficou ``limite_s`` segundos sem receber nada
        (travamento); False se ele terminou normalmente.

    Funcionamento:
        A cada 20 ms verifica se a thread do motor terminou. Se não terminou e a
        última amostra chegou há mais de ``limite_s``, declara travamento. É o
        mesmo papel do watchdog da pulseira no Dilema 1 da Parte B.
    """
    while True:
        motor.join(timeout=0.02)
        if not motor.is_alive():
            return False
        if time.monotonic() - estado.ultimo_recebimento > limite_s:
            return True


def executar_uma_vez(produtor: FuncaoThread, consumidor: FuncaoThread,
                     preparar: Optional[FuncaoThread], execucao: int, n: int,
                     total: int, limite_s: float) -> Resultado:
    """Roda uma execução completa: cria o estado, as duas threads e o watchdog.

    Parâmetros:
        produtor: função da thread do sensor.
        consumidor: função da thread do motor.
        preparar: função opcional que cria os semáforos da versão no estado
            (None na versão 1, que não usa semáforos).
        execucao: número desta execução.
        n: posições do buffer circular.
        total: amostras a produzir.
        limite_s: critério de travamento, em segundos sem receber.

    Retorno:
        O ``Resultado`` da execução.

    Funcionamento:
        As threads são ``daemon``: se ficarem presas para sempre num semáforo
        (deadlock da versão 3), não impedem o programa de seguir para a próxima
        execução nem de terminar. O pedido de parada (``parar``) só é atendido
        por quem está em espera ocupada.
    """
    estado = EstadoCompartilhado(n, total)
    if preparar is not None:
        preparar(estado)
    sensor = threading.Thread(target=produtor, args=(estado,), name="sensor", daemon=True)
    motor = threading.Thread(target=consumidor, args=(estado,), name="motor", daemon=True)

    inicio = time.monotonic()
    estado.ultimo_recebimento = inicio
    motor.start()
    sensor.start()
    travou = vigiar(estado, motor, limite_s)
    duracao_s = time.monotonic() - inicio   # até o veredito do watchdog
    estado.parar.set()          # libera quem está em espera ocupada (versão 1)
    sensor.join(timeout=0.2)    # thread presa em semáforo não volta; seguimos assim mesmo
    motor.join(timeout=0.2)
    return analisar(estado, execucao, travou, duracao_s)


# ---------------------------------------------------------------------------
# Saída no terminal
# ---------------------------------------------------------------------------
def _milhar(valor: int) -> str:
    """Formata um inteiro com ponto de milhar, como em português (20.000).

    Parâmetros:
        valor: inteiro a formatar.

    Retorno:
        O texto formatado.
    """
    return f"{valor:,}".replace(",", ".")


def _segundos(valor: float) -> str:
    """Formata segundos com uma casa e vírgula decimal (2,3 s).

    Parâmetros:
        valor: duração em segundos.

    Retorno:
        O texto formatado.
    """
    return f"{valor:.1f}".replace(".", ",") + " s"


def _plural(quantidade: int, singular: str, plural: str) -> str:
    """Escolhe a forma singular ou plural de uma palavra.

    Parâmetros:
        quantidade: o número que acompanha a palavra.
        singular: forma usada quando a quantidade é 1.
        plural: forma usada nos demais casos (inclusive 0).

    Retorno:
        A palavra adequada.
    """
    return singular if quantidade == 1 else plural


class Relatorio:
    """Escreve no terminal e, se pedido, também num arquivo de texto (--log)."""

    def __init__(self, caminho_log: Optional[str]) -> None:
        """Prepara o relatório.

        Parâmetros:
            caminho_log: arquivo onde gravar uma cópia da saída, ou None.

        Retorno:
            Nenhum (construtor).
        """
        self.caminho_log = caminho_log
        self.linhas: List[str] = []

    def escrever(self, linha: str = "") -> None:
        """Mostra uma linha no terminal na hora e guarda uma cópia dela.

        Parâmetros:
            linha: texto a mostrar.

        Retorno:
            Nenhum.
        """
        print(linha, flush=True)
        self.linhas.append(linha)

    def fechar(self) -> None:
        """Grava a cópia da saída no arquivo de log, se um foi informado.

        Retorno:
            Nenhum.
        """
        if self.caminho_log:
            with open(self.caminho_log, "w", encoding="utf-8") as arquivo:
                arquivo.write("\n".join(self.linhas) + "\n")


def _borda(larguras: Sequence[int], esquerda: str, meio: str, direita: str) -> str:
    """Monta uma linha horizontal da tabela (topo, separador ou base).

    Parâmetros:
        larguras: largura de cada coluna, sem contar a margem de um espaço.
        esquerda: caractere do canto esquerdo (por exemplo, "┌").
        meio: caractere de cruzamento entre colunas (por exemplo, "┬").
        direita: caractere do canto direito (por exemplo, "┐").

    Retorno:
        A linha pronta, como "┌───────┬────────┐".
    """
    return esquerda + meio.join("─" * (w + 2) for w in larguras) + direita


def _linha_tabela(celulas: Sequence[str], larguras: Sequence[int]) -> str:
    """Monta uma linha de dados da tabela, com as células alinhadas à direita.

    Parâmetros:
        celulas: textos das células, na ordem das colunas.
        larguras: largura de cada coluna.

    Retorno:
        A linha pronta, como "│     1 │ 20.000 │".
    """
    return "│" + "│".join(f" {c:>{w}} " for c, w in zip(celulas, larguras)) + "│"


def _tabela(resultados: Sequence[Resultado]) -> List[str]:
    """Monta a tabela de resultados com bordas, uma linha por execução.

    Parâmetros:
        resultados: resultados das execuções, na ordem em que rodaram.

    Retorno:
        As linhas de texto da tabela.
    """
    cabecalho = ["Exec.", "Produzidas", "Consumidas", "Perdidas", "Duplicadas",
                 "Travou?", "Contador final", "Tempo"]
    linhas = [[str(r.execucao), _milhar(r.produzidas), _milhar(r.consumidas),
               _milhar(r.perdidas), _milhar(r.duplicadas),
               "SIM" if r.travou else "não", str(r.contador_final),
               _segundos(r.duracao_s)] for r in resultados]
    larguras = [max([len(cabecalho[i])] + [len(l[i]) for l in linhas])
                for i in range(len(cabecalho))]
    saida = [_borda(larguras, "┌", "┬", "┐"), _linha_tabela(cabecalho, larguras),
             _borda(larguras, "├", "┼", "┤")]
    saida += [_linha_tabela(l, larguras) for l in linhas]
    saida.append(_borda(larguras, "└", "┴", "┘"))
    return saida


def _argumentos(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    """Lê e valida as opções de linha de comando (todas opcionais).

    Parâmetros:
        argv: lista de argumentos; None usa ``sys.argv``.

    Retorno:
        Namespace com ``amostras``, ``execucoes``, ``posicoes``, ``limite`` e ``log``.
        Valores fora do domínio (zero ou negativos) encerram o programa com uma
        mensagem de erro do argparse.
    """
    parser = argparse.ArgumentParser(
        description="Produtor (sensor) e consumidor (motor) num buffer circular.")
    parser.add_argument("--amostras", type=int, default=TOTAL_AMOSTRAS,
                        help=f"amostras por execução (padrão: {TOTAL_AMOSTRAS})")
    parser.add_argument("--execucoes", type=int, default=EXECUCOES,
                        help=f"quantas execuções (padrão: {EXECUCOES})")
    parser.add_argument("--posicoes", type=int, default=N_POSICOES,
                        help=f"posições do buffer, N (padrão: {N_POSICOES})")
    parser.add_argument("--limite", type=float, default=LIMITE_SEM_RECEBER_S,
                        help="segundos sem receber para declarar travamento (padrão: 1.0)")
    parser.add_argument("--log", default=None,
                        help="também grava a saída neste arquivo de texto")
    args = parser.parse_args(argv)
    if min(args.amostras, args.execucoes, args.posicoes) < 1 or args.limite <= 0:
        parser.error("--amostras, --execucoes e --posicoes devem ser >= 1 e --limite > 0")
    return args


def executar_versao(titulo: str, ordem: Sequence[str], produtor: FuncaoThread,
                    consumidor: FuncaoThread, preparar: Optional[FuncaoThread] = None,
                    argv: Optional[Sequence[str]] = None) -> List[Resultado]:
    """Ponto de entrada comum: roda todas as execuções de uma versão e imprime a tabela.

    Parâmetros:
        titulo: nome da versão, mostrado no cabeçalho.
        ordem: linhas que descrevem as operações do produtor e do consumidor.
        produtor: função da thread do sensor.
        consumidor: função da thread do motor.
        preparar: função opcional que cria os semáforos no estado.
        argv: argumentos de linha de comando (None usa ``sys.argv``).

    Retorno:
        A lista de ``Resultado``, um por execução.

    Funcionamento:
        Ajusta o intervalo de troca de threads do interpretador, chama
        ``executar_uma_vez`` para cada execução, informa o andamento e, se houve
        travamento, mostra onde cada thread estava. No fim imprime a tabela
        pedida na questão (consumidas, perdidas, duplicadas, travou).
    """
    try:  # garante acentos e bordas mesmo com a saída redirecionada no Windows
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    args = _argumentos(argv)
    sys.setswitchinterval(INTERVALO_TROCA_S)   # ver o comentário junto da constante
    rel = Relatorio(args.log)
    barra = "═" * 92
    rel.escrever(barra)
    rel.escrever(f" Tato · A4 · {titulo}")
    rel.escrever(f" N = {args.posicoes} posições · {_milhar(args.amostras)} amostras por execução · "
                 f"{args.execucoes} {_plural(args.execucoes, 'execução', 'execuções')} · "
                 f"travou = {args.limite:g} s sem receber")
    for item in ordem:
        rel.escrever(f"   {item}")
    rel.escrever(barra)

    resultados: List[Resultado] = []
    for i in range(1, args.execucoes + 1):
        r = executar_uma_vez(produtor, consumidor, preparar, i, args.posicoes,
                             args.amostras, args.limite)
        resultados.append(r)
        if r.travou:
            recebidas = (f"{_milhar(r.consumidas)} "
                         f"{_plural(r.consumidas, 'amostra recebida', 'amostras recebidas')}")
            rel.escrever(f" Execução {i}: TRAVOU depois de {recebidas} "
                         f"({_milhar(r.produzidas)} produzidas, contador = {r.contador_final})")
            rel.escrever(f"     sensor parado em: {r.onde_sensor}")
            rel.escrever(f"     motor  parado em: {r.onde_motor}")
        else:
            rel.escrever(f" Execução {i}: terminou em {_segundos(r.duracao_s)}")

    rel.escrever()
    for linha in _tabela(resultados):
        rel.escrever(" " + linha)
    rel.escrever(" Perdidas = amostras de 0 a total-1 que o motor nunca recebeu (sobrescritas ou nunca")
    rel.escrever(" entregues). Duplicadas = leituras repetidas de uma amostra já recebida.")
    rel.escrever(" Tempo = até terminar ou até o watchdog declarar o travamento.")
    invalidas = sum(r.invalidas for r in resultados)
    if invalidas:
        rel.escrever(f" Atenção: {_milhar(invalidas)} leituras de posição que nunca foi escrita "
                     "(contam em Consumidas).")
    rel.fechar()
    return resultados
