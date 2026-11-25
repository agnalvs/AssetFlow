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

Num personagem, mais duas seções: ``body_types`` (a forma do corpo que um
termo nomeia) e ``category_body_types`` (o corpo que uma categoria implica,
para quando nenhum termo o nomeou). Qualquer lista aceita sublistas, e o
``character.yaml`` usa uma por palavra, com todas as formas dela.

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
    #: Topologia corporal, quando o termo a nomeia. Eixo **diferente** de
    #: `category`: um goblin é `creature` de corpo `humanoid`. Categoria diz
    #: que tipo de coisa é; topologia diz que forma o corpo tem — e é a forma
    #: que o gerador precisa saber.
    body_type: str | None = None

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass(slots=True)
class TaxonomyEntry:
    """O vocabulário de um tipo de asset, como veio do YAML."""

    asset_type: AssetType
    priority: int = 0
    terms: tuple[TaxonomyTerm, ...] = ()
    #: Corpo que uma categoria implica (``{"humanoid": "humanoid"}``): só a
    #: categoria em que todo membro tem o mesmo corpo. Quem consulta é o
    #: resolvedor do spec, quando nenhum termo do pedido disse a forma.
    category_body_types: Mapping[str, str] = field(default_factory=dict)

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
        # `body_types` é um eixo à parte de `categories`, e não um sinônimo: um
        # goblin é `creature` de corpo humanoide. Ver o comentário no
        # `config/asset_taxonomy/character.yaml`.
        body_types = _category_index(payload.get("body_types") or {})
        category_body_types = _category_body_types(
            payload.get("category_body_types") or {},
            categorias=set(categories.values()),
            corpos=set(body_types.values()),
            tipo=raw_type,
        )

        # Um termo que aparece só em `body_types` também é um sujeito deste
        # tipo — se dá para nomear a topologia do corpo dele, é um personagem.
        # Registrá-lo aqui evita a duplicação de listar cada bicho duas vezes,
        # e é o que faz acrescentar uma ave ao vocabulário ser **uma** edição.
        implicit_keywords = tuple(body_types)

        terms: list[TaxonomyTerm] = []
        for marker, key in ((True, "markers"), (False, "keywords")):
            source = _flatten_languages(payload.get(key) or {})
            if not marker:
                source = (*source, *implicit_keywords)
            for text in source:
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
                        body_type=body_types.get(normalized),
                    )
                )

        # Termos duplicados no mesmo arquivo (ex.: o mesmo nome nas duas
        # línguas) viram uma entrada só; ordenar por tamanho aqui poupa o
        # classificador de reordenar a cada pedido.
        unique = {(term.text, term.marker): term for term in terms}
        ordered = tuple(
            sorted(unique.values(), key=lambda term: (-term.words, -len(term.text)))
        )
        return cls(
            asset_type=asset_type,
            priority=priority,
            terms=ordered,
            category_body_types=category_body_types,
        )


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


def _category_body_types(
    payload: Any, *, categorias: set[str], corpos: set[str], tipo: str
) -> dict[str, str]:
    """``{humanoid: humanoid}`` conferido contra o próprio arquivo.

    Uma linha torta da tabela sai com aviso e o resto do vocabulário segue:
    perder a classificação inteira de personagens por um erro de digitação
    aqui seria trocar uma dedução que falta por uma que nunca acontece.
    """
    if not isinstance(payload, Mapping):
        _LOG.warning(
            "taxonomia '%s': category_body_types ignorado (não é um mapeamento)", tipo
        )
        return {}
    tabela: dict[str, str] = {}
    for categoria, corpo in payload.items():
        categoria, corpo = str(categoria).strip(), str(corpo or "").strip()
        if categoria not in categorias:
            _LOG.warning(
                "taxonomia '%s': category_body_types cita a categoria '%s', que não "
                "está em categories; linha ignorada",
                tipo,
                categoria,
            )
        elif corpo not in corpos:
            _LOG.warning(
                "taxonomia '%s': category_body_types dá à categoria '%s' o corpo "
                "'%s', que não está em body_types; linha ignorada",
                tipo,
                categoria,
                corpo,
            )
        else:
            tabela[categoria] = corpo
    return tabela


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

    def body_type_for_category(self, asset_type: AssetType, category: str) -> str | None:
        """O corpo que ``category`` implica no vocabulário de ``asset_type``.

        ``None`` quando a categoria não implica corpo nenhum — uma categoria
        mista, como ``creature``, ou uma que a tabela não lista.
        """
        for entry in self.entries:
            if entry.asset_type is asset_type and category in entry.category_body_types:
                return entry.category_body_types[category]
        return None

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
