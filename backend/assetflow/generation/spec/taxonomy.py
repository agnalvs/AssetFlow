"""Vocabulário semântico de tipos de asset (plano T→J §5).

A taxonomia é **configuração**, não código: ela mora em
``config/asset_taxonomy/*.yaml``, um arquivo por tipo, com termos em
português e inglês. Acrescentar "candelabro" ao vocabulário de props não pode
exigir editar um ``.py`` — é a mesma regra que já vale para profiles, engines
e contratos Pixel.

Estrutura de cada arquivo::

    type: prop
    priority: 40
    markers:    { en: [prop, object], pt: [objeto, item] }
    keywords:   { en: [tree, rock],   pt: [árvore, pedra] }
    categories: { vegetation: [tree, árvore], mineral: [rock, pedra] }

A distinção entre ``markers`` e ``keywords`` é o que resolve os casos que uma
lista única erra:

    markers   nomeiam o próprio tipo de asset  — "tileset", "fundo", "ícone"
    keywords  nomeiam o sujeito                — "grass", "floresta", "espada"

Em "grass tileset" as duas listas casam ("grass" é prop, "tileset" é tileset).
O marker ganha, e o resultado é um tileset — que é o que a pessoa pediu.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from ..schemas import AssetType

__all__ = ["AssetTaxonomy", "TaxonomyEntry", "TaxonomyTerm", "normalize_text"]

_LOG = logging.getLogger("assetflow.generation.spec.taxonomy")


def normalize_text(text: str) -> str:
    """Minúsculas, sem acento e com espaçamento normalizado.

    Existe para que "ÁRVORE", "arvore" e "Árvore" sejam o mesmo termo. Quem
    escreve o prompt não digita acento com constância, e o vocabulário não
    pode depender disso para funcionar.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    # Pontuação vira espaço: "tree, 32x32" precisa casar "tree" sozinho.
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in without_accents)
    return " ".join(cleaned.split())


@dataclass(frozen=True, slots=True)
class TaxonomyTerm:
    """Um termo do vocabulário, já normalizado."""

    text: str
    asset_type: AssetType
    #: ``True`` para termo que nomeia o tipo ("tileset"); ``False`` para
    #: sujeito ("grass").
    marker: bool
    priority: int
    category: str | None = None

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass(slots=True)
class TaxonomyEntry:
    """O vocabulário de um tipo de asset, como veio do YAML."""

    asset_type: AssetType
    priority: int = 0
    terms: tuple[TaxonomyTerm, ...] = ()

    @classmethod
    def from_config(cls, payload: Mapping[str, Any], *, origin: str = "") -> "TaxonomyEntry":
        raw_type = str(payload.get("type") or "").strip()
        try:
            asset_type = AssetType(raw_type)
        except ValueError as exc:
            raise ValueError(
                f"taxonomia {origin or '(sem origem)'}: tipo '{raw_type}' desconhecido"
            ) from exc

        priority = int(payload.get("priority") or 0)
        categories = _category_index(payload.get("categories") or {})

        terms: list[TaxonomyTerm] = []
        for marker, key in ((True, "markers"), (False, "keywords")):
            for text in _flatten_languages(payload.get(key) or {}):
                normalized = normalize_text(text)
                if not normalized:
                    continue
                terms.append(
                    TaxonomyTerm(
                        text=normalized,
                        asset_type=asset_type,
                        marker=marker,
                        priority=priority,
                        category=categories.get(normalized),
                    )
                )

        # Termos duplicados no mesmo arquivo (ex.: o mesmo nome nas duas
        # línguas) viram uma entrada só; ordenar por tamanho aqui poupa o
        # classificador de reordenar a cada pedido.
        unique = {(term.text, term.marker): term for term in terms}
        ordered = tuple(
            sorted(unique.values(), key=lambda term: (-term.words, -len(term.text)))
        )
        return cls(asset_type=asset_type, priority=priority, terms=ordered)


def _flatten_languages(payload: Any) -> Iterable[str]:
    """``{en: [...], pt: [...]}`` ou ``[...]`` -> termos, sem distinção.

    A língua serve para organizar o arquivo e para quem o edita; o
    classificador não precisa dela — casa o que casar. Aceitar a lista solta
    também é de propósito: um vocabulário monolíngue não deve exigir
    cerimônia.
    """
    if isinstance(payload, Mapping):
        for values in payload.values():
            yield from _flatten_languages(values)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            if isinstance(item, str):
                yield item
            else:
                yield from _flatten_languages(item)
    elif isinstance(payload, str):
        yield payload


def _category_index(payload: Mapping[str, Any]) -> dict[str, str]:
    """``{vegetation: [tree, árvore]}`` -> ``{"tree": "vegetation", ...}``."""
    index: dict[str, str] = {}
    for category, values in payload.items():
        for text in _flatten_languages(values):
            normalized = normalize_text(text)
            if normalized:
                index.setdefault(normalized, str(category))
    return index


@dataclass(slots=True)
class AssetTaxonomy:
    """Todos os vocabulários carregados, prontos para consulta."""

    entries: tuple[TaxonomyEntry, ...] = ()
    _terms: tuple[TaxonomyTerm, ...] = field(default=(), init=False, repr=False)

    def __post_init__(self) -> None:
        # Ordem de busca: frase longa antes de palavra solta. É o que faz
        # "sala do trono" ganhar de "sala" sem depender de sorte na iteração.
        self._terms = tuple(
            sorted(
                (term for entry in self.entries for term in entry.terms),
                key=lambda term: (-term.words, -len(term.text), term.text),
            )
        )

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def terms(self) -> tuple[TaxonomyTerm, ...]:
        return self._terms

    def types(self) -> tuple[AssetType, ...]:
        return tuple(entry.asset_type for entry in self.entries)

    @classmethod
    def empty(cls) -> "AssetTaxonomy":
        return cls(entries=())

    @classmethod
    def from_configs(cls, payloads: Iterable[Mapping[str, Any]]) -> "AssetTaxonomy":
        entries: list[TaxonomyEntry] = []
        for payload in payloads:
            try:
                entries.append(TaxonomyEntry.from_config(payload))
            except ValueError as exc:
                # Um arquivo torto do vocabulário não pode derrubar o boot: o
                # classificador degrada para "não sei", e o profile continua
                # respondendo. Silêncio é que não pode haver.
                _LOG.warning("vocabulário ignorado: %s", exc)
        return cls(entries=tuple(entries))

    @classmethod
    def from_directory(cls, directory: Path) -> "AssetTaxonomy":
        """Carrega todos os ``*.yaml`` de ``config/asset_taxonomy/``."""
        if not directory.exists():
            _LOG.info(
                "diretório de taxonomia '%s' não existe; classificação semântica "
                "desligada e o tipo do profile prevalece",
                directory,
            )
            return cls.empty()

        payloads: list[Mapping[str, Any]] = []
        for path in sorted(directory.glob("*.yaml")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = yaml.safe_load(handle) or {}
            except Exception as exc:  # pragma: no cover - YAML corrompido
                _LOG.warning("falha ao ler a taxonomia '%s': %s", path.name, exc)
                continue
            if not isinstance(data, Mapping):
                _LOG.warning("taxonomia '%s' ignorada: raiz não é um mapeamento", path.name)
                continue
            payloads.append(data)
        return cls.from_configs(payloads)
