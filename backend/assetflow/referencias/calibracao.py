"""Relatório de calibração: as referências contra os números ``a_calibrar``.

Ele **propõe**; nunca altera ``proporcoes.yaml`` nem nenhum outro YAML. Cada
medida da base sai numa de quatro situações, ditas com franqueza:

- **comparada**: há quadros que medem a mesma coisa, e sai uma proposta;
- **não comparável**: o número depende do quadro (chão, margem, ocupação,
  folga), e o quadro das referências é outro;
- **circular**: a altura do corpo escolhe os quadros de porte parecido, então
  compará-la com eles devolveria ela mesma;
- **não medida**: exigiria separar cabeça, tronco e membros.

A última seção roda o validador atual sobre as referências: é o insumo da
calibração anotada na Fase 5 (blocos pequenos e cor de 1 pixel).
"""

from __future__ import annotations

from collections import Counter
from statistics import median

import numpy as np
from PIL import Image

from ..pixel import PixelOutputSpec, PixelValidator
from ..pixel_knowledge import BaseDeConhecimento
from .colecao import QuadroMedido, ReferenciasAtivas, quantis
from .medidor import carregar, detectar_escala

__all__ = ["MAX_VALIDADOS_POR_PACOTE", "gerar_relatorio"]

#: Teto de quadros validados por pacote, para o relatório não levar minutos.
MAX_VALIDADOS_POR_PACOTE = 300

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


def gerar_relatorio(base: BaseDeConhecimento, referencias: ReferenciasAtivas) -> str:
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
        tamanhos = [(t, m, None) for t, m in forma.tamanhos.items()]
        tamanhos += [(q.tamanho, forma.tamanhos[q.corpo], q) for q in forma.quadros.values()]
        for tamanho, medidas, quadro in tamanhos:
            titulo = f"{forma.nome} {tamanho}" + (f" (corpo {quadro.corpo})" if quadro else "")
            linhas += ["", f"## {titulo}", ""]
            if not candidatos:
                linhas.append(f"Sem quadros de `{tipo}`" + (f"/`{corpo}`" if corpo else "") + " nas referências ativas.")
                continue
            altura = medidas["altura_px"].valor if "altura_px" in medidas else None
            porte = referencias.do_mesmo_porte(candidatos, altura)
            faixa = referencias.faixa(altura)
            linhas.append(
                f"{len(candidatos)} quadros de estilo; "
                + (
                    f"{len(porte)} de porte parecido ({faixa[0]}–{faixa[1]} px de altura)."
                    if faixa
                    else "sem faixa de porte (forma sem altura ou sem `porte.faixa_altura`)."
                )
            )
            linhas += ["", "| medida | base | referências (p25–mediana–p75, n) | proposta | nota |",
                       "|---|---|---|---|---|"]
            nomes = dict.fromkeys([*medidas, "chao_y"] if quadro else medidas)
            for nome in nomes:
                valor = quadro.chao_y.valor if quadro and nome == "chao_y" else medidas[nome].valor
                linhas.append(_linha_da_medida(nome, valor, candidatos, porte, altura))
            if porte:
                cores = quantis(porte, lambda q: q.cores)
                linhas.append(
                    f"| cores por quadro (informativo) | — | {_resumo(cores, porte)} | — | "
                    "o limite vem do pedido; serve de régua para o 8 ou 12 de costume |"
                )

    linhas += ["", *_secao_do_validador(referencias)]
    return "\n".join(linhas) + "\n"


def _linha_da_medida(
    nome: str,
    valor: object,
    candidatos: list[QuadroMedido],
    porte: list[QuadroMedido],
    altura: int | None,
) -> str:
    base = _fmt(valor, nome)
    if nome == "tons_por_material":
        tons = quantis(candidatos, lambda q: q.tons_por_grupo)
        if not tons:
            return f"| {nome} | {base} | sem dados | — | — |"
        proposta = round(tons[1])
        return (
            f"| {nome} | {base} | {_resumo(tons, candidatos)} | "
            f"{'(manter)' if proposta == valor else proposta} | "
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
        if nome == "largura_tronco_px" and porte and altura:
            largura = quantis(porte, lambda q: q.largura / q.altura)[1] * altura
            extra = (
                f"; o conteúdo do mesmo porte tem largura de ~{round(largura)} px "
                "(com braços, arma e pose)"
            )
        return f"| {nome} | {base} | — | — | não medida: {_NAO_MEDIDA[nome]}{extra} |"
    return f"| {nome} | {base} | — | — | sem comparação definida |"


def _secao_do_validador(referencias: ReferenciasAtivas) -> list[str]:
    linhas = [
        "## O validador atual sobre as referências",
        "",
        "Cada quadro validado no próprio tamanho, sem limite de paleta. É o insumo da",
        "calibração da Fase 5: quantas referências levariam os avisos de blocos pequenos",
        "(`PX-WARN-MICROCLUSTER`) e de cor de 1 pixel (`PX-WARN-PALETTE-RARE`).",
        "",
    ]
    if referencias.esta_vazia or referencias.raiz is None:
        return [*linhas, "Sem referências ativas."]
    validador = PixelValidator()
    linhas += ["| pacote | quadros | nota (mediana) | blocos pequenos | cor de 1 px |",
               "|---|---|---|---|---|"]
    for pacote in referencias.pacotes:
        quadros = [q for q in referencias.quadros if q.pacote == pacote.id][:MAX_VALIDADOS_POR_PACOTE]
        notas, avisos = [], Counter()
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
            for codigo in {aviso.code for aviso in relatorio.quality.warnings}:
                avisos[codigo] += 1
        if not quadros:
            continue
        n = len(quadros)
        linhas.append(
            f"| `{pacote.id}` | {n} | {_fmt(median(notas))} | "
            f"{_pct(avisos['PX-WARN-MICROCLUSTER'] / n)} | {_pct(avisos['PX-WARN-PALETTE-RARE'] / n)} |"
        )
    return linhas


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


def _resumo(valores: tuple[float, float, float], quadros: list[QuadroMedido]) -> str:
    """p25–mediana–p75 (peso igual por pacote), com quantos quadros e pacotes."""
    pacotes = len({q.pacote for q in quadros})
    p25, p50, p75 = valores
    return f"{_fmt(p25)}–{_fmt(p50)}–{_fmt(p75)} (n={len(quadros)}, {pacotes} pac.)"


def _fmt(valor: object, nome: str = "") -> str:
    if isinstance(valor, float):
        return f"{valor:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    if isinstance(valor, tuple):
        # Olho é largura × altura; o resto que vem em par é faixa.
        return "×".join(map(str, valor)) if nome == "olho_px" else " a ".join(map(str, valor))
    return str(valor)


def _pct(fracao: float) -> str:
    return f"{round(fracao * 100)}%"
