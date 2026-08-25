"""A suíte comparativa entre motores (plano de motores §19).

Um conjunto fixo de pedidos, rodado igual em todos os motores. "Fixo" é a
propriedade que interessa: comparar motores com prompts diferentes não compara
nada, e comparar com prompts que alguém escolheu depois de ver os resultados
compara ainda menos.

A suíte é **configuração** (``config/benchmark_suite.yaml``), pelo mesmo motivo
que a taxonomia e os profiles são: acrescentar um caso não pode exigir alterar
código, senão a suíte para de crescer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

__all__ = ["BenchmarkCase", "BenchmarkSuite", "DEFAULT_CASES"]


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """Um pedido da suíte."""

    id: str
    prompt: str
    #: Profile usado. Ele decide capability e pipeline, como em qualquer job.
    profile: str = "pixel_character_64"
    asset_type: str | None = None
    logical_size: int | None = None
    max_colors: int | None = None
    variations: int = 1
    #: Seed fixa: sem ela, duas execuções do mesmo caso no mesmo motor já
    #: diferem, e a comparação entre motores perde o chão.
    seed: int = 20240101

    def label(self) -> str:
        size = f" {self.logical_size}×{self.logical_size}" if self.logical_size else ""
        return f"{self.prompt}{size}"

    @classmethod
    def from_config(cls, data: dict[str, Any]) -> "BenchmarkCase":
        return cls(
            id=str(data["id"]),
            prompt=str(data["prompt"]),
            profile=str(data.get("profile", "pixel_character_64")),
            asset_type=data.get("asset_type"),
            logical_size=_as_int(data.get("logical_size")),
            max_colors=_as_int(data.get("max_colors")),
            variations=int(data.get("variations", 1)),
            seed=int(data.get("seed", 20240101)),
        )


#: A suíte do plano de motores §19, embutida para o caso de o YAML não existir.
#:
#: Ela não é um padrão "provisório": é a lista que o plano nomeia, e tê-la no
#: código garante que `python -m scripts.benchmark_engines` funcione em uma
#: instalação recém-clonada, antes de qualquer configuração.
DEFAULT_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(id="tree_32", prompt="tree", asset_type="prop", logical_size=32, max_colors=16),
    BenchmarkCase(id="tree_64", prompt="tree", asset_type="prop", logical_size=64, max_colors=16),
    BenchmarkCase(
        id="red_potion_16",
        prompt="red potion",
        asset_type="prop",
        logical_size=16,
        max_colors=8,
    ),
    BenchmarkCase(
        id="wooden_chest_32",
        prompt="wooden chest",
        asset_type="prop",
        logical_size=32,
        max_colors=16,
    ),
    BenchmarkCase(
        id="stone_sword_32",
        prompt="stone sword",
        asset_type="prop",
        logical_size=32,
        max_colors=16,
    ),
    BenchmarkCase(
        id="knight_side_64",
        prompt="knight side view",
        asset_type="character",
        logical_size=64,
        max_colors=16,
    ),
    BenchmarkCase(
        id="mage_front_64",
        prompt="mage front view",
        asset_type="character",
        logical_size=64,
        max_colors=16,
    ),
    BenchmarkCase(
        id="slime_32", prompt="slime", asset_type="character", logical_size=32, max_colors=8
    ),
    BenchmarkCase(
        id="house_64",
        prompt="small medieval house",
        asset_type="prop",
        logical_size=64,
        max_colors=16,
    ),
)


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    """Os casos e os motores a comparar."""

    cases: tuple[BenchmarkCase, ...] = DEFAULT_CASES
    #: Motores a exercitar. Vazio = todos os habilitados que atenderem.
    engines: tuple[str, ...] = ()
    project_id: str = "benchmark"
    metadata: dict[str, Any] = field(default_factory=dict)

    def case(self, case_id: str) -> BenchmarkCase | None:
        return next((case for case in self.cases if case.id == case_id), None)

    def filtered(self, case_ids: Iterable[str] | None) -> "BenchmarkSuite":
        """Uma suíte com um subconjunto dos casos."""
        if not case_ids:
            return self
        wanted = set(case_ids)
        return BenchmarkSuite(
            cases=tuple(case for case in self.cases if case.id in wanted),
            engines=self.engines,
            project_id=self.project_id,
            metadata=self.metadata,
        )

    @classmethod
    def from_config(cls, data: dict[str, Any] | None) -> "BenchmarkSuite":
        """Carrega de ``config/benchmark_suite.yaml``; ausente, usa o padrão."""
        data = data or {}
        raw_cases = data.get("cases")
        cases = (
            tuple(
                BenchmarkCase.from_config(item)
                for item in raw_cases
                if isinstance(item, dict)
            )
            if raw_cases
            else DEFAULT_CASES
        )
        return cls(
            cases=cases,
            engines=tuple(str(item) for item in (data.get("engines") or ())),
            project_id=str(data.get("project_id", "benchmark")),
            metadata=dict(data.get("metadata") or {}),
        )


def _as_int(value: Any) -> int | None:
    return None if value is None else int(value)
