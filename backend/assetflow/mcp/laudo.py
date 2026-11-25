"""Os textos que o Claude lê: o que o pedido virou, e o laudo de um desenho.

Texto, e não JSON, porque é o mais barato de ler e o mais fácil de agir: cada
linha diz uma coisa. Nada aqui recalcula o pedido — o resumo do pedido **lê**
o ``FinalResolvedSpec``, e o laudo **lê** os relatórios que o Pixel Exact e o
Pixel Optimizer já gravaram (``validation.json``, ``optimizer.json``).

Quando um problema tem lugar, o laudo diz onde, com teto. Só entra posição
que o validador expõe: pixels isolados (``orphan_positions``) e o lado em que o
conteúdo encosta na borda (pela caixa do conteúdo e o tamanho da grade). O
contorno fragmentado o validador só conta — não diz onde —, e o laudo não
inventa.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = [
    "FORMATO_RECEITA",
    "LIBERDADE_EQUILIBRADO",
    "TETO_PENDENTES",
    "bloco_do_pedido",
    "formatar_consulta",
    "formatar_laudo",
    "formatar_pendentes",
    "linha_de_liberdade",
]

#: A abertura do recorte em ``equilibrado``. Não cita números: os limites
#: duros estão nas linhas ``grade``/``paleta``/``fundo`` logo acima.
LIBERDADE_EQUILIBRADO = (
    "liberdade: equilibrado — as medidas, a luz e as rampas abaixo são ponto de "
    "partida, não regra: desvie delas quando o pedido justificar (uma capa longa, "
    "um chapéu alto, uma cor que nenhuma rampa tem). Grade, número de cores e "
    "fundo não mudam."
)

#: Teto da resposta de ``pedidos_pendentes``, em caracteres (~5.300 tokens a
#: ~3 caracteres por token). O pedido que não couber fica na fila, sem reserva.
TETO_PENDENTES = 16_000

#: O formato da receita, em poucas linhas. Vai na resposta de
#: ``consultar_pedido`` — e não na descrição de ``desenhar`` — para só ocupar
#: contexto quando há desenho. Referência completa: backend/docs/DESENHISTA.md.
FORMATO_RECEITA = """\
receita: {"grade": [l, a], "paleta": {"k": "#rrggbb", ...}, "camadas": [{"nome": ..., "espelho"?: "x"|"y"|"xy", "ops": [...]}]}
ops: ret|elipse [x, y, l, a] e poligono [x0, y0, ...], com cor e contorno? · linha [x0, y0, x1, y1, ...] cor
     balde [x, y] cor (não vale em camada com espelho) · px ["linha", ...] em [x, y] ('.' mantém, '-' apaga)
