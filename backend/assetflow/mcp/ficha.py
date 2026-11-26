"""A ficha de verificação de um asset (lote F5, FUNDAMENTOS_E_FERRAMENTAS §7).

Uma linha por regra da base que vale para o pedido, com o tipo de verificação
que a regra declara e o resultado:

    tipo          quem confere           de onde vem o resultado
    construcao    o comando da receita   a receita usou o comando (``sombrear``…)
    medida        o app                  os desvios do olho e os avisos do validador
    olhar         o Claude               a resposta dele à pergunta, no concluir_pedido
    autora        a autora               o "gostei" ou "não gostei" dela

E o **cruzamento**: uma pergunta respondida "sim" quando a medida que confere a
mesma coisa acusou o problema vira **divergência**, que a tela destaca. É o que
reduz o risco de um olhar de faz de conta (§7, "como evitar").

Só lê: os relatórios gravados ao lado do PNG, a receita e as respostas.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

__all__ = [
    "CONFERE",
    "MEDIDAS_CONHECIDAS",
    "montar_ficha",
    "resultado_da_resposta",
]

#: As medidas que o app sabe fazer: os códigos do olho do app e o de pixel
#: solto do validador. Uma regra ``medida:<código>`` precisa apontar para uma
#: delas (tests/test_ficha.py).
MEDIDAS_CONHECIDAS = {
    "VALOR", "PREENCHIMENTO", "PROPORCAO", "ALTURA", "CORES", "TONS", "RAMPAS", "CONTORNO",
    "ORFAOS",
}
#: Pergunta do olhar -> a medida que confere a mesma coisa (para o cruzamento).
CONFERE = {"valores": "VALOR", "limpeza": "ORFAOS"}
_AVISOS_DO_VALIDADOR = {"PX-WARN-ORPHAN": "ORFAOS"}


def resultado_da_resposta(resposta: str | None) -> tuple[str, str]:
    """``("passou"|"nao_passou"|"sem_resposta", detalhe)`` de uma resposta livre."""
    if not resposta or not str(resposta).strip():
        return "sem_resposta", ""
    texto = str(resposta).strip()
    baixo = texto.lower()
    if baixo.startswith(("sim", "ok", "s ")) or baixo == "s":
        return "passou", texto
    if baixo.startswith(("não", "nao", "n ")) or baixo == "n":
        return "nao_passou", texto
    return "sem_resposta", texto


def _usados(receita: Mapping[str, Any] | None) -> set[str]:
    usados: set[str] = set()
    if not receita:
        return usados
    for chave in receita:
        usados.add(str(chave))
    for camada in receita.get("camadas") or []:
        if isinstance(camada, Mapping):
            if camada.get("material"):
                usados.add("material")
            for op in camada.get("ops") or []:
                if isinstance(op, Mapping):
                    usados.update(str(k) for k in op)
    return usados


def montar_ficha(
    *,
    regras: Iterable[Any],
    perguntas: Iterable[str],
    respostas: Mapping[str, str] | None,
    olhar: Mapping[str, Any] | None,
    validacao: Mapping[str, Any] | None,
    receita: Mapping[str, Any] | None,
    gostei: bool | None = None,
) -> dict[str, Any]:
    """A ficha: as linhas, as respostas e as divergências."""
    desvios = {
        d.get("codigo"): d.get("texto", "")
        for d in ((olhar or {}).get("olho") or {}).get("desvios") or []
    }
    for aviso in ((validacao or {}).get("quality") or {}).get("warnings") or []:
        codigo = _AVISOS_DO_VALIDADOR.get(aviso.get("code"))
        if codigo:
            desvios[codigo] = aviso.get("message", codigo)
    medidas = ((olhar or {}).get("olho") or {}).get("medidas") or {}
    usados = _usados(receita)
    respostas = {str(k).strip().lower(): str(v) for k, v in (respostas or {}).items()}

    linhas = []
    for regra in regras:
        tipo = regra.tipo_de_verificacao
        alvo = regra.alvo_da_verificacao
        if tipo == "medida":
            if alvo in desvios:
                resultado, detalhe = "nao_passou", desvios[alvo]
            elif alvo == "VALOR" and not medidas.get("contraste_por_camada"):
                resultado, detalhe = "nao_se_aplica", "sem camadas vizinhas medidas"
            else:
                resultado, detalhe = "passou", "o olho do app não acusou"
            quem = "app"
        elif tipo == "olhar":
            nome = alvo.split("/", 1)[-1]
            resultado, detalhe = resultado_da_resposta(respostas.get(nome))
            quem = "Claude"
        elif tipo == "construcao":
            if alvo in usados:
                resultado, detalhe = "passou", f"por construção ({alvo})"
            else:
                resultado, detalhe = "nao_se_aplica", f"a receita não usou {alvo}"
            quem = "receita"
        else:  # autora
            resultado = "passou" if gostei else ("nao_passou" if gostei is False else "sem_resposta")
            detalhe = ""
            quem = "autora"
        linhas.append(
            {
                "regra": regra.texto,
                "verificacao": regra.verificacao,
                "tipo": tipo,
                "resultado": resultado,
                "detalhe": detalhe,
                "quem": quem,
            }
        )

    divergencias = []
    lista = [p.strip().lower() for p in perguntas]
    for nome in lista:
        medida = CONFERE.get(nome)
        resultado, _ = resultado_da_resposta(respostas.get(nome))
        if medida and resultado == "passou" and medida in desvios:
            divergencias.append(
                {
                    "pergunta": nome,
                    "resposta": respostas.get(nome),
                    "medida": medida,
                    "detalhe": desvios[medida],
                }
            )
    return {
        "linhas": linhas,
        "respostas": {nome: respostas.get(nome) for nome in lista},
        "sem_resposta": [
            nome for nome in lista
            if resultado_da_resposta(respostas.get(nome))[0] == "sem_resposta"
        ],
        "divergencias": divergencias,
    }
