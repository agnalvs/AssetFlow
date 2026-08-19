"""PixelOutputSpec — o contrato central do Pixel Exact (plano Pixel §10).

Este é o **único** objeto que o PixelPostProcessor recebe além da imagem. Ele
descreve o que o arquivo final precisa ser, e nunca como ele foi gerado:

    imagem + PixelOutputSpec  ->  imagem Pixel Exact + ProcessingReport

Nenhum campo aqui cita motor, checkpoint, `engine_id` ou biblioteca — é a
regra de desacoplamento do plano Pixel §5 escrita em código. Trocar o motor
que produziu a imagem não muda uma linha deste arquivo.

Os valores concretos (64, 16, 128) moram em ``config/pixel_profiles.yaml``,
nunca espalhados pelo código (plano Pixel §64).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, model_validator

from ...generation.schemas import AssetFlowModel

__all__ = [
    "AlphaSpec",
    "AttemptsSpec",
    "BackgroundSpec",
    "CanvasSpec",
    "CleanupSpec",
    "DitheringSpec",
    "HexColor",
    "LogicalReductionSpec",
    "LogicalSize",
    "PaletteSpec",
    "PixelOutputSpec",
    "PreviewSpec",
    "ValidationSpec",
    "normalize_hex",
]


def normalize_hex(value: Any) -> Any:
    """Normaliza uma cor hexadecimal para a forma ``#rrggbb`` minúscula.

    Aceita ``#FFF``, ``ffffff`` e ``#rrggbbaa`` (o alpha é descartado — no
    Pixel Exact ele é binário e mora no canal alpha, não na paleta).
    Normalizar na entrada evita que ``#FFFFFF`` e ``#ffffff`` contem como duas
    cores diferentes ao conferir uma paleta LOCKED.
    """
    if not isinstance(value, str):
        return value
    raw = value.strip().lstrip("#").lower()
    if len(raw) == 3:
        raw = "".join(char * 2 for char in raw)
    if len(raw) == 8:
        raw = raw[:6]
    if len(raw) != 6 or any(char not in "0123456789abcdef" for char in raw):
        raise ValueError(f"cor hexadecimal inválida: {value!r}")
    return f"#{raw}"


#: Cor hexadecimal normalizada (``#rrggbb``, minúscula).
HexColor = Annotated[str, BeforeValidator(normalize_hex)]


class LogicalSize(AssetFlowModel):
    """A resolução real do arquivo final — a regra de ouro nº 1.

    Um asset 64×64 é um PNG de 64×64 pixels, não um PNG de 512×512 com
    quadradinhos desenhados (plano Pixel §3 e §103).
    """

    width: int = Field(ge=1, le=1024)
    height: int = Field(ge=1, le=1024)

    @property
    def as_tuple(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def pixels(self) -> int:
        return self.width * self.height


class BackgroundSpec(AssetFlowModel):
    """O que existe atrás do sprite."""

    mode: Literal["transparent", "solid"] = "transparent"
    color: HexColor = "#000000"


class AlphaSpec(AssetFlowModel):
    """Regra de transparência (plano Pixel §21 a §24).

    ``binary`` é o único modo do Pixel Exact 1.0: alpha só pode ser 0 ou 255.
    O modo ``limited`` (0/85/170/255) está previsto no plano §24 para efeitos
    especiais e **não** pertence ao perfil estrito — por isso não existe aqui.
    """

    mode: Literal["binary"] = "binary"
    threshold: int = Field(default=128, ge=1, le=255)

    @property
    def allowed_values(self) -> tuple[int, ...]:
        return (0, 255)


class PaletteSpec(AssetFlowModel):
    """Os três modos de paleta do plano Pixel §11.

    ``max_colors`` (AUTO)
        O AssetFlow deriva uma paleta de N cores da própria imagem.
    ``locked`` (LOCKED)
        Só as cores informadas podem sobreviver.
    ``project_palette`` (PROJECT)
        Uma paleta nomeada do projeto — resolvida para ``colors`` antes de
        chegar ao quantizador, para manter personagem/inimigo/tile coerentes.
    """

    mode: Literal["max_colors", "locked", "project_palette"] = "max_colors"
    max_colors: int | None = Field(default=16, ge=1, le=256)
    colors: tuple[HexColor, ...] = ()
    palette_id: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> PaletteSpec:
        if self.mode == "locked" and not self.colors:
            raise ValueError("paleta 'locked' exige a lista 'colors'")
        if self.mode == "project_palette" and not self.palette_id:
            raise ValueError("paleta 'project_palette' exige 'palette_id'")
        if self.mode == "max_colors" and not self.max_colors:
            raise ValueError("paleta 'max_colors' exige 'max_colors'")
        return self

    @property
    def effective_limit(self) -> int | None:
        """Quantidade máxima de cores que o asset pode ter."""
        if self.mode == "locked":
            return len(set(self.colors))
        return self.max_colors

    @property
    def is_locked(self) -> bool:
        return self.mode in ("locked", "project_palette")


class DitheringSpec(AssetFlowModel):
    """Dithering é escolha artística, não correção técnica (plano Pixel §26)."""

    enabled: bool = False
    method: Literal["floyd_steinberg"] = "floyd_steinberg"


class CanvasSpec(AssetFlowModel):
    """Como a composição bruta chega ao aspect ratio lógico (plano Pixel §13/§14).

    Nunca esticar 1024×768 para 64×64: o personagem sairia achatado. Os modos
    são explícitos justamente para que a deformação nunca seja acidental.

    ``contain``
        Reduz mantendo o aspect e preenche a sobra (padrão para personagem).
    ``cover``
        Reduz mantendo o aspect até cobrir o alvo e descarta o excedente.
    ``center_crop``
        Corta o centro no aspect alvo; a redução em si fica para o estágio
        seguinte, que é quem sabe reduzir sem borrar.
    ``transparent_pad``
        Não reduz nada: centraliza a imagem no canvas alvo e preenche o resto.
    ``stretch``
        Deforma. Existe apenas para casos em que isso é intencional (tiles).
    """

    mode: Literal["contain", "cover", "center_crop", "transparent_pad", "stretch"] = "contain"
    #: Preenchimento usado por ``contain``/``transparent_pad``.
    pad: Literal["transparent", "solid"] = "transparent"
    pad_color: HexColor = "#000000"
    #: Recorta a caixa do conteúdo não transparente antes de encaixar.
    trim_transparent: bool = False


class LogicalReductionSpec(AssetFlowModel):
    """Como a imagem grande vira a imagem lógica (plano Pixel §15 a §19).

    ``box_then_quantize``
        Padrão. Média de área (``BOX``) e só depois quantização de paleta.
        Nearest ao **reduzir** descartaria informação demais (§16).
    ``block_vote``
        Para fontes que já vêm em blocos: cada pixel lógico é decidido por
        votação dentro do bloco de origem correspondente (§18).
    """

    method: Literal["box_then_quantize", "block_vote"] = "box_then_quantize"
    #: Estatística usada pelo ``block_vote``.
    statistic: Literal["dominant", "median"] = "dominant"
    #: Quantos níveis por canal a votação usa para agrupar cores parecidas.
    vote_bins: int = Field(default=16, ge=2, le=256)


class CleanupSpec(AssetFlowModel):
    """Limpeza conservadora (plano Pixel §29 a §31).

    ``aggressive`` é reservado para pesquisa futura e por isso não existe
    neste enum: um pixel isolado pode ser um olho, um brilho ou a ponta de
    uma espada, e o plano §106 proíbe destruí-lo para melhorar uma nota.
    """

    mode: Literal["off", "conservative"] = "conservative"
    #: Um pixel só é corrigido se TODOS os vizinhos válidos concordarem e a
    #: sua cor for rara o bastante para não ser detalhe intencional.
    max_rare_color_ratio: float = Field(default=0.0015, ge=0.0, le=1.0)
    #: Pixels do contorno do sprite nunca são tocados.
    protect_outline: bool = True


class PreviewSpec(AssetFlowModel):
    """Ampliação só para visualização (plano Pixel §34, §80 e §81).

    A escala é inteira de propósito: ``scale(7.8125)`` produz linhas de pixel
    com larguras diferentes e o sprite parece defeituoso.
    """

    enabled: bool = True
    scale: int = Field(default=8, ge=1, le=32)


class ValidationSpec(AssetFlowModel):
    """Quais requisitos são obrigatórios neste profile (plano Pixel §39 a §45)."""

    require_exact_dimensions: bool = True
    require_binary_alpha: bool = True
    require_palette_limit: bool = True
    require_locked_palette: bool = True
    require_non_empty: bool = True
    #: Mínimo de pixels opacos para a imagem não ser considerada vazia (§44).
    min_foreground_pixels: int = Field(default=1, ge=1)
    min_foreground_ratio: float = Field(default=0.002, ge=0.0, le=1.0)
    #: Personagem encostando na borda: ignorar, avisar ou reprovar (§45).
    boundary_touch: Literal["ignore", "warn", "fail"] = "warn"
    #: Faixa saudável de ocupação do canvas (§53). Fora dela, aviso.
    min_occupancy: float = Field(default=0.05, ge=0.0, le=1.0)
    max_occupancy: float = Field(default=0.95, ge=0.0, le=1.0)
    #: Nota mínima para APPROVED em vez de QUALITY_WARNING (plano Pixel §60).
    #: Valor experimental por decisão do plano — por isso é configuração.
    quality_threshold: int = Field(default=70, ge=0, le=100)

    @model_validator(mode="after")
    def _validate(self) -> ValidationSpec:
        if self.min_occupancy > self.max_occupancy:
            raise ValueError("min_occupancy não pode ser maior que max_occupancy")
        return self


class AttemptsSpec(AssetFlowModel):
    """Tetos contra loop infinito (plano Pixel §61)."""

    #: Passagens do PixelPostProcessor sobre a mesma imagem bruta. A segunda
    #: só acontece com um spec endurecido, e só quando a falha tem correção
    #: conhecida — repetir às cegas queimaria a tentativa (ver ``service.py``).
    max_processing_attempts: int = Field(default=2, ge=1, le=5)
    #: Teto de **novas gerações** (voltar ao motor) por asset reprovado. O
    #: plano §61 trata isso como um "futuramente": a versão 1.0 não regenera,
    #: e o campo existe para que o limite já esteja declarado no contrato
    #: quando o job passar a poder pedir outra imagem.
    max_regeneration_attempts: int = Field(default=1, ge=0, le=3)


class PixelOutputSpec(AssetFlowModel):
    """Contrato completo de saída de um asset Pixel Art.

    Exemplo mínimo::

        PixelOutputSpec(logical_size={"width": 64, "height": 64})

    ``id``/``version`` acompanham todos os relatórios: dois benchmarks só são
    comparáveis se tiverem sido produzidos pelo mesmo profile (§76).
    """

    id: str = "inline"
    version: str = "1.0.0"
    mode: Literal["pixel_exact"] = "pixel_exact"

    logical_size: LogicalSize
    background: BackgroundSpec = Field(default_factory=BackgroundSpec)
    alpha: AlphaSpec = Field(default_factory=AlphaSpec)
    palette: PaletteSpec = Field(default_factory=PaletteSpec)
    dithering: DitheringSpec = Field(default_factory=DitheringSpec)
    canvas: CanvasSpec = Field(default_factory=CanvasSpec)
    logical_reduction: LogicalReductionSpec = Field(default_factory=LogicalReductionSpec)
    cleanup: CleanupSpec = Field(default_factory=CleanupSpec)
    preview: PreviewSpec = Field(default_factory=PreviewSpec)
    validation: ValidationSpec = Field(default_factory=ValidationSpec)
    attempts: AttemptsSpec = Field(default_factory=AttemptsSpec)

    #: Espaço livre do profile (display_name, notas). Nunca lido pelos estágios.
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    @property
    def target_size(self) -> tuple[int, int]:
        return self.logical_size.as_tuple

    @property
    def max_colors(self) -> int | None:
        return self.palette.effective_limit

    @property
    def preview_size(self) -> tuple[int, int]:
        scale = self.preview.scale
        return (self.logical_size.width * scale, self.logical_size.height * scale)

    def with_palette_colors(self, colors: tuple[str, ...]) -> PixelOutputSpec:
        """Resolve uma paleta PROJECT para uma paleta LOCKED concreta."""
        return self.model_copy(
            update={
                "palette": self.palette.model_copy(
                    update={"mode": "locked", "colors": tuple(colors)}
                )
            }
        )
