"""QualityScorer — a nota de qualidade estrutural (plano Pixel §56 e §60).

A nota começa em 100 e **desconta**: cada indicador estrutural fora da faixa
saudável tira pontos, e o quanto tirou fica registrado em ``penalties``. Sem
esse registro a nota seria um número mágico impossível de depurar — o
relatório precisa poder responder "por que 62?" com "órfãos 12,4 + ocupação
15,0 + paleta 10,6".

O que esta nota **não** é (plano Pixel §57, e o §107 chama isso de essencial):

    pixel_exact   ->  verdade técnica, binária, decidida pelos hard checks
    quality_score ->  indicador estrutural, contínuo, decidido aqui

As duas nunca se misturam nem se compensam. Um asset pode ser
``PIXEL EXACT: sim / QUALITY: 58`` — tecnicamente correto e artisticamente
problemático — e outro pode ser ``PIXEL EXACT: não / QUALITY: 90`` — bonito e
fora da especificação. Somar as duas coisas em um número só destruiria
exatamente a informação que o operador precisa para decidir o que fazer, e
esconderia um erro fatal atrás de uma média boa (§38).

Os pesos abaixo são **experimentais** por decisão do próprio plano (§60):
eles nasceram de estimativa, não de medição, e a expectativa é ajustá-los com
o benchmark rodando. Por isso moram todos aqui em cima, nomeados e isolados —
mexer na calibração não pode exigir tocar em analisador nenhum.
"""

from __future__ import annotations

import math

from ..contracts.output_spec import PixelOutputSpec, ValidationSpec
from ..contracts.validation_report import QualityMetrics, QualityWarning

__all__ = [
    "MICROCLUSTER_FREE_RATIO",
    "MICROCLUSTER_PENALTY_MAX",
    "MICROCLUSTER_PENALTY_RATE",
    "OCCUPANCY_PENALTY_MAX",
    "ORPHAN_FREE_RATIO",
    "ORPHAN_PENALTY_MAX",
    "ORPHAN_PENALTY_RATE",
    "OUTLINE_FREE_FRAGMENTATION",
    "OUTLINE_PENALTY_MAX",
    "OUTLINE_PENALTY_RATE",
    "RARE_COLOR_PENALTY_MAX",
    "RARE_COLOR_PENALTY_PER_COLOR",
    "REDUNDANCY_PENALTY_MAX",
    "REDUNDANCY_PENALTY_PER_PAIR",
    "QualityScorer",
]

# ---------------------------------------------------------------------------
# Calibração — TODOS os valores desta seção são EXPERIMENTAIS e ajustáveis
# (plano Pixel §60). Cada bloco tem uma franquia (abaixo dela não há
# desconto), uma taxa e um teto: o teto impede que um único indicador ruim
# zere sozinho a nota de um asset que acerta todo o resto.
# ---------------------------------------------------------------------------

#: Órfãos: alguma sujeira isolada é normal em Pixel Art (olhos, brilhos).
ORPHAN_FREE_RATIO = 0.01
ORPHAN_PENALTY_RATE = 400.0
ORPHAN_PENALTY_MAX = 20.0

#: Microclusters: um quinto dos blocos com 3 pixels ou menos ainda é detalhe.
MICROCLUSTER_FREE_RATIO = 0.20
MICROCLUSTER_PENALTY_RATE = 100.0
MICROCLUSTER_PENALTY_MAX = 20.0

#: Ocupação: a franquia é a faixa saudável do próprio profile (§53), e o teto
#: vale para o pior desvio que aquele profile permite existir — ver
#: `_occupancy_penalty`.
OCCUPANCY_PENALTY_MAX = 15.0

#: Cores redundantes: cada par desperdiça uma entrada do palette budget.
REDUNDANCY_PENALTY_PER_PAIR = 2.0
REDUNDANCY_PENALTY_MAX = 10.0

#: Contorno esfarelado.
OUTLINE_FREE_FRAGMENTATION = 0.20
OUTLINE_PENALTY_RATE = 50.0
OUTLINE_PENALTY_MAX = 10.0

#: Cores raras: sintoma leve, teto baixo — várias delas são intencionais.
RARE_COLOR_PENALTY_PER_COLOR = 1.0
RARE_COLOR_PENALTY_MAX = 5.0


