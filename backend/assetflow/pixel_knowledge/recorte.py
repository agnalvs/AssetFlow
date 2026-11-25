"""O recorte: o pedaço da base que vale para um pedido (PIXEL_KNOWLEDGE §18).

O documento inteiro nunca entra na conversa — só as linhas daquele pedido, que
``consultar_pedido`` devolve. O seletor lê o ``FinalResolvedSpec`` (o
``context.resolved`` do pipeline) e **não recalcula** campo nenhum: tamanho,
paleta, tipo e corpo continuam vindo só do spec, e o recorte só acrescenta
orientação. Os campos lidos são estes, e mais nenhum:

    logical_resolution               a linha de proporção e o molde
    asset.type                       a forma de um objeto (``prop``)
    character.body_type              a forma de um personagem
    palette                          o limite de cores, ou as cores travadas
    style.shading.light_direction    a luz, quando o pedido a define

O que um estilo decide — paleta-mestra, luz padrão, proporções e moldes —
chega por um ponto só, :meth:`BaseDeConhecimento.estilo`. O código não tem
paleta nem direção de luz próprias: sem configuração, a linha some.

O recorte tem teto, para a base poder crescer sem aumentar o gasto por pedido.
As seções entram em ordem de prioridade; a que não couber sai **inteira**, e a
última linha diz qual saiu.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..generation.schemas import AssetType
from .base import BaseDeConhecimento, Forma, Luz, Medida, Molde, Paleta

__all__ = ["TETO_CARACTERES", "USO_DO_MOLDE", "montar_recorte"]

#: Teto do recorte, em caracteres (cerca de 1.300 tokens). Contagem de
#: caracteres porque é determinística; um tokenizador mudaria com o modelo.
TETO_CARACTERES = 4000

#: Como o Claude deve usar o molde: medidas e camadas, não um desenho pronto.
USO_DO_MOLDE = (
    "o molde é guia de medidas e de camadas, não desenho a copiar: mantenha as "
    "proporções, a linha de chão e os nomes das camadas; redesenhe pose, "
    "silhueta e detalhes para o pedido"
)

#: Medidas que a primeira frase das proporções já diz.
_DITAS_NA_ALTURA = ("altura_px", "cabeca_px", "tronco_px", "pernas_px", "chao_y")
#: Faixa de origem, que justifica as medidas mas não orienta o desenho.
_SO_REFERENCIA = ("cabecas",)


def montar_recorte(
    resolved: Any, base: BaseDeConhecimento | None, *, teto: int = TETO_CARACTERES
) -> str:
    """As linhas da base que valem para este spec; ``""`` quando não há nada."""
    if base is None or base.esta_vazia:
        return ""
    logica = resolved.logical_resolution
    if logica is None:  # pedido que não é Pixel Art
        return ""

    estilo = base.estilo()
    largura, altura = logica.width, logica.height
    forma = estilo.formas.get(_forma(resolved))
    medidas = forma.medidas(largura, altura) if forma else None
    molde = estilo.molde(forma.id, largura, altura) if forma else None

    secoes = [
        ("proporções", _proporcoes(forma, medidas, largura, altura)),
        ("luz", _luz(resolved, estilo.luz)),
        ("cores", _cores(resolved, estilo.paleta)),
        ("silhueta", _silhueta(forma)),
        ("molde", _molde(molde)),
    ]
    return _caber([(nome, texto) for nome, texto in secoes if texto], teto)


# ---------------------------------------------------------------------------
# Seções
# ---------------------------------------------------------------------------
def _forma(resolved: Any) -> str:
    """Num personagem, a forma é o corpo; nos demais, o tipo de asset.

    Corpo ``unknown`` não vira ``humanoid``: sem forma conhecida, o recorte
    fica sem proporções e sem molde, em vez de chutar.
    """
    tipo = resolved.asset.type
    if tipo == AssetType.CHARACTER:
        return _valor(resolved.character.body_type)
    return _valor(tipo)


def _proporcoes(
    forma: Forma | None, medidas: Mapping[str, Medida] | None, largura: int, altura: int
) -> str:
    if forma is None or not medidas:
        return ""
    valor = {nome: medida.valor for nome, medida in medidas.items()}
    partes: list[str] = []
    if all(nome in valor for nome in ("altura_px", "cabeca_px", "tronco_px", "pernas_px")):
        partes.append(
            f"altura {valor['altura_px']} = cabeça {valor['cabeca_px']} + tronco "
            f"{valor['tronco_px']} + pernas {valor['pernas_px']}"
        )
    if "chao_y" in valor:
        chao = valor["chao_y"]
        topo = f"topo y={chao - valor['altura_px'] + 1}, " if "altura_px" in valor else ""
        partes.append(f"{topo}chão y={chao} (pixel opaco mais baixo)")
    for nome, medida in medidas.items():
        if nome not in _DITAS_NA_ALTURA and nome not in _SO_REFERENCIA:
            partes.append(_frase(medida))
    return f"{forma.nome} {largura}×{altura}: " + " · ".join(partes)


def _frase(medida: Medida) -> str:
    valor = medida.valor
    if medida.nome == "olho_px" and isinstance(valor, tuple) and len(valor) == 2:
        texto = f"olho {valor[0]}×{valor[1]}"
    elif medida.nome == "braco_px":
        texto = f"braço {valor} px"
    elif medida.nome == "margem_px":
        texto = f"margem {valor} px até a borda"
    elif medida.nome == "tons_por_material":
        texto = f"{valor} tons por material"
    elif medida.nome == "ocupacao_min" and isinstance(valor, (int, float)):
        texto = f"ocupar ao menos {round(valor * 100)}% da grade"
    else:
        # Medida nova na configuração aparece mesmo sem frase própria.
        bruto = " a ".join(map(str, valor)) if isinstance(valor, tuple) else str(valor)
        texto = f"{medida.nome.replace('_', ' ')} {bruto}"
    return f"{texto} {medida.nota}" if medida.nota else texto


def _luz(resolved: Any, luz: Luz | None) -> str:
    pedida = resolved.style.shading.light_direction
    if pedida:
        cabeca = f"luz: {pedida} (do pedido)"
    elif luz is not None:
        cabeca = f"luz: {luz.padrao} (padrão da base; o pedido não definiu)"
    else:
        return ""
    regras = [regra.texto for regra in luz.regras] if luz is not None else []
    return " · ".join([cabeca, *regras])


def _cores(resolved: Any, paleta: Paleta | None) -> str:
    pedida = resolved.palette
    if pedida is not None and pedida.mode == "locked" and pedida.colors:
        # Paleta travada é do spec: as rampas da mestra não se aplicam.
        return f"cores: paleta travada pelo pedido, use só estas: {' '.join(pedida.colors)}"

    limite = pedida.max_colors if pedida is not None else None
    cabeca = f"cores: até {limite}, contorno incluído" if limite else "cores: o pedido não limita"
    if paleta is None or not paleta.rampas:
        return cabeca

    linhas = [
        (
            f"{cabeca} · paleta-mestra {paleta.id}, rampas do escuro ao claro; "
            "cada material usa tons vizinhos de uma rampa:"
        ),
        f"  contorno {paleta.contorno}",
    ]
    rampas = [f"{material} {' '.join(cores)}" for material, cores in paleta.rampas.items()]
    for i in range(0, len(rampas), 2):
        linhas.append("  " + " · ".join(rampas[i : i + 2]))
    return "\n".join(linhas)


def _silhueta(forma: Forma | None) -> str:
    if forma is None or not forma.regras:
        return ""
    return "silhueta: " + " · ".join(regra.texto for regra in forma.regras)


def _molde(molde: Molde | None) -> str:
    if molde is None:
        return ""
    camadas = ", ".join(str(camada.get("nome")) for camada in molde.receita.get("camadas") or [])
    chaves = " · ".join(f"{chave} {papel}" for chave, papel in molde.chaves.items())
    return "\n".join(
        [
            f"molde {molde.id}: {molde.descricao}; camadas {camadas}; chaves {chaves}",
            json.dumps(molde.receita, ensure_ascii=False, separators=(",", ":")),
            USO_DO_MOLDE,
        ]
    )


# ---------------------------------------------------------------------------
# Teto
# ---------------------------------------------------------------------------
def _caber(secoes: list[tuple[str, str]], teto: int) -> str:
    """Junta as seções até o teto, tirando inteiras as de menor prioridade."""
    escolhidas = list(secoes)
    omitidas: list[str] = []
    while True:
        linhas = [texto for _, texto in escolhidas]
        if omitidas:
            linhas.append(f"omitido pelo teto de {teto} caracteres: {', '.join(omitidas)}")
        texto = "\n".join(linhas)
        if len(texto) <= teto or not escolhidas:
            return texto
        nome, _ = escolhidas.pop()
        omitidas.insert(0, nome)


def _valor(valor: Any) -> str:
    return str(getattr(valor, "value", valor))
