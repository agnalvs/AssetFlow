"""Como falar com o GPT Image nesta instalação.

A chave **nunca** vem daqui. O que fica na configuração é o *nome da variável
de ambiente* que a guarda — `engines.yaml` é versionado, e uma chave de API em
um arquivo que vai para o repositório é um incidente, não um detalhe.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ....generation.schemas import EngineRuntimeConfig

__all__ = ["ADAPTER_VERSION", "DEFAULT_MODEL", "QUALITY_MAP", "GPTImageConfig"]

#: Versão do adapter — o código desta pasta (plano de motores §18).
ADAPTER_VERSION = "1.0.0"

DEFAULT_MODEL = "gpt-image-2"

#: Qualidade do AssetFlow -> qualidade do provedor.
#:
#: A tradução mora aqui, e não no núcleo, porque `quality` do AssetFlow é uma
#: abstração de produto: outro motor transforma `balanced` em contagem de
#: passos, em resolução ou em nada. O núcleo não pode conhecer `medium`.
QUALITY_MAP: dict[str, str] = {
    "draft": "low",
    "standard": "medium",
    "high": "high",
}


@dataclass(frozen=True, slots=True)
class GPTImageConfig:
    """Configuração de runtime da gaveta."""

    model: str = DEFAULT_MODEL
    base_url: str = "https://api.openai.com/v1"
    #: Nome da **variável de ambiente** que guarda a chave — não a chave.
    api_key_env: str = "OPENAI_API_KEY"
    timeout_s: float = 180.0
    #: `low` relaxa o filtro de conteúdo; `auto` é o padrão do provedor.
    moderation: str = "auto"
    #: Cabeçalhos extras (organização, projeto, proxies corporativos).
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) or None

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)

    def unavailable_reason(self) -> str | None:
        """Por que a gaveta não roda agora, em português; ``None`` se roda."""
        if not self.base_url or not self.model:
            return "GPT Image não configurado: faltam `base_url` ou `model`"
        if not self.api_key:
            return (
                f"GPT Image sem credencial: defina a variável de ambiente "
                f"`{self.api_key_env}`. A chave nunca vai no engines.yaml, que "
                "é versionado."
            )
        return None

    def quality_for(self, quality: str) -> str:
        return QUALITY_MAP.get(quality, "auto")

    @classmethod
    def from_runtime(cls, config: EngineRuntimeConfig) -> GPTImageConfig:
        options: dict[str, Any] = config.options or {}
        return cls(
            model=str(config.model.id or options.get("model") or DEFAULT_MODEL),
            base_url=str(options.get("base_url") or "https://api.openai.com/v1").rstrip("/"),
            api_key_env=str(options.get("api_key_env") or "OPENAI_API_KEY"),
            timeout_s=float(options.get("timeout_s", 180.0)),
            moderation=str(options.get("moderation") or "auto"),
            headers={
                str(key): str(value)
                for key, value in (options.get("headers") or {}).items()
            },
        )
