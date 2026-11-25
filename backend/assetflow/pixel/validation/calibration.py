"""Calibração da nota: blocos pequenos e cores raras (plano Pixel §60).

Os limiares destas duas verificações saíram do código e moram em
``config/quality.yaml``. O motivo está medido em
``backend/docs/RELATORIO_ESTADO.md``: com os valores do plano, o aviso de blocos
pequenos aparecia em 89% a 100% dos quadros de pacotes profissionais, e o
laudo empurrava o desenho para a simplificação.

Os valores **padrão** desta classe continuam sendo os do plano §60, e valem
quando ninguém injeta outra calibração: testes da ilha e instalação sem
``quality.yaml`` (o boot avisa). É o mesmo padrão do ``optimizer.yaml``.

Três regras:

- **só a nota de estilo.** Nada aqui toca um hard check; dimensão, alpha e
  paleta continuam decididos pelos checks e pelo spec;
- **número sem fonte leva ``a_calibrar: true``**, como na base de
  conhecimento. Um número que não diga nenhum dos dois é recusado e fica o
  padrão do plano, com o problema anotado;
- **aviso e desconto acima do limiar**, nunca no limiar: o limiar é o maior
  valor que as referências mostram como normal.

Este módulo não lê arquivo: recebe o mapeamento já carregado. Quem lê o YAML
é ``settings.py``; quem monta o validador é ``bootstrap.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

__all__ = [
    "MICROCLUSTER_FREE_RATIO",
    "MICROCLUSTER_PENALTY_MAX",
    "MICROCLUSTER_PENALTY_RATE",
    "MICROCLUSTER_WARNING_RATIO",
    "PLANO",
    "RARE_COLOR_FLOOR",
    "RARE_COLOR_FREE_COUNT",
    "RARE_COLOR_PENALTY_MAX",
    "RARE_COLOR_PENALTY_PER_COLOR",
    "RARE_COLOR_RATIO",
    "RARE_COLOR_WARNING_COUNT",
    "MicroclusterCalibration",
    "QualityCalibration",
    "RareColorCalibration",
]

# ---------------------------------------------------------------------------
# Padrões do plano §60 — estimativa, não medição. Valem sem quality.yaml.
# ---------------------------------------------------------------------------

#: Blocos pequenos: um quinto dos blocos com 3 pixels ou menos ainda é detalhe.
MICROCLUSTER_FREE_RATIO = 0.20
MICROCLUSTER_PENALTY_RATE = 100.0
MICROCLUSTER_PENALTY_MAX = 20.0
#: Acima desta fração de blocos pequenos o relatório avisa.
MICROCLUSTER_WARNING_RATIO = 0.25

#: Uma cor é "rara" quando pinta no máximo esta fração do foreground...
RARE_COLOR_RATIO = 0.002
#: ...ou este piso, em pixels: em um sprite minúsculo 0,2% arredonda para zero.
RARE_COLOR_FLOOR = 1
#: Quantas cores raras passam sem aviso e sem desconto. O plano: nenhuma.
RARE_COLOR_WARNING_COUNT = 0
RARE_COLOR_FREE_COUNT = 0
RARE_COLOR_PENALTY_PER_COLOR = 1.0
RARE_COLOR_PENALTY_MAX = 5.0

#: Rótulo da calibração quando nada foi injetado.
PLANO = "padrão do plano §60"


@dataclass(frozen=True, slots=True)
class MicroclusterCalibration:
    """``PX-WARN-MICROCLUSTER`` e a penalidade ``microcluster``."""

    warning_ratio: float = MICROCLUSTER_WARNING_RATIO
    free_ratio: float = MICROCLUSTER_FREE_RATIO
    rate: float = MICROCLUSTER_PENALTY_RATE
    ceiling: float = MICROCLUSTER_PENALTY_MAX


@dataclass(frozen=True, slots=True)
class RareColorCalibration:
    """``PX-WARN-PALETTE-RARE`` e a penalidade ``rare_colors``."""

    ratio: float = RARE_COLOR_RATIO
    floor_px: int = RARE_COLOR_FLOOR
    #: O aviso sai com **mais** cores raras que isto.
    warning_count: int = RARE_COLOR_WARNING_COUNT
    #: O desconto conta só as cores raras **além** destas.
    free_count: int = RARE_COLOR_FREE_COUNT
    per_color: float = RARE_COLOR_PENALTY_PER_COLOR
    ceiling: float = RARE_COLOR_PENALTY_MAX


@dataclass(frozen=True, slots=True)
class QualityCalibration:
    """Os limiares de blocos pequenos e cores raras que o validador usa."""

    microcluster: MicroclusterCalibration = field(default_factory=MicroclusterCalibration)
    rare_colors: RareColorCalibration = field(default_factory=RareColorCalibration)
    #: De onde vieram os valores: ``PLANO`` ou o nome do arquivo.
    source: str = PLANO
    #: O que a carga recusou (cada item ficou com o padrão do plano).
    problems: tuple[str, ...] = ()

    @classmethod
    def from_config(
        cls, data: Mapping[str, Any] | None, *, source: str = "config/quality.yaml"
    ) -> QualityCalibration:
        """Lê o conteúdo de ``quality.yaml``. Vazio ou ausente: o plano."""
        if not data:
            return cls()
        problems: list[str] = []
        if not isinstance(data, Mapping):
            return cls(problems=("a raiz não é um mapeamento",))
        _unknown(data, set(_SECTIONS), "quality.yaml", problems)

        micro = _section(data, "blocos_pequenos", MicroclusterCalibration(), problems)
        rare = _section(data, "cores_raras", RareColorCalibration(), problems)
        return cls(microcluster=micro, rare_colors=rare, source=source, problems=tuple(problems))

    def describe(self) -> str:
        """Uma linha para o relatório: de onde e com que limiares."""
        m, r = self.microcluster, self.rare_colors
        return (
            f"{self.source}: blocos pequenos aviso > {m.warning_ratio:g}, "
            f"desconto > {m.free_ratio:g}; cores raras aviso > {r.warning_count}, "
            f"desconto > {r.free_count}"
        )


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

#: chave do YAML -> (campo da dataclass, tipo, mínimo, máximo)
_SECTIONS: dict[str, dict[str, tuple[str, type, float, float | None]]] = {
    "blocos_pequenos": {
        "aviso": ("warning_ratio", float, 0.0, 1.0),
        "franquia": ("free_ratio", float, 0.0, 1.0),
        "taxa": ("rate", float, 0.0, None),
        "teto": ("ceiling", float, 0.0, None),
    },
    "cores_raras": {
        "fracao_do_sprite": ("ratio", float, 0.0, 1.0),
        "piso_px": ("floor_px", int, 0, None),
        "aviso": ("warning_count", int, 0, None),
        "franquia": ("free_count", int, 0, None),
        "por_cor": ("per_color", float, 0.0, None),
        "teto": ("ceiling", float, 0.0, None),
    },
}

_NUMBER_KEYS = {"valor", "fonte", "a_calibrar", "nota"}


def _section(data: Mapping[str, Any], name: str, default, problems: list[str]):
    raw = data.get(name)
    if raw is None:
        return default
    if not isinstance(raw, Mapping):
        problems.append(f"{name}: mapeamento esperado")
        return default
    keys = _SECTIONS[name]
    _unknown(raw, set(keys), name, problems)
    updates: dict[str, Any] = {}
    for key, (attr, kind, low, high) in keys.items():
        if key in raw:
            value = _number(raw[key], f"{name}.{key}", kind, low, high, problems)
            if value is not None:
                updates[attr] = value
    return replace(default, **updates)


def _number(
    raw: Any, where: str, kind: type, low: float, high: float | None, problems: list[str]
) -> float | int | None:
    """``{valor: N, a_calibrar: true}`` ou ``{valor: N, fonte: ...}``."""
    if not isinstance(raw, Mapping) or "valor" not in raw:
        problems.append(f"{where}: use {{valor: N, a_calibrar: true}}")
        return None
    strange = sorted(str(k) for k in raw if k not in _NUMBER_KEYS)
    if strange:
        problems.append(f"{where}: chave desconhecida ({', '.join(strange)})")
        return None
    if not raw.get("fonte") and raw.get("a_calibrar") is not True:
        problems.append(f"{where}: número sem fonte; marque a_calibrar: true")
        return None
    value = raw["valor"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        problems.append(f"{where}: valor precisa ser número")
        return None
    if kind is int and value != int(value):
        problems.append(f"{where}: valor precisa ser inteiro")
        return None
    if value < low or (high is not None and value > high):
        faixa = f"entre {low:g} e {high:g}" if high is not None else f"maior ou igual a {low:g}"
        problems.append(f"{where}: valor {value} fora da faixa ({faixa})")
        return None
    return kind(value)


def _unknown(raw: Mapping[str, Any], accepted: set[str], where: str, problems: list[str]) -> None:
    strange = sorted(str(k) for k in raw if k not in accepted)
    if strange:
        problems.append(
            f"{where}: chave desconhecida ({', '.join(strange)}); "
            f"aceitas: {', '.join(sorted(accepted))}"
        )
