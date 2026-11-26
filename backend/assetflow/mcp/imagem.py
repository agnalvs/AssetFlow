"""A imagem do olhar: ampliada, silhueta em preto e tamanho real, num PNG só.

Fase B2 do plano do app. O ``desenhar`` e o ``ver_asset`` devolvem esta
imagem, para o Claude julgar a aparência do que desenhou:

* à esquerda, o sprite ampliado por vizinho mais próximo até :data:`LADO`
  pixels (8× numa grade de 48, 12× em 32, 24× em 16), sobre cinza claro;
* no meio, a silhueta em preto, na metade da ampliação — o "preview da
  silhueta" do ``PIXEL_KNOWLEDGE.md`` §3;
* embaixo dela, o tamanho real, em 2× e em 1×.

O custo segue a regra da Anthropic para imagens: ⌈largura ÷ 28⌉ × ⌈altura ÷
28⌉ tokens. Com lado 384, a imagem tem 588 × 384 em qualquer grade quadrada
até 48, e custa 294 tokens (o ``ver_asset`` antigo, 256 de lado, custava 81).
"""

from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image

__all__ = ["LADO", "imagem_do_olhar", "tokens_da_imagem"]

#: Lado do painel ampliado, em pixels.
LADO = 384
_FUNDO = (214, 214, 214, 255)
_BRANCO = (255, 255, 255, 255)
_VAO = 12


def tokens_da_imagem(largura: int, altura: int) -> int:
    """Quanto a imagem custa à conversa: um token por bloco de 28 × 28 pixels."""
    return math.ceil(largura / 28) * math.ceil(altura / 28)


def imagem_do_olhar(png: bytes) -> tuple[bytes, int, tuple[int, int]]:
    """O PNG dos três painéis, a ampliação do painel grande e o tamanho final."""
    with Image.open(io.BytesIO(png)) as aberta:
        sprite = aberta.convert("RGBA")
    largura, altura = sprite.size
    escala = max(1, LADO // max(largura, altura))
    meia = max(1, escala // 2)

    grande = Image.new("RGBA", (largura * escala, altura * escala), _FUNDO)
    grande.alpha_composite(sprite.resize(grande.size, Image.NEAREST))

    alfa = np.asarray(sprite)[..., 3] >= 128
    silhueta = np.full((altura, largura, 4), 255, dtype=np.uint8)
    silhueta[alfa, :3] = 0
    silhueta_img = Image.fromarray(silhueta, "RGBA").resize(
        (largura * meia, altura * meia), Image.NEAREST
    )

    real2 = Image.new("RGBA", (largura * 2, altura * 2), _FUNDO)
    real2.alpha_composite(sprite.resize(real2.size, Image.NEAREST))
    real1 = Image.new("RGBA", (largura, altura), _FUNDO)
    real1.alpha_composite(sprite)

    direita = max(silhueta_img.width, real2.width + _VAO + real1.width)
    tela = Image.new(
        "RGBA",
        (grande.width + _VAO + direita, max(grande.height, silhueta_img.height + _VAO + real2.height)),
        _BRANCO,
    )
    tela.paste(grande, (0, 0))
    x = grande.width + _VAO
    tela.paste(silhueta_img, (x, 0))
    tela.paste(real2, (x, silhueta_img.height + _VAO))
    tela.paste(real1, (x + real2.width + _VAO, silhueta_img.height + _VAO))

    saida = io.BytesIO()
    tela.convert("RGB").save(saida, format="PNG", optimize=True)
    return saida.getvalue(), escala, tela.size
