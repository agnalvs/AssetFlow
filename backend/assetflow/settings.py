"""Configuração do backend (plano §65).

Nada de motor, modelo, device ou precisão fica hardcoded. Tudo vem de:

1. arquivos YAML em ``config/`` (``engines``, ``capabilities``, ``profiles``);
2. variáveis de ambiente com prefixo ``ASSETFLOW_`` (que têm precedência).

O objetivo prático: habilitar/desabilitar uma gaveta, trocar o modelo ou
mudar a ordem de preferência sem tocar em código nem reconstruir imagem.
"""

from __future__ import annotations

import json
import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from .generation.schemas import (
    AssetFlowModel,
    EngineDeviceConfig,
    EngineModelConfig,
    EnginePrecisionConfig,
    EngineRuntimeConfig,
)

__all__ = [
    "StorageSettings",
    "WorkerSettings",
    "ApiSettings",
    "AppEnvironment",
    "Settings",
    "load_settings",
    "engine_runtime_configs",
]

_ENV_PREFIX = "ASSETFLOW_"

_LOG = logging.getLogger("assetflow.settings")
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


class AppEnvironment(str, Enum):
    """Onde o AssetFlow está rodando (plano de correção §6).

    A única coisa que isto decide é se as gavetas de referência — os mocks —
    são registradas, e desde a Fase A do plano do app
    (``PLANO_APP_DESENHISTA.md``) a resposta é: **só nos testes**. O app tem
    um gerador, a desenhista; um mock que gerasse no lugar dela entregaria um
    placeholder a quem achou que pediu arte. Em ``development`` e em
    ``production`` o app registra só as gavetas de produto.

    ``TEST`` não vem de variável de ambiente: ``ASSETFLOW_APP_ENV=test`` é
    recusado por :func:`_app_env`. Ele só existe quando um código o escreve —
    o ``tests/conftest.py`` e o ``scripts/preview_engine.py``, que é
    diagnóstico e liga só a gaveta nomeada.
    """

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"

    @property
    def shows_mock_engines(self) -> bool:
        return self is AppEnvironment.TEST


class StorageSettings(AssetFlowModel):
    """Onde os assets e o histórico são gravados."""

    backend: str = Field(default="local", pattern=r"^(local)$")
    root: str = "data/assets"
    history_file: str = "data/history/generations.jsonl"


class WorkerSettings(AssetFlowModel):
    """Execução dos jobs."""

    #: Sobe o worker dentro do processo da API (bom para dev, ruim para GPU).
    embedded: bool = True
    concurrency: int = Field(default=1, ge=1, le=32)
    job_timeout_s: float = Field(default=900.0, gt=0)
    poll_timeout_s: float = Field(default=0.5, gt=0)
    max_attempts: int = Field(default=2, ge=1, le=10)
    retry_base_delay_s: float = Field(default=1.0, ge=0)
    #: Filas por capacidade (plano §33), ex.: {"text_to_image.pixel": "generation.pixel"}.
    queue_routes: dict[str, str] = Field(default_factory=dict)


class ApiSettings(AssetFlowModel):
    title: str = "AssetFlow Generation API"
    root_path: str = ""
    cors_origins: tuple[str, ...] = ("*",)
    serve_local_assets: bool = True
    #: Endpoints de diagnóstico (`/api/dev/...`). Desligados por padrão: eles
    #: aceitam imagem arbitrária e existem para pesquisa, não para produção
    #: (plano Pixel §78). Ligue com `ASSETFLOW_DEV_ENDPOINTS=1`.
    dev_endpoints: bool = False


