"""O recorte: o pedaço da base que vale para um pedido (PIXEL_KNOWLEDGE §18).

O documento inteiro nunca entra na conversa — só as linhas daquele pedido, que
``consultar_pedido`` devolve. O seletor lê o ``FinalResolvedSpec`` (o
``context.resolved`` do pipeline) e **não recalcula** campo nenhum: tamanho,
paleta, tipo e corpo continuam vindo só do spec, e o recorte só acrescenta
orientação. Os campos lidos são estes, e mais nenhum:

    logical_resolution               a linha de proporção e o molde
    asset.type                       a forma de um objeto (``prop``)
    character.body_type              a forma de um personagem
    palette                          o limite de cores, ou as cores travadas
    style.shading.light_direction    a luz, quando o pedido a define

O que um estilo decide — paleta-mestra, luz padrão, proporções e moldes —
chega por um ponto só, :meth:`BaseDeConhecimento.estilo`. O código não tem
paleta nem direção de luz próprias: sem configuração, a linha some.

Corpo e quadro são coisas diferentes. A grade do spec é o **quadro**; o corpo
que vive nele sai de ``proporcoes.yaml`` — do mesmo tamanho (``tamanhos``) ou
menor (``quadros``, como um corpo de 32 num quadro de 48). As medidas do corpo
não mudam: ele fica centrado na horizontal, e as faixas de y descem junto com o
chão do quadro. Nada disso lê outro campo do spec além da grade.

O molde entra por padrão só como **medidas e nomes de camadas**. A receita
inteira vem quando quem consulta pede (``molde=True``): entregue sempre, ela
virava o desenho em vez de orientá-lo — o corpo do manequim aparecia em todo
personagem.

O recorte tem teto, para a base poder crescer sem aumentar o gasto por pedido.
As seções entram em ordem de prioridade; a que não couber sai **inteira**, e a
última linha diz qual saiu.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from ..generation.schemas import AssetType
from .base import BaseDeConhecimento, Forma, Luz, Medida, Molde, Paleta

__all__ = [
    "TETO_CARACTERES",
    "USO_DO_MOLDE",
    "FonteDeReferencias",
    "Porte",
    "montar_recorte",
    "porte",
]

#: Teto do recorte, em caracteres (cerca de 1.300 tokens). Contagem de
#: caracteres porque é determinística; um tokenizador mudaria com o modelo.
TETO_CARACTERES = 4000

#: Como o Claude deve usar o molde: medidas e camadas, não um desenho pronto.
USO_DO_MOLDE = (
    "o molde é guia de medidas e de camadas, não desenho a copiar: mantenha as "
    "proporções, a linha de chão e os nomes das camadas; redesenhe pose, "
    "silhueta e detalhes para o pedido"
)

#: As partes do corpo, de cima para baixo, como viram faixas de y.
_PARTES = (("cabeca_px", "cabeça"), ("tronco_px", "tronco"), ("pernas_px", "pernas"))
#: Larguras, ditas juntas numa frase só.
_LARGURAS = (
    ("largura_cabeca_px", "cabeça"),
    ("largura_tronco_px", "tronco"),
    ("largura_braco_px", "braço"),
    ("largura_perna_px", "perna"),
)
#: Proporção de origem, que justifica as medidas mas não orienta o desenho.
_SO_REFERENCIA = ("cabecas",)


class FonteDeReferencias(Protocol):
    """Quem soma as referências medidas (``assetflow.referencias``).

    O recorte não importa aquele módulo: recebe a linha pronta por aqui, e o
    seletor continua sendo o único que lê o spec.
    """

    def linha(self, tipo: str, corpo: str | None, altura: int | None) -> str: ...


@dataclass(frozen=True, slots=True)
class Porte:
    """O que as referências precisam saber do pedido, lido do spec uma vez só."""

    tipo: str
    #: Forma do corpo quando o spec a conhece; ``None`` em objeto ou corpo
    #: ``unknown`` — que não vira humanoide.
    corpo: str | None
    #: Altura do corpo da tabela da base (``tamanhos`` ou ``quadros``); ``None``
    #: quando a forma não tem altura (um objeto) ou o tamanho não tem tabela.
    altura: int | None


def porte(resolved: Any, base: BaseDeConhecimento | None) -> Porte | None:
    """Tipo, corpo e altura do corpo deste pedido; ``None`` fora de Pixel Art."""
    logica = resolved.logical_resolution
    if logica is None:
        return None
    tipo = _valor(resolved.asset.type)
    corpo = _valor(resolved.character.body_type) if resolved.asset.type == AssetType.CHARACTER else None
    altura = None
    if base is not None and not base.esta_vazia:
        forma = base.estilo().formas.get(_forma(resolved))
        encaixe = _encaixe(forma, logica.width, logica.height)
        if encaixe is not None and "altura_px" in encaixe.medidas:
            altura = int(encaixe.medidas["altura_px"].valor)
    return Porte(tipo=tipo, corpo=None if corpo in (None, "unknown") else corpo, altura=altura)


def montar_recorte(
    resolved: Any,
    base: BaseDeConhecimento | None,
    *,
    molde: bool = False,
    referencias: FonteDeReferencias | None = None,
    teto: int = TETO_CARACTERES,
) -> str:
    """As linhas da base que valem para este spec; ``""`` quando não há nada.

    Com ``molde=True``, a receita do molde-base vem inteira no lugar da linha
    de camadas. Com ``referencias``, a linha ``referências:`` entra por último
    — é a primeira a sair quando o teto aperta.
    """
    logica = resolved.logical_resolution
    if logica is None:  # pedido que não é Pixel Art
        return ""
    linha_de_referencias = ""
    if referencias is not None:
        alvo = porte(resolved, base)
        linha_de_referencias = referencias.linha(alvo.tipo, alvo.corpo, alvo.altura)
    if base is None or base.esta_vazia:
        return _caber([("referências", linha_de_referencias)] if linha_de_referencias else [], teto)

    estilo = base.estilo()
    largura, altura = logica.width, logica.height
    forma = estilo.formas.get(_forma(resolved))
    encaixe = _encaixe(forma, largura, altura)
    molde_base = estilo.molde(forma.id, *encaixe.corpo) if forma and encaixe else None

    secoes = [
        ("proporções", _proporcoes(forma, encaixe, largura, altura)),
        ("luz", _luz(resolved, estilo.luz)),
        ("cores", _cores(resolved, estilo.paleta)),
        ("silhueta", _silhueta(forma)),
        ("molde", _molde(molde_base, encaixe, largura, altura, completo=molde)),
        ("referências", linha_de_referencias),
    ]
    return _caber([(nome, texto) for nome, texto in secoes if texto], teto)


@dataclass(frozen=True, slots=True)
class _Encaixe:
    """Onde o corpo fica na grade do spec."""

    #: Tamanho do corpo, ``(32, 32)``.
    corpo: tuple[int, int]
    medidas: Mapping[str, Medida]
    #: Linha do chão na grade do spec (do corpo, ou do quadro maior).
    chao: int | None
    #: Quanto o corpo anda para caber no quadro: centrado em x, pelo chão em y.
    dx: int = 0
    dy: int = 0

    @property
    def em_quadro_maior(self) -> bool:
        return bool(self.dx or self.dy)


def _encaixe(forma: Forma | None, largura: int, altura: int) -> _Encaixe | None:
    """O corpo para esta grade: do mesmo tamanho, ou num quadro maior."""
    if forma is None:
        return None
    medidas = forma.medidas(largura, altura)
    if medidas:
        chao = medidas["chao_y"].valor if "chao_y" in medidas else None
        return _Encaixe(corpo=(largura, altura), medidas=medidas, chao=chao)

    quadro = forma.quadros.get(f"{largura}x{altura}")
    if quadro is None:
        return None
    corpo_l, corpo_a = (int(lado) for lado in quadro.corpo.split("x"))
    medidas = forma.tamanhos[quadro.corpo]
    chao = quadro.chao_y.valor
    chao_do_corpo = medidas["chao_y"].valor if "chao_y" in medidas else chao
    return _Encaixe(
        corpo=(corpo_l, corpo_a),
        medidas=medidas,
        chao=chao,
        dx=(largura - corpo_l) // 2,
        dy=chao - chao_do_corpo,
    )


# ---------------------------------------------------------------------------
# Seções
# ---------------------------------------------------------------------------
def _forma(resolved: Any) -> str:
    """Num personagem, a forma é o corpo; nos demais, o tipo de asset.

    Corpo ``unknown`` não vira ``humanoid``: sem forma conhecida, o recorte
    fica sem proporções e sem molde, em vez de chutar.
    """
    tipo = resolved.asset.type
    if tipo == AssetType.CHARACTER:
        return _valor(resolved.character.body_type)
    return _valor(tipo)


def _proporcoes(forma: Forma | None, encaixe: _Encaixe | None, largura: int, altura: int) -> str:
    if forma is None or encaixe is None:
        return ""
    medidas = encaixe.medidas
    valor = {nome: medida.valor for nome, medida in medidas.items()}
    chao = encaixe.chao
    ditas: set[str] = {*_SO_REFERENCIA, "vao_braco_px"}
    partes: list[str] = []

    # As faixas de y saem das medidas da configuração, de cima para baixo a
    # partir do topo (chão - altura + 1). Nada aqui vem do spec além do tamanho.
    topo = None
    if chao is not None and "altura_px" in valor:
        topo = chao - valor["altura_px"] + 1
        if all(nome in valor for nome, _ in _PARTES):
            inicio = topo
            for nome, rotulo in _PARTES:
                fim = inicio + valor[nome] - 1
                partes.append(f"{rotulo} y{inicio}–{fim} ({valor[nome]} px)")
                inicio = fim + 1
            ditas.update(nome for nome, _ in _PARTES)
            ditas.add("altura_px")
    if chao is not None:
        partes.append(f"chão y={chao} (pixel opaco mais baixo)")
        ditas.add("chao_y")
    folga = valor.get("folga_topo_px", 0)
    if topo is not None and folga:
        texto = f"folga y{topo - folga}–{topo - 1}"
        nota = medidas["folga_topo_px"].nota
        partes.append(f"{texto} {nota}" if nota else texto)
        ditas.add("folga_topo_px")

    larguras = [(rotulo, valor[nome]) for nome, rotulo in _LARGURAS if nome in valor]
    if larguras:
        partes.append(
            "larguras com contorno: " + ", ".join(f"{rotulo} {px}" for rotulo, px in larguras)
        )
        ditas.update(nome for nome, _ in _LARGURAS)

    partes.extend(_frase(medida) for nome, medida in medidas.items() if nome not in ditas)
    corpo_l, corpo_a = encaixe.corpo
    titulo = (
        f"{forma.nome}, corpo {corpo_l}×{corpo_a} num quadro {largura}×{altura}"
        if encaixe.em_quadro_maior
        else f"{forma.nome} {largura}×{altura}"
    )
    linhas = [f"{titulo}: " + " · ".join(partes)]
    quadro = _linha_do_quadro(valor, largura, topo - folga if topo is not None else None)
    if quadro:
        linhas.append(quadro)
    return "\n".join(linhas)


def _linha_do_quadro(valor: Mapping[str, Any], largura: int, acima_de: int | None) -> str:
    """Onde o corpo fica na largura da grade, e o que sobra dos lados e acima.

    A largura do corpo com os braços sai das medidas: tronco + 2 × (vão +
    braço). Sobra é o que fica entre o corpo e a margem de 1 px da borda.
    """
    if not all(nome in valor for nome in ("largura_tronco_px", "largura_braco_px", "vao_braco_px")):
        return ""
    corpo = valor["largura_tronco_px"] + 2 * (valor["vao_braco_px"] + valor["largura_braco_px"])
    inicio = (largura - corpo) // 2
    fim = inicio + corpo - 1
    centro = (
        f"entre x={largura // 2 - 1} e x={largura // 2}" if largura % 2 == 0 else f"em x={largura // 2}"
    )
    livres = [
        f"x{a}–{b}" for a, b in ((1, inicio - 1), (fim + 1, largura - 2)) if a <= b
    ]
    sobra = []
    if livres:
        sobra.append(f"{' e '.join(livres)} dos lados")
    if acima_de is not None and acima_de - 1 >= 1:
        sobra.append(f"y1–{acima_de - 1} acima")
    texto = (
        f"quadro: corpo centrado {centro}, com braços em x{inicio}–{fim} "
        # O vão entra na conta da largura, mas não é exigência: só vale com o
        # membro à mostra (a regra de silhueta em proporcoes.yaml).
        f"(colunas contando o braço separado do tronco por {valor['vao_braco_px']} px, "
        "o que só vale com o membro à mostra)"
    )
    if sobra:
        texto += f"; livre {' e '.join(sobra)}, para arma, escudo, crista e animação"
    return texto


def _frase(medida: Medida) -> str:
    valor = medida.valor
    if medida.nome == "olho_px" and isinstance(valor, tuple) and len(valor) == 2:
        texto = f"olho {valor[0]}×{valor[1]}"
    elif medida.nome == "braco_px":
        texto = f"braço {valor} px"
    elif medida.nome == "margem_px":
        texto = f"margem {valor} px até a borda"
    elif medida.nome == "tons_por_material":
        texto = f"{valor} tons por material"
    elif medida.nome == "ocupacao_min" and isinstance(valor, (int, float)):
        texto = f"ocupar ao menos {round(valor * 100)}% da grade"
    else:
        # Medida nova na configuração aparece mesmo sem frase própria.
        bruto = " a ".join(map(str, valor)) if isinstance(valor, tuple) else str(valor)
        texto = f"{medida.nome.replace('_', ' ')} {bruto}"
    return f"{texto} {medida.nota}" if medida.nota else texto


def _luz(resolved: Any, luz: Luz | None) -> str:
    pedida = resolved.style.shading.light_direction
    if pedida:
        cabeca = f"luz: {pedida} (do pedido)"
    elif luz is not None:
        cabeca = f"luz: {luz.padrao} (padrão da base; o pedido não definiu)"
    else:
        return ""
    regras = [regra.texto for regra in luz.regras] if luz is not None else []
    return " · ".join([cabeca, *regras])


def _cores(resolved: Any, paleta: Paleta | None) -> str:
    pedida = resolved.palette
    if pedida is not None and pedida.mode == "locked" and pedida.colors:
        # Paleta travada é do spec: as rampas da mestra não se aplicam.
        return f"cores: paleta travada pelo pedido, use só estas: {' '.join(pedida.colors)}"

    limite = pedida.max_colors if pedida is not None else None
    cabeca = f"cores: até {limite}, contorno incluído" if limite else "cores: o pedido não limita"
    if paleta is None or not paleta.rampas:
        return cabeca

    linhas = [
        (
            f"{cabeca} · paleta-mestra {paleta.id}, rampas do escuro ao claro; "
            "cada material usa tons vizinhos de uma rampa:"
        ),
        f"  contorno {paleta.contorno}",
    ]
    rampas = [f"{material} {' '.join(cores)}" for material, cores in paleta.rampas.items()]
    for i in range(0, len(rampas), 2):
        linhas.append("  " + " · ".join(rampas[i : i + 2]))
    return "\n".join(linhas)


def _silhueta(forma: Forma | None) -> str:
    if forma is None or not forma.regras:
        return ""
    return "silhueta: " + " · ".join(regra.texto for regra in forma.regras)


def _molde(
    molde: Molde | None,
    encaixe: _Encaixe | None,
    largura: int,
    altura: int,
    *,
    completo: bool,
) -> str:
    if molde is None or encaixe is None:
        return ""
    camadas = ", ".join(str(camada.get("nome")) for camada in molde.receita.get("camadas") or [])
    if not completo:
        nota = f" ({molde.nota_camadas})" if molde.nota_camadas else ""
        return f"camadas: {camadas}{nota} · a receita do molde-base vem com molde=true"

    receita, onde = molde.receita, ""
    if encaixe.em_quadro_maior:
        receita = _deslocar(molde.receita, encaixe.dx, encaixe.dy, (largura, altura))
        onde = f" (deslocado +{encaixe.dx}, +{encaixe.dy} para o quadro {largura}×{altura})"
    chaves = " · ".join(f"{chave} {papel}" for chave, papel in molde.chaves.items())
    return "\n".join(
        [
            f"molde {molde.id}{onde}: {molde.descricao}; camadas {camadas}; chaves {chaves}",
            json.dumps(receita, ensure_ascii=False, separators=(",", ":")),
            USO_DO_MOLDE,
        ]
    )


def _deslocar(
    receita: Mapping[str, Any], dx: int, dy: int, grade: tuple[int, int]
) -> dict[str, Any]:
    """A receita do molde movida para o quadro maior, sem tocar na original.

    Move toda coordenada de operação (``em``, ``ret``, ``elipse``, ``linha``,
    ``poligono``, ``balde``) e troca a grade. O espelho em ``x`` continua certo
    porque o corpo é centrado na horizontal; um espelho em ``y`` não seria —
    nenhum molde usa hoje, e um que use precisa de outra conta.
    """
    nova = copy.deepcopy(dict(receita))
    nova["grade"] = list(grade)
    for camada in nova.get("camadas") or []:
        for op in camada.get("ops") or []:
            for chave in ("em", "balde"):
                if chave in op:
                    x, y = op[chave]
                    op[chave] = [x + dx, y + dy]
            for chave in ("ret", "elipse"):
                if chave in op:
                    x, y, largura, altura = op[chave]
                    op[chave] = [x + dx, y + dy, largura, altura]
            for chave in ("linha", "poligono"):
                if chave in op:
                    op[chave] = [v + (dx if i % 2 == 0 else dy) for i, v in enumerate(op[chave])]
    return nova


# ---------------------------------------------------------------------------
# Teto
# ---------------------------------------------------------------------------
def _caber(secoes: list[tuple[str, str]], teto: int) -> str:
    """Junta as seções até o teto, tirando inteiras as de menor prioridade."""
    escolhidas = list(secoes)
    omitidas: list[str] = []
    while True:
        linhas = [texto for _, texto in escolhidas]
        if omitidas:
            linhas.append(f"omitido pelo teto de {teto} caracteres: {', '.join(omitidas)}")
        texto = "\n".join(linhas)
        if len(texto) <= teto or not escolhidas:
            return texto
        nome, _ = escolhidas.pop()
        omitidas.insert(0, nome)


def _valor(valor: Any) -> str:
    return str(getattr(valor, "value", valor))
