"""AlphaNormalizer — transparência binária, sem meio-termo (plano Pixel §21 a §24).

No perfil ``pixel_exact`` **não existe alpha 37, 128 ou 211**: só 0 e 255. A
regra não é purismo estético, é o que o asset encontra depois de sair daqui:

* ampliado na engine com nearest, um pixel de alpha 128 vira um bloco cinza
  translúcido de 8×8 no meio do contorno — a "franja suja" que denuncia Pixel
  Art gerada por IA;
* colisão e seleção por máscara precisam responder "este pixel existe?" com
  sim ou não, e alpha parcial não responde;
* a contagem de cores da paleta deixa de ser confiável, porque a mesma cor
  aparece em várias opacidades.

O corte é ``spec.alpha.threshold``: abaixo dele o pixel some, a partir dele o
pixel é sólido. O plano §24 prevê um modo ``limited`` (0/85/170/255) para
efeitos especiais como vidro e fumaça; ele está **explicitamente fora de
escopo da versão 1.0** e nem sequer existe em
:class:`~assetflow.pixel.contracts.output_spec.AlphaSpec`, cujo ``mode`` é
``Literal["binary"]`` — a proibição está no contrato, não só na intenção.

Este estágio roda **antes** do quantizador de paleta (plano Pixel §8): pixel
invisível não pode gastar uma das N cores do asset.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from ...imaging import opaque_mask, to_array, to_image
from .base import PixelContext, PixelTransform

__all__ = ["AlphaNormalizer"]


class AlphaNormalizer(PixelTransform):
    """Binariza o canal alpha e limpa o RGB do que ficou invisível."""

    name = "pixel.alpha_normalizer"
    version = "1.0.0"

    def apply(self, image: Image.Image, context: PixelContext) -> Image.Image:
        spec = context.spec
        threshold = spec.alpha.threshold

        array = to_array(image)
        before = array[:, :, 3]
        semitransparent_before = int(np.count_nonzero((before > 0) & (before < 255)))

        # Fundo sólido significa asset opaco: não há o que recortar, e manter
        # um buraco transparente sobre um fundo pintado seria contraditório.
        forced_opaque = spec.background.mode == "solid"
        keep = (
            np.ones(before.shape, dtype=bool)
            if forced_opaque
            else opaque_mask(array, threshold=threshold)
        )

        result = array.copy()
        result[:, :, 3] = np.where(keep, 255, 0).astype(np.uint8)

        # Só agora, com o alpha já decidido, o RGB dos pixels invisíveis vai a
        # zero. Um pixel totalmente transparente ainda carrega a cor que o
        # gerador pintou ali: ela reaparece como "cor fantasma" ao borrar ou
        # ampliar em um editor, contamina a leitura da paleta e faz o PNG
        # comprimir pior (o filtro do PNG adora regiões constantes). Zerar
        # também torna o arquivo determinístico: duas execuções que decidem o
        # mesmo alpha produzem os mesmos bytes.
        result[~keep, :3] = 0

        opaque_after = int(np.count_nonzero(keep))
        context.detail("threshold", threshold)
        context.detail("semitransparent_before", semitransparent_before)
        context.detail("removed_pixels", int(np.count_nonzero((before > 0) & ~keep)))
        context.detail("promoted_pixels", int(np.count_nonzero((before < 255) & keep)))
        context.detail("opaque_after", opaque_after)
        context.detail("transparent_after", int(keep.size - opaque_after))
        context.detail("forced_opaque", forced_opaque)

        return to_image(result)
