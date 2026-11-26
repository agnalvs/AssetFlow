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

Desde a Fase B2, o laudo tem uma segunda fonte de posições: o **olho do app**
(:mod:`assetflow.referencias.olho`), gravado em ``olhar.json`` ao lado do PNG.
Ele só informa: nenhum desvio dele reprova. E o laudo termina pedindo o
**olhar** — a lista de verificação da base no primeiro olhar de cada pedido,
uma linha lembrando dela nos remendos, e o que fazer depois.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = [
    "FORMATO_RECEITA",
    "LIBERDADE_EQUILIBRADO",
    "MAX_CAMPO_CONCEITO",
    "MAX_OLHAR",
    "MAX_SIMPLIFICAR",
    "TETO_LICOES",
    "TETO_PENDENTES",
    "bloco_de_conceito",
    "bloco_do_pedido",
    "bloco_em_revisao",
    "conceito_na_medida",
    "formatar_consulta",
    "formatar_laudo",
    "formatar_pendentes",
    "instrucao_avulsa",
    "instrucao_do_pedido",
    "linha_da_banca",
    "linha_de_liberdade",
    "secao_de_licoes",
    "secao_de_opinioes",
]

#: Teto de cada campo de um conceito, e do "o que simplificar" (lote 1).
MAX_CAMPO_CONCEITO = 120
MAX_SIMPLIFICAR = 80

#: Teto da seção de lições no recorte, em caracteres.
TETO_LICOES = 900
#: Teto da linha do olhar que conclui um pedido.
MAX_OLHAR = 240

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

#: As linhas de cada grupo de comandos opcionais da receita, que entram no
#: formato quando o grupo está ligado na gaveta (sessão de lotes).
FORMATO_OPCIONAL = {
    "cor_e_luz": """\
cor e luz (opcionais): raiz "rampas": [{"chaves": "abc", "base": "#rrggbb", "desvio"?: 0–20}] gera os tons do escuro ao claro · raiz "luz": cima-esquerda|cima-direita|cima|esquerda|direita
     camada "material": metal|vidro|tecido|pele|madeira|pelo|pedra · {"sombrear": esfera|cilindro|caixa|plano, "rampa": "abc"} · {"brilho": "c", "sobre": "ab"}
     {"oclusao": "<camada anterior>", "cor": "a"} · {"sombra_projetada": "<camada de trás>", "cor": "a", "distancia"?: 1} — efeitos não valem em camada com espelho""",
    "construcao": """construção (opcional): {"capsula": [x0, y0, x1, y1, (x2, y2)], "espessura": 1–8, "cor": "b", "contorno"?: "k", "vao"?: "<camada>"} · {"copiar": "<camada>", "desloca": [dx, dy], "espelho"?: "x"|"y"}
     raiz "boneco": {"altura", "cabecas": 1.5–8, "chao", "centro", "forma": circulo|quadrado|triangulo, "acao": reta|curva|inclinada, "lado", "pose": parado|andando|ataque|conjurando, "cores": {"pele", "roupa", "contorno"}} — gera camadas boneco_* antes das suas""",
}


