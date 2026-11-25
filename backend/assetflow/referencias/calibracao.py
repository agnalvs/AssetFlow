"""Relatório de calibração: as referências contra os números ``a_calibrar``.

Ele **propõe**; nunca altera ``proporcoes.yaml`` nem nenhum outro YAML. Cada
medida da base sai numa de quatro situações, ditas com franqueza:

- **comparada**: há quadros que medem a mesma coisa, e sai uma proposta;
- **não comparável**: o número depende do quadro (chão, margem, ocupação,
  folga), e o quadro das referências é outro;
- **circular**: a altura do corpo escolhe os quadros de porte parecido, então
  compará-la com eles devolveria ela mesma;
- **não medida**: exigiria separar cabeça, tronco e membros.

Cada parte (estilo e porte) segue as regras da linha ``referências:``: pacote
abaixo de ``minimo_por_pacote`` sai dela, com nome e contagem no relatório. A
parte com menos de ``minimo_de_pacotes`` continua aqui, com os números, mas
marcada como insuficiente e sem proposta: ela não chega ao Claude.

A última seção roda o validador sobre as referências, com os limiares de
``config/quality.yaml``, e propõe esses limiares pela regra escrita lá: o p90
do pacote mais alto, arredondado para cima. Só propõe.
"""

from __future__ import annotations

import math
from collections import Counter
from statistics import median

import numpy as np
from PIL import Image

from ..pixel import PixelOutputSpec, PixelValidator, QualityCalibration
from ..pixel_knowledge import BaseDeConhecimento
from .colecao import ParteDaLinha, QuadroMedido, ReferenciasAtivas, quantis
from .medidor import carregar, detectar_escala

__all__ = ["MAX_VALIDADOS_POR_PACOTE", "PERCENTIL_DA_PROPOSTA", "gerar_relatorio"]

#: Teto de quadros validados por pacote, para o relatório não levar minutos.
#: Acima dele, a amostra é espaçada por igual no pacote inteiro (os primeiros
#: quadros costumam ser de um personagem só).
MAX_VALIDADOS_POR_PACOTE = 300

#: O limiar proposto é este percentil do pacote mais alto (``quality.yaml``).
PERCENTIL_DA_PROPOSTA = 90

_NAO_COMPARAVEL = {
    "chao_y": "depende do quadro, e o quadro das referências é outro",
    "margem_px": "depende do quadro",
    "folga_topo_px": "depende do quadro",
    "ocupacao_min": "depende do quadro (ocupação é pixels ÷ área do quadro)",
}
_NAO_MEDIDA = {
    "cabecas": "exige separar a cabeça",
    "cabeca_px": "exige separar a cabeça",
    "tronco_px": "exige separar o tronco",
    "pernas_px": "exige separar as pernas",
    "olho_px": "exige achar o olho",
    "largura_cabeca_px": "exige separar a cabeça",
    "largura_tronco_px": "exige separar o tronco",
    "largura_braco_px": "exige separar o braço",
    "largura_perna_px": "exige separar a perna",
    "vao_braco_px": "exige separar o braço",
    "braco_px": "exige separar o braço",
}
#: Forma da base -> (tipo de asset, corpo) dos quadros que valem para ela.
_ALVO = {"humanoid": ("character", "humanoid"), "prop": ("prop", None)}