class PedidosSettings(AssetFlowModel):
    """A fila de pedidos da tela (Fase B do plano do app).

    A fila mora num SQLite em ``data/``, porque a API e o servidor MCP são
    dois processos, cada um com a sua fila de jobs em memória: só um arquivo
    em disco é visto pelos dois.
    """

    #: O projeto da tela e dos pedidos. Fixo, e não um id do navegador: limpar
    #: o navegador não pode fazer a lista sumir. ``ASSETFLOW_PROJETO_PADRAO``.
    projeto_padrao: str = Field(default="principal", min_length=1)
    #: O arquivo da fila. ``ASSETFLOW_PEDIDOS_DB``.
    arquivo: str = "data/pedidos/pedidos.sqlite3"
    #: Desenhos não aprovados antes de o pedido ir para "falhou".
    #: ``ASSETFLOW_PEDIDOS_TENTATIVAS``.
    tentativas: int = Field(default=3, ge=1, le=10)
    #: Por quantos minutos ``pedidos_pendentes`` reserva um pedido para quem o
    #: pegou. Cada ``desenhar(pedido_id)`` renova a reserva da leva inteira.
    #: ``ASSETFLOW_PEDIDOS_RESERVA_MIN``.
    reserva_min: float = Field(default=30.0, gt=0)
    #: Quanto esperar por outro processo que esteja escrevendo na fila antes
    #: de desistir com erro (``busy_timeout``). ``ASSETFLOW_PEDIDOS_ESPERA_S``.
    espera_s: float = Field(default=5.0, ge=0)
    #: Remendos que o olhar pode pedir num pedido depois de um desenho
    #: aprovado (Fase B2). Um por olhar é da própria forma do fluxo: cada
    #: remendo devolve uma imagem nova, que é um olhar novo.
    #: ``ASSETFLOW_PEDIDOS_REMENDOS``. **Ajuste de custo**: cada remendo a
    #: menos economiza ~650 tokens no pior caso (docs/CUSTO.md).
    remendos: int = Field(default=2, ge=0, le=10)
    #: O modo de conceito dos pedidos que não dizem o seu (lote 1):
    #: ``eu_escolho``, ``claude_escolhe`` ou ``sem_conceito``.
    #: ``ASSETFLOW_CONCEITO``. **Ajuste de custo**: ``sem_conceito`` economiza
    #: ~900 tokens por pedido (docs/CUSTO.md).
    conceito: str = Field(default="eu_escolho", pattern="^(eu_escolho|claude_escolhe|sem_conceito)$")
    #: O editor de pixels da tela (lote 5): a autora troca pixels de um asset
    #: pronto e salva como remendo, sem chamar o Claude. ``ASSETFLOW_EDITOR``
    #: (``0`` desliga). **Ajuste de custo**: cada correção feita ali poupa um
    #: remendo (~1.000 tokens) ou um pedido de ajuste (docs/CUSTO.md).
    editor: bool = True


class AprendizadoSettings(AssetFlowModel):
    """O que o desenho aprende com o uso (Fase B2 do plano do app).

    Lições, opiniões da autora e os exemplos já mostrados ficam num SQLite em
    ``data/`` — são da instalação, não vão ao git —, dividido pela API e pelo
    servidor MCP como a fila de pedidos.
    """

    #: O arquivo. ``ASSETFLOW_APRENDIZADO_DB``.
    arquivo: str = "data/aprendizado/aprendizado.sqlite3"
    #: Liga o exemplo convertido de um sprite CC0 no recorte.
    #: ``ASSETFLOW_EXEMPLO=1`` liga. **Desligado por padrão** desde 2026-11-25:
    #: para personagem vestido, o único exemplo do porte era um corpo-base sem
    #: roupa, e atrapalhou. Volta quando houver pacotes melhores, medido.
    exemplo: bool = False
    #: Liga as lições no recorte. ``ASSETFLOW_LICOES`` (``0`` desliga).
    licoes: bool = True
    #: Quanto pesa uma lição da autora contra uma do Claude, na ordem do recorte.
    #: ``ASSETFLOW_LICOES_PESO_AUTORA``.
    peso_autora: int = Field(default=3, ge=1, le=20)
    #: Quantas lições entram no recorte de um pedido, no máximo.
    max_licoes: int = Field(default=5, ge=0, le=20)
    #: Lista de verificação curta: no primeiro olhar, só os nomes das
    #: perguntas, numa linha, em vez das perguntas inteiras.
    #: ``ASSETFLOW_OLHAR_LISTA_CURTA``. **Ajuste de custo**: ~170 tokens por
    #: pedido (docs/CUSTO.md).
    lista_curta: bool = False
    #: O formato dos comandos opcionais da receita (lotes F1 a F4) só na
    #: primeira resposta de cada conversa; nas seguintes, uma linha com os
    #: nomes, e ``consultar_pedido(..., formato=true)`` o repete.
    #: ``ASSETFLOW_FORMATO_UMA_VEZ`` (``0`` manda sempre). **Ajuste de custo**:
    #: ~600 tokens por consulta depois da primeira (docs/CUSTO.md).
    formato_uma_vez: bool = True
    #: A base por temas (lote 8): a linha ``temas da base`` no recorte e a
    #: ferramenta ``consultar_base(tema)``. ``ASSETFLOW_CONSULTAR_BASE``
    #: (``0`` desliga as duas). Custo: ~30 tokens por pedido na linha; o tema,
    #: ~150 a 300 tokens, só quando o Claude pede.
    consultar_base: bool = True
    #: A ficha de verificação de cada asset concluído (lote F5): uma linha por
    #: regra aplicável, com as respostas do olhar e o cruzamento com as
    #: medidas. ``ASSETFLOW_FICHA`` (``0`` desliga).
    ficha: bool = True
    #: Como ``pedidos.espera_s``: ``busy_timeout`` do SQLite.
    espera_s: float = Field(default=5.0, ge=0)


