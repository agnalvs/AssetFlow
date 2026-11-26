"""A lista de verificação do olhar (Fase B2 do plano do app).

A base de conhecimento serve também para **julgar**: no primeiro olhar de cada
pedido, o laudo do ``desenhar`` traz de 4 a 6 perguntas tiradas de
``config/pixel_knowledge/olhar.yaml``, escolhidas pela forma do pedido. Cada
pergunta cita a seção do ``PIXEL_KNOWLEDGE.md`` e, quando há, a regra de outro
YAML de onde sai — nenhuma é inventada na hora.

Como o recorte, a escolha só **lê** o spec: o tipo, o corpo e a direção de luz.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..generation.schemas import AssetType

__all__ = [
    "ListasDoOlhar",
    "Pergunta",
    "lembrete_da_lista",
    "ler_olhar",
    "lista_de_verificacao",
]

_SECAO = re.compile(r"^§\d+$")
_ORIGEM = re.compile(r"^(?P<arquivo>[a-z_]+\.yaml)(?:/(?P<forma>[a-z_]+))?: (?P<trecho>.+)$")


class OlharInvalido(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Pergunta:
    nome: str
    texto: str
    secao: str
    #: ``"proporcoes.yaml/humanoid: trecho"`` ou ``"luz.yaml: trecho"``; ``None``
    #: quando a pergunta sai só do documento.
    de: str | None = None

    def origem(self) -> tuple[str, str | None, str] | None:
        """``(arquivo, forma, trecho)`` de ``de``."""
        if not self.de:
            return None
        casou = _ORIGEM.match(self.de)
        return (casou["arquivo"], casou["forma"], casou["trecho"]) if casou else None


@dataclass(frozen=True, slots=True)
class ListasDoOlhar:
    abertura: str
    listas: Mapping[str, tuple[Pergunta, ...]] = field(default_factory=dict)
    #: A pergunta do conceito (lote 1), que entra quando o pedido tem um.
    conceito: Pergunta | None = None


def ler_olhar(dados: Mapping[str, Any], origem: str) -> ListasDoOlhar:
    abertura = dados.get("abertura")
    if not isinstance(abertura, str) or "{ampliacao}" not in abertura:
        raise OlharInvalido(f"{origem}: 'abertura' é um texto com {{ampliacao}}")
    listas: dict[str, tuple[Pergunta, ...]] = {}
    for forma, brutas in (dados.get("listas") or {}).items():
        if not isinstance(brutas, list) or not 4 <= len(brutas) <= 6:
            raise OlharInvalido(f"{origem}: a lista de '{forma}' tem de 4 a 6 perguntas")
        perguntas = []
        for i, bruta in enumerate(brutas):
            onde = f"{origem}: listas.{forma}[{i}]"
            if not isinstance(bruta, Mapping):
                raise OlharInvalido(f"{onde}: mapeamento esperado")
            estranhas = sorted(set(bruta) - {"nome", "texto", "secao", "de"})
            if estranhas:
                raise OlharInvalido(f"{onde}: chave desconhecida ({', '.join(estranhas)})")
            nome, texto, secao = bruta.get("nome"), bruta.get("texto"), bruta.get("secao")
            if not all(isinstance(v, str) and v.strip() for v in (nome, texto, secao)):
                raise OlharInvalido(f"{onde}: nome, texto e secao são textos")
            if not _SECAO.match(secao):
                raise OlharInvalido(f"{onde}: secao como \"§3\" ({secao!r})")
            pergunta = Pergunta(nome=nome, texto=texto, secao=secao, de=bruta.get("de"))
            if pergunta.de is not None and pergunta.origem() is None:
                raise OlharInvalido(
                    f"{onde}: 'de' como \"proporcoes.yaml/humanoid: trecho\" ({pergunta.de!r})"
                )
            perguntas.append(pergunta)
        listas[str(forma)] = tuple(perguntas)
    conceito = None
    bruta = dados.get("conceito")
    if bruta is not None:
        if not isinstance(bruta, Mapping) or "{traco}" not in str(bruta.get("texto", "")):
            raise OlharInvalido(f"{origem}: 'conceito' é uma pergunta com {{traco}} no texto")
        if not _SECAO.match(str(bruta.get("secao", ""))):
            raise OlharInvalido(f"{origem}: 'conceito.secao' como \"§3\"")
        conceito = Pergunta(
            nome=str(bruta.get("nome") or "conceito"),
            texto=str(bruta["texto"]),
            secao=str(bruta["secao"]),
        )
    return ListasDoOlhar(abertura=abertura, listas=listas, conceito=conceito)


def _forma_e_lista(resolved: Any, olhar: ListasDoOlhar) -> tuple[str, tuple[Pergunta, ...]]:
    tipo = _valor(resolved.asset.type)
    if resolved.asset.type == AssetType.CHARACTER:
        corpo = _valor(resolved.character.body_type)
        if corpo in olhar.listas:
            return corpo, olhar.listas[corpo]
        return tipo, olhar.listas.get(tipo, ())
    return tipo, olhar.listas.get(tipo, ())


def lista_de_verificacao(
    resolved: Any,
    olhar: ListasDoOlhar | None,
    *,
    ampliacao: int,
    luz_padrao: str | None,
    traco: str | None = None,
    curta: bool = False,
) -> str:
    """A lista do primeiro olhar, pronta para o laudo; uma linha de "sem lista" se faltar.

    ``traco`` (o traço marcante do conceito escolhido) acrescenta a pergunta
    do conceito. ``curta`` (ajuste de custo) põe só os nomes, numa linha.
    """
    if olhar is None:
        return "olhar — confira a imagem (a base não tem olhar.yaml: sem lista de verificação)"
    forma, perguntas = _forma_e_lista(resolved, olhar)
    perguntas = _com_conceito(perguntas, olhar, traco)
    abertura = olhar.abertura.format(ampliacao=ampliacao)
    if not perguntas:
        return (
            abertura.rsplit(".", 1)[0]
            + f". A base não tem lista de verificação para {forma}: olhe a imagem e julgue."
        )
    if curta:
        nomes = ", ".join(p.nome for p in perguntas)
        return abertura.rsplit(".", 1)[0] + f". Confira: {nomes}."
    luz = resolved.style.shading.light_direction or luz_padrao or "de um lado só"
    linhas = [abertura]
    for n, pergunta in enumerate(perguntas, start=1):
        linhas.append(f"{n}. {pergunta.nome}: {pergunta.texto.format(luz=luz, traco=traco or '')}")
    return "\n".join(linhas)


def lembrete_da_lista(
    resolved: Any, olhar: ListasDoOlhar | None, *, traco: str | None = None
) -> str:
    """A linha curta dos remendos: os nomes da lista do primeiro olhar."""
    if olhar is None:
        return "olhar — confira a imagem de novo."
    _, perguntas = _forma_e_lista(resolved, olhar)
    perguntas = _com_conceito(perguntas, olhar, traco)
    if not perguntas:
        return "olhar — confira a imagem de novo."
    nomes = ", ".join(p.nome for p in perguntas)
    return f"olhar — confira de novo a lista do primeiro olhar ({nomes})."


def _com_conceito(
    perguntas: tuple[Pergunta, ...], olhar: ListasDoOlhar, traco: str | None
) -> tuple[Pergunta, ...]:
    if traco and olhar.conceito is not None and perguntas:
        return (*perguntas, olhar.conceito)
    return perguntas


def _valor(valor: Any) -> str:
    return str(getattr(valor, "value", valor))