origem no canto superior esquerdo; chave de cor tem 1 caractere; camada seguinte pinta por cima;
o espelho só preenche o que a camada não pintou."""

#: Teto de coordenadas de pixels isolados listadas no laudo.
MAX_POSICOES = 8

_ORIGENS = {
    "manual_override": "correção manual",
    "explicit_prompt": "do texto",
    "ui_selection": "da interface",
    "inference": "inferido",
    "category_inference": "inferido da categoria",
    "profile_default": "do perfil",
    "global_default": "padrão",
}

_STATUS = {
    "approved": "APROVADO",
    "quality_warning": "NÃO APROVADO (qualidade abaixo do mínimo)",
    "rejected": "REPROVADO (falhou requisito técnico)",
}

#: Os tipos de problema do revisor do Optimizer (``pixel/optimizer/reviewer.py``)
#: em português. Tipo sem tradução aparece como veio.
_TIPOS_DE_PROBLEMA = {
    "orphan_pixel": "pixels isolados",
    "fragmented_outline": "contorno fragmentado",
    "palette_overflow": "cores além do limite",
    "locked_palette_violation": "cores fora da paleta travada",
    "border_touch": "encosto na borda",
}


# ---------------------------------------------------------------------------
# consultar_pedido
# ---------------------------------------------------------------------------
def formatar_consulta(
    pedido: str,
    perfil: str,
    spec: Any,
    *,
    conhecimento: str = "",
    liberdade: str | None = None,
    com_formato: bool = True,
) -> str:
    """O que o AssetFlow entendeu do pedido, o formato da receita e o recorte.

    ``liberdade`` abre o recorte com a linha dela (nada em ``fiel``). Sem
    ``com_formato``, o formato da receita fica de fora — quem lista vários
    pedidos o põe uma vez só.
    """
    asset = spec.asset
    partes_tipo = [_valor(asset.type)]
    if asset.subject:
        partes_tipo.append(asset.subject)
    if getattr(asset, "category", None):
        partes_tipo.append(f"categoria {_valor(asset.category)}")
    corpo = _valor(spec.character.body_type) if spec.character else "unknown"
    if corpo != "unknown":
        # A origem no fim da linha é a do tipo; o corpo só diz a dele quando
        # ela é outra — o caso do corpo deduzido da categoria.
        origem_do_corpo = _origem(spec, "character.body_type")
        if origem_do_corpo != _origem(spec, "asset.type"):
            partes_tipo.append(f"corpo {corpo} ({origem_do_corpo})")
        else:
            partes_tipo.append(f"corpo {corpo}")

    logica = spec.logical_resolution
    grade = (
        f"{logica.width}×{logica.height} ({_origem(spec, 'logical_resolution')})"
        if logica
        else "sem grade lógica (o pedido não é Pixel Art)"
    )

    estilo = spec.style
    luz = estilo.shading.light_direction or "não definida"

    linhas = [
        f"pedido: {pedido} (perfil {perfil})",
        f"tipo: {' · '.join(partes_tipo)} ({_origem(spec, 'asset.type')})",
        (
            f"grade: {grade} · paleta: {_paleta(spec.palette)} ({_origem(spec, 'palette')}) · "
            f"fundo: {_fundo(spec.background.mode)} ({_origem(spec, 'background')})"
        ),
        (
            f"estilo: contorno {_valor(estilo.outline.mode)} · sombreamento "
            f"{_valor(estilo.shading.mode)} · luz {luz}"
        ),
        f"motor: {spec.engine.engine_id or 'automático'}",
        "",
    ]
    if com_formato:
        linhas.extend([FORMATO_RECEITA, ""])
    # O recorte da base (assetflow.pixel_knowledge) vem pronto; aqui só entra
    # no lugar. Sem nada para este pedido, a linha diz isso em vez de sumir.
    abertura = linha_de_liberdade(liberdade, spec)
    if conhecimento:
        linhas.extend(["conhecimento:", *([abertura] if abertura else []), conhecimento])
    else:
        linhas.append("conhecimento: (nada da base para este pedido)")
        if abertura:
            linhas.append(abertura)
    return "\n".join(linhas)


def linha_de_liberdade(liberdade: str | None, spec: Any) -> str:
    """A primeira linha do recorte em ``equilibrado`` e em ``ousado``.

    A do ousado diz os limites duros com os números do spec — grade, cores e
    fundo —, e por isso é montada aqui: o recorte só lê cinco campos do spec, e
    o fundo não é um deles.
    """
    valor = _valor(liberdade) if liberdade else "fiel"
    if valor == "equilibrado":
        return LIBERDADE_EQUILIBRADO
    if valor != "ousado":
        return ""
    limites = []
    logica = spec.logical_resolution
    if logica is not None:
        limites.append(f"grade {logica.width}×{logica.height}")
    paleta = spec.palette
    if paleta is not None and paleta.mode == "locked":
        limites.append(f"só as {len(paleta.colors)} cores da paleta travada")
    elif paleta is not None and paleta.max_colors:
        limites.append(f"até {paleta.max_colors} cores com o contorno")
    limites.append(f"fundo {_fundo(spec.background.mode)}")
    juntos = ", ".join(limites[:-1]) + f" e {limites[-1]}" if len(limites) > 1 else limites[0]
    return (
        f"liberdade: ousado — os limites duros são {juntos}; o resto é seu. Proponha "
        "uma silhueta e uma ideia próprias para o pedido, em vez da figura de sempre."
    )


# ---------------------------------------------------------------------------
# pedidos_pendentes
# ---------------------------------------------------------------------------
def bloco_do_pedido(
    *,
    pedido_id: str,
    tipo: str,
    liberdade: str,
    esperando_min: int,
    consulta: str,
    direcao_de_arte: str | None = None,
    tentativas: int = 0,
    max_tentativas: int = 3,
    ultimo_asset: str | None = None,
    ajuste: tuple[str, str] | None = None,
    base: str | None = None,
) -> str:
    """Um pedido na lista: cabeçalho, direção de arte, base do ajuste e consulta."""
    if ajuste is not None:
        origem, texto = ajuste
        cabeca = f'== {pedido_id} · ajuste de {origem}: "{texto}"'
    else:
        cabeca = f"== {pedido_id} · {tipo}"
    cabeca += f" · liberdade {liberdade} · na fila há {esperando_min} min"
    linhas = [cabeca]
    if tentativas:
        linhas.append(
            f"já houve {tentativas} de {max_tentativas} desenho(s) não aprovado(s); o "
            f"último é {ultimo_asset}: corrija com base={ultimo_asset}"
        )
    if direcao_de_arte:
        linhas.append(f'direção de arte (como escrita no pedido): "{direcao_de_arte}"')
    if base:
        linhas.append(base)
    linhas.append(consulta)
    return "\n".join(linhas)


def formatar_pendentes(
    blocos: list[str], *, restantes: int, reserva_min: float, rampas: str
) -> str:
    """A resposta de ``pedidos_pendentes``: o comum uma vez, depois cada pedido."""
    if not blocos:
        return (
            "nenhum pedido esperando desenho na fila do AssetFlow"
            + (f" (há {restantes} que não couberam nesta resposta)" if restantes else "")
            + "."
        )
    quantos = len(blocos)
    plural = "s" if quantos > 1 else ""
    linhas = [
        (
            f"{quantos} pedido{plural} da tela, reservado{plural} para você por "
            f"{reserva_min:g} min (mais {restantes} na fila)."
        ),
        (
            "Desenhe cada um com desenhar(pedido_id=..., receita=...): o texto, o perfil e "
            "os controles vêm do pedido. Cada desenhar renova a reserva dos outros."
        ),
        "",
        FORMATO_RECEITA,
    ]
    if rampas:
        linhas.extend(["", rampas])
    for bloco in blocos:
        linhas.extend(["", bloco])
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# desenhar
# ---------------------------------------------------------------------------
def formatar_laudo(
    *,
    pedido: str,
    asset_id: str,
    variante: Any,
    spec: Any,
    validacao: dict[str, Any],
    otimizacao: dict[str, Any] | None,
    avisos_receita: list[str],
    caminho: Path,
    remendo: str | None = None,
) -> str:
    """O laudo de um desenho: o veredito primeiro, depois o que fazer com ele."""
    aceite = validacao.get("acceptance") or {}
    status = aceite.get("status") or variante.status or "desconhecido"
    nota = aceite.get("quality_score", variante.quality_score)
    minimo = aceite.get("quality_threshold")
    exato = aceite.get("pixel_exact", variante.pixel_exact)

    linhas: list[str] = []
    if remendo:
        linhas.append(remendo)
    linhas.append(f"{_STATUS.get(status, status.upper())} · {asset_id} · {pedido}")
    linhas.append(
        f"Pixel Exact {'✓' if exato else '✗'} · qualidade {nota}/100"
        + (f" (mínimo {minimo})" if minimo is not None else "")
    )

    limite = spec.palette.max_colors if spec.palette else None
    cores = variante.color_count
    linhas.append(
        f"grade {variante.logical_width}×{variante.logical_height} · "
        + (f"{cores} de {limite} cores" if limite else f"{cores} cores")
        + f" · fundo {_fundo(spec.background.mode)}"
    )

    falhas = [_mensagem(item) for item in aceite.get("failures") or []]
    if falhas:
        linhas.append("falhas:")
        linhas.extend(f"- {falha}" for falha in falhas)

    problemas = _problemas(validacao)
    if problemas:
        linhas.append("problemas:")
        linhas.extend(problemas)

    if avisos_receita:
        linhas.append("avisos da receita:")
        linhas.extend(f"- {aviso}" for aviso in avisos_receita)

    if otimizacao is not None:
        linhas.append(f"Optimizer: {_otimizacao(otimizacao)}")
    linhas.append(f"arquivo: {caminho}")
    return "\n".join(linhas)


def _problemas(validacao: dict[str, Any]) -> list[str]:
    """Os avisos de qualidade, cada um com o lugar quando o validador o expõe."""
    qualidade = validacao.get("quality") or {}
    metricas = qualidade.get("metrics") or {}
    tecnico = validacao.get("technical") or {}

    linhas = []
    for aviso in qualidade.get("warnings") or []:
        linhas.append(f"- {aviso.get('message', aviso.get('code', '?'))}")
        onde = _onde(aviso, metricas, tecnico)
        if onde:
            linhas.append(f"  onde: {onde}")
    return linhas


def _onde(aviso: dict[str, Any], metricas: dict[str, Any], tecnico: dict[str, Any]) -> str:
    codigo = aviso.get("code")
    if codigo == "PX-WARN-ORPHAN":
        posicoes = list(metricas.get("orphan_positions") or [])
        if not posicoes:
            return ""
        total = int(metricas.get("orphan_pixel_count") or len(posicoes))
        mostradas = posicoes[:MAX_POSICOES]
        texto = " ".join(f"({x},{y})" for x, y in mostradas)
        resto = total - len(mostradas)
        return texto + (f" +{resto}" if resto > 0 else "")

    if codigo == "PX-WARN-BORDER":
        caixa = (aviso.get("detail") or {}).get("bounding_box") or metricas.get("bounding_box")
        largura, altura = tecnico.get("width"), tecnico.get("height")
        if not caixa or largura is None or altura is None:
            return ""
        x0, y0, x1, y1 = caixa  # inclusiva, como o validador grava
        lados = [
            lado
            for lado, encosta in (
                ("cima", y0 == 0),
                ("baixo", y1 == altura - 1),
                ("esquerda", x0 == 0),
                ("direita", x1 == largura - 1),
            )
            if encosta
        ]
        return ", ".join(lados)

    # PX-WARN-OUTLINE-FRAGMENTED e os demais: o validador não diz onde.
    return ""


def _otimizacao(dados: dict[str, Any]) -> str:
    status = dados.get("status")
    trocados = dados.get("pixels_changed") or 0
    antes, depois = dados.get("score_before"), dados.get("score_after")
    if status == "skipped":
        return "nada a corrigir"
    if status == "optimized":
        return f"corrigiu {trocados} pixel(s); qualidade {antes} → {depois}"
    if status == "exhausted":
        return (
            f"parou no teto de iterações; corrigiu {trocados} pixel(s); "
            f"qualidade {antes} → {depois}"
        )
    if status == "disabled":
        return "desligado na instalação"
    if status == "no_safe_repairs":
        mantidos = _mantidos(dados)
        return "nenhum reparo seguro" + (
            f"; manteve de propósito {mantidos} (motivos no optimizer.json ao lado do PNG)"
            if mantidos
            else ""
        )
    return str(status)


def _mantidos(dados: dict[str, Any]) -> str:
    """O que o Optimizer decidiu preservar, contado por tipo."""
    contagem: dict[str, int] = {}
    for plano in dados.get("plans") or []:
        for recusa in plano.get("declined") or []:
            tipo = recusa.get("issue_type", "?")
            contagem[tipo] = contagem.get(tipo, 0) + 1
    return ", ".join(
        f"{_TIPOS_DE_PROBLEMA.get(tipo, tipo)} ×{quantos}" for tipo, quantos in contagem.items()
    )


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _valor(valor: Any) -> str:
    return str(getattr(valor, "value", valor))


def _origem(spec: Any, campo: str) -> str:
    return _ORIGENS.get(_valor(spec.source_of(campo)), _valor(spec.source_of(campo)))


def _paleta(paleta: Any) -> str:
    if paleta is None:
        return "livre"
    if paleta.mode == "locked" and paleta.colors:
        return f"travada em {len(paleta.colors)} cores ({' '.join(paleta.colors)})"
    if paleta.max_colors:
        return f"até {paleta.max_colors} cores"
    return "livre"


def _fundo(modo: Any) -> str:
    return {"transparent": "transparente", "solid": "sólido"}.get(_valor(modo), _valor(modo))


def _mensagem(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("message") or item.get("code") or item)
    return str(item)
