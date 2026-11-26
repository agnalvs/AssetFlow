"""Os temas da base consultável (lote 8, PLANO_BASE_CONHECIMENTO §6).

Cada tema (``config/pixel_knowledge/temas/<id>.yaml``) tem regras curtas com
etiquetas — tipo de asset, corpo, faixa de tamanho, liberdade, material. O
pedido aciona as etiquetas: um prop de 16 px puxa "não pontilhe até 32×32", e
não puxa "suavize por dentro da silhueta", que é a partir de 32.

Duas saídas, para a base crescer sem crescer o recorte:

* :func:`linha_dos_temas` — uma linha no recorte, só com os temas e quantas
  regras valem (~30 tokens);
* :func:`texto_do_tema` — o tema inteiro, filtrado pelo pedido, que
  ``consultar_base(tema)`` devolve quando o Claude pede.

Como o recorte, só lê três campos do spec: ``logical_resolution``,
``asset.type`` e ``character.body_type``.
"""

from __future__ import annotations

from typing import Any

from .base import BaseDeConhecimento, Regra, Tema

__all__ = ["linha_dos_temas", "linha_geral_dos_temas", "regras_que_valem", "texto_do_tema"]


def _valor(campo: Any) -> str | None:
    return None if campo is None else str(getattr(campo, "value", campo))


def _alvo(resolved: Any | None) -> tuple[str | None, str | None, int | None]:
    if resolved is None:
        return None, None, None
    logica = getattr(resolved, "logical_resolution", None)
    lado = max(logica.width, logica.height) if logica is not None else None
    asset = getattr(resolved, "asset", None)
    personagem = getattr(resolved, "character", None)
    return (
        _valor(getattr(asset, "type", None)),
        _valor(getattr(personagem, "body_type", None)),
        lado,
    )


def regras_que_valem(tema: Tema, resolved: Any | None, liberdade: str = "fiel") -> list[Regra]:
    """As regras do tema cujas etiquetas o pedido aciona; sem pedido, todas."""
    if resolved is None:
        return list(tema.regras)
    tipo, corpo, lado = _alvo(resolved)
    return [
        r for r in tema.regras
        if r.etiquetas is None or r.etiquetas.vale(tipo=tipo, corpo=corpo, lado=lado, liberdade=liberdade)
    ]


def linha_dos_temas(base: BaseDeConhecimento | None, resolved: Any, liberdade: str = "fiel") -> str:
    """``temas (consultar_base): contorno 8 · pontilhado 3…``; ``""`` sem temas."""
    if base is None or not base.temas:
        return ""
    partes = []
    for tema in base.temas.values():
        n = len(regras_que_valem(tema, resolved, liberdade))
        if n:
            partes.append(f"{tema.id} {n}")
    if not partes:
        return ""
    return "temas (consultar_base, regras que valem): " + " · ".join(partes)


def linha_geral_dos_temas(base: BaseDeConhecimento | None) -> str:
    """A linha única do topo de uma lista de pedidos: os temas, sem contagem."""
    if base is None or not base.temas:
        return ""
    return (
        f"temas da base: {', '.join(base.temas)} — consultar_base(tema, pedido=...) traz as "
        "regras que valem para um pedido"
    )


def texto_do_tema(tema: Tema, resolved: Any | None, liberdade: str = "fiel") -> str:
    """O tema inteiro, filtrado pelo pedido: uma regra por linha, com a origem."""
    regras = regras_que_valem(tema, resolved, liberdade)
    linhas = [f"{tema.titulo} (PIXEL_KNOWLEDGE {tema.secao})" + (
        f" — {len(regras)} de {len(tema.regras)} valem para este pedido" if resolved is not None else ""
    )]
    for regra in regras:
        confere = {
            "construcao": "por construção",
            "medida": "o app mede",
            "olhar": "no seu olhar",
            "autora": "a autora julga",
        }[regra.tipo_de_verificacao]
        alvo = f" ({regra.alvo_da_verificacao})" if regra.alvo_da_verificacao else ""
        linhas.append(f"- {regra.texto} · {confere}{alvo}")
    if not regras:
        linhas.append("- nenhuma regra deste tema vale para este pedido")
    return "\n".join(linhas)
