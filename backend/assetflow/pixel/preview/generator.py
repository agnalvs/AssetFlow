"""PreviewGenerator — a ampliação de visualização (plano Pixel §34, §80 e §81).

O asset entregue é ``logical.png``, um PNG na resolução lógica real. Só que um
sprite de 64×64 aberto em uma tela de 1440p é um selo minúsculo, e ninguém
consegue avaliar arte assim. O preview existe para resolver **esse** problema,
e nada além dele:

    logical.png   64×64    o asset   (o que o jogo usa)
    preview.png   512×512  a lupa    (o que a pessoa olha)

Duas regras dão a forma deste módulo:

``escala inteira`` (§81)
    ``scale(7.8125)`` distribui 64 pixels lógicos em 500 pixels de tela, e
    como não existe pixel fracionário alguns blocos saem com 7 colunas e
    outros com 8. O sprite ganha listras de larguras diferentes e parece
    defeituoso — o artista culpa a arte, quando o culpado é o zoom. Com
    escala inteira todo bloco tem exatamente o mesmo tamanho.

``nearest-neighbor`` (§20 e §80)
    Qualquer interpolação (bilinear, bicúbica, Lanczos) inventa cores
    intermediárias nas bordas. O preview mostraria um sprite borrado que não
    corresponde a nenhum pixel do arquivo real.

E a regra que este módulo **não** pode quebrar (§35): o preview nunca
substitui o asset. Ele é devolvido separado justamente para que ninguém possa
gravá-lo por cima de ``logical.png`` sem perceber.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from ..contracts.output_spec import PixelOutputSpec
from ..imaging import ensure_rgba, scale_nearest, to_array
from ..version import PREVIEW_GENERATOR_VERSION

__all__ = ["PreviewGenerator"]


class PreviewGenerator:
    """Amplia a imagem lógica por um fator inteiro, sem interpolar."""

    version = PREVIEW_GENERATOR_VERSION

    def generate(self, logical: Image.Image, spec: PixelOutputSpec) -> Image.Image | None:
        """Devolve a ampliação, ou ``None`` quando o profile dispensa preview.

        ``None`` e não uma cópia da imagem lógica: quem chama precisa
        distinguir "não há preview" de "o preview é igual ao asset", senão
        acabaria gravando um ``preview.png`` que o profile não pediu.

        O fator usado é ``spec.preview.scale`` — não ``spec.preview_size``
        dividido pelo tamanho real da imagem. Os dois coincidem sempre que a
        imagem respeita o spec, mas se ela vier fora da resolução lógica
        (imagem de teste, spec trocado), forçar o tamanho alvo exigiria uma
        escala fracionária e produziria justamente os blocos irregulares que
        o §81 proíbe. Preserva-se a propriedade, não o número.
        """
        if not spec.preview.enabled:
            return None
        return scale_nearest(ensure_rgba(logical), spec.preview.scale)

    def blocks_are_uniform(
        self, logical: Image.Image, preview: Image.Image, scale: int
    ) -> bool:
        """Confere a propriedade que define um preview correto (plano §89).

        Cada pixel lógico precisa ter virado um bloco ``scale × scale`` de
        pixels **idênticos a ele**. A verificação mora aqui, e não no teste,
        porque a regra é do módulo: se o teste a reimplementasse, os dois
        poderiam divergir e o teste passaria a validar a sua própria cópia da
        regra em vez do comportamento real.

        ``np.repeat`` nos dois eixos é a expressão literal de "cada pixel
        vira um bloco": comparar o preview com esse array confere de uma vez
        o tamanho, a uniformidade de cada bloco e a correspondência de cor.
        """
        if scale < 1:
            return False
        source = to_array(ensure_rgba(logical))
        blocks = to_array(ensure_rgba(preview))
        expected_shape = (source.shape[0] * scale, source.shape[1] * scale)
        if blocks.shape[:2] != expected_shape:
            return False
        expected = np.repeat(np.repeat(source, scale, axis=0), scale, axis=1)
        return bool(np.array_equal(blocks, expected))