class BackupSettings(AssetFlowModel):
    """A cópia de segurança de ``backend/data/`` (lote 9)."""

    #: Liga o botão da tela e a rota ``/api/backup``. ``ASSETFLOW_BACKUP``
    #: (``0`` desliga). O comando ``python -m assetflow.backup`` vale sempre.
    ligado: bool = True
    #: Onde as cópias ficam: **fora do repositório** (a cópia recusa uma pasta
    #: dentro dele). ``ASSETFLOW_BACKUP_DIR``.
    pasta: str = "~/AssetFlow-copias"
    #: Leva também os pacotes de referência importados à mão (~13 MB).
    #: ``ASSETFLOW_BACKUP_REFERENCIAS``.
    referencias: bool = True


class BancaSettings(AssetFlowModel):
    """A banca de teste (etapa K1 do plano da base de conhecimento)."""

    #: As rodadas e os votos. ``ASSETFLOW_BANCA_DB``.
    arquivo: str = "data/banca/banca.sqlite3"
    #: O projeto dos desenhos da banca, para não misturar com a galeria.
    projeto: str = Field(default="banca", min_length=1)


class Settings(AssetFlowModel):
    """Configuração completa do backend."""

    #: Ambiente de execução (plano de correção §6). ``ASSETFLOW_APP_ENV``.
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT

    base_dir: Path = _BACKEND_ROOT
    config_dir: Path = _BACKEND_ROOT / "config"
    data_dir: Path = _BACKEND_ROOT / "data"

    storage: StorageSettings = Field(default_factory=StorageSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    pedidos: PedidosSettings = Field(default_factory=PedidosSettings)
    aprendizado: AprendizadoSettings = Field(default_factory=AprendizadoSettings)
    banca: BancaSettings = Field(default_factory=BancaSettings)
    backup: BackupSettings = Field(default_factory=BackupSettings)

    #: Conteúdo bruto dos YAMLs (interpretado pelos respectivos registries).
    engines_config: dict[str, Any] = Field(default_factory=dict)
    capabilities_config: dict[str, Any] = Field(default_factory=dict)
    profiles_config: dict[str, Any] = Field(default_factory=dict)
    #: `pixel_profiles.yaml` — o contrato Pixel Exact de cada profile
    #: (resolução lógica, paleta, alpha, canvas, preview). Plano Pixel §64.
    pixel_profiles_config: dict[str, Any] = Field(default_factory=dict)
    #: `optimizer.yaml` — o estágio que toda geração Pixel atravessa: teto de
    #: iterações, revisor e o interruptor de instalação (plano Optimizer §33,
    #: §42 e §46). Ausente, valem os padrões do próprio Optimizer.
    optimizer_config: dict[str, Any] = Field(default_factory=dict)
    #: `quality.yaml` — limiares de blocos pequenos e cores raras da nota de
    #: qualidade (plano Pixel §60), calibrados pelas referências. Ausente,
    #: valem os do plano, escritos no código.
    quality_config: dict[str, Any] = Field(default_factory=dict)

    @property
    def show_mock_engines(self) -> bool:
        """As gavetas de referência entram nesta instalação? Só em ``TEST``."""
        return self.app_env.shows_mock_engines

    # ------------------------------------------------------------------
    @property
    def asset_taxonomy_dir(self) -> Path:
        """``config/asset_taxonomy/`` — o vocabulário semântico (plano T→J §5).

        É um diretório, e não um arquivo, porque cada tipo de asset tem o seu
        (``prop.yaml``, ``character.yaml``...). Acrescentar um tipo é
        acrescentar um arquivo — sem tocar em código nem nos outros.

        Ausente, o classificador fica mudo e o tipo do profile prevalece: o
        AssetFlow perde a classificação semântica, não a capacidade de gerar.
        """
        return self._resolve(self.config_dir / "asset_taxonomy")

    @property
    def pixel_knowledge_dir(self) -> Path:
        """``config/pixel_knowledge/`` — a base de conhecimento do desenhista.

        Paletas, luz, proporções e moldes (plano desenhista, Fase 3). Ausente,
        a base vem vazia e o recorte de ``consultar_pedido`` sai vazio: o
        AssetFlow perde orientação de desenho, não a capacidade de desenhar.
        """
        return self._resolve(self.config_dir / "pixel_knowledge")

    @property
    def referencias_dir(self) -> Path:
        """``data/referencias/`` — pacotes de pixel art livres, importados à mão.

        Fica em ``data/`` porque é arte de terceiros: não vai para o git.
        Ausente, a linha de referências do recorte some e nada mais muda.
        """
        return self._resolve(self.data_dir / "referencias")

    @property
    def referencias_config(self) -> Path:
        """``config/pixel_knowledge/referencias.yaml`` — quais pacotes estão ativos."""
        return self._resolve(self.config_dir / "pixel_knowledge" / "referencias.yaml")

    @property
    def engine_discovery_paths(self) -> tuple[Path, ...]:
        discovery = self.engines_config.get("discovery") or {}
        paths = discovery.get("paths") or ["assetflow/generation/engines"]
        return tuple(self._resolve(Path(path)) for path in paths)

    @property
    def engine_allowlist(self) -> tuple[str, ...] | None:
        discovery = self.engines_config.get("discovery") or {}
        allowlist = discovery.get("allowlist")
        if allowlist is None:
            return None
        return tuple(str(item) for item in allowlist)

    @property
    def engine_defaults(self) -> dict[str, Any]:
        return dict(self.engines_config.get("defaults") or {})

    @property
    def gerador(self) -> str | None:
        """O gerador do app: a gaveta que desenha os pedidos da tela.

        Vem do ``engines.yaml`` (chave ``gerador``), e não do código — nenhum id
        de motor fica escrito fora das gavetas. Ausente, criar pedido falha
        dizendo isso.
        """
        valor = self.engines_config.get("gerador")
        return str(valor) if valor else None

    @property
    def pedidos_path(self) -> Path:
        """O SQLite da fila de pedidos (``data/pedidos/pedidos.sqlite3``)."""
        return self._resolve(Path(self.pedidos.arquivo))

    @property
    def banca_path(self) -> Path:
        """O SQLite das rodadas e votos da banca (``data/banca/banca.sqlite3``)."""
        return self._resolve(Path(self.banca.arquivo))

    @property
    def banca_config_path(self) -> Path:
        """Os pedidos da banca (``config/banca.yaml``), versionados."""
        return self.config_dir / "banca.yaml"

    @property
    def aprendizado_path(self) -> Path:
        """O SQLite das lições e opiniões (``data/aprendizado/aprendizado.sqlite3``)."""
        return self._resolve(Path(self.aprendizado.arquivo))

    @property
    def storage_root(self) -> Path:
        return self._resolve(Path(self.storage.root))

    @property
    def history_path(self) -> Path:
        return self._resolve(Path(self.storage.history_file))

    def engine_workspace(self, engine_id: str) -> Path:
        return self._resolve(self.data_dir / "engines" / engine_id)

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (self.base_dir / path).resolve()


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"configuração inválida em {path}: raiz deve ser um mapeamento")
    return data


