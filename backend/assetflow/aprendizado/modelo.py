"""Lição e opinião: o que o desenho aprende com o uso (Fase B2 do plano do app).

Uma **lição** nasce de um olhar que achou algo feio ou estranho: o que errou,
por quê e a regra para não repetir. Ela tem etiquetas (tipo, corpo, porte e
tema) e um contador: a mesma lição de novo não duplica, soma.

Uma **opinião** é da autora, dada na tela sobre um asset pronto. "Gostei" e
"não gostei" sem motivo ficam só como nota do asset. "Não gostei" com motivo
fica **pendente** até o Claude convertê-la em lição (``registrar_licao`` com
``da_autora=true``); o texto original fica guardado ao lado da regra escrita.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..generation.schemas import AssetType

__all__ = [
    "MAX_ERROU",
    "MAX_MOTIVO",
    "MAX_PORQUE",
    "MAX_REGRA",
    "QUALQUER",
    "Licao",
    "Natureza",
    "Opiniao",
    "Origem",
    "SituacaoDaOpiniao",
    "Tema",
    "etiquetas_do_spec",
    "ler_tema",
    "palavras",
]

#: Tetos de cada parte da lição, em caracteres. Só a regra entra no recorte.
MAX_ERROU = 120
MAX_PORQUE = 120
MAX_REGRA = 140
#: Teto do motivo de um "não gostei".
MAX_MOTIVO = 280

#: Etiqueta que casa com qualquer valor (lição geral, ou corpo de um objeto).
QUALQUER = "qualquer"


class Natureza(str, Enum):
    #: Proporção, pose, silhueta: o que o ``ousado`` deixa livre.
    FORMA = "forma"
    #: Luz, cor, valor, contorno, limpeza: vale em qualquer liberdade.
    TECNICA = "tecnica"


class Tema(str, Enum):
    SILHUETA = "silhueta"
    PROPORCAO = "proporcao"
    POSE = "pose"
    ROSTO = "rosto"
    EQUIPAMENTO = "equipamento"
    VALOR = "valor"
    LUZ = "luz"
    COR = "cor"
    CONTORNO = "contorno"
    LIMPEZA = "limpeza"

    @property
    def natureza(self) -> Natureza:
        return Natureza.TECNICA if self in _TECNICA else Natureza.FORMA


_TECNICA = {Tema.VALOR, Tema.LUZ, Tema.COR, Tema.CONTORNO, Tema.LIMPEZA}


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )


def ler_tema(valor: str | None) -> Tema | None:
    """``"proporção"``, ``"Proporcao"`` e ``"proporcao"`` são o mesmo tema."""
    if not valor:
        return None
    try:
        return Tema(_sem_acento(str(valor)).strip().lower())
    except ValueError:
        return None


_VAZIAS = frozenset(
    {
        "a", "o", "as", "os", "e", "de", "da", "do", "das", "dos", "em", "no", "na", "nos",
        "nas", "um", "uma", "uns", "umas", "com", "para", "por", "que", "se", "ao", "aos",
        "sem", "mais", "menos", "muito", "nao", "sim", "ou", "como", "entre", "sobre", "sob",
    }
)


def palavras(texto: str) -> frozenset[str]:
    """As palavras que contam para dizer se duas regras são a mesma."""
    return frozenset(
        p
        for p in re.split(r"[^a-z0-9]+", _sem_acento(texto).lower())
        if len(p) > 2 and p not in _VAZIAS
    )


class Origem(str, Enum):
    CLAUDE = "claude"
    AUTORA = "autora"


class Licao(BaseModel):
    model_config = ConfigDict(frozen=True)

    numero: int
    errou: str
    porque: str
    regra: str
    tema: Tema
    tipo: str
    corpo: str
    porte: str
    origem: Origem
    #: O motivo do "não gostei", como a autora escreveu (lição da autora).
    texto_da_autora: str | None = None
    contador: int = 1
    ligada: bool = True
    asset_id: str | None = None
    pedido_id: str | None = None
    #: Os assets em que a lição apareceu, do mais recente (no máximo 10).
    assets: tuple[str, ...] = ()
    criada_em: datetime
    atualizada_em: datetime

    @property
    def id(self) -> str:
        return f"L{self.numero}"

    @property
    def natureza(self) -> Natureza:
        return self.tema.natureza


class SituacaoDaOpiniao(str, Enum):
    #: Só nota do asset: "gostei", ou "não gostei" sem motivo.
    NOTA = "nota"
    #: "Não gostei" com motivo, esperando o Claude convertê-lo em lição.
    PENDENTE = "pendente"
    #: Já virou lição (``licao``).
    CONVERTIDA = "convertida"


class Opiniao(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_id: str
    gostei: bool
    motivo: str | None = None
    situacao: SituacaoDaOpiniao
    licao: int | None = None
    #: Etiquetas do asset, lidas do spec dele quando a opinião foi dada.
    tipo: str | None = None
    corpo: str | None = None
    porte: str | None = None
    em: datetime


def etiquetas_do_spec(spec: Any) -> tuple[str, str, str]:
    """Tipo, corpo e porte (a grade) de um spec, como lições e opiniões os etiquetam.

    Só lê o spec: o tipo, o corpo (``qualquer`` num objeto ou num corpo
    ``unknown``) e a grade lógica (``"48x48"``).
    """
    tipo = str(getattr(spec.asset.type, "value", spec.asset.type))
    corpo = QUALQUER
    if spec.asset.type == AssetType.CHARACTER and spec.character is not None:
        valor = str(getattr(spec.character.body_type, "value", spec.character.body_type))
        if valor != "unknown":
            corpo = valor
    logica = spec.logical_resolution
    grade = f"{logica.width}x{logica.height}" if logica is not None else QUALQUER
    return tipo, corpo, grade
