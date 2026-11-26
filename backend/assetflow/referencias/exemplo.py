"""O exemplo de construção: um sprite CC0 convertido para o formato de receita.

Fase B2 do plano do app, com autorização da autora: a regra "nenhum sprite de
terceiro vira receita" passou a ser "sprites CC0 da biblioteca podem ser
convertidos para o formato de receita e mostrados como **exemplo de
construção**". O exemplo mostra como um pacote resolve o porte do pedido —
quantas cores, onde vai o contorno, como a rampa assenta. Ele **nunca é a base
de um asset e não entra em remendo**, e um desenho que repita a silhueta dele é
não aprovado (:func:`assetflow.referencias.olho.repete_o_exemplo`).

A escolha:

* do **porte** do pedido (tipo, corpo e altura do corpo), ou do **estilo**
  (qualquer altura) quando o porte não basta ou a liberdade é ``ousado``;
* uma **fonte** por vez, em rotação: cada pacote é uma fonte, e os assets que a
  autora marcou com "gostei" (do mesmo tipo, corpo e grade) são mais uma. Quem
  chama diz a ordem (as menos mostradas primeiro);
* dentro da fonte, **quadro parado** primeiro (``idle`` no caminho), quadros
  de pulo, ataque, dano e queda por último — só entram sem alternativa; e,
  entre iguais, o mais perto das medianas;
* o quadro tem de caber no teto (:data:`TETO_EXEMPLO`) e na paleta de chaves
  de um caractere; o que não cabe é pulado.

Só CC0 entra: a coleção ativa já deixa de fora o que exige atribuição sem
aceite, e aqui um pacote fora da coleção principal é pulado de novo.
"""

from __future__ import annotations

import json
import re
import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from .colecao import QuadroMedido, ReferenciasAtivas, quantis
from .medidor import _luminancia
from .pacote import LICENCA_PRINCIPAL

__all__ = [
    "CHAVES",
    "FONTE_GOSTEI",
    "TETO_EXEMPLO",
    "CandidatoDeGostei",
    "ExemploConvertido",
    "converter",
    "escolher_exemplo",
    "fonte_do_pacote",
    "fontes_do_exemplo",
]

#: Teto do exemplo no recorte, em caracteres (cabeçalho e JSON).
TETO_EXEMPLO = 1500
#: As chaves de cor da receita, da cor mais escura para a mais clara.
CHAVES = string.ascii_lowercase + string.ascii_uppercase + string.digits
#: Fonte dos assets marcados com "gostei".
FONTE_GOSTEI = "gostei"

_PARADO = re.compile(r"idle|parad|stand|breath", re.IGNORECASE)
_EM_ACAO = re.compile(
    r"jump|pulo|salto|fall|queda|attack|ataque|atk|slash|hit|hurt|dano|death|dead|morte|"
    r"die|double|wall|roll|dash|throw|shoot|cast",
    re.IGNORECASE,
)


def fonte_do_pacote(pacote: str) -> str:
    return f"pacote:{pacote}"


