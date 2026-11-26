"""Pacotes de referência: manifesto, licença, partes e a lista de ativos.

Um pacote é uma pasta em ``data/referencias/<id>/`` com os arquivos como
vieram (``original/``), o que o medidor extraiu (``medidas.json``) e o
``manifesto.yaml`` escrito pelo importador. A lista do que vale como
referência do projeto mora em ``config/pixel_knowledge/referencias.yaml``.

Licença decide a coleção: só ``CC0-1.0`` entra na **principal**. Qualquer
outra entra em ``atribuicao``, marcada ``attribution_required``, e fica fora
do recorte até alguém aceitar a atribuição na lista de ativos.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..generation.schemas import AssetType
from ..generation.schemas.resolved_spec import BodyType

__all__ = [
    "LICENCA_PRINCIPAL",
    "Ativo",
    "ConfiguracaoDeReferencias",
    "ConfiguracaoDoOlho",
    "Manifesto",
    "Parte",
    "ReferenciaInvalida",
    "ler_configuracao",
    "ler_manifesto",
    "ler_quadro",
    "normalizar_licenca",
]

LICENCA_PRINCIPAL = "CC0-1.0"

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_QUADRO = re.compile(r"^([1-9][0-9]{0,3})x([1-9][0-9]{0,3})$")
_TIPOS = {tipo.value for tipo in AssetType}
_CORPOS = {corpo.value for corpo in BodyType if corpo is not BodyType.UNKNOWN}


class ReferenciaInvalida(ValueError):
    """Pacote, manifesto ou configuração fora do formato; a mensagem diz o quê."""


def normalizar_licenca(licenca: str) -> str:
    """``cc0``, ``CC0 1.0`` e ``CC0-1.0`` são a mesma licença; o resto fica como veio."""
    texto = licenca.strip()
    if re.fullmatch(r"(?i)cc0([ -]?1\.0)?", texto):
        return LICENCA_PRINCIPAL
    return texto


def ler_quadro(texto: str | None, onde: str) -> tuple[int, int] | None:
    if not texto:
        return None
    casou = _QUADRO.match(str(texto).strip().lower())
    if not casou:
        raise ReferenciaInvalida(f"{onde}: quadro é \"LxA\", como \"16x16\" ({texto!r})")
    return int(casou.group(1)), int(casou.group(2))


# ---------------------------------------------------------------------------
# Partes
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Parte:
    """Um pedaço do pacote: os arquivos que casam com ``padrao`` e o que eles são.

    O padrão é um glob sobre o caminho relativo à raiz do pacote, com ``/``:
    ``*`` não atravessa pasta, ``**`` atravessa. Sem diferença de maiúsculas.
    """

    padrao: str
    tipo: str
    corpo: str | None = None
    #: Grade das folhas desta parte, quando conhecida (``--quadro`` ou o nome).
    quadro: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if not self.padrao.strip():
            raise ReferenciaInvalida("parte sem padrão")
        if self.tipo not in _TIPOS:
            raise ReferenciaInvalida(
                f"parte '{self.padrao}': tipo '{self.tipo}' desconhecido ({', '.join(sorted(_TIPOS))})"
            )
        if self.corpo is not None and self.corpo not in _CORPOS:
            raise ReferenciaInvalida(
                f"parte '{self.padrao}': corpo '{self.corpo}' desconhecido ({', '.join(sorted(_CORPOS))})"
            )

    def casa(self, caminho: str) -> bool:
        return _glob(self.padrao).fullmatch(caminho) is not None

    @classmethod
    def de_texto(cls, texto: str) -> Parte:
        """``PADRAO:TIPO[:CORPO][:QUADRO]``, como no ``--parte`` do importador."""
        pedacos = texto.split(":")
        if len(pedacos) < 2 or len(pedacos) > 4:
            raise ReferenciaInvalida(
                f"--parte '{texto}': use PADRAO:TIPO[:CORPO][:QUADRO], como "
                "'Personagens/**:character:humanoid:16x16'"
            )
        padrao, tipo, *resto = pedacos
        # `PADRAO:tile:16x16` também vale: um terceiro campo LxA é o quadro.
        if len(resto) == 1 and _QUADRO.match(resto[0].strip().lower()):
            resto = ["", resto[0]]
        corpo = resto[0] if resto and resto[0] else None
        quadro = ler_quadro(resto[1], f"--parte '{texto}'") if len(resto) > 1 else None
        return cls(padrao=padrao.strip(), tipo=tipo.strip(), corpo=corpo, quadro=quadro)

    def como_dict(self) -> dict[str, Any]:
        dados: dict[str, Any] = {"padrao": self.padrao, "tipo": self.tipo}
        if self.corpo:
            dados["corpo"] = self.corpo
        if self.quadro:
            dados["quadro"] = f"{self.quadro[0]}x{self.quadro[1]}"
        return dados


def _glob(padrao: str) -> re.Pattern[str]:
    partes: list[str] = []
    i = 0
    while i < len(padrao):
        if padrao.startswith("**/", i):
            partes.append("(?:.*/)?")
            i += 3
        elif padrao.startswith("**", i):
            partes.append(".*")
            i += 2
        elif padrao[i] == "*":
            partes.append("[^/]*")
            i += 1
        elif padrao[i] == "?":
            partes.append("[^/]")
            i += 1
        else:
            partes.append(re.escape(padrao[i]))
            i += 1
    return re.compile("".join(partes), re.IGNORECASE)


# ---------------------------------------------------------------------------
# Manifesto
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Manifesto:
    """O que se sabe de um pacote além dos pixels: de onde veio e sob qual licença."""

    id: str
    nome: str
    source_url: str
    autor: str
    license_id: str
    license_url: str
    license_verified_at: str
    partes: tuple[Parte, ...]
    observacoes: str = ""
    importado_em: str = ""
    origem: str = ""
    origem_sha256: str = ""
    #: Globs (mesma regra das partes) de arquivos que não entram, em parte
    #: nenhuma — retratos, sprites "na mão" e afins que casam com um padrão
    #: largo como ``Monster/**``. Valem na importação e na medição.
    excluir: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _ID.match(self.id):
            raise ReferenciaInvalida(
                f"pacote '{self.id}': id em minúsculas, números e hífen, como 'ninja-adventure'"
            )
        for campo in ("source_url", "autor", "license_id", "license_url", "license_verified_at"):
            if not str(getattr(self, campo) or "").strip():
                raise ReferenciaInvalida(f"pacote '{self.id}': falta {campo}")
        if not self.partes:
            raise ReferenciaInvalida(f"pacote '{self.id}': nenhuma parte declarada")

    @property
    def colecao(self) -> str:
        return "principal" if self.license_id == LICENCA_PRINCIPAL else "atribuicao"

    @property
    def attribution_required(self) -> bool:
        return self.colecao != "principal"

    def excluido(self, caminho: str) -> bool:
        return any(_glob(padrao).fullmatch(caminho) for padrao in self.excluir)

    def parte_de(self, caminho: str) -> Parte | None:
        """A primeira parte que casa com o caminho; a ordem do manifesto manda.

        Arquivo que casa com ``excluir`` não tem parte, qualquer que seja ela.
        """
        if self.excluido(caminho):
            return None
        return next((parte for parte in self.partes if parte.casa(caminho)), None)

    def como_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "source_url": self.source_url,
            "autor": self.autor,
            "license_id": self.license_id,
            "license_url": self.license_url,
            "license_verified_at": self.license_verified_at,
            "colecao": self.colecao,
            "attribution_required": self.attribution_required,
            "partes": [parte.como_dict() for parte in self.partes],
            "excluir": list(self.excluir),
            "observacoes": self.observacoes,
            "importado_em": self.importado_em,
            "origem": self.origem,
            "origem_sha256": self.origem_sha256,
        }

    def gravar(self, pasta: Path) -> Path:
        caminho = pasta / "manifesto.yaml"
        cabecalho = (
            "# Escrito pelo importador (python -m assetflow.referencias importar).\n"
            "# `colecao` e `attribution_required` saem de `license_id`: só CC0-1.0\n"
            "# entra na coleção principal.\n"
        )
        corpo = yaml.safe_dump(self.como_dict(), allow_unicode=True, sort_keys=False)
        caminho.write_text(cabecalho + corpo, encoding="utf-8")
        return caminho


def ler_manifesto(pasta: Path) -> Manifesto:
    caminho = pasta / "manifesto.yaml"
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ReferenciaInvalida(f"{caminho}: {exc}") from exc
    if not isinstance(dados, Mapping):
        raise ReferenciaInvalida(f"{caminho}: a raiz não é um mapeamento")
    partes = []
    for i, bruta in enumerate(dados.get("partes") or []):
        if not isinstance(bruta, Mapping):
            raise ReferenciaInvalida(f"{caminho}: partes[{i}] não é um mapeamento")
        partes.append(
            Parte(
                padrao=str(bruta.get("padrao") or ""),
                tipo=str(bruta.get("tipo") or ""),
                corpo=bruta.get("corpo") or None,
                quadro=ler_quadro(bruta.get("quadro"), f"{caminho}: partes[{i}]"),
            )
        )
    return Manifesto(
        id=str(dados.get("id") or ""),
        nome=str(dados.get("nome") or dados.get("id") or ""),
        source_url=str(dados.get("source_url") or ""),
        autor=str(dados.get("autor") or ""),
        license_id=normalizar_licenca(str(dados.get("license_id") or "")),
        license_url=str(dados.get("license_url") or ""),
        license_verified_at=str(dados.get("license_verified_at") or ""),
        partes=tuple(partes),
        observacoes=str(dados.get("observacoes") or ""),
        importado_em=str(dados.get("importado_em") or ""),
        origem=str(dados.get("origem") or ""),
        origem_sha256=str(dados.get("origem_sha256") or ""),
        excluir=_padroes(dados.get("excluir"), f"{caminho}: excluir"),
    )


def _padroes(bruto: Any, onde: str) -> tuple[str, ...]:
    if bruto is None:
        return ()
    if not isinstance(bruto, list) or not all(isinstance(p, str) and p.strip() for p in bruto):
        raise ReferenciaInvalida(f"{onde}: lista de padrões, como [\"**/Faceset.png\"]")
    return tuple(p.strip() for p in bruto)


# ---------------------------------------------------------------------------
# Configuração do projeto: quais pacotes estão ativos, e a faixa de porte
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Ativo:
    pacote: str
    #: Pacote fora da coleção principal só entra com este aceite explícito.
    aceitar_atribuicao: bool = False


@dataclass(frozen=True, slots=True)
class ConfiguracaoDoOlho:
    """Os limiares do olho do app (Fase B2). Todos ``a_calibrar``.

    ``None`` em um campo desliga só aquela verificação: sem configuração, o
    olho não inventa número.
    """

    #: Fora de [p_baixo, p_alto] das referências é desvio.
    p_baixo: float | None = None
    p_alto: float | None = None
    #: Partes vizinhas (camadas da receita) com ΔL* abaixo disto têm o mesmo valor.
    contraste_minimo: float | None = None
    #: IoU da silhueta com a do exemplo mostrado, a partir do qual o desenho o repete.
    iou_copia: float | None = None
    #: Por tipo de asset: o máximo de cantos em L, dobras e degraus fora de
    #: progressão por 100 px do contorno escuro (lote F1). Tipo ausente, sem
    #: comparação.
    linha: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfiguracaoDeReferencias:
    ativos: tuple[Ativo, ...] = ()
    #: Referências de "porte parecido": altura do conteúdo dentro de
    #: altura do corpo × (1 ± faixa). ``None`` = sem configuração, sem a parte.
    faixa_altura: float | None = None
    #: Menos quadros que isto numa parte da linha, e ela some.
    minimo_de_quadros: int | None = None
    #: Pacote com menos quadros que isto numa parte sai dela: com peso igual
    #: por pacote, um quadro solto pesaria como centenas. ``None`` = sem filtro.
    minimo_por_pacote: int | None = None
    #: Menos pacotes que isto numa parte (depois do filtro acima), e ela some
    #: da linha e do ``ver_referencia``; o ``calibrar`` a mostra marcada.
    minimo_de_pacotes: int | None = None
    olho: ConfiguracaoDoOlho = field(default_factory=ConfiguracaoDoOlho)
    problemas: tuple[str, ...] = field(default=())


def ler_configuracao(caminho: Path) -> ConfiguracaoDeReferencias:
    """Lê ``config/pixel_knowledge/referencias.yaml``. Ausente, nada está ativo."""
    if not caminho.is_file():
        return ConfiguracaoDeReferencias()
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return ConfiguracaoDeReferencias(problemas=(f"{caminho.name}: {exc}",))
    if not isinstance(dados, Mapping):
        return ConfiguracaoDeReferencias(problemas=(f"{caminho.name}: a raiz não é um mapeamento",))

    problemas: list[str] = []
    estranhas = sorted(str(chave) for chave in dados if chave not in {"ativos", "porte", "olho"})
    if estranhas:
        problemas.append(f"{caminho.name}: chave desconhecida ({', '.join(estranhas)})")

    ativos: list[Ativo] = []
    for item in dados.get("ativos") or []:
        if isinstance(item, str):
            ativos.append(Ativo(pacote=item))
        elif isinstance(item, Mapping) and len(item) == 1:
            (pacote, opcoes), = item.items()
            aceite = bool((opcoes or {}).get("aceitar_atribuicao", False)) if isinstance(opcoes, Mapping) else False
            ativos.append(Ativo(pacote=str(pacote), aceitar_atribuicao=aceite))
        else:
            problemas.append(f"{caminho.name}: item de ativos fora do formato ({item!r})")

    porte = dados.get("porte") or {}
    faixa = _numero_a_calibrar(porte.get("faixa_altura"), "porte.faixa_altura", problemas)
    minimo = _numero_a_calibrar(porte.get("minimo_de_quadros"), "porte.minimo_de_quadros", problemas)
    por_pacote = _inteiro_positivo(porte, "minimo_por_pacote", problemas)
    de_pacotes = _inteiro_positivo(porte, "minimo_de_pacotes", problemas)
    if faixa is not None and not 0 < faixa < 1:
        problemas.append("porte.faixa_altura: fração entre 0 e 1, como 0.2")
        faixa = None
    olho = _olho(dados.get("olho") or {}, problemas)
    return ConfiguracaoDeReferencias(
        ativos=tuple(ativos),
        faixa_altura=faixa,
        minimo_de_quadros=int(minimo) if minimo is not None else None,
        minimo_por_pacote=por_pacote,
        minimo_de_pacotes=de_pacotes,
        olho=olho,
        problemas=tuple(problemas),
    )


def _olho(bruto: Any, problemas: list[str]) -> ConfiguracaoDoOlho:
    if not isinstance(bruto, Mapping):
        problemas.append("olho: a seção é um mapeamento")
        return ConfiguracaoDoOlho()
    valores: dict[str, float | None] = {}
    for chave, minimo, maximo in (
        ("p_baixo", 0.0, 0.5),
        ("p_alto", 0.5, 1.0),
        ("contraste_minimo", 0.0, 100.0),
        ("iou_copia", 0.0, 1.0),
    ):
        valor = _numero_a_calibrar(bruto.get(chave), f"olho.{chave}", problemas)
        if valor is not None and not minimo <= valor <= maximo:
            problemas.append(f"olho.{chave}: entre {minimo:g} e {maximo:g}")
            valor = None
        valores[chave] = valor
    return ConfiguracaoDoOlho(**valores, linha=_limites_de_linha(bruto.get("linha"), problemas))


#: As medidas de linha que o olho compara (lote F1).
MEDIDAS_DE_LINHA = ("cantos", "dobras", "degraus")


def _limites_de_linha(bruto: Any, problemas: list[str]) -> dict[str, dict[str, float]]:
    if bruto is None:
        return {}
    if not isinstance(bruto, Mapping):
        problemas.append("olho.linha: um mapeamento de tipo de asset para os limites")
        return {}
    limites: dict[str, dict[str, float]] = {}
    for tipo, valores in bruto.items():
        onde = f"olho.linha.{tipo}"
        if not isinstance(valores, Mapping):
            problemas.append(f"{onde}: use {{cantos: N, dobras: N, degraus: N, a_calibrar: true}}")
            continue
        if not valores.get("fonte") and valores.get("a_calibrar") is not True:
            problemas.append(f"{onde}: número sem fonte; marque a_calibrar: true")
            continue
        estranhas = set(valores) - {*MEDIDAS_DE_LINHA, "classe", "secao", "fonte", "a_calibrar"}
        if estranhas:
            problemas.append(f"{onde}: chaves desconhecidas {sorted(estranhas)}")
        lidos = {}
        for medida in MEDIDAS_DE_LINHA:
            valor = valores.get(medida)
            if valor is None:
                continue
            if not isinstance(valor, (int, float)) or valor < 0:
                problemas.append(f"{onde}.{medida}: um número de 0 para cima")
                continue
            lidos[medida] = float(valor)
        limites[str(tipo)] = lidos
    return limites


def _inteiro_positivo(porte: Mapping[str, Any], chave: str, problemas: list[str]) -> int | None:
    valor = _numero_a_calibrar(porte.get(chave), f"porte.{chave}", problemas)
    if valor is None:
        return None
    if valor < 1 or valor != int(valor):
        problemas.append(f"porte.{chave}: inteiro a partir de 1")
        return None
    return int(valor)


def _numero_a_calibrar(bruto: Any, onde: str, problemas: list[str]) -> float | None:
    """Número da configuração: sem fonte externa, leva ``a_calibrar: true``."""
    if bruto is None:
        return None
    if not isinstance(bruto, Mapping) or not isinstance(bruto.get("valor"), (int, float)):
        problemas.append(f"{onde}: use {{valor: N, a_calibrar: true, ...}}")
        return None
    if not bruto.get("fonte") and bruto.get("a_calibrar") is not True:
        problemas.append(f"{onde}: número sem fonte; marque a_calibrar: true")
        return None
    return float(bruto["valor"])
