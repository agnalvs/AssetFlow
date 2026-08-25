"""Cliente de chat do AssetFlow — um LLM, nenhum fornecedor.

Este pacote existe por causa de uma regra que o projeto leva a sério: nenhuma
parte do AssetFlow pode ficar acoplada a uma tecnologia de IA específica. Vale
para modelos de imagem — é o que a arquitetura de gavetas resolve — e vale
igualmente para modelos de texto.

Por isso o cliente aqui fala ``/chat/completions`` sobre ``urllib`` da
biblioteca padrão, e não o SDK de ninguém. O formato é o denominador comum de
OpenAI, Ollama, LM Studio, OpenRouter, Groq, vLLM e llama.cpp: implementá-lo
uma vez alcança desde um modelo local rodando de graça até um serviço pago, e
trocar de provedor vira uma linha de configuração.

Ele mora fora de ``generation/`` porque não é sobre gerar imagem, e fora de
``pixel/`` porque a ilha Pixel Exact não faz rede, não lê configuração e não
conhece fornecedor. A ilha define o contrato; esta camada o implementa e entra
por injeção no ``bootstrap``.

Quem usa o cliente hoje é o :class:`LLMPixelReviewer`, o revisor do Pixel
Optimizer feito por modelo (plano Optimizer §42). Ele **descreve** problemas
estruturais; corrigir continua sendo do planejador determinístico, atrás da
guarda de paleta e da regra de que otimizar não pode piorar.
"""

from .chat import ChatClient, ChatConfig, ChatError
from .pixel_reviewer import LLMPixelReviewer

__all__ = ["ChatClient", "ChatConfig", "ChatError", "LLMPixelReviewer"]