@dataclass(frozen=True, slots=True)
class ExemploConvertido:
    """O exemplo pronto para o recorte, e de onde ele veio."""

    fonte: str
    #: ``cc0`` (pacote da biblioteca) ou ``gostei`` (asset da autora).
    origem: str
    descricao: str
    paleta: Mapping[str, str]
    px: tuple[str, ...]
    largura: int
    altura: int
    cores: int
    pacote: str | None = None
    arquivo: str | None = None
    asset_id: str | None = None

    @property
    def texto(self) -> str:
        corpo = json.dumps(
            {"paleta": dict(self.paleta), "px": list(self.px)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return f"{self.descricao}\n{corpo}"

    def como_dict(self) -> dict:
        """O que fica gravado no pedido e no asset (``envio``)."""
        return {
            "fonte": self.fonte,
            "origem": self.origem,
            "pacote": self.pacote,
            "arquivo": self.arquivo,
            "asset_id": self.asset_id,
            "conteudo": [self.largura, self.altura],
            "cores": self.cores,
            "caracteres": len(self.texto),
            "paleta": dict(self.paleta),
            "px": list(self.px),
        }


@dataclass(frozen=True, slots=True)
class CandidatoDeGostei:
    """Um asset da autora marcado com "gostei", já lido pelo chamador."""

    asset_id: str
    rgba: np.ndarray


def converter(rgba: np.ndarray) -> tuple[dict[str, str], tuple[str, ...]] | None:
    """Os pixels (já recortados) no formato de receita: paleta e linhas ``px``.

    As chaves seguem a luminância (``a`` é a mais escura), para a paleta se ler
    como rampa. ``None`` se houver mais cores do que chaves de um caractere.
    """
    opaco = rgba[..., 3] > 0
    if not opaco.any():
        return None
    codigos = (
        (rgba[..., 0].astype(np.int64) << 16) | (rgba[..., 1].astype(np.int64) << 8) | rgba[..., 2]
    )
    unicos = np.unique(codigos[opaco])
    if len(unicos) > len(CHAVES):
        return None
    cores = [f"#{int(c):06x}" for c in unicos]
    rgb = np.array(
        [[[int(c[i : i + 2], 16) for i in (1, 3, 5)] + [255] for c in cores]], dtype=np.uint8
    )
    luminancias = _luminancia(rgb)[0]
    ordem = sorted(range(len(cores)), key=lambda i: (float(luminancias[i]), cores[i]))
    chave_do_codigo = {int(unicos[i]): CHAVES[posicao] for posicao, i in enumerate(ordem)}
    paleta = {CHAVES[posicao]: cores[i] for posicao, i in enumerate(ordem)}
    linhas = []
    for y in range(rgba.shape[0]):
        linha = "".join(
            chave_do_codigo[int(codigos[y, x])] if opaco[y, x] else "."
            for x in range(rgba.shape[1])
        )
        linhas.append(linha.rstrip("."))
    return paleta, tuple(linhas)


def fontes_do_exemplo(
    referencias: ReferenciasAtivas,
    tipo: str,
    corpo: str | None,
    altura: int | None,
    *,
    por_estilo: bool = False,
    so_bons: bool = False,
) -> dict[str, list[QuadroMedido]]:
    """As fontes CC0 de exemplo deste pedido, cada uma com os quadros na ordem de preferência.

    Com ``so_bons`` e uma lista de bons exemplos na coleção (lote 13), só os
    quadros dela entram; sem lista, todos.
    """
    parte = referencias.parte_do_exemplo(tipo, corpo, altura, por_estilo=por_estilo)
    if not parte.suficiente:
        return {}
    candidatos = [
        q
        for q in parte.quadros
        if (m := referencias.manifesto(q.pacote)) is not None
        and m.license_id == LICENCA_PRINCIPAL
    ]
    if so_bons and referencias.bons:
        candidatos = [
            q for q in candidatos if (q.pacote, q.arquivo, tuple(q.caixa)) in referencias.bons
        ]
    if not candidatos:
        return {}
    alvo = (
        quantis(candidatos, lambda q: q.altura)[1],
        quantis(candidatos, lambda q: q.cores)[1],
        quantis(candidatos, lambda q: q.preenchimento)[1],
    )

    def preferencia(q: QuadroMedido) -> tuple:
        if _PARADO.search(q.arquivo):
            pose = 0
        elif _EM_ACAO.search(q.arquivo):
            pose = 2
        else:
            pose = 1
        distancia = (
            abs(q.altura - alvo[0]) / max(alvo[0], 1)
            + abs(q.cores - alvo[1]) / max(alvo[1], 1)
            + abs(q.preenchimento - alvo[2])
        )
        return (pose, round(distancia, 6), q.arquivo, q.caixa)

    por_fonte: dict[str, list[QuadroMedido]] = {}
    for q in candidatos:
        por_fonte.setdefault(fonte_do_pacote(q.pacote), []).append(q)
    return {fonte: sorted(quadros, key=preferencia) for fonte, quadros in por_fonte.items()}


def escolher_exemplo(
    referencias: ReferenciasAtivas,
    fontes: Mapping[str, Sequence[QuadroMedido]],
    ordem: Sequence[str],
    *,
    gostei: Sequence[CandidatoDeGostei] = (),
    teto: int = TETO_EXEMPLO,
) -> ExemploConvertido | None:
    """O primeiro quadro que cabe, percorrendo as fontes na ``ordem`` dada.

    ``ordem`` lista as fontes (``pacote:<id>`` e ``gostei``) na ordem da
    rotação; uma fonte fora dela não é usada.
    """
    for fonte in ordem:
        if fonte == FONTE_GOSTEI:
            for candidato in gostei:
                exemplo = _do_gostei(candidato, teto)
                if exemplo is not None:
                    return exemplo
            continue
        for quadro in fontes.get(fonte, ()):
            exemplo = _do_quadro(referencias, fonte, quadro, teto)
            if exemplo is not None:
                return exemplo
    return None


def _do_quadro(
    referencias: ReferenciasAtivas, fonte: str, quadro: QuadroMedido, teto: int
) -> ExemploConvertido | None:
    try:
        pedaco = referencias.recortar(quadro)
    except (OSError, ValueError):
        return None
    convertido = converter(pedaco)
    if convertido is None:
        return None
    paleta, px = convertido
    manifesto = referencias.manifesto(quadro.pacote)
    descricao = (
        f"exemplo de construção (CC0 · {manifesto.nome} · {manifesto.autor} · {quadro.arquivo}; "
        f"conteúdo {pedaco.shape[1]}×{pedaco.shape[0]}, {len(paleta)} cores, contorno "
        f"{quadro.contorno_tipo}): mostra como o pacote resolve o porte; não é base nem "
        "entra em remendo"
    )
    exemplo = ExemploConvertido(
        fonte=fonte,
        origem="cc0",
        descricao=descricao,
        paleta=paleta,
        px=px,
        largura=int(pedaco.shape[1]),
        altura=int(pedaco.shape[0]),
        cores=len(paleta),
        pacote=quadro.pacote,
        arquivo=quadro.arquivo,
    )
    return exemplo if len(exemplo.texto) <= teto else None


def _do_gostei(candidato: CandidatoDeGostei, teto: int) -> ExemploConvertido | None:
    rgba = candidato.rgba
    opaco = rgba[..., 3] > 0
    if not opaco.any():
        return None
    ys, xs = np.nonzero(opaco)
    pedaco = np.ascontiguousarray(rgba[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1])
    convertido = converter(pedaco)
    if convertido is None:
        return None
    paleta, px = convertido
    descricao = (
        f"exemplo de construção (um asset seu marcado com \"gostei\": {candidato.asset_id}; "
        f"conteúdo {pedaco.shape[1]}×{pedaco.shape[0]}, {len(paleta)} cores): mostra o que "
        "funcionou; não é base nem entra em remendo"
    )
    exemplo = ExemploConvertido(
        fonte=FONTE_GOSTEI,
        origem="gostei",
        descricao=descricao,
        paleta=paleta,
        px=px,
        largura=int(pedaco.shape[1]),
        altura=int(pedaco.shape[0]),
        cores=len(paleta),
        asset_id=candidato.asset_id,
    )
    return exemplo if len(exemplo.texto) <= teto else None
