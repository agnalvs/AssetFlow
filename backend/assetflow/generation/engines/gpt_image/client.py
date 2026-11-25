"""O cliente HTTP do GPT Image — sem SDK.

O teste de fronteiras **permitiria** o SDK aqui: esta é uma gaveta, e é
exatamente onde uma dependência de fornecedor pode viver. A escolha de não
usá-lo é outra, e é de projeto: falar `POST /v1/images/generations` com
`urllib` custa poucas dezenas de linhas, não acrescenta nenhuma dependência à
instalação, e é o mesmo caminho que o `assetflow/llm/` já tomou.

Consequência prática: qualquer provedor com API compatível — um gateway
corporativo, um proxy, um serviço equivalente — funciona trocando `base_url`,
sem tocar em código.

A rede roda em thread separada de propósito. `urllib` é síncrono, e chamá-lo
direto dentro do loop de eventos travaria o worker inteiro durante os segundos
(ou dezenas de segundos) da geração — inclusive o cancelamento, que precisa
continuar respondendo.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from ....generation.kernel.exceptions import (
    EngineExecutionError,
    EngineTimeoutError,
)

__all__ = ["GPTImageClient", "ImageRequest"]

_LOG = logging.getLogger("assetflow.engine.gpt_image")
_ENGINE_ID = "gpt-image-v1"


@dataclass(frozen=True, slots=True)
class ImageRequest:
    """Uma chamada de geração, já traduzida para o vocabulário do provedor."""

    prompt: str
    size: str
    n: int = 1
    quality: str = "auto"
    background: str = "auto"
    output_format: str = "png"
    moderation: str = "auto"

    def payload(self, model: str) -> dict[str, object]:
        body: dict[str, object] = {
            "model": model,
            "prompt": self.prompt,
            "size": self.size,
            "n": self.n,
            "quality": self.quality,
            "output_format": self.output_format,
            "moderation": self.moderation,
        }
        # `background` só é enviado quando há uma decisão: mandar "auto"
        # explicitamente é ruído, e alguns gateways compatíveis o recusam.
        if self.background != "auto":
            body["background"] = self.background
        return body


class GPTImageClient:
    """Envia a geração e devolve os PNGs."""

    def __init__(self, config) -> None:
        self._config = config

    def describe(self) -> str:
        return f"{self._config.base_url} · {self._config.model}"

    async def generate(self, request: ImageRequest) -> list[bytes]:
        """Gera e devolve as imagens em bytes.

        Raises:
            EngineExecutionError: recusa do provedor, resposta ilegível, ou
                configuração incompleta.
            EngineTimeoutError: o provedor não respondeu no prazo.
        """
        reason = self._config.unavailable_reason()
        if reason:
            raise EngineExecutionError(reason, engine_id=_ENGINE_ID)

        return await asyncio.to_thread(self._post, request)

    # ------------------------------------------------------------------
    def _post(self, request: ImageRequest) -> list[bytes]:
        body = json.dumps(request.payload(self._config.model)).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key}",
            **self._config.headers,
        }
        http_request = urllib.request.Request(
            f"{self._config.base_url}/images/generations",
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                http_request, timeout=self._config.timeout_s
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise EngineExecutionError(
                _http_message(exc),
                engine_id=_ENGINE_ID,
                retryable=_is_retryable(exc.code),
            ) from exc
        except urllib.error.URLError as exc:
            raise EngineExecutionError(
                f"não foi possível falar com {self._config.base_url}: {exc.reason}",
                engine_id=_ENGINE_ID,
            ) from exc
        except TimeoutError as exc:
            raise EngineTimeoutError(
                f"o GPT Image não respondeu em {self._config.timeout_s:.0f}s",
                engine_id=_ENGINE_ID,
            ) from exc
        except json.JSONDecodeError as exc:
            raise EngineExecutionError(
                "o GPT Image devolveu uma resposta ilegível", engine_id=_ENGINE_ID
            ) from exc

        return _decode(payload)


def _decode(payload: dict) -> list[bytes]:
    """Extrai os PNGs da resposta.

    O provedor devolve base64 em `data[].b64_json`. Uma resposta sem imagem
    **não** vira lista vazia: seguir em frente produziria um job "concluído"
    sem asset, que é o pior resultado possível.
    """
    entries = payload.get("data")
    if not isinstance(entries, list) or not entries:
        raise EngineExecutionError(
            f"o GPT Image não devolveu imagem: {str(payload)[:300]}",
            engine_id=_ENGINE_ID,
        )

    images: list[bytes] = []
    for entry in entries:
        encoded = (entry or {}).get("b64_json") if isinstance(entry, dict) else None
        if not encoded:
            continue
        try:
            images.append(base64.b64decode(encoded))
        except (ValueError, TypeError) as exc:  # pragma: no cover - defensivo
            raise EngineExecutionError(
                "o GPT Image devolveu uma imagem que não pôde ser decodificada",
                engine_id=_ENGINE_ID,
            ) from exc

    if not images:
        raise EngineExecutionError(
            "o GPT Image respondeu sem `b64_json` — nenhuma imagem utilizável",
            engine_id=_ENGINE_ID,
        )
    return images


def _is_retryable(status: int) -> bool:
    """Vale tentar de novo com este código?

    A distinção é dinheiro e tempo. `429` (limite de taxa) e os `5xx` são
    transitórios — insistir resolve. Um `400` não é: chave sem crédito, prompt
    recusado pela moderação ou tamanho inválido devolvem o **mesmo** erro na
    segunda tentativa, e cada tentativa é uma chamada cobrável.

    Foi o primeiro erro real desta gaveta que mostrou isso: um "Billing hard
    limit has been reached" foi repetido pelo retry do worker, e a mensagem
    ainda ficou escondida atrás de um job em `queued`.
    """
    return status == 429 or status >= 500


def _http_message(exc: urllib.error.HTTPError) -> str:
    """A recusa do provedor em português, com a causa preservada.

    A mensagem do provedor é mantida porque ela costuma ser a informação
    inteira — cota estourada, prompt recusado pela moderação, tamanho
    inválido. Traduzir isso para "erro na geração" apagaria o diagnóstico.
    """
    detail = exc.read().decode("utf-8", errors="replace")[:600]
    try:
        message = json.loads(detail).get("error", {}).get("message") or detail
    except (json.JSONDecodeError, AttributeError):
        message = detail

    if exc.code == 401:
        return f"credencial do GPT Image recusada (401): {message}"
    if exc.code == 429:
        return f"limite de uso do GPT Image atingido (429): {message}"
    if exc.code == 400:
        return f"o GPT Image recusou o pedido (400): {message}"
    return f"o GPT Image respondeu HTTP {exc.code}: {message}"