def _env(name: str) -> str | None:
    return os.environ.get(f"{_ENV_PREFIX}{name}")


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(
    *,
    config_dir: Path | str | None = None,
    data_dir: Path | str | None = None,
    base_dir: Path | str | None = None,
) -> Settings:
    """Carrega a configuração de YAML + ambiente.

    Precedência: argumento explícito > variável de ambiente > YAML > padrão.
    """
    base = Path(base_dir or _env("BASE_DIR") or _BACKEND_ROOT).resolve()
    configs = Path(config_dir or _env("CONFIG_DIR") or (base / "config"))
    data = Path(data_dir or _env("DATA_DIR") or (base / "data"))

    engines_config = _read_yaml(configs / "engines.yaml")
    capabilities_config = _read_yaml(configs / "capabilities.yaml")
    profiles_config = _read_yaml(configs / "profiles.yaml")
    pixel_profiles_config = _read_yaml(configs / "pixel_profiles.yaml")
    optimizer_config = _read_yaml(configs / "optimizer.yaml")
    quality_config = _read_yaml(configs / "quality.yaml")

    storage = StorageSettings(
        root=_env("STORAGE_ROOT") or str(data / "assets"),
        history_file=_env("HISTORY_FILE") or str(data / "history" / "generations.jsonl"),
    )

    worker = WorkerSettings(
        embedded=_env_bool("WORKER_EMBEDDED", True),
        concurrency=int(_env("WORKER_CONCURRENCY") or 1),
        job_timeout_s=float(_env("JOB_TIMEOUT_S") or 900.0),
        max_attempts=int(_env("JOB_MAX_ATTEMPTS") or 2),
        queue_routes=_parse_queue_routes(_env("QUEUE_ROUTES")),
    )

    api = ApiSettings(
        title=_env("API_TITLE") or "AssetFlow Generation API",
        root_path=_env("API_ROOT_PATH") or "",
        cors_origins=tuple((_env("CORS_ORIGINS") or "*").split(",")),
        dev_endpoints=_env_bool("DEV_ENDPOINTS", False),
    )

    padrao_pedidos = PedidosSettings()
    pedidos = PedidosSettings(
        projeto_padrao=_env("PROJETO_PADRAO") or padrao_pedidos.projeto_padrao,
        arquivo=_env("PEDIDOS_DB") or str(data / "pedidos" / "pedidos.sqlite3"),
        tentativas=int(_env("PEDIDOS_TENTATIVAS") or padrao_pedidos.tentativas),
        reserva_min=float(_env("PEDIDOS_RESERVA_MIN") or padrao_pedidos.reserva_min),
        espera_s=float(_env("PEDIDOS_ESPERA_S") or padrao_pedidos.espera_s),
        remendos=int(_env("PEDIDOS_REMENDOS") or padrao_pedidos.remendos),
        conceito=_env("CONCEITO") or padrao_pedidos.conceito,
        editor=_env_bool("EDITOR", padrao_pedidos.editor),
    )

    padrao_aprendizado = AprendizadoSettings()
    aprendizado = AprendizadoSettings(
        arquivo=_env("APRENDIZADO_DB") or str(data / "aprendizado" / "aprendizado.sqlite3"),
        exemplo=_env_bool("EXEMPLO", padrao_aprendizado.exemplo),
        licoes=_env_bool("LICOES", padrao_aprendizado.licoes),
        peso_autora=int(_env("LICOES_PESO_AUTORA") or padrao_aprendizado.peso_autora),
        lista_curta=_env_bool("OLHAR_LISTA_CURTA", padrao_aprendizado.lista_curta),
        formato_uma_vez=_env_bool("FORMATO_UMA_VEZ", padrao_aprendizado.formato_uma_vez),
        consultar_base=_env_bool("CONSULTAR_BASE", padrao_aprendizado.consultar_base),
        ficha=_env_bool("FICHA", padrao_aprendizado.ficha),
        espera_s=float(_env("PEDIDOS_ESPERA_S") or padrao_aprendizado.espera_s),
    )

    return Settings(
        app_env=_app_env(),
        base_dir=base,
        config_dir=configs,
        data_dir=data,
        storage=storage,
        worker=worker,
        api=api,
        pedidos=pedidos,
        aprendizado=aprendizado,
        banca=BancaSettings(
            arquivo=_env("BANCA_DB") or str(data / "banca" / "banca.sqlite3"),
        ),
        backup=BackupSettings(
            ligado=_env_bool("BACKUP", True),
            pasta=_env("BACKUP_DIR") or BackupSettings().pasta,
            referencias=_env_bool("BACKUP_REFERENCIAS", True),
        ),
        engines_config=engines_config,
        capabilities_config=capabilities_config,
        profiles_config=profiles_config,
        pixel_profiles_config=pixel_profiles_config,
        optimizer_config=optimizer_config,
        quality_config=quality_config,
    )


