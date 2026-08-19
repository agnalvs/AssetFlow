"""PixelExporter — os arquivos que saem de um asset Pixel (plano Pixel §32 e §70).

**Este módulo não é um :class:`PixelTransform`, e a diferença é proposital.**
O plano Pixel §8 desenha o exporter como o último estágio do pipeline, mas o
contrato de um estágio é ``(imagem, contexto) -> imagem``: ele transforma
pixels e devolve pixels. O exporter faz outra coisa — devolve *bytes* — e
precisa de material que **ainda não existe** enquanto a lista de transforms
está rodando:

* o :class:`ProcessingReport` só fica completo depois do último estágio;
* o :class:`PixelValidationReport` e a :class:`AcceptanceDecision` vêm de
  serviços que rodam **depois** do PixelPostProcessor inteiro (§37 e §59).

Colocá-lo na lista de transforms obrigaria o ``PixelContext`` a carregar o
relatório de validação, ou seja, faria a camada de processamento depender da
camada de validação — exatamente a inversão que a separação do plano §6/§37
existe para impedir. Por isso quem chama ``export()`` é o
:class:`~assetflow.pixel.service.PixelAssetProcessor`, no fim de tudo. O
arquivo continua morando em ``stages/`` porque é ali que o plano desenha o
exporter, e mudá-lo de lugar tornaria o mapa mental mais difícil, não mais
fácil.

A regra inegociável do plano Pixel §35: ``logical.png`` é o asset real e
**nunca** pode ser substituído pelo preview. O preview é ampliação de
visualização; entregá-lo no lugar do asset é entregar um PNG 512×512 fingindo
ser um sprite 64×64 — a violação nº 1 do plano §103.
"""

from __future__ import annotations

import json
from typing import Any

from PIL import Image

from ...contracts.output_spec import PixelOutputSpec
from ...contracts.processing_report import ProcessingReport
from ...contracts.validation_report import AcceptanceDecision, PixelValidationReport
from ...imaging import color_counts, encode_png, to_array

__all__ = ["ARTIFACT_NAMES", "PixelExporter"]

#: Catálogo completo dos artefatos do plano Pixel §70, na ordem de gravação.
#: Só ``logical.png``, ``palette.json`` e ``processing.json`` são obrigatórios;
#: os outros três dependem do que o chamador tiver em mãos.
ARTIFACT_NAMES: tuple[str, ...] = (
    "logical.png",
    "preview.png",
    "palette.json",
    "processing.json",
    "validation.json",
    "raw.png",
)


class PixelExporter:
    """Converte o resultado do módulo Pixel no conjunto de arquivos do §70."""

    def export(
        self,
        logical: Image.Image,
        *,
        spec: PixelOutputSpec,
        processing: ProcessingReport,
        validation: PixelValidationReport | None = None,
        decision: AcceptanceDecision | None = None,
        preview: Image.Image | None = None,
        raw: bytes | None = None,
    ) -> dict[str, bytes]:
        """Monta ``{nome_do_arquivo: bytes}`` pronto para o storage gravar.

        Args:
            logical: o asset real, já na resolução lógica (§33 e §72).
            spec: o contrato que descreve o que o arquivo deveria ser.
            processing: vira ``processing.json`` (§74).
            validation: vira ``validation.json`` (§75). Sem ele o arquivo não
                é gerado — um relatório de validação ausente é diferente de um
                relatório vazio.
            decision: entra **dentro** de ``validation.json``, na chave
                ``acceptance``. A decisão só existe a partir de um relatório,
                então sem ``validation`` ela não tem onde morar e é ignorada.
            preview: vira ``preview.png`` (§34 e §73), nunca ``logical.png``.
            raw: bytes originais do motor, preservados como ``raw.png`` para
                debug e benchmark (§71).

        O dicionário sai na ordem de :data:`ARTIFACT_NAMES`: a mesma entrada
        produz sempre a mesma sequência de arquivos.
        """
        artifacts: dict[str, bytes] = {}

        artifacts["logical.png"] = encode_png(logical)
        if preview is not None:
            artifacts["preview.png"] = encode_png(preview)
        artifacts["palette.json"] = self._encode_json(self._palette_document(logical, spec))
        artifacts["processing.json"] = self._encode_json(processing.model_dump(mode="json"))
        if validation is not None:
            artifacts["validation.json"] = self._encode_json(
                self._validation_document(validation, decision)
            )
        if raw is not None:
            # Gravado sem reencode: o valor de `raw.png` é ser byte a byte o
            # que o motor devolveu. Passá-lo pelo Pillow o tornaria uma cópia
            # nossa da saída do motor, e o benchmark do §71 perderia o sentido.
            artifacts["raw.png"] = bytes(raw)

        return artifacts

    # ------------------------------------------------------------------
    def _palette_document(
        self, logical: Image.Image, spec: PixelOutputSpec
    ) -> dict[str, Any]:
        """A paleta **medida no arquivo entregue**, não a pedida no spec.

        ``color_counts`` ignora os pixels transparentes (plano Pixel §28): um
        pixel invisível não é uma cor do sprite e não pode gastar uma entrada
        da paleta. A ordem vem do próprio ``color_counts`` — frequência
        decrescente, empate resolvido pelo hexadecimal —, o que dá uma lista
        estável e faz a cor dominante aparecer primeiro (§54).
        """
        counts = color_counts(to_array(logical))
        return {
            "mode": spec.palette.mode,
            "max_colors": spec.max_colors,
            "color_count": len(counts),
            "colors": list(counts),
            "counts": counts,
        }

    def _validation_document(
        self,
        validation: PixelValidationReport,
        decision: AcceptanceDecision | None,
    ) -> dict[str, Any]:
        """Relatório completo + o veredito, lado a lado (plano Pixel §75).

        ``acceptance`` é uma chave anexada aqui, e não um campo do relatório,
        porque o Validator mede e a política decide (§59): juntar as duas
        coisas no mesmo modelo acabaria com essa fronteira.
        """
        document: dict[str, Any] = validation.model_dump(mode="json")
        if decision is not None:
            document["acceptance"] = decision.model_dump(mode="json")
        return document

    def _encode_json(self, document: dict[str, Any]) -> bytes:
        """JSON legível e determinístico.

        ``ensure_ascii=False`` porque as mensagens são em português e
        ``\u00e3`` no meio de um relatório de erro não ajuda ninguém;
        ``indent=2`` porque estes arquivos são lidos por humanos durante o
        benchmark; ``sort_keys=False`` para preservar a ordem declarada nos
        contratos — que já é fixa e portanto determinística, e é a ordem em
        que o relatório faz sentido ser lido.
        """
        text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False)
        return text.encode("utf-8")
