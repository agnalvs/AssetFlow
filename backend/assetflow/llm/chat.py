"""Cliente de chat compatível com a API da OpenAI (plano Optimizer §42).

Um cliente só, para todos os provedores. O formato ``/chat/completions`` virou
o denominador comum — OpenAI, Ollama, LM Studio, OpenRouter, Groq, vLLM e
llama.cpp falam todos ele —, e implementá-lo uma vez cobre desde um modelo
local rodando de graça na máquina até um serviço pago.

Duas decisões que valem explicação:

**Sem SDK.** A requisição é `urllib` da biblioteca padrão, e não o pacote
``openai``. Não é economia de dependência: o teste de fronteiras proíbe SDKs
de fornecedor fora de ``generation/engines/<gaveta>/``, e a proibição está
certa — ela é o que impede o AssetFlow de trocar a dependência de um modelo de
imagem pela de um provedor de LLM. Falar HTTP puro mantém o planner livre de
fornecedor **de fato**, e não só por organização de pastas.

**Sem chave no YAML.** ``config/optimizer.yaml`` é versionado. A chave vem de
variável de ambiente, e o nome dela é que fica na configuração.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field

__all__ = ["ChatClient", "ChatConfig", "ChatError"]

_LOG = logging.getLogger("assetflow.llm")


class ChatError(RuntimeError):
    """Falha ao falar com o modelo.

    Nunca deve subir até o job. Quem usa este cliente a captura e segue pelo
    caminho determinístico: um provedor fora do ar pode rebaixar o resultado,
    com aviso, mas nunca derrubar uma geração.
    """


@dataclass(frozen=True, slots=True)
class ChatConfig:
    """Como falar com o modelo."""

    #: Base da API, com ``/v1``. Exemplos:
    #:   OpenAI     https://api.openai.com/v1
    #:   Ollama     http://localhost:11434/v1
    #:   LM Studio  http://localhost:1234/v1
    base_url: str = ""
    model: str = ""
    #: Nome da **variável de ambiente** que guarda a chave — não a chave.
    #: Provedores locais não precisam de nenhuma.
    api_key_env: str = "ASSETFLOW_OPTIMIZER_API_KEY"
    temperature: float = 0.4
    timeout_s: float = 60.0
    max_output_tokens: int = 4096
    #: Cabeçalhos extras, para provedores que os exijam (OpenRouter, por ex.).
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) or None

    @classmethod
    def from_config(cls, data: dict | None) -> ChatConfig:
        data = data or {}
        return cls(
            base_url=str(data.get("base_url") or "").rstrip("/"),
            model=str(data.get("model") or ""),
            api_key_env=str(data.get("api_key_env") or "ASSETFLOW_OPTIMIZER_API_KEY"),
            temperature=float(data.get("temperature", 0.4)),
            timeout_s=float(data.get("timeout_s", 60.0)),
            max_output_tokens=int(data.get("max_output_tokens", 4096)),
            headers={str(k): str(v) for k, v in (data.get("headers") or {}).items()},
        )


class ChatClient:
    """Envia uma conversa e devolve o texto da resposta."""

    def __init__(self, config: ChatConfig) -> None:
        self._config = config

    @property
    def config(self) -> ChatConfig:
        return self._config

    def describe(self) -> str:
        """Identificação para os metadados do job (plano de correção §28)."""
        return f"{self._config.base_url} · {self._config.model}"

    # ------------------------------------------------------------------
    def complete(self, system: str, user: str) -> str:
        """Uma volta de conversa. Devolve o conteúdo da primeira escolha.

        Raises:
            ChatError: qualquer coisa que impeça a resposta — não configurado,
                rede fora, HTTP de erro, JSON inesperado. Sempre com a causa
                em português, porque essa mensagem vira aviso no job.
        """
        if not self._config.configured:
            raise ChatError(
                "cliente de LLM não configurado: defina `base_url` e "
                "`model` em config/optimizer.yaml"
            )

        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_output_tokens,
            # Nem todo provedor honra este campo; os que honram passam a
            # devolver JSON válido com muito mais frequência, e os que não
            # honram simplesmente o ignoram.
            "response_format": {"type": "json_object"},
        }

        headers = {"Content-Type": "application/json", **self._config.headers}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        request = urllib.request.Request(
            f"{self._config.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self._config.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise ChatError(
                f"o modelo respondeu HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ChatError(
                f"não foi possível falar com o modelo em "
                f"{self._config.base_url}: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise ChatError(
                f"o modelo não respondeu em {self._config.timeout_s:.0f}s"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ChatError("o modelo devolveu uma resposta ilegível") from exc

        try:
            return body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ChatError(
                f"resposta do modelo em formato inesperado: {str(body)[:200]}"
            ) from exc

    def health(self) -> tuple[bool, str | None]:
        """``(dá para usar?, por que não)`` — sem gastar uma geração.

        Verifica só a configuração, e não a rede: esta pergunta é feita a cada
        listagem de métodos, e um timeout de rede a cada abertura de tela
        custaria caro por uma informação que a primeira geração daria de
        qualquer jeito.
        """
        if not self._config.configured:
            return (False, "cliente de LLM não configurado")
        return (True, None)