class QualityScorer:
    """Converte as métricas estruturais em uma nota de 0 a 100."""

    def score(
        self,
        metrics: QualityMetrics,
        warnings: tuple[QualityWarning, ...],
        spec: PixelOutputSpec,
    ) -> tuple[int, dict[str, float]]:
        """Devolve ``(nota, {penalidade: pontos})``.

        ``warnings`` entra na assinatura porque a severidade dos avisos é o
        eixo natural de evolução da calibração (§60), mas hoje não vira
        desconto: aviso e métrica são a mesma medida vista de dois ângulos, e
        somar os dois puniria o mesmo defeito duas vezes.
        """
        limits = spec.validation

        # A ordem desta tupla é a ordem em que as penalidades aparecem no
        # relatório: fixa, para que dois `validation.json` sejam comparáveis
        # linha a linha.
        raw: tuple[tuple[str, float], ...] = (
            (
                "orphan",
                _threshold_penalty(
                    metrics.orphan_pixel_ratio,
                    free=ORPHAN_FREE_RATIO,
                    rate=ORPHAN_PENALTY_RATE,
                    ceiling=ORPHAN_PENALTY_MAX,
                ),
            ),
            (
                "microcluster",
                _threshold_penalty(
                    metrics.microcluster_ratio,
                    free=MICROCLUSTER_FREE_RATIO,
                    rate=MICROCLUSTER_PENALTY_RATE,
                    ceiling=MICROCLUSTER_PENALTY_MAX,
                ),
            ),
            (
                "occupancy",
                _occupancy_penalty(metrics.foreground_occupancy, limits),
            ),
            (
                "redundancy",
                min(
                    REDUNDANCY_PENALTY_MAX,
                    REDUNDANCY_PENALTY_PER_PAIR * len(metrics.redundant_color_pairs),
                ),
            ),
            (
                "outline",
                _threshold_penalty(
                    metrics.outline_fragmentation,
                    free=OUTLINE_FREE_FRAGMENTATION,
                    rate=OUTLINE_PENALTY_RATE,
                    ceiling=OUTLINE_PENALTY_MAX,
                ),
            ),
            (
                "rare_colors",
                min(
                    RARE_COLOR_PENALTY_MAX,
                    RARE_COLOR_PENALTY_PER_COLOR * len(metrics.rare_colors),
                ),
            ),
        )

        # Penalidade zero fica de fora: o dicionário existe para explicar o
        # que tirou pontos, e uma lista de zeros só faria ruído no relatório.
        penalties = {
            name: round(value, 2) for name, value in raw if round(value, 2) > 0.0
        }

        # A soma usa os valores já arredondados para que o relatório feche:
        # `100 - sum(penalties.values())` reproduz a nota. E o piso é `floor`,
        # não `round`, para que nenhuma penalidade real seja arredondada até
        # sumir — meio ponto perdido continua sendo um ponto a menos.
        total = math.fsum(penalties.values())
        return max(0, min(100, math.floor(100.0 - total))), penalties


def _threshold_penalty(value: float, *, free: float, rate: float, ceiling: float) -> float:
    """Desconto linear sobre o que passa da franquia, limitado pelo teto."""
    if value <= free:
        return 0.0
    return min(ceiling, (value - free) * rate)


def _occupancy_penalty(occupancy: float, limits: ValidationSpec) -> float:
    """Desconto por sair da faixa de ocupação do profile (§53).

    A distância é normalizada pelo **espaço que existe fora da faixa do lado
    que foi violado**, e não pela largura da faixa. A diferença não é
    cosmética: ocupação é uma fração de 0 a 1, então abaixo de
    ``min_occupancy`` só cabem ``min_occupancy`` pontos percentuais e acima de
    ``max_occupancy`` só cabem ``1 - max_occupancy``. Normalizar pela largura
    da faixa media dois eixos diferentes e tornava o teto inalcançável: com a
    faixa padrão ``[0.05, 0.95]``, um sprite **inteiramente vazio** — o pior
    desvio que pode existir — descontava 0,83 de 15 pontos possíveis, e o
    indicador virava decoração no relatório.

    Assim a penalidade lê como fração do desvio máximo possível naquele
    profile: no limite da faixa é zero, no extremo do eixo é o teto. O efeito
    que a normalização anterior buscava continua de pé, e por um caminho mais
    direto — um profile que exige de 50% a 100% de ocupação (o tile do §66)
    tem meio eixo para errar, enquanto um que aceita a partir de 5% declara
    que quase não se importa, e nele só chega perto do teto quem chega perto
    do vazio.

    Faixa degenerada (``min == max``) continua significando exigência exata:
    qualquer desvio leva o teto.
    """
    if limits.min_occupancy <= occupancy <= limits.max_occupancy:
        return 0.0

    if limits.max_occupancy - limits.min_occupancy <= 0.0:
        return OCCUPANCY_PENALTY_MAX

    if occupancy < limits.min_occupancy:
        distance = limits.min_occupancy - occupancy
        room = limits.min_occupancy
    else:
        distance = occupancy - limits.max_occupancy
        room = 1.0 - limits.max_occupancy

    # `room` só seria zero se o profile proibisse um lado que a própria escala
    # já torna impossível (nada ocupa menos que 0% nem mais que 100%), ou seja
    # em um desvio que não pode acontecer. Se acontecer, é o pior caso.
    if room <= 0.0:  # pragma: no cover - inalcançável pela escala da métrica
        return OCCUPANCY_PENALTY_MAX

    return min(OCCUPANCY_PENALTY_MAX, distance / room * OCCUPANCY_PENALTY_MAX)