def gerar_relatorio(
    base: BaseDeConhecimento,
    referencias: ReferenciasAtivas,
    calibracao: QualityCalibration | None = None,
) -> str:
    """O relatório inteiro, em Markdown. ``calibracao``: a de ``quality.yaml``."""
    linhas = [
        "# Calibração pelas referências",
        "",
        "Gerado por `python -m assetflow.referencias calibrar`. **Só propõe**: nenhum YAML",
        "foi alterado. Medidas de conteúdo incluem chapéu, penacho e arma.",
        "",
        "## Pacotes",
        "",
    ]
    if not referencias.pacotes:
        linhas.append("Nenhum pacote ativo e autorizado. Veja `config/pixel_knowledge/referencias.yaml`.")
    for pacote in referencias.pacotes:
        n = sum(1 for q in referencias.quadros if q.pacote == pacote.id)
        linhas.append(f"- `{pacote.id}` — {pacote.autor}, {pacote.license_id}, {n} quadros")
    for aviso in referencias.avisos:
        linhas.append(f"- aviso: {aviso}")

    for forma in base.formas.values():
        tipo, corpo = _ALVO.get(forma.id, (forma.id, None))
        candidatos = referencias.candidatos(tipo, corpo)
        estilo = referencias.estilo(tipo, corpo)
        tamanhos = [(t, m, None) for t, m in forma.tamanhos.items()]
        tamanhos += [(q.tamanho, forma.tamanhos[q.corpo], q) for q in forma.quadros.values()]
        for tamanho, medidas, quadro in tamanhos:
            titulo = f"{forma.nome} {tamanho}" + (f" (corpo {quadro.corpo})" if quadro else "")
            linhas += ["", f"## {titulo}", ""]
            if not candidatos:
                linhas.append(f"Sem quadros de `{tipo}`" + (f"/`{corpo}`" if corpo else "") + " nas referências ativas.")
                continue
            altura = medidas["altura_px"].valor if "altura_px" in medidas else None
            porte = referencias.porte(tipo, corpo, altura)
            faixa = referencias.faixa(altura)
            linhas.append(
                f"{len(estilo.quadros)} quadros de estilo; "
                + (
                    f"{len(porte.quadros)} de porte parecido ({faixa[0]}–{faixa[1]} px de altura)."
                    if faixa
                    else "sem faixa de porte (forma sem altura ou sem `porte.faixa_altura`)."
                )
            )
            linhas += _avisos_da_parte("estilo", estilo, referencias)
            if faixa:
                linhas += _avisos_da_parte("porte", porte, referencias)
            linhas += ["", "| medida | base | referências (p25–mediana–p75, n) | proposta | nota |",
                       "|---|---|---|---|---|"]
            nomes = dict.fromkeys([*medidas, "chao_y"] if quadro else medidas)
            for nome in nomes:
                valor = quadro.chao_y.valor if quadro and nome == "chao_y" else medidas[nome].valor
                linhas.append(_linha_da_medida(nome, valor, estilo, porte, altura))
            if porte.quadros:
                cores = quantis(list(porte.quadros), lambda q: q.cores)
                linhas.append(
                    f"| cores por quadro (informativo) | — | {_resumo(cores, porte)} | — | "
                    "o limite vem do pedido; serve de régua para o 8 ou 12 de costume |"
                )

    linhas += ["", *_secao_do_validador(referencias, calibracao or QualityCalibration())]
    return "\n".join(linhas) + "\n"


def _avisos_da_parte(nome: str, parte: ParteDaLinha, referencias: ReferenciasAtivas) -> list[str]:
    """Quem saiu da parte por amostra pequena, e se ela basta para a linha."""
    linhas = []
    if parte.fora:
        minimo = referencias.configuracao.minimo_por_pacote
        fora = ", ".join(f"`{p}` ({n})" for p, n in parte.fora)
        linhas.append(f"- {nome}: fora por amostra pequena (menos de {minimo} quadros na parte): {fora}.")
    if parte.quadros and not parte.suficiente:
        linhas.append(
            f"- {nome}: **insuficiente** ({parte.falta}): os números de {nome} abaixo "
            "não entram na linha `referências:` nem no `ver_referencia`."
        )
    return ["", *linhas] if linhas else []