def _app_env() -> AppEnvironment:
    """Lê ``ASSETFLOW_APP_ENV``, tolerando valor desconhecido.

    Um valor errado cai em ``development`` **e** avisa. ``test`` também é
    recusado: é o único ambiente que registra os mocks, e ele não pode ser
    ligado por uma variável esquecida no terminal — só por código de teste.
    """
    raw = (_env("APP_ENV") or "").strip().lower()
    if not raw:
        return AppEnvironment.DEVELOPMENT
    validos = (AppEnvironment.DEVELOPMENT, AppEnvironment.PRODUCTION)
    try:
        ambiente = AppEnvironment(raw)
    except ValueError:
        ambiente = None
    if ambiente not in validos:
        _LOG.warning(
            "ASSETFLOW_APP_ENV=%r não é aceito; usando 'development'. "
            "Valores válidos: %s",
            raw,
            ", ".join(item.value for item in validos),
        )
        return AppEnvironment.DEVELOPMENT
    return ambiente


def _parse_queue_routes(raw: str | None) -> dict[str, str]:
    """``"text_to_image.pixel=generation.pixel,..."`` -> dict."""
    if not raw:
        return {}
    routes: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        routes[key.strip()] = value.strip()
    return routes


def engine_runtime_configs(settings: Settings) -> dict[str, EngineRuntimeConfig]:
    """Constrói a configuração de runtime de cada gaveta.

    A habilitação pode vir do ambiente::

        ASSETFLOW_ENGINES_ENABLED="mock-pixel-alt-v1"
        ASSETFLOW_ENGINES_DISABLED="mock-image-v1"

    E as **opções** da gaveta também, como um objeto JSON por motor::

        ASSETFLOW_ENGINE_MOCK_IMAGE_V1_OPTIONS={"simulated_latency_ms": 0}

    O nome sai do id da gaveta em maiúsculas, com ``-`` e ``.`` virando ``_``.

    Isto não é conveniência: é o que torna possível ajustar uma gaveta à
    máquina **sem editar `engines.yaml`**. Caminhos de executável, pastas e
    limites mudam de máquina para máquina — mas `engines.yaml` é versionado e
    compartilhado. Sem esta porta, cada ajuste exigiria escrever um caminho
    absoluto em um arquivo que vai para o repositório, e todo `git pull`
    viraria um conflito (ou, pior, o caminho de outra pessoa entraria no seu
    ambiente).

    O merge é **raso e por chave**: o que o ambiente disser substitui aquela
    chave, e o resto do bloco do YAML continua valendo. É o que permite
    mudar uma opção sem ter de repetir as outras.
    """
    forced_enabled = {
        item.strip() for item in (_env("ENGINES_ENABLED") or "").split(",") if item.strip()
    }
    forced_disabled = {
        item.strip() for item in (_env("ENGINES_DISABLED") or "").split(",") if item.strip()
    }

    configs: dict[str, EngineRuntimeConfig] = {}
    for engine_id, raw in (settings.engines_config.get("engines") or {}).items():
        raw = raw or {}
        enabled = bool(raw.get("enabled", False))
        if engine_id in forced_enabled:
            enabled = True
        if engine_id in forced_disabled:
            enabled = False

        timeouts = raw.get("timeouts") or {}
        configs[engine_id] = EngineRuntimeConfig(
            engine_id=engine_id,
            enabled=enabled,
            model=EngineModelConfig.model_validate(raw.get("model") or {}),
            device=EngineDeviceConfig.model_validate(raw.get("device") or {}),
            precision=EnginePrecisionConfig.model_validate(raw.get("precision") or {}),
            runtime=dict(raw.get("runtime") or {}),
            options={**(raw.get("options") or {}), **_engine_options_env(engine_id)},
            workspace_dir=str(settings.engine_workspace(engine_id)),
            timeout_s=_optional_float(timeouts.get("timeout_s")),
            load_timeout_s=_optional_float(timeouts.get("load_timeout_s")),
        )
    return configs


def _engine_options_env(engine_id: str) -> dict[str, Any]:
    """As opções que o ambiente sobrescreve para esta gaveta.

    JSON inválido é **ignorado com aviso**, e não derruba o boot: uma aspa a
    menos em uma variável de ambiente não pode impedir o sistema de subir. Mas
    também não pode passar em silêncio — quem escreveu a variável precisa
    saber que ela não teve efeito, senão vai passar a tarde procurando o motivo
    de o motor continuar dizendo "não configurado".
    """
    suffix = engine_id.upper().replace("-", "_").replace(".", "_")
    raw = _env(f"ENGINE_{suffix}_OPTIONS")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        _LOG.warning(
            "%sENGINE_%s_OPTIONS não é JSON válido (%s); as opções do "
            "engines.yaml continuam valendo",
            _ENV_PREFIX,
            suffix,
            exc,
        )
        return {}
    if not isinstance(parsed, dict):
        _LOG.warning(
            "%sENGINE_%s_OPTIONS precisa ser um objeto JSON, e veio %s",
            _ENV_PREFIX,
            suffix,
            type(parsed).__name__,
        )
        return {}
    return parsed


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
