"""Mede cantos em L, dobras e degraus nas referências ativas (lote F1).

Os limites ``cantos_max``, ``dobras_max`` e ``degraus_max`` do olho do app
(``config/pixel_knowledge/referencias.yaml``, seção ``olho:``) saíram daqui:
o p90 dos quadros com contorno "escuro único", com peso igual por pacote.
Rodar de novo depois de importar pacotes; o script só imprime, não muda YAML.

    python scripts/calibrar_linha.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assetflow.referencias.colecao import ReferenciasAtivas, quantis
from assetflow.referencias.linha import medir_linha
from assetflow.settings import load_settings


def main() -> None:
    settings = load_settings()
    colecao = ReferenciasAtivas.carregar(settings.referencias_dir, settings.referencias_config)
    medidos = defaultdict(list)
    vistos = set()
    for quadro in colecao.quadros:
        if quadro.contorno_tipo != "escuro único":
            continue
        rgba = colecao.recortar(quadro)
        chave = (quadro.pacote, rgba.tobytes())
        if chave in vistos:
            continue
        vistos.add(chave)
        medida = medir_linha(rgba, quadro.contorno_cor)
        if medida is None:
            continue
        medidos[quadro.tipo].append((quadro, medida))
    for tipo, itens in sorted(medidos.items()):
        pacotes = sorted({q.pacote for q, _ in itens})
        print(f"## {tipo}: {len(itens)} quadros de {len(pacotes)} pacotes ({', '.join(pacotes)})")
        for campo in ("cantos_por_100", "dobras_por_100", "degraus_por_100"):
            # quantis() lê um atributo do quadro: o valor vai num campo emprestado.
            quadros = [replace(q, rampas_provaveis=m[campo]) for q, m in itens]
            faixa = quantis(quadros, lambda q: q.rampas_provaveis, (0.5, 0.75, 0.9))
            com_valor = sum(1 for _, m in itens if m[campo] is not None)
            print(f"  {campo}: p50/p75/p90 = {faixa} ({com_valor} quadros com valor)")


if __name__ == "__main__":
    main()