def _linha_da_medida(
    nome: str,
    valor: object,
    estilo: ParteDaLinha,
    porte: ParteDaLinha,
    altura: int | None,
) -> str:
    base = _fmt(valor, nome)
    if nome == "tons_por_material":
        tons = quantis(list(estilo.quadros), lambda q: q.tons_por_grupo)
        if not tons:
            return f"| {nome} | {base} | sem dados | — | — |"
        proposta = round(tons[1])
        if not estilo.suficiente:
            sugestao = "— (insuficiente)"
        else:
            sugestao = "(manter)" if proposta == valor else str(proposta)
        return (
            f"| {nome} | {base} | {_resumo(tons, estilo)} | {sugestao} | "
            "por grupo de matiz, de qualquer tamanho; material não se separa por matiz |"
        )
    if nome == "altura_px":
        return (
            f"| {nome} | {base} | — | (manter) | circular: é ela que escolhe os quadros de porte "
            "parecido; quadros de outros pacotes têm outra escala |"
        )
    if nome in _NAO_COMPARAVEL:
        return f"| {nome} | {base} | — | — | não comparável: {_NAO_COMPARAVEL[nome]} |"
    if nome in _NAO_MEDIDA:
        extra = ""
        if nome == "largura_tronco_px" and porte.quadros and altura:
            largura = quantis(list(porte.quadros), lambda q: q.largura / q.altura)[1] * altura
            extra = (
                f"; o conteúdo do mesmo porte tem largura de ~{round(largura)} px "
                "(com braços, arma e pose)"
                + ("" if porte.suficiente else f"; porte insuficiente: {porte.falta}")
            )
        return f"| {nome} | {base} | — | — | não medida: {_NAO_MEDIDA[nome]}{extra} |"
    return f"| {nome} | {base} | — | — | sem comparação definida |"


def _secao_do_validador(referencias: ReferenciasAtivas, calibracao: QualityCalibration) -> list[str]:
    micro, rara = calibracao.microcluster, calibracao.rare_colors
    linhas = [
        "## O validador atual sobre as referências",
        "",
        "Cada quadro validado no próprio tamanho, sem limite de paleta, com os limiares de",
        f"`{calibracao.source}`. Até {MAX_VALIDADOS_POR_PACOTE} quadros por pacote, espaçados por igual.",
        "Avisos: blocos pequenos (`PX-WARN-MICROCLUSTER`) e cor rara (`PX-WARN-PALETTE-RARE`);",
        "p90: percentil 90 da fração de blocos pequenos e da contagem de cores raras.",
        "",
    ]
    if referencias.esta_vazia or referencias.raiz is None:
        return [*linhas, "Sem referências ativas."]
    validador = PixelValidator(calibration=calibracao)
    linhas += [
        (
            "| pacote | quadros | nota (mediana) | aviso de blocos pequenos | aviso de cor rara "
            "| blocos pequenos p90 | cores raras p90 |"
        ),
        "|---|---|---|---|---|---|---|",
    ]
    p90_micro: dict[str, float] = {}
    p90_raras: dict[str, float] = {}
    for pacote in referencias.pacotes:
        quadros = _amostra([q for q in referencias.quadros if q.pacote == pacote.id])
        if not quadros:
            continue
        notas, avisos, fracoes, raras = [], Counter(), [], []
        cache: dict[str, np.ndarray] = {}
        for q in quadros:
            imagem = _quadro_como_imagem(referencias, q, cache)
            spec = PixelOutputSpec(
                logical_size={"width": imagem.width, "height": imagem.height},
                palette={"mode": "max_colors", "max_colors": 256},
                validation={"boundary_touch": "ignore", "min_occupancy": 0.0, "max_occupancy": 1.0},
            )
            relatorio = validador.validate(imagem, spec)
            notas.append(relatorio.quality.score)
            fracoes.append(relatorio.quality.metrics.microcluster_ratio)
            raras.append(len(relatorio.quality.metrics.rare_colors))
            for codigo in {aviso.code for aviso in relatorio.quality.warnings}:
                avisos[codigo] += 1
        n = len(quadros)
        p90_micro[pacote.id] = float(np.percentile(fracoes, PERCENTIL_DA_PROPOSTA))
        p90_raras[pacote.id] = float(np.percentile(raras, PERCENTIL_DA_PROPOSTA))
        linhas.append(
            f"| `{pacote.id}` | {n} | {_fmt(median(notas))} | "
            f"{_pct(avisos['PX-WARN-MICROCLUSTER'] / n)} | {_pct(avisos['PX-WARN-PALETTE-RARE'] / n)} | "
            f"{_fmt(round(p90_micro[pacote.id], 3), casas=3)} | {_fmt(p90_raras[pacote.id])} |"
        )
    if not p90_micro:
        return linhas

    alto_micro = max(p90_micro, key=lambda p: (p90_micro[p], p))
    alto_raras = max(p90_raras, key=lambda p: (p90_raras[p], p))
    proposta_micro = math.ceil(round(p90_micro[alto_micro] * 100, 6)) / 100
    proposta_raras = math.ceil(round(p90_raras[alto_raras], 6))
    linhas += [
        "",
        (
            f"Proposta pela regra de `quality.yaml`: p{PERCENTIL_DA_PROPOSTA} do pacote mais alto, "
            "arredondado para cima, para nenhum pacote receber o aviso em mais de "
            f"{100 - PERCENTIL_DA_PROPOSTA}% dos quadros. Só propõe: o arquivo não foi alterado."
        ),
        "",
        "| limiar | configurado (aviso / desconto) | proposta | pacote mais alto (p90) |",
        "|---|---|---|---|",
        (
            f"| blocos pequenos (fração) | {_fmt(micro.warning_ratio, casas=3)} / "
            f"{_fmt(micro.free_ratio, casas=3)} | {_fmt(proposta_micro, casas=3)} | "
            f"`{alto_micro}` ({_fmt(round(p90_micro[alto_micro], 3), casas=3)}) |"
        ),
        (
            f"| cores raras (quantas) | {rara.warning_count} / {rara.free_count} | "
            f"{proposta_raras} | `{alto_raras}` ({_fmt(p90_raras[alto_raras])}) |"
        ),
    ]
    return linhas


