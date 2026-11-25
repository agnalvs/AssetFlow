"""Remendo: uma receita parcial aplicada sobre a receita de um asset anterior.

Corrigir um detalhe não deveria custar a receita inteira de novo. O remendo
manda só o que mudou, e o servidor junta com a receita da base, que o
histórico guarda completa:

* ``paleta`` — junta por chave: chave existente é trocada, chave nova entra;
* camada com ``nome`` que já existe — é trocada **no mesmo lugar**, e a ordem
  de pintura não muda;
* camada com ``nome`` novo — entra no fim (pinta por cima de tudo);
* ``{"nome": "brilho", "remover": true}`` — tira a camada;
* ``grade`` — não muda. Vir diferente é erro, não ajuste.

O resultado é sempre uma receita **inteira**: é ela que vai para a gaveta e
para o histórico, e é por isso que dá para remendar um remendo. A gaveta
continua validando tudo como valida uma receita nova — aqui só se junta.

Este módulo trabalha com o JSON cru e não conhece a gaveta: o formato da
receita é dela (``engines/desenhista/receita.py``), e uma camada fora dela não
importa gaveta nenhuma (``tests/test_architecture_boundaries.py``).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

__all__ = ["RemendoInvalido", "ResumoRemendo", "aplicar_remendo"]

_CHAVES = frozenset({"paleta", "camadas", "grade"})


class RemendoInvalido(ValueError):
    """O remendo não pode ser aplicado; a mensagem diz por quê."""


@dataclass(slots=True)
class ResumoRemendo:
    """O que o remendo mudou, para a primeira linha do laudo."""

    paleta: list[str] = field(default_factory=list)
    trocadas: list[str] = field(default_factory=list)
    acrescentadas: list[str] = field(default_factory=list)
    removidas: list[str] = field(default_factory=list)

    def texto(self) -> str:
        partes = []
        if self.paleta:
            partes.append(f"paleta {', '.join(self.paleta)}")
        if self.trocadas:
            partes.append(f"trocou {_lista('camada', self.trocadas)}")
        if self.acrescentadas:
            partes.append(f"acrescentou {_lista('camada', self.acrescentadas)}")
        if self.removidas:
            partes.append(f"removeu {_lista('camada', self.removidas)}")
        return "; ".join(partes)


def aplicar_remendo(base: dict[str, Any], parcial: Any) -> tuple[dict[str, Any], ResumoRemendo]:
    """Junta ``parcial`` à receita ``base`` e devolve a receita inteira.

    Raises:
        RemendoInvalido: com a razão, em português.
    """
    if not isinstance(parcial, dict):
        raise RemendoInvalido("o remendo precisa ser um objeto com 'paleta' e/ou 'camadas'")
    estranhas = sorted(str(chave) for chave in parcial if chave not in _CHAVES)
    if estranhas:
        raise RemendoInvalido(
            f"chave desconhecida no remendo: {', '.join(repr(c) for c in estranhas)} "
            "(aceitas: camadas, grade, paleta)"
        )
    if not parcial.get("paleta") and not parcial.get("camadas"):
        raise RemendoInvalido("o remendo não muda nada: mande 'paleta' e/ou 'camadas'")

    receita = copy.deepcopy(base)
    resumo = ResumoRemendo()

    if "grade" in parcial and parcial["grade"] != base.get("grade"):
        raise RemendoInvalido(
            f"o remendo não muda a grade (a base declara {base.get('grade')}); "
            "para outro tamanho, mande uma receita nova, sem base"
        )

    paleta = parcial.get("paleta")
    if paleta:
        if not isinstance(paleta, dict):
            raise RemendoInvalido("'paleta' do remendo precisa ser um objeto de chave para cor")
        atual = dict(receita.get("paleta") or {})
        for chave, cor in paleta.items():
            if atual.get(chave) != cor:
                resumo.paleta.append(str(chave))
            atual[chave] = cor
        receita["paleta"] = atual

    camadas = parcial.get("camadas")
    if camadas:
        receita["camadas"] = _juntar_camadas(list(receita.get("camadas") or []), camadas, resumo)

    return receita, resumo


def _juntar_camadas(
    atuais: list[Any], novas: Any, resumo: ResumoRemendo
) -> list[Any]:
    if not isinstance(novas, list):
        raise RemendoInvalido("'camadas' do remendo precisa ser uma lista")

    # Congela os nomes da base antes de mexer: uma camada sem nome se chama
    # "camada N" pela posição, e remover uma anterior mudaria o N dela.
    atuais = [
        {**camada, "nome": _nome_efetivo(camada, indice)} if isinstance(camada, dict) else camada
        for indice, camada in enumerate(atuais)
    ]

    for indice, camada in enumerate(novas):
        onde = f"camadas[{indice}] do remendo"
        if not isinstance(camada, dict):
            raise RemendoInvalido(f"{onde}: cada camada precisa ser um objeto")
        nome = camada.get("nome")
        if not isinstance(nome, str) or not nome.strip():
            raise RemendoInvalido(
                f"{onde}: no remendo toda camada precisa de 'nome' — é por ele que a "
                "camada da base é encontrada"
            )

        posicao = _posicao(atuais, nome)
        if camada.get("remover") is True:
            if set(camada) - {"nome", "remover"}:
                raise RemendoInvalido(f"{onde}: 'remover' não se mistura com outros campos")
            if posicao is None:
                raise RemendoInvalido(
                    f"{onde}: a base não tem camada '{nome}' para remover "
                    f"(camadas: {', '.join(_nomes(atuais))})"
                )
            del atuais[posicao]
            resumo.removidas.append(nome)
        elif "remover" in camada:
            raise RemendoInvalido(f"{onde}: 'remover' só aceita true")
        elif posicao is not None:
            atuais[posicao] = camada
            resumo.trocadas.append(nome)
        else:
            atuais.append(camada)
            resumo.acrescentadas.append(nome)

    if not atuais:
        raise RemendoInvalido("o remendo removeu todas as camadas")
    return atuais


def _nome_efetivo(camada: Any, indice: int) -> str:
    """O nome com que a gaveta conhece a camada: o declarado, ou "camada N"."""
    if isinstance(camada, dict) and isinstance(camada.get("nome"), str):
        return camada["nome"]
    return f"camada {indice + 1}"


def _nomes(camadas: list[Any]) -> list[str]:
    return [_nome_efetivo(camada, indice) for indice, camada in enumerate(camadas)]


def _posicao(camadas: list[Any], nome: str) -> int | None:
    for indice, atual in enumerate(_nomes(camadas)):
        if atual == nome:
            return indice
    return None


def _lista(palavra: str, nomes: list[str]) -> str:
    plural = palavra + ("s" if len(nomes) > 1 else "")
    return f"{plural} {', '.join(nomes)}"
