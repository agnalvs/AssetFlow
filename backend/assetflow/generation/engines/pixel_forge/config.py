"""Configuração da ponte para o Pixel Forge (plano §65; plano de motores §8.3).

O Pixel Forge é um gerador de sprites em **Rust**, com três modelos de
difusão embutidos, que roda localmente e produz sprites 32×32. O plano de motores §8.3 é
explícito sobre a consequência arquitetural disso: *"o AssetFlow não deve
acoplar backend principal ao runtime Rust"*.

Então a integração é um binário invocado como processo, com o caminho e os
argumentos vindos de ``config/engines.yaml``. Não existe FFI, não existe
biblioteca compilada dentro do venv, e o backend continua subindo em uma
máquina que nunca ouviu falar de Rust.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ....generation.schemas import EngineRuntimeConfig

__all__ = [
    "ADAPTER_VERSION",
    "DEFAULT_CLASS_MAP",
    "DEFAULT_SUBJECT_MAP",
    "FALLBACK_CLASS",
    "NATIVE_SIZE",
    "PixelForgeConfig",
]

#: Versão do adapter — o código desta pasta (plano de motores §18).
ADAPTER_VERSION = "1.0.0"

#: Resolução nativa do projeto (plano de motores §2.3). Não é um limite arbitrário nosso:
#: é o tamanho em que os modelos dele foram treinados, e pedir outro é pedir
#: um upscale disfarçado.
NATIVE_SIZE = 32

#: A classe usada quando nada mais responde. O Pixel Forge exige **uma**
#: classe na linha de comando; mandar vazio é um erro de invocação, não uma
#: geração genérica.
FALLBACK_CLASS = "misc"

#: Tradução padrão de tipo de asset do AssetFlow -> classe do Pixel Forge.
#:
#: Ela é só o **piso**: o vocabulário real depende do modelo que foi treinado,
#: e por isso `options.class_map` no `engines.yaml` sobrescreve chave a chave.
#: Um mapa fixo em código seria uma promessa sobre um modelo que não é nosso.
#:
#: A tradução existe porque os dois vocabulários não coincidem. O AssetFlow
#: pensa em *papel no produto* (prop, tileset, spritesheet); o Pixel Forge, em
#: *o que está desenhado* (weapon, potion, tree). São perguntas diferentes, e
#: é justamente por isso que o **sujeito** costuma responder melhor que o tipo
#: — ver `subject_map`.
DEFAULT_CLASS_MAP: dict[str, str] = {
    "character": "character",
    "prop": "misc",
    "background": "terrain",
    "tile": "terrain",
    "tileset": "terrain",
    "spritesheet": "character",
    "icon": "misc",
    "effect": "effect",
    "ui": "ui",
    "raw": "misc",
}

#: Termos do sujeito que nomeiam uma classe do Pixel Forge melhor do que o
#: tipo do asset. "uma casa de pedra" é um `prop` para o AssetFlow e um
#: `building` para o Pixel Forge — e `building` é a resposta útil.
#:
#: Português e inglês, porque a descrição chega nas duas línguas. Como o mapa
#: acima, é ponto de partida sobrescrevível por `options.subject_map`.
DEFAULT_SUBJECT_MAP: dict[str, str] = {
    "sword": "weapon", "espada": "weapon", "axe": "weapon", "machado": "weapon",
    "bow": "weapon", "arco": "weapon", "shield": "armor", "escudo": "armor",
    "armor": "armor", "armadura": "armor", "helmet": "armor", "capacete": "armor",
    "potion": "potion", "poção": "potion", "pocao": "potion", "elixir": "potion",
    "tree": "tree", "árvore": "tree", "arvore": "tree", "bush": "tree",
    "house": "building", "casa": "building", "castle": "building",
    "castelo": "building", "tower": "building", "torre": "building",
    "chest": "misc", "baú": "misc", "bau": "misc", "barrel": "misc",
    "food": "food", "comida": "food", "bread": "food", "pão": "food",
    "fruit": "food", "fruta": "food", "meat": "food", "carne": "food",
    "enemy": "enemy", "inimigo": "enemy", "slime": "enemy", "goblin": "enemy",
    "monster": "enemy", "monstro": "enemy", "skeleton": "enemy",
    "animal": "animal", "cat": "animal", "gato": "animal", "dog": "animal",
    "cachorro": "animal", "horse": "animal", "cavalo": "animal",
    "pickaxe": "tool", "picareta": "tool", "hammer": "tool", "martelo": "tool",
    "shovel": "tool", "pá": "tool", "tool": "tool", "ferramenta": "tool",
    "cart": "vehicle", "carroça": "vehicle", "boat": "vehicle",
    "barco": "vehicle", "ship": "vehicle", "navio": "vehicle",
}


@dataclass(frozen=True, slots=True)
class PixelForgeConfig:
    """Como invocar o Pixel Forge nesta máquina."""

    #: Caminho do binário. Vazio = gaveta não configurada.
    binary: str = ""
    #: Argumentos com placeholders, aplicados depois do binário.
    args: tuple[str, ...] = ()
    working_dir: str | None = None
    output_glob: str = "*.png"
    output_dir: str | None = None
    process_timeout_s: float = 300.0
    env: dict[str, str] = field(default_factory=dict)
    #: Qual dos modelos do projeto usar, quando a CLI aceitar escolher.
    model_id: str = "pixel-forge"
    #: Tipo de asset -> classe do Pixel Forge, sobrescrevendo o padrão.
    class_map: dict[str, str] = field(default_factory=dict)
    #: Termo do sujeito -> classe do Pixel Forge, sobrescrevendo o padrão.
    subject_map: dict[str, str] = field(default_factory=dict)
    #: A classe usada quando nem sujeito nem tipo respondem.
    fallback_class: str = FALLBACK_CLASS

    @property
    def configured(self) -> bool:
        return bool(self.binary)

    @property
    def command(self) -> tuple[str, ...]:
        return (self.binary, *self.args) if self.binary else ()

    @classmethod
    def from_runtime(cls, config: EngineRuntimeConfig) -> "PixelForgeConfig":
        options: dict[str, Any] = config.options or {}
        raw_args = options.get("args") or ()
        if isinstance(raw_args, str):
            raw_args = [raw_args]

        return cls(
            binary=str(options.get("binary") or config.model.path or ""),
            args=tuple(str(item) for item in raw_args),
            working_dir=options.get("working_dir"),
            output_glob=str(options.get("output_glob", "*.png")),
            output_dir=options.get("output_dir"),
            process_timeout_s=float(options.get("process_timeout_s", 300.0)),
            env={str(k): str(v) for k, v in (options.get("env") or {}).items()},
            model_id=str(config.model.id or "pixel-forge"),
            class_map={
                str(k).lower(): str(v)
                for k, v in (options.get("class_map") or {}).items()
            },
            subject_map={
                str(k).lower(): str(v)
                for k, v in (options.get("subject_map") or {}).items()
            },
            fallback_class=str(options.get("fallback_class") or FALLBACK_CLASS),
        )

    # ------------------------------------------------------------------
    def resolve_class(self, asset_type: str, subject: str) -> str:
        """A classe que vai na linha de comando do Pixel Forge.

        O **sujeito ganha do tipo**, e essa ordem é a decisão inteira: para o
        AssetFlow, "uma casa de pedra" é um `prop`; para o Pixel Forge, é um
        `building`. Perguntar primeiro ao tipo entregaria `misc` — a classe que
        não diz nada — para um pedido que dizia tudo.

        A busca no sujeito é por palavra, e não por substring: `"pá"` dentro de
        `"pássaro"` faria uma ave virar ferramenta.
        """
        subjects = {**DEFAULT_SUBJECT_MAP, **self.subject_map}
        for word in _words(subject):
            found = subjects.get(word)
            if found:
                return found

        classes = {**DEFAULT_CLASS_MAP, **self.class_map}
        return classes.get(asset_type.lower(), self.fallback_class)


def _words(text: str) -> list[str]:
    """As palavras do sujeito, em minúsculas e sem pontuação."""
    return [
        piece
        for piece in re.split(r"[^0-9A-Za-zÀ-ÿ]+", (text or "").lower())
        if piece
    ]