def formato_da_receita(ligados) -> str:
    """O formato da receita com as linhas dos grupos opcionais ligados."""
    extras = [FORMATO_OPCIONAL[g] for g in FORMATO_OPCIONAL if g in ligados]
    return "\n".join([FORMATO_RECEITA, *extras])


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
    "nao_aprovado_fora": "NÃO APROVADO (repete o exemplo de construção)",
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
    extras: str = "",
    formato: str = FORMATO_RECEITA,
) -> str:
    """O que o AssetFlow entendeu do pedido, o formato da receita e o recorte.

    ``extras`` (o exemplo de construção e as lições, Fase B2) entram depois do
    recorte, cada um com o seu teto.

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
        linhas.extend([formato, ""])
    # O recorte da base (assetflow.pixel_knowledge) vem pronto; aqui só entra
    # no lugar. Sem nada para este pedido, a linha diz isso em vez de sumir.
    abertura = linha_de_liberdade(liberdade, spec)
    if conhecimento:
        linhas.extend(["conhecimento:", *([abertura] if abertura else []), conhecimento])
    else:
        linhas.append("conhecimento: (nada da base para este pedido)")
        if abertura:
            linhas.append(abertura)
    if extras:
        linhas.append(extras)
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
    conceito_por: str | None = None,
    banca: dict[str, Any] | None = None,
) -> str:
    """Um pedido na lista: cabeçalho, direção de arte, base do ajuste e consulta.

    ``conceito_por`` ("pela autora" ou "pelo Claude") diz que a direção de
    arte é o conceito escolhido (lote 1).
    """
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
    if banca:
        linhas.append(linha_da_banca(banca))
    if direcao_de_arte:
        rotulo = f"conceito escolhido {conceito_por}" if conceito_por else "como escrita no pedido"
        linhas.append(f'direção de arte ({rotulo}): "{direcao_de_arte}"')
    if base:
        linhas.append(base)
    linhas.append(consulta)
    return "\n".join(linhas)


def conceito_na_medida(largura: int, altura: int) -> str:
    """O que cabe num conceito para esta grade (FUNDAMENTOS_E_FERRAMENTAS §2).

    Em 16 px quase tudo vira uma decisão só, a silhueta; em 32 cabe um traço e
    um objeto simples; de 48 em diante, o conceito completo.
    """
    maior = max(largura, altura)
    grade = f"{largura}×{altura}"
    if maior <= 16:
        return (
            f"conceito na medida da grade {grade}: um traço marcante só, de forma grande; "
            "objeto e pose só se couberem nessa mesma forma."
        )
    if maior <= 32:
        return (
            f"conceito na medida da grade {grade}: um traço marcante e um objeto simples; "
            "a pose, curta."
        )
    return (
        f"conceito na medida da grade {grade}: o conceito completo — traço marcante, "
        "silhueta, objeto e pose."
    )


def linha_da_banca(banca: dict[str, Any] | None) -> str:
    """A etiqueta de um pedido da banca de teste, para o bloco."""
    if not banca:
        return ""
    return (
        f"banca {banca.get('rodada')} · {banca.get('item')} ({banca.get('ordem')} de "
        f"{banca.get('total')}): desenhe do zero, sem olhar desenhos de outras rodadas"
    )


_MODO_LIDO = {"eu_escolho": "a autora escolhe", "claude_escolhe": "você escolhe"}


def bloco_de_conceito(
    *,
    pedido_id: str,
    modo: str,
    liberdade: str,
    esperando_min: int,
    resumo: str,
    largura: int,
    altura: int,
    direcao_de_arte: str | None = None,
    recusados: tuple[dict[str, Any], ...] = (),
    banca: dict[str, Any] | None = None,
) -> str:
    """Um pedido na fase de conceito (lote 1): curto, sem medidas nem rampas."""
    linhas = [
        (
            f"== {pedido_id} · conceito ({_MODO_LIDO.get(modo, modo)}) · liberdade {liberdade} · "
            f"na fila há {esperando_min} min"
        )
    ]
    if banca:
        linhas.append(linha_da_banca(banca))
    linhas.append(resumo)
    if direcao_de_arte:
        linhas.append(f'direção de arte (como escrita no pedido): "{direcao_de_arte}"')
    linhas.append(conceito_na_medida(largura, altura))
    linhas.append(
        f"proponha 3 conceitos com propor_conceitos(pedido_id={pedido_id}, conceitos=[{{traco, "
        "silhueta, objeto, pose, simplificar}} × 3]): diferentes entre si e próprios deste "
        "personagem — se um serviria para qualquer personagem do mesmo tipo, refaça. "
        f"\"simplificar\" diz o que some se faltar espaço. Até {MAX_CAMPO_CONCEITO} caracteres "
        f"por campo ({MAX_SIMPLIFICAR} no simplificar)."
    )
    if modo == "claude_escolhe":
        linhas.append(
            "você escolhe: mande também escolhido (1 a 3) e motivo; a resposta traz o recorte "
            "para desenhar em seguida."
        )
    else:
        linhas.append("a autora escolhe um na tela: não desenhe agora.")
    if recusados:
        ditos = " · ".join(
            f"{n}) {c.get('traco', '?')}" for n, c in enumerate(recusados, start=1)
        )
        linhas.append(f"conceitos já recusados pela autora (não repita): {ditos}")
    return "\n".join(linhas)


def bloco_em_revisao(
    *,
    pedido_id: str,
    texto: str,
    candidato: str,
    remendos: int,
    max_remendos: int,
    esperando_min: int,
) -> str:
    """Um pedido que já tem desenho aprovado e só espera o olhar."""
    linhas = [
        f"== {pedido_id} · falta o olhar · na fila há {esperando_min} min",
        f"pedido: {texto}",
        (
            f"já desenhado e aprovado no validador: {candidato}. Veja com ver_asset({candidato}) "
            f"e conclua com concluir_pedido(pedido_id={pedido_id}, olhar=\"<a linha>\")"
            + (
                f", ou remende com desenhar(pedido_id={pedido_id}, base={candidato}, "
                f"receita=<só o que muda>) (remendos: {remendos} de {max_remendos})"
                if remendos < max_remendos
                else f" (os {max_remendos} remendos já foram usados)"
            )
        ),
    ]
    return "\n".join(linhas)


def secao_de_licoes(licoes: list[tuple[str, int, str, str]], *, so_tecnica: bool) -> str:
    """As lições do recorte: ``(id, contador, origem, regra)``, até :data:`TETO_LICOES`."""
    if not licoes:
        return ""
    cabeca = (
        "lições de técnica (a forma é livre em ousado; as mais repetidas primeiro):"
        if so_tecnica
        else "lições (de desenhos anteriores; as mais repetidas primeiro):"
    )
    linhas = [cabeca]
    total = len(cabeca)
    for licao_id, contador, origem, regra in licoes:
        linha = f"- {licao_id} ×{contador}" + (" (autora)" if origem == "autora" else "") + f": {regra}"
        if total + len(linha) + 1 > TETO_LICOES:
            break
        linhas.append(linha)
        total += len(linha) + 1
    return "\n".join(linhas) if len(linhas) > 1 else ""


def secao_de_opinioes(opinioes: list[tuple[str, str, str]]) -> str:
    """As opiniões novas da autora: ``(asset_id, pedido do asset, motivo)``."""
    if not opinioes:
        return ""
    linhas = [
        (
            f"opiniões novas da autora ({len(opinioes)}): converta cada uma em lição com "
            "registrar_licao(asset_id=..., da_autora=true, tema=..., errou=..., porque=..., "
            "regra=...), sem mudar o sentido do texto dela; o texto original fica guardado ao lado."
        )
    ]
    for asset_id, pedido, motivo in opinioes:
        linhas.append(f"- {asset_id} ({pedido}): \"{motivo}\"")
    return "\n".join(linhas)


def instrucao_do_pedido(
    pedido_id: str,
    candidato: str,
    *,
    remendos: int,
    max_remendos: int,
    candidatos: tuple[str, ...] = (),
) -> str:
    """O que fazer depois de olhar um desenho aprovado de um pedido."""
    if remendos < max_remendos:
        return (
            "Diga em uma linha o que está feio ou estranho. Se houver algo, corrija com UM "
            f"remendo — desenhar(pedido_id={pedido_id}, base={candidato}, receita=<só o que "
            "muda>) — e registre a lição com registrar_licao. Se estiver bom, diga que está e "
            f"conclua: concluir_pedido(pedido_id={pedido_id}, olhar=\"<a linha>\")."
        )
    escolha = (
        f", com asset_id entre {', '.join(candidatos)} se um anterior estava melhor"
        if len(candidatos) > 1
        else ""
    )
    return (
        f"Os {max_remendos} remendos do pedido acabaram: diga em uma linha como ficou e "
        f"conclua com concluir_pedido(pedido_id={pedido_id}, olhar=\"<a linha>\"){escolha}."
    )


def instrucao_avulsa(asset_id: str) -> str:
    """O que fazer depois de olhar um desenho avulso (sem pedido da fila)."""
    return (
        "Diga em uma linha o que está feio ou estranho. Se houver algo, corrija com um "
        f"remendo — desenhar(base={asset_id}, receita=<só o que muda>) — e registre a lição "
        "com registrar_licao. Se estiver bom, diga que está e pare."
    )


def formatar_pendentes(
    blocos: list[str],
    *,
    restantes: int,
    reserva_min: float,
    rampas: str,
    opinioes: str = "",
    com_formato: bool = True,
    formato: str = FORMATO_RECEITA,
) -> str:
    """A resposta de ``pedidos_pendentes``: as opiniões novas, o comum uma vez, depois cada pedido.

    Sem ``com_formato`` (só pedidos de conceito ou de olhar), o formato da
    receita e as rampas ficam de fora: ninguém vai desenhar nesta resposta.
    """
    if not blocos:
        vazio = (
            "nenhum pedido esperando desenho na fila do AssetFlow"
            + (f" (há {restantes} que não couberam nesta resposta)" if restantes else "")
            + "."
        )
        return f"{opinioes}\n\n{vazio}" if opinioes else vazio
    quantos = len(blocos)
    plural = "s" if quantos > 1 else ""
    linhas = [*([opinioes, ""] if opinioes else []),
        (
            f"{quantos} pedido{plural} da tela, reservado{plural} para você por "
            f"{reserva_min:g} min (mais {restantes} na fila)."
        ),
        (
            "Desenhe cada um com desenhar(pedido_id=..., receita=...): o texto, o perfil e "
            "os controles vêm do pedido. Cada desenhar renova a reserva dos outros."
        ),
    ]
    if com_formato:
        linhas.extend(["", formato])
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
    falhas_extra: tuple[str, ...] = (),
    olho: list[str] | None = None,
    olhar: str | None = None,
    instrucao: str | None = None,
) -> str:
    """O laudo de um desenho: o veredito primeiro, depois o que fazer com ele.

    ``falhas_extra`` são reprovações de fora do validador (a guarda "repete o
    exemplo"); ``olho``, as linhas do olho do app; ``olhar``, a lista de
    verificação (ou o lembrete dela); ``instrucao``, o que fazer depois.
    """
    aceite = validacao.get("acceptance") or {}
    status = aceite.get("status") or variante.status or "desconhecido"
    nota = aceite.get("quality_score", variante.quality_score)
    minimo = aceite.get("quality_threshold")
    exato = aceite.get("pixel_exact", variante.pixel_exact)

    linhas: list[str] = []
    if remendo:
        linhas.append(remendo)
    if falhas_extra and status == "approved":
        status = "nao_aprovado_fora"
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

    falhas = [_mensagem(item) for item in aceite.get("failures") or []] + list(falhas_extra)
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
    if olho:
        linhas.extend(olho)
    if olhar:
        linhas.append(olhar)
    if instrucao:
        linhas.append(instrucao)
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