def _amostra(quadros: list[QuadroMedido]) -> list[QuadroMedido]:
    """Até ``MAX_VALIDADOS_POR_PACOTE`` quadros, espaçados pelo pacote inteiro."""
    n = len(quadros)
    if n <= MAX_VALIDADOS_POR_PACOTE:
        return quadros
    return [quadros[i * n // MAX_VALIDADOS_POR_PACOTE] for i in range(MAX_VALIDADOS_POR_PACOTE)]


def _quadro_como_imagem(referencias: ReferenciasAtivas, q: QuadroMedido, cache: dict) -> Image.Image:
    caminho = referencias.raiz / q.pacote / "original" / q.arquivo
    chave = str(caminho)
    if chave not in cache:
        rgba = carregar(caminho)
        escala = detectar_escala(rgba)
        cache.clear()  # um arquivo por vez basta: os quadros vêm em ordem de arquivo
        cache[chave] = rgba[::escala, ::escala] if escala > 1 else rgba
    x, y, largura, altura = q.caixa
    pedaco = np.ascontiguousarray(cache[chave][y : y + altura, x : x + largura])
    return Image.fromarray(pedaco, "RGBA")


def _resumo(valores: tuple[float, float, float], parte: ParteDaLinha) -> str:
    """p25–mediana–p75 (peso igual por pacote), com quantos quadros e pacotes."""
    p25, p50, p75 = valores
    marca = "" if parte.suficiente else f"; insuficiente: {parte.falta}"
    return f"{_fmt(p25)}–{_fmt(p50)}–{_fmt(p75)} (n={len(parte.quadros)}, {parte.pacotes} pac.{marca})"


def _fmt(valor: object, nome: str = "", *, casas: int = 1) -> str:
    if isinstance(valor, float):
        return f"{valor:.{casas}f}".rstrip("0").rstrip(".").replace(".", ",")
    if isinstance(valor, tuple):
        # Olho é largura × altura; o resto que vem em par é faixa.
        return "×".join(map(str, valor)) if nome == "olho_px" else " a ".join(map(str, valor))
    return str(valor)


def _pct(fracao: float) -> str:
    return f"{round(fracao * 100)}%"
