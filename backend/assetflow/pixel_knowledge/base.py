"""A base de conhecimento de pixel art, lida de ``config/pixel_knowledge/``.

Plano desenhista, Fase 3, e a trilha de base de conhecimento. Conhecimento é
configuração: paletas, luz, proporções e moldes moram em YAML, e acrescentar
uma paleta ou um molde nunca exige editar um ``.py``. Este módulo lê e confere
o formato; o que entra na conversa quem decide é :mod:`.recorte`.

    paletas.yaml        paletas nomeadas, rampas por material e a mestra
    luz.yaml            a direção de luz padrão do projeto
    proporcoes.yaml     medidas e regras por forma e tamanho de grade
    silhuetas/*.yaml    moldes-base: receitas da desenhista-v1 em camadas
    olhar.yaml          a lista de verificação do olhar (Fase B2 do plano do app)

A carga é tolerante como a da taxonomia: diretório ausente dá uma base vazia,
e um arquivo fora do formato é ignorado com aviso — o boot não cai por causa
de conhecimento. Mas nada some em silêncio: cada arquivo ignorado vira uma
linha em :attr:`BaseDeConhecimento.problemas`, e o teste de carga exige zero.

Mora na estante, ao lado de ``assetflow/pixel/``, e nunca numa gaveta: a
desenhista recebe a receita pronta e não sabe que esta base existe.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any, TypeVar

import yaml

from .olhar import ListasDoOlhar, OlharInvalido, ler_olhar

__all__ = [
    "CLASSES",
    "BaseDeConhecimento",
    "ConhecimentoInvalido",
    "Estilo",
    "Forma",
    "Luz",
    "Medida",
    "Molde",
    "Paleta",
    "Quadro",
    "Regra",
    "luminancia",
]

_LOG = logging.getLogger("assetflow.pixel_knowledge")

#: As classes de promessa do ``SPEC_CONSTRAINTS``, sem a ``engine_hint`` (que
#: não tem promessa visual e não cabe numa regra de desenho).
CLASSES = frozenset({"hard", "semantic", "style"})

_HEX = re.compile(r"^#[0-9a-f]{6}$")
_TAMANHO = re.compile(r"^[1-9][0-9]*x[1-9][0-9]*$")
_DIGITO = re.compile(r"[0-9]")

T = TypeVar("T")


class ConhecimentoInvalido(ValueError):
    """Um arquivo da base fora do formato; a mensagem diz onde e o quê."""


# ---------------------------------------------------------------------------
# O que a base contém
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Regra:
    """Uma regra em uma frase, com a classe e a origem."""

    texto: str
    classe: str
    secao: str
    fonte: str | None = None
    #: Número sem fonte externa — inclusive "convenção comum" no documento.
    a_calibrar: bool = False
    #: Como a regra é conferida (lote F5): ``tipo:alvo``. Tipos: ``construcao``
    #: (o comando da receita a cumpre: ``construcao:sombrear``), ``medida`` (o
    #: app mede: ``medida:VALOR``), ``olhar`` (uma pergunta do olhar:
    #: ``olhar:humanoid/silhueta``) e ``autora`` (só a nota dela).
    verificacao: str = ""

    @property
    def tipo_de_verificacao(self) -> str:
        return self.verificacao.split(":", 1)[0]

    @property
    def alvo_da_verificacao(self) -> str:
        return self.verificacao.split(":", 1)[1] if ":" in self.verificacao else ""


#: Os tipos de verificação de uma regra (FUNDAMENTOS_E_FERRAMENTAS §7).
TIPOS_DE_VERIFICACAO = ("construcao", "medida", "olhar", "autora")
_VERIFICACAO = re.compile(r"^(construcao|medida|olhar):[\w/ çãéíóú-]+$|^autora$")


@dataclass(frozen=True, slots=True)
class Medida:
    """Um número de ``proporcoes.yaml``: um valor, ou uma faixa/par."""

    nome: str
    valor: int | float | tuple[int | float, ...]
    classe: str
    secao: str
    fonte: str | None = None
    a_calibrar: bool = False
    #: Complemento que acompanha o valor no recorte ("com brilho de 1 px").
    nota: str = ""


@dataclass(frozen=True, slots=True)
class Paleta:
    """Uma paleta nomeada, com as rampas marcadas por material."""

    id: str
    nome: str
    fonte: str
    contorno: str
    cores: tuple[str, ...]
    #: Do escuro ao claro, só com cores da própria paleta.
    rampas: Mapping[str, tuple[str, ...]]
    autor: str = ""
    conferida_em: str = ""


@dataclass(frozen=True, slots=True)
class Luz:
    """A direção de luz padrão e as regras que valem para qualquer direção."""

    padrao: str
    regras: tuple[Regra, ...] = ()


@dataclass(frozen=True, slots=True)
class Quadro:
    """Um quadro maior que o corpo: qual corpo vive nele e onde fica o chão.

    O corpo não muda de medida no quadro maior: fica centrado na horizontal,
    e as faixas de y descem junto com o chão do quadro.
    """

    #: A grade do quadro, ``"48x48"``.
    tamanho: str
    #: A chave de ``tamanhos`` cujo corpo vive neste quadro, ``"32x32"``.
    corpo: str
    chao_y: Medida


@dataclass(frozen=True, slots=True)
class Forma:
    """Uma forma (``humanoid``, ``prop``...) com regras e medidas por tamanho."""

    id: str
    nome: str
    regras: tuple[Regra, ...]
    #: ``"32x32"`` -> medidas do corpo, num quadro do mesmo tamanho.
    tamanhos: Mapping[str, Mapping[str, Medida]]
    #: ``"48x48"`` -> qual corpo de :attr:`tamanhos` vive num quadro maior.
    quadros: Mapping[str, Quadro] = field(default_factory=dict)

    def medidas(self, largura: int, altura: int) -> Mapping[str, Medida] | None:
        return self.tamanhos.get(f"{largura}x{altura}")


@dataclass(frozen=True, slots=True)
class Molde:
    """Um molde-base: uma receita da desenhista-v1, em camadas com nome."""

    id: str
    forma: str
    grade: tuple[int, int]
    descricao: str
    #: Chave da paleta -> papel ("p": "pele"). Mesmas chaves da paleta.
    chaves: Mapping[str, str]
    receita: Mapping[str, Any]
    #: O que os nomes das camadas pressupõem ("direita e esquerda do
    #: personagem"). Vai na linha de camadas do recorte, que não traz a receita.
    nota_camadas: str = ""

    @property
    def tamanho(self) -> str:
        return f"{self.grade[0]}x{self.grade[1]}"


@dataclass(frozen=True, slots=True)
class Estilo:
    """O que vale como padrão num desenho: paleta, luz, proporções e moldes.

    É o **ponto único** por onde o seletor do recorte lê o que um estilo
    decide. Hoje há um estilo só, montado da configuração — ``mestra`` de
    ``paletas.yaml``, ``padrao`` de ``luz.yaml``, ``proporcoes.yaml`` e
    ``silhuetas/``. Uma fase futura de estilos troca os quatro juntos (e o
    contorno, quando ele existir), e para isso basta mudar
    :meth:`BaseDeConhecimento.estilo`; o seletor não muda. Nenhum valor aqui
    vem do código.
    """

    paleta: Paleta | None
    luz: Luz | None
    formas: Mapping[str, Forma]
    moldes: Mapping[tuple[str, str], Molde]

    def molde(self, forma: str, largura: int, altura: int) -> Molde | None:
        return self.moldes.get((forma, f"{largura}x{altura}"))


@dataclass(frozen=True, slots=True)
class BaseDeConhecimento:
    """Tudo o que ``config/pixel_knowledge/`` trouxe, já conferido."""

    paletas: Mapping[str, Paleta] = field(default_factory=dict)
    #: O id da paleta-mestra, como veio de ``paletas.yaml``.
    mestra: str | None = None
    luz: Luz | None = None
    formas: Mapping[str, Forma] = field(default_factory=dict)
    moldes: Mapping[tuple[str, str], Molde] = field(default_factory=dict)
    #: A lista de verificação do olhar (``olhar.yaml``); ``None`` sem o arquivo.
    olhar: ListasDoOlhar | None = None
    #: Um texto por arquivo ignorado na carga. Vazio numa base saudável.
    problemas: tuple[str, ...] = ()

    @classmethod
    def vazia(cls) -> BaseDeConhecimento:
        return cls()

    @property
    def esta_vazia(self) -> bool:
        return not (self.paletas or self.luz or self.formas or self.moldes)

    def estilo(self) -> Estilo:
        """O estilo em vigor — o ponto único que uma fase de estilos troca."""
        return Estilo(
            paleta=self.paletas.get(self.mestra) if self.mestra else None,
            luz=self.luz,
            formas=self.formas,
            moldes=self.moldes,
        )

    @classmethod
    def do_diretorio(cls, diretorio: Path) -> BaseDeConhecimento:
        """Carrega ``config/pixel_knowledge/``. Ausente, a base vem vazia."""
        if not diretorio.is_dir():
            _LOG.info(
                "diretório de conhecimento '%s' não existe; o recorte de "
                "consultar_pedido sai vazio",
                diretorio,
            )
            return cls.vazia()

        problemas: list[str] = []

        def carregar(nome: str, leitor: Callable[[Mapping[str, Any], str], T]) -> T | None:
            caminho = diretorio / nome
            if not caminho.is_file():
                return None
            try:
                return leitor(_ler_yaml(caminho), nome)
            except (ConhecimentoInvalido, OlharInvalido, yaml.YAMLError, OSError) as exc:
                # Um arquivo torto não derruba o boot nem os outros arquivos;
                # silêncio é que não pode haver.
                problemas.append(f"{nome}: {exc}")
                _LOG.warning("conhecimento ignorado: %s: %s", nome, exc)
                return None

        paletas, mestra = carregar("paletas.yaml", _ler_paletas) or ({}, None)
        luz = carregar("luz.yaml", _ler_luz)
        formas = carregar("proporcoes.yaml", _ler_proporcoes) or {}
        olhar = carregar("olhar.yaml", ler_olhar)

        moldes: dict[tuple[str, str], Molde] = {}
        pasta = diretorio / "silhuetas"
        for caminho in sorted(pasta.glob("*.yaml")) if pasta.is_dir() else ():
            nome = f"silhuetas/{caminho.name}"
            molde = carregar(
                nome, lambda dados, origem, mid=caminho.stem: _ler_molde(dados, origem, mid)
            )
            if molde is None:
                continue
            chave = (molde.forma, molde.tamanho)
            if chave in moldes:
                problemas.append(
                    f"{nome}: já existe molde de {molde.forma} {molde.tamanho} "
                    f"({moldes[chave].id}); este foi ignorado"
                )
                continue
            moldes[chave] = molde

        return cls(
            paletas=paletas,
            mestra=mestra,
            luz=luz,
            formas=formas,
            moldes=moldes,
            olhar=olhar,
            problemas=tuple(problemas),
        )


def luminancia(cor: str) -> float:
    """Luminância relativa (sRGB, WCAG) de ``"#rrggbb"``: 0 é preto, 1 é branco."""

    def canal(hexa: str) -> float:
        c = int(hexa, 16) / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(cor[i : i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ---------------------------------------------------------------------------
# Leitores, um por arquivo
# ---------------------------------------------------------------------------
def _ler_paletas(dados: Mapping[str, Any], origem: str) -> tuple[dict[str, Paleta], str | None]:
    _so_chaves(dados, {"mestra", "paletas"}, origem)
    brutas = _mapa(dados.get("paletas"), "paletas")
    if not brutas:
        raise ConhecimentoInvalido("'paletas' está vazio")
    paletas = {
        str(pid): _ler_paleta(str(pid), bruta, f"paletas.{pid}") for pid, bruta in brutas.items()
    }

    mestra = dados.get("mestra")
    if mestra is not None:
        if not isinstance(mestra, str) or mestra not in paletas:
            raise ConhecimentoInvalido(
                f"mestra: '{mestra}' não é uma das paletas ({', '.join(paletas)})"
            )
        if not paletas[mestra].rampas:
            raise ConhecimentoInvalido(
                f"mestra: a paleta '{mestra}' não tem rampas, e o recorte oferece as rampas"
            )
    return paletas, mestra


def _ler_paleta(pid: str, bruta: Any, onde: str) -> Paleta:
    bruta = _mapa(bruta, onde)
    _so_chaves(bruta, {"nome", "autor", "fonte", "conferida_em", "contorno", "cores", "rampas"}, onde)

    cores = tuple(
        _cor(valor, f"{onde}.cores[{i}]") for i, valor in enumerate(_lista(bruta.get("cores"), f"{onde}.cores"))
    )
    if len(cores) < 2:
        raise ConhecimentoInvalido(f"{onde}.cores: precisa de pelo menos 2 cores")
    repetidas = sorted({cor for cor in cores if cores.count(cor) > 1})
    if repetidas:
        raise ConhecimentoInvalido(f"{onde}.cores: cor repetida ({', '.join(repetidas)})")

    contorno = _cor(bruta.get("contorno"), f"{onde}.contorno")
    if contorno not in cores:
        raise ConhecimentoInvalido(f"{onde}.contorno: {contorno} não está nas cores da paleta")
    mais_escura = min(cores, key=luminancia)
    if luminancia(contorno) > luminancia(mais_escura):
        raise ConhecimentoInvalido(
            f"{onde}.contorno: {contorno} não é a cor mais escura da paleta ({mais_escura})"
        )

    rampas: dict[str, tuple[str, ...]] = {}
    for material, valores in _mapa(bruta.get("rampas") or {}, f"{onde}.rampas").items():
        lugar = f"{onde}.rampas.{material}"
        rampa = tuple(_cor(valor, f"{lugar}[{i}]") for i, valor in enumerate(_lista(valores, lugar)))
        if len(rampa) < 2:
            raise ConhecimentoInvalido(f"{lugar}: uma rampa tem pelo menos 2 cores")
        fora = [cor for cor in rampa if cor not in cores]
        if fora:
            raise ConhecimentoInvalido(f"{lugar}: {', '.join(fora)} fora da paleta")
        for anterior, seguinte in pairwise(rampa):
            if luminancia(seguinte) <= luminancia(anterior):
                raise ConhecimentoInvalido(
                    f"{lugar}: a rampa vai do escuro ao claro, e {seguinte} não é "
                    f"mais clara que {anterior}"
                )
        rampas[str(material)] = rampa

    return Paleta(
        id=pid,
        nome=_texto(bruta.get("nome"), f"{onde}.nome"),
        fonte=_texto(bruta.get("fonte"), f"{onde}.fonte"),
        contorno=contorno,
        cores=cores,
        rampas=rampas,
        autor=_texto(bruta.get("autor") or "", f"{onde}.autor", vazio=True),
        # Sem aspas, o YAML lê 2026-11-25 como data; o texto é o que importa.
        conferida_em=str(bruta.get("conferida_em") or ""),
    )


def _ler_luz(dados: Mapping[str, Any], origem: str) -> Luz:
    _so_chaves(dados, {"padrao", "regras"}, origem)
    return Luz(
        padrao=_texto(dados.get("padrao"), "padrao"),
        regras=_regras(dados.get("regras"), "regras"),
    )


def _ler_proporcoes(dados: Mapping[str, Any], origem: str) -> dict[str, Forma]:
    _so_chaves(dados, {"formas"}, origem)
    formas: dict[str, Forma] = {}
    for fid, bruta in _mapa(dados.get("formas"), "formas").items():
        onde = f"formas.{fid}"
        bruta = _mapa(bruta, onde)
        _so_chaves(bruta, {"nome", "regras", "tamanhos", "quadros"}, onde)

        tamanhos: dict[str, dict[str, Medida]] = {}
        for tamanho, medidas in _mapa(bruta.get("tamanhos") or {}, f"{onde}.tamanhos").items():
            lugar = f"{onde}.tamanhos.{tamanho}"
            if not _TAMANHO.match(str(tamanho)):
                raise ConhecimentoInvalido(f"{lugar}: tamanho é \"LxA\", como \"32x32\"")
            tamanhos[str(tamanho)] = {
                str(nome): _ler_medida(str(nome), valor, f"{lugar}.{nome}")
                for nome, valor in _mapa(medidas, lugar).items()
            }

        formas[str(fid)] = Forma(
            id=str(fid),
            nome=_texto(bruta.get("nome"), f"{onde}.nome"),
            regras=_regras(bruta.get("regras"), f"{onde}.regras"),
            tamanhos=tamanhos,
            quadros=_ler_quadros(bruta.get("quadros") or {}, tamanhos, f"{onde}.quadros"),
        )
    return formas


def _ler_quadros(
    brutos: Any, tamanhos: Mapping[str, Mapping[str, Medida]], onde: str
) -> dict[str, Quadro]:
    quadros: dict[str, Quadro] = {}
    for tamanho, bruto in _mapa(brutos, onde).items():
        tamanho = str(tamanho)
        lugar = f"{onde}.{tamanho}"
        if not _TAMANHO.match(tamanho):
            raise ConhecimentoInvalido(f"{lugar}: quadro é \"LxA\", como \"48x48\"")
        if tamanho in tamanhos:
            raise ConhecimentoInvalido(
                f"{lugar}: {tamanho} já é um tamanho de corpo; quadro é só para corpo menor"
            )
        bruto = _mapa(bruto, lugar)
        _so_chaves(bruto, {"corpo", "chao_y"}, lugar)
        corpo = _texto(bruto.get("corpo"), f"{lugar}.corpo")
        if corpo not in tamanhos:
            raise ConhecimentoInvalido(
                f"{lugar}.corpo: '{corpo}' não está em tamanhos ({', '.join(tamanhos)})"
            )
        if "chao_y" not in tamanhos[corpo]:
            # O corpo desce do chão dele para o do quadro; sem o primeiro, não
            # há como saber quanto.
            raise ConhecimentoInvalido(f"{lugar}.corpo: o corpo '{corpo}' não declara chao_y")
        (qw, qh), (cw, ch) = _lados(tamanho), _lados(corpo)
        if qw < cw or qh < ch:
            raise ConhecimentoInvalido(f"{lugar}: o quadro é menor que o corpo {corpo}")
        if (qw - cw) % 2:
            raise ConhecimentoInvalido(
                f"{lugar}: a sobra de largura ({qw - cw}) é ímpar, e o corpo não fica "
                "centrado em coluna inteira"
            )
        chao = _ler_medida("chao_y", bruto.get("chao_y"), f"{lugar}.chao_y")
        if not isinstance(chao.valor, int) or not 0 <= chao.valor < qh:
            raise ConhecimentoInvalido(f"{lugar}.chao_y: linha inteira dentro do quadro")
        quadros[tamanho] = Quadro(tamanho=tamanho, corpo=corpo, chao_y=chao)
    return quadros


def _lados(tamanho: str) -> tuple[int, int]:
    largura, altura = tamanho.split("x")
    return int(largura), int(altura)


def _ler_medida(nome: str, bruta: Any, onde: str) -> Medida:
    bruta = _mapa(bruta, onde)
    _so_chaves(bruta, {"valor", "classe", "secao", "fonte", "a_calibrar", "nota"}, onde)

    valor = bruta.get("valor")
    if isinstance(valor, list):
        if not valor or not all(_numero(item) for item in valor):
            raise ConhecimentoInvalido(f"{onde}.valor: lista de números esperada")
        valor = tuple(valor)
    elif not _numero(valor):
        raise ConhecimentoInvalido(f"{onde}.valor: número ou lista de números esperado")

    fonte, a_calibrar = _origem(bruta, onde)
    # Toda medida é número: sem fonte, é a calibrar (plano desenhista, trilha).
    if not fonte and not a_calibrar:
        raise ConhecimentoInvalido(f"{onde}: número sem fonte; marque a_calibrar: true")
    return Medida(
        nome=nome,
        valor=valor,
        classe=_classe(bruta.get("classe"), onde),
        secao=_texto(bruta.get("secao"), f"{onde}.secao"),
        fonte=fonte,
        a_calibrar=a_calibrar,
        nota=_texto(bruta.get("nota") or "", f"{onde}.nota", vazio=True),
    )


def _ler_molde(dados: Mapping[str, Any], origem: str, mid: str) -> Molde:
    _so_chaves(dados, {"forma", "grade", "descricao", "nota_camadas", "chaves", "receita"}, origem)

    grade = dados.get("grade")
    if (
        not isinstance(grade, list)
        or len(grade) != 2
        or not all(isinstance(lado, int) and not isinstance(lado, bool) and lado > 0 for lado in grade)
    ):
        raise ConhecimentoInvalido("grade: [largura, altura] com inteiros positivos")

    receita = _mapa(dados.get("receita"), "receita")
    if receita.get("grade") != grade:
        raise ConhecimentoInvalido(
            f"receita.grade ({receita.get('grade')}) diferente da grade do molde ({grade})"
        )
    paleta = _mapa(receita.get("paleta"), "receita.paleta")
    camadas = _lista(receita.get("camadas"), "receita.camadas")
    nomes: list[str] = []
    for i, camada in enumerate(camadas):
        camada = _mapa(camada, f"receita.camadas[{i}]")
        nomes.append(_texto(camada.get("nome"), f"receita.camadas[{i}].nome"))
    repetidos = sorted({nome for nome in nomes if nomes.count(nome) > 1})
    if repetidos:
        raise ConhecimentoInvalido(f"receita.camadas: nome repetido ({', '.join(repetidos)})")

    chaves = {str(chave): _texto(papel, f"chaves.{chave}") for chave, papel in _mapa(dados.get("chaves"), "chaves").items()}
    if set(chaves) != {str(chave) for chave in paleta}:
        raise ConhecimentoInvalido(
            f"chaves ({' '.join(sorted(chaves))}) diferentes das chaves da paleta "
            f"({' '.join(sorted(map(str, paleta)))})"
        )

    return Molde(
        id=mid,
        forma=_texto(dados.get("forma"), "forma"),
        grade=(grade[0], grade[1]),
        descricao=_texto(dados.get("descricao"), "descricao"),
        chaves=chaves,
        receita=receita,
        nota_camadas=_texto(dados.get("nota_camadas") or "", "nota_camadas", vazio=True),
    )


# ---------------------------------------------------------------------------
# Auxiliares de formato
# ---------------------------------------------------------------------------
def _ler_yaml(caminho: Path) -> Mapping[str, Any]:
    with caminho.open("r", encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)
    if not isinstance(dados, Mapping):
        raise ConhecimentoInvalido("a raiz do arquivo não é um mapeamento")
    return dados


def _regras(bruta: Any, onde: str) -> tuple[Regra, ...]:
    return tuple(_ler_regra(item, f"{onde}[{i}]") for i, item in enumerate(_lista(bruta or [], onde)))


def _ler_regra(bruta: Any, onde: str) -> Regra:
    bruta = _mapa(bruta, onde)
    _so_chaves(bruta, {"texto", "classe", "secao", "fonte", "a_calibrar", "verificacao"}, onde)
    texto = _texto(bruta.get("texto"), f"{onde}.texto")
    fonte, a_calibrar = _origem(bruta, onde)
    if _DIGITO.search(texto) and not fonte and not a_calibrar:
        raise ConhecimentoInvalido(
            f"{onde}: regra com número sem fonte ({texto!r}); marque a_calibrar: true"
        )
    verificacao = bruta.get("verificacao")
    if not isinstance(verificacao, str) or not _VERIFICACAO.match(verificacao):
        raise ConhecimentoInvalido(
            f"{onde}: toda regra declara como é conferida — 'verificacao' como "
            "\"medida:VALOR\", \"olhar:humanoid/silhueta\", \"construcao:sombrear\" ou "
            f"\"autora\" ({verificacao!r})"
        )
    return Regra(
        texto=texto,
        classe=_classe(bruta.get("classe"), onde),
        secao=_texto(bruta.get("secao"), f"{onde}.secao"),
        fonte=fonte,
        a_calibrar=a_calibrar,
        verificacao=verificacao,
    )


def _origem(bruta: Mapping[str, Any], onde: str) -> tuple[str | None, bool]:
    fonte = bruta.get("fonte")
    if fonte is not None:
        fonte = _texto(fonte, f"{onde}.fonte")
    a_calibrar = bruta.get("a_calibrar", False)
    if not isinstance(a_calibrar, bool):
        raise ConhecimentoInvalido(f"{onde}.a_calibrar: true ou false")
    return fonte, a_calibrar


def _classe(valor: Any, onde: str) -> str:
    if valor not in CLASSES:
        raise ConhecimentoInvalido(
            f"{onde}.classe: '{valor}' não é uma classe ({', '.join(sorted(CLASSES))})"
        )
    return str(valor)


def _cor(valor: Any, onde: str) -> str:
    if not isinstance(valor, str) or not _HEX.match(valor):
        raise ConhecimentoInvalido(f"{onde}: cor no formato \"#rrggbb\", em minúsculas ({valor!r})")
    return valor


def _texto(valor: Any, onde: str, *, vazio: bool = False) -> str:
    if not isinstance(valor, str) or (not vazio and not valor.strip()):
        raise ConhecimentoInvalido(f"{onde}: texto esperado ({valor!r})")
    return valor.strip()


def _numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _mapa(valor: Any, onde: str) -> Mapping[str, Any]:
    if not isinstance(valor, Mapping):
        raise ConhecimentoInvalido(f"{onde}: mapeamento esperado")
    return valor


def _lista(valor: Any, onde: str) -> list[Any]:
    if not isinstance(valor, list):
        raise ConhecimentoInvalido(f"{onde}: lista esperada")
    return valor


def _so_chaves(bruta: Mapping[str, Any], aceitas: set[str], onde: str) -> None:
    estranhas = sorted(str(chave) for chave in bruta if chave not in aceitas)
    if estranhas:
        raise ConhecimentoInvalido(
            f"{onde}: chave desconhecida ({', '.join(estranhas)}); aceitas: {', '.join(sorted(aceitas))}"
        )
