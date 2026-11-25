"""Base de conhecimento do desenhista: carga, formato, moldes e recorte.

Plano desenhista, Fase 3. Três grupos:

- **carga e formato** — a configuração real carrega sem nenhum arquivo
  ignorado, e cada regra da trilha vale: classe declarada, número com fonte
  ou ``a_calibrar``, rampa do escuro ao claro;
- **moldes** — cada molde é uma receita válida da desenhista-v1, pisa na
  linha de chão de ``proporcoes.yaml`` e cabe num pedido de 8 cores;
- **recorte** — o seletor lê só o spec, não tem paleta nem luz próprias e
  respeita o teto.
"""

from __future__ import annotations

import colorsys
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from assetflow.generation.engines.desenhista.rasterizador import desenhar
from assetflow.generation.engines.desenhista.receita import ler_receita
from assetflow.generation.schemas import AssetType
from assetflow.generation.schemas.resolved_spec import (
    BodyType,
    LogicalResolution,
    ResolvedPalette,
)
from assetflow.pixel_knowledge import (
    CLASSES,
    SEM_CORPO,
    TETO_CARACTERES,
    USO_DO_MOLDE,
    BaseDeConhecimento,
    Estilo,
    Molde,
    luminancia,
    montar_recorte,
)
from assetflow.pixel_knowledge.recorte import _deslocar
from tests.conftest import BACKEND_ROOT

DIRETORIO = BACKEND_ROOT / "config" / "pixel_knowledge"


@pytest.fixture(scope="module")
def base() -> BaseDeConhecimento:
    return BaseDeConhecimento.do_diretorio(DIRETORIO)


def _spec(
    largura: int = 32,
    altura: int = 32,
    *,
    tipo: AssetType = AssetType.CHARACTER,
    corpo: BodyType = BodyType.HUMANOID,
    paleta: ResolvedPalette | None = None,
    luz: str | None = None,
    pixel: bool = True,
) -> SimpleNamespace:
    """Um spec com **só** os campos que o seletor pode ler.

    Não é um ``FinalResolvedSpec`` de propósito: se o seletor passar a ler
    outro campo (o prompt, o profile), o teste quebra com ``AttributeError``.
    """
    return SimpleNamespace(
        logical_resolution=LogicalResolution(width=largura, height=altura) if pixel else None,
        asset=SimpleNamespace(type=tipo),
        character=SimpleNamespace(body_type=corpo),
        palette=paleta if paleta is not None else ResolvedPalette(max_colors=8),
        style=SimpleNamespace(shading=SimpleNamespace(light_direction=luz)),
    )


def _copia(tmp_path: Path) -> Path:
    destino = tmp_path / "pixel_knowledge"
    shutil.copytree(DIRETORIO, destino)
    return destino


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
def test_a_configuracao_real_carrega_sem_arquivo_ignorado(base: BaseDeConhecimento):
    assert base.problemas == ()
    assert base.mestra == "endesga-32"
    assert base.luz is not None
    assert set(base.formas) == {"humanoid", "prop"}


def test_todo_molde_do_diretorio_e_carregado(base: BaseDeConhecimento):
    """Um molde torto sumiria do recorte em silêncio; aqui ele é contado."""
    arquivos = sorted((DIRETORIO / "silhuetas").glob("*.yaml"))
    assert len(base.moldes) == len(arquivos) >= 2
    assert {molde.id for molde in base.moldes.values()} == {arquivo.stem for arquivo in arquivos}


def test_diretorio_ausente_da_base_vazia_e_recorte_vazio(tmp_path: Path):
    vazia = BaseDeConhecimento.do_diretorio(tmp_path / "nao-existe")

    assert vazia.esta_vazia
    assert vazia.problemas == ()
    assert montar_recorte(_spec(), vazia) == ""


def test_arquivo_torto_e_ignorado_sem_derrubar_os_outros(tmp_path: Path):
    diretorio = _copia(tmp_path)
    (diretorio / "paletas.yaml").write_text("paletas: [isto, não, é, um, mapa]\n", encoding="utf-8")

    parcial = BaseDeConhecimento.do_diretorio(diretorio)

    assert len(parcial.problemas) == 1
    assert parcial.problemas[0].startswith("paletas.yaml: paletas: mapeamento esperado")
    assert parcial.paletas == {}
    assert set(parcial.formas) == {"humanoid", "prop"}, "proporções não dependem das paletas"
    assert parcial.moldes


def test_yaml_quebrado_tambem_vira_problema(tmp_path: Path):
    diretorio = _copia(tmp_path)
    (diretorio / "luz.yaml").write_text("padrao: [sem fechar\n", encoding="utf-8")

    parcial = BaseDeConhecimento.do_diretorio(diretorio)

    assert parcial.luz is None
    assert [problema.split(":")[0] for problema in parcial.problemas] == ["luz.yaml"]


# ---------------------------------------------------------------------------
# Formato: paletas
# ---------------------------------------------------------------------------
#: Quantas cores cada paleta pública tem no Lospec.
CORES_NO_LOSPEC = {"endesga-32": 32, "sweetie-16": 16, "pico-8": 16, "dawnbringer-16": 16}


def test_paletas_publicas_tem_o_tamanho_e_a_origem_do_lospec(base: BaseDeConhecimento):
    assert {pid: len(paleta.cores) for pid, paleta in base.paletas.items()} == CORES_NO_LOSPEC
    for pid, paleta in base.paletas.items():
        assert paleta.fonte == f"https://lospec.com/palette-list/{pid}"
        assert paleta.conferida_em, f"{pid}: sem data de conferência"


def test_contorno_e_a_cor_mais_escura(base: BaseDeConhecimento):
    for paleta in base.paletas.values():
        assert paleta.contorno == min(paleta.cores, key=luminancia)


def test_rampas_vao_do_escuro_ao_claro_com_cores_da_paleta(base: BaseDeConhecimento):
    for paleta in base.paletas.values():
        for material, rampa in paleta.rampas.items():
            assert set(rampa) <= set(paleta.cores), f"{paleta.id}.{material}"
            valores = [luminancia(cor) for cor in rampa]
            assert valores == sorted(valores) and len(set(valores)) == len(valores), (
                f"{paleta.id}.{material} não vai do escuro ao claro"
            )


def test_a_mestra_tem_rampa_dos_materiais_do_documento(base: BaseDeConhecimento):
    """§5: pele, metal, madeira, folha, pedra, tecido."""
    rampas = set(base.paletas[base.mestra].rampas)
    assert {"pele", "metal", "madeira", "folha", "pedra"} <= rampas
    assert any(material.startswith("tecido") for material in rampas)


@pytest.mark.parametrize(
    ("trecho", "erro"),
    [
        ('"#BE4A2F"', "em minúsculas"),
        ('"#zzzzzz"', "#rrggbb"),
    ],
)
def test_cor_fora_do_formato_e_recusada(tmp_path: Path, trecho: str, erro: str):
    diretorio = _copia(tmp_path)
    arquivo = diretorio / "paletas.yaml"
    arquivo.write_text(arquivo.read_text(encoding="utf-8").replace('"#be4a2f"', trecho, 1), encoding="utf-8")

    problemas = BaseDeConhecimento.do_diretorio(diretorio).problemas

    assert len(problemas) == 1 and erro in problemas[0]


def test_rampa_fora_de_ordem_e_recusada(tmp_path: Path):
    diretorio = _copia(tmp_path)
    arquivo = diretorio / "paletas.yaml"
    texto = arquivo.read_text(encoding="utf-8").replace(
        'pedra:           ["#262b44", "#3a4466"', 'pedra:           ["#3a4466", "#262b44"', 1
    )
    arquivo.write_text(texto, encoding="utf-8")

    problemas = BaseDeConhecimento.do_diretorio(diretorio).problemas

    assert len(problemas) == 1 and "do escuro ao claro" in problemas[0]


# ---------------------------------------------------------------------------
# Formato: classe e origem de cada regra
# ---------------------------------------------------------------------------
def _todas_as_regras(base: BaseDeConhecimento):
    yield from base.luz.regras
    for forma in base.formas.values():
        yield from forma.regras


def _todas_as_medidas(base: BaseDeConhecimento):
    for forma in base.formas.values():
        for medidas in forma.tamanhos.values():
            yield from medidas.values()


def test_toda_regra_e_medida_declara_classe_e_secao(base: BaseDeConhecimento):
    for item in [*_todas_as_regras(base), *_todas_as_medidas(base)]:
        assert item.classe in CLASSES
        assert item.secao.startswith("§")


def test_numero_sem_fonte_leva_a_calibrar(base: BaseDeConhecimento):
    for medida in _todas_as_medidas(base):
        assert medida.fonte or medida.a_calibrar, medida.nome
    for regra in _todas_as_regras(base):
        if any(caractere.isdigit() for caractere in regra.texto):
            assert regra.fonte or regra.a_calibrar, regra.texto


def test_a_carga_recusa_numero_sem_fonte(tmp_path: Path):
    diretorio = _copia(tmp_path)
    arquivo = diretorio / "proporcoes.yaml"
    texto = arquivo.read_text(encoding="utf-8").replace(
        'largura_braco_px:  {valor: 5,      classe: style,    secao: "§9", a_calibrar: true}',
        'largura_braco_px:  {valor: 5,      classe: style,    secao: "§9"}',
        1,
    )
    arquivo.write_text(texto, encoding="utf-8")

    problemas = BaseDeConhecimento.do_diretorio(diretorio).problemas

    assert len(problemas) == 1, "a troca no YAML precisa ter acontecido"
    assert "número sem fonte; marque a_calibrar: true" in problemas[0]


def test_a_carga_recusa_classe_desconhecida(tmp_path: Path):
    diretorio = _copia(tmp_path)
    arquivo = diretorio / "luz.yaml"
    arquivo.write_text(
        arquivo.read_text(encoding="utf-8").replace("classe: style", "classe: gosto", 1),
        encoding="utf-8",
    )

    problemas = BaseDeConhecimento.do_diretorio(diretorio).problemas

    assert len(problemas) == 1 and "não é uma classe" in problemas[0]


# ---------------------------------------------------------------------------
# Proporções
# ---------------------------------------------------------------------------
def _humanoides(base: BaseDeConhecimento):
    for tamanho, medidas in base.formas["humanoid"].tamanhos.items():
        yield tamanho, {nome: medida.valor for nome, medida in medidas.items()}


def test_as_partes_somam_a_altura(base: BaseDeConhecimento):
    for tamanho, m in _humanoides(base):
        assert m["cabeca_px"] + m["tronco_px"] + m["pernas_px"] == m["altura_px"], tamanho


def test_a_altura_em_cabecas_bate_com_as_medidas(base: BaseDeConhecimento):
    """`cabecas` é faixa (da fonte) ou valor (nosso); nos dois, a conta fecha."""
    for tamanho, m in _humanoides(base):
        razao = m["altura_px"] / m["cabeca_px"]
        if isinstance(m["cabecas"], tuple):
            minimo, maximo = m["cabecas"]
            assert minimo <= razao <= maximo, tamanho
        else:
            assert razao == pytest.approx(m["cabecas"], abs=0.05), tamanho


def test_chao_topo_e_folga_cabem_na_grade_com_margem(base: BaseDeConhecimento):
    for forma in base.formas.values():
        for tamanho, medidas in forma.tamanhos.items():
            altura_da_grade = int(tamanho.split("x")[1])
            chao = medidas["chao_y"].valor
            assert chao <= altura_da_grade - 2, f"{forma.id} {tamanho}: sem margem embaixo"
            if "altura_px" in medidas:
                topo = chao - medidas["altura_px"].valor + 1
                folga = medidas["folga_topo_px"].valor if "folga_topo_px" in medidas else 0
                assert topo - folga >= 1, f"{forma.id} {tamanho}: topo ou folga sem margem"


def test_humanoide_32_tem_cabeca_de_10_e_larguras_a_calibrar(base: BaseDeConhecimento):
    medidas = base.formas["humanoid"].tamanhos["32x32"]
    assert medidas["cabeca_px"].valor == 10
    larguras = sorted(nome for nome in medidas if nome.startswith("largura_"))
    assert larguras == [
        "largura_braco_px",
        "largura_cabeca_px",
        "largura_perna_px",
        "largura_tronco_px",
    ]
    assert all(medidas[nome].a_calibrar for nome in larguras)


def test_vao_entre_membros_so_vale_com_o_membro_a_mostra(base: BaseDeConhecimento):
    """Com manto, capa ou vestido, a silhueta é da roupa, e o vão não é exigido."""
    regra = next(r for r in base.formas["humanoid"].regras if r.texto.startswith("vão entre braço"))

    assert "quando a roupa deixa o membro à mostra" in regra.texto
    for roupa in ("manto", "capa", "vestido", "roupa larga"):
        assert roupa in regra.texto
    assert regra.texto in montar_recorte(_spec(), base)


def test_regras_de_sombra_e_de_equipamento(base: BaseDeConhecimento):
    assert any("vizinho imediato da rampa" in regra.texto for regra in base.luz.regras)
    assert any(
        "equipamento muda o contorno" in regra.texto for regra in base.formas["humanoid"].regras
    )


def test_tecido_vermelho_da_mestra_fica_perto_do_vermelho(base: BaseDeConhecimento):
    """O tom escuro era um roxo (#68386c), a mais de 60° do vermelho."""
    for cor in base.paletas[base.mestra].rampas["tecido_vermelho"]:
        r, g, b = (int(cor[i : i + 2], 16) / 255 for i in (1, 3, 5))
        matiz = colorsys.rgb_to_hsv(r, g, b)[0] * 360
        assert min(matiz, 360 - matiz) <= 30, cor


# ---------------------------------------------------------------------------
# Moldes
# ---------------------------------------------------------------------------
def _moldes() -> list[Molde]:
    return sorted(BaseDeConhecimento.do_diretorio(DIRETORIO).moldes.values(), key=lambda m: m.id)


def _linhas(molde: Molde) -> list[str]:
    desenho = desenhar(ler_receita(dict(molde.receita)), *molde.grade)
    assert desenho.avisos == (), f"{molde.id}: {desenho.avisos}"
    return desenho.grade.linhas()


@pytest.mark.parametrize("molde", _moldes(), ids=lambda m: m.id)
def test_molde_e_receita_valida_da_desenhista(molde: Molde):
    linhas = _linhas(molde)
    assert any(linha.strip(".") for linha in linhas)


@pytest.mark.parametrize("molde", _moldes(), ids=lambda m: m.id)
def test_molde_pisa_na_linha_de_chao_das_proporcoes(base: BaseDeConhecimento, molde: Molde):
    medidas = base.formas[molde.forma].tamanhos[molde.tamanho]
    opacas = [y for y, linha in enumerate(_linhas(molde)) if linha.strip(".")]

    assert opacas[-1] == medidas["chao_y"].valor
    if "altura_px" in medidas:
        assert opacas[-1] - opacas[0] + 1 == medidas["altura_px"].valor


def _so_camada(molde: Molde, nome: str) -> list[str]:
    receita = dict(molde.receita)
    receita["camadas"] = [camada for camada in molde.receita["camadas"] if camada["nome"] == nome]
    return desenhar(ler_receita(receita), *molde.grade).grade.linhas()


def _corridas(linha: str) -> list[int]:
    """Comprimento de cada trecho opaco da linha, da esquerda para a direita."""
    return [len(trecho) for trecho in linha.split(".") if trecho]


def test_molde_humanoide_segue_faixas_e_larguras(base: BaseDeConhecimento):
    """O molde é a medida desenhada: cada parte na faixa e na largura do YAML."""
    molde = base.moldes[("humanoid", "32x32")]
    m = {nome: medida.valor for nome, medida in base.formas["humanoid"].tamanhos["32x32"].items()}
    topo = m["chao_y"] - m["altura_px"] + 1
    faixas = {
        "cabeca": (topo, topo + m["cabeca_px"] - 1),
        "tronco": (topo + m["cabeca_px"], topo + m["cabeca_px"] + m["tronco_px"] - 1),
        "pernas": (m["chao_y"] - m["pernas_px"] + 1, m["chao_y"]),
    }
    for nome, (inicio, fim) in faixas.items():
        opacas = [y for y, linha in enumerate(_so_camada(molde, nome)) if linha.strip(".")]
        assert (opacas[0], opacas[-1]) == (inicio, fim), nome

    meio_tronco = sum(faixas["tronco"]) // 2
    meio_pernas = sum(faixas["pernas"]) // 2
    cabeca = _so_camada(molde, "cabeca")
    assert max(len(linha.strip(".")) for linha in cabeca) == m["largura_cabeca_px"]
    assert _corridas(_so_camada(molde, "tronco")[meio_tronco]) == [m["largura_tronco_px"]]
    for braco in ("braco_dir", "braco_esq"):
        assert _corridas(_so_camada(molde, braco)[meio_tronco]) == [m["largura_braco_px"]], braco
    assert _corridas(_so_camada(molde, "pernas")[meio_pernas]) == [m["largura_perna_px"]] * 2


@pytest.mark.parametrize("molde", _moldes(), ids=lambda m: m.id)
def test_molde_respeita_a_margem_de_um_pixel(molde: Molde):
    linhas = _linhas(molde)
    largura, altura = molde.grade
    assert not linhas[0].strip(".") and not linhas[altura - 1].strip(".")
    assert all(linha[0] == "." and linha[largura - 1] == "." for linha in linhas)


@pytest.mark.parametrize("molde", _moldes(), ids=lambda m: m.id)
def test_molde_cabe_num_pedido_de_8_cores(molde: Molde):
    """A desenhista conta cor por **chave** da paleta, não por hexadecimal."""
    assert len(molde.receita["paleta"]) <= 8


@pytest.mark.parametrize("molde", _moldes(), ids=lambda m: m.id)
def test_molde_usa_cores_da_paleta_mestra(base: BaseDeConhecimento, molde: Molde):
    mestra = base.paletas[base.mestra]
    assert set(molde.receita["paleta"].values()) <= set(mestra.cores)


def test_molde_humanoide_separa_as_partes_em_camadas(base: BaseDeConhecimento):
    """Remendo e animação (Fase 6) trocam uma parte sem reenviar o resto."""
    molde = base.moldes[("humanoid", "32x32")]
    nomes = [camada["nome"] for camada in molde.receita["camadas"]]
    assert sorted(nomes) == ["braco_dir", "braco_esq", "cabeca", "pernas", "tronco"]


def test_chaves_documentadas_tem_de_bater_com_a_paleta(tmp_path: Path):
    diretorio = _copia(tmp_path)
    arquivo = diretorio / "silhuetas" / "prop_32x32.yaml"
    arquivo.write_text(
        arquivo.read_text(encoding="utf-8").replace("  M: brilho do metal\n", "", 1),
        encoding="utf-8",
    )

    parcial = BaseDeConhecimento.do_diretorio(diretorio)

    assert ("prop", "32x32") not in parcial.moldes
    assert len(parcial.problemas) == 1 and "chaves" in parcial.problemas[0]


# ---------------------------------------------------------------------------
# Recorte
# ---------------------------------------------------------------------------
def test_recorte_do_cavaleiro_traz_medidas_e_nao_a_receita(base: BaseDeConhecimento):
    recorte = montar_recorte(_spec(), base)
    linhas = recorte.splitlines()

    assert linhas[0] == (
        "humanóide 32×32: cabeça y3–12 (10 px) · tronco y13–20 (8 px) · pernas y21–30 (10 px)"
        " · chão y=30 (pixel opaco mais baixo)"
        " · folga y1–2 acima da cabeça, para crista, penacho ou cabelo"
        " · larguras com contorno: cabeça 12, tronco 12, braço 5, perna 5"
        " · olho 2×2 com brilho de 1 px · 3 tons por material"
    )
    assert linhas[1] == (
        "quadro: corpo centrado entre x=15 e x=16, com braços em x4–27 (colunas contando o"
        " braço separado do tronco por 1 px, o que só vale com o membro à mostra); livre x1–3"
        " e x28–30 dos lados, para arma, escudo, crista e animação"
    )
    assert linhas[2].startswith("luz: de cima e da esquerda (padrão da base; o pedido não definiu)")
    assert linhas[3].startswith("cores: até 8, contorno incluído · paleta-mestra endesga-32")
    assert "  contorno #181425" in linhas
    assert any(linha.startswith("silhueta: arma e escudo fora do corpo") for linha in linhas)
    assert linhas[-1] == (
        "camadas: pernas, tronco, braco_dir, braco_esq, cabeca (direita e esquerda do"
        " personagem) · a receita do molde-base vem com molde=true"
    )
    assert "{" not in recorte and USO_DO_MOLDE not in recorte
    assert len(recorte) <= TETO_CARACTERES


def test_com_molde_a_receita_vem_no_lugar_da_linha_de_camadas(base: BaseDeConhecimento):
    recorte = montar_recorte(_spec(), base, molde=True)
    linhas = recorte.splitlines()

    assert linhas[-3].startswith("molde humanoid_32x32: manequim de frente")
    assert linhas[-2].startswith('{"grade":[32,32],"paleta":')
    assert linhas[-1] == USO_DO_MOLDE
    assert not any(linha.startswith("camadas: ") for linha in linhas)
    assert len(recorte) <= TETO_CARACTERES


def test_recorte_de_objeto_usa_as_medidas_e_o_molde_de_prop(base: BaseDeConhecimento):
    objeto = _spec(tipo=AssetType.PROP, corpo=BodyType.UNKNOWN)
    recorte = montar_recorte(objeto, base)

    assert recorte.startswith("objeto 32×32: chão y=30 (pixel opaco mais baixo) · margem 1 px")
    assert recorte.endswith(
        "camadas: topo, frente, detalhe · a receita do molde-base vem com molde=true"
    )
    assert "molde prop_32x32: " in montar_recorte(objeto, base, molde=True)


def test_corpo_desconhecido_nao_vira_humanoide(base: BaseDeConhecimento):
    recorte = montar_recorte(_spec(corpo=BodyType.UNKNOWN), base)
    linhas = recorte.splitlines()

    assert "humanóide" not in recorte and "molde" not in recorte
    # A falta de medidas é dita, não omitida: quem desenha sabe o que pedir.
    assert linhas[0] == SEM_CORPO
    assert linhas[1].startswith("luz: "), "paleta e luz valem para qualquer forma"


def test_corpo_conhecido_sem_tabela_nao_finge_que_e_desconhecido(base: BaseDeConhecimento):
    """Quadrúpede não tem medidas na base, mas o corpo foi identificado: a
    linha de corpo `unknown` diria uma coisa falsa."""
    recorte = montar_recorte(_spec(corpo=BodyType.QUADRUPED), base)

    assert SEM_CORPO not in recorte
    assert recorte.startswith("luz: ")


def test_tamanho_sem_tabela_fica_sem_proporcao_e_sem_molde(base: BaseDeConhecimento):
    recorte = montar_recorte(_spec(24, 24), base)

    assert "×" not in recorte.splitlines()[0]
    assert "molde" not in recorte
    assert "silhueta: " in recorte, "as regras de silhueta não dependem do tamanho"


def test_pedido_que_nao_e_pixel_art_nao_tem_recorte(base: BaseDeConhecimento):
    assert montar_recorte(_spec(pixel=False), base) == ""


def test_paleta_travada_do_pedido_tira_as_rampas(base: BaseDeConhecimento):
    travada = ResolvedPalette(mode="locked", max_colors=3, colors=("#000000", "#ff0000", "#ffffff"))
    recorte = montar_recorte(_spec(paleta=travada), base)

    assert "cores: paleta travada pelo pedido, use só estas: #000000 #ff0000 #ffffff" in recorte
    assert "paleta-mestra" not in recorte and "#181425" not in recorte


def test_luz_do_pedido_ganha_do_padrao_da_base(base: BaseDeConhecimento):
    recorte = montar_recorte(_spec(luz="top_right"), base)

    assert "luz: top_right (do pedido)" in recorte
    assert "de cima e da esquerda" not in recorte


def test_mestra_e_luz_vem_da_configuracao(tmp_path: Path):
    """Nada de paleta ou luz fixas no código: trocar o YAML troca o recorte."""
    diretorio = _copia(tmp_path)
    paletas = diretorio / "paletas.yaml"
    paletas.write_text(
        paletas.read_text(encoding="utf-8").replace("mestra: endesga-32", "mestra: sweetie-16"),
        encoding="utf-8",
    )
    luz = diretorio / "luz.yaml"
    luz.write_text(
        luz.read_text(encoding="utf-8").replace(
            "padrao: de cima e da esquerda", "padrao: de cima e da direita"
        ),
        encoding="utf-8",
    )

    recorte = montar_recorte(_spec(), BaseDeConhecimento.do_diretorio(diretorio))

    assert "paleta-mestra sweetie-16" in recorte and "contorno #1a1c2c" in recorte
    assert "luz: de cima e da direita (padrão da base" in recorte


def test_sem_mestra_nem_luz_na_configuracao_as_linhas_somem(tmp_path: Path):
    diretorio = _copia(tmp_path)
    (diretorio / "luz.yaml").unlink()
    paletas = diretorio / "paletas.yaml"
    paletas.write_text(
        paletas.read_text(encoding="utf-8").replace("mestra: endesga-32\n", ""), encoding="utf-8"
    )

    recorte = montar_recorte(_spec(), BaseDeConhecimento.do_diretorio(diretorio))

    assert "luz:" not in recorte
    assert "cores: até 8, contorno incluído" in recorte and "paleta-mestra" not in recorte


def test_o_estilo_e_o_ponto_unico_de_paleta_luz_proporcoes_e_moldes(
    base: BaseDeConhecimento, monkeypatch: pytest.MonkeyPatch
):
    """Uma fase de estilos troca :meth:`estilo`; o seletor não muda."""
    outro = Estilo(paleta=base.paletas["sweetie-16"], luz=None, formas={}, moldes={})
    monkeypatch.setattr(BaseDeConhecimento, "estilo", lambda self: outro)

    recorte = montar_recorte(_spec(), base)

    assert "paleta-mestra sweetie-16" in recorte
    assert "humanóide" not in recorte and "luz:" not in recorte and "molde" not in recorte


def test_teto_tira_secoes_inteiras_e_diz_quais(base: BaseDeConhecimento):
    completo = montar_recorte(_spec(), base, molde=True)
    # Cabe tudo até a silhueta, mais a linha que diz o que saiu (~45 caracteres).
    teto = completo.index("molde humanoid_32x32") + 50

    cortado = montar_recorte(_spec(), base, molde=True, teto=teto)

    assert len(cortado) <= teto
    assert cortado.endswith(f"omitido pelo teto de {teto} caracteres: molde")
    assert "silhueta: " in cortado and "{" not in cortado


def test_teto_corta_na_ordem_de_prioridade(base: BaseDeConhecimento):
    # Proporções são duas linhas (medidas e quadro); depois vem a luz.
    primeiras = montar_recorte(_spec(), base).splitlines()[:3]
    # Cabem proporções e luz, mais a linha do que saiu; as cores já não cabem.
    teto = sum(map(len, primeiras)) + 3 + 70

    cortado = montar_recorte(_spec(), base, teto=teto)

    assert cortado.splitlines()[:3] == primeiras
    assert cortado.splitlines()[-1] == (
        f"omitido pelo teto de {teto} caracteres: cores, silhueta, molde"
    )


# ---------------------------------------------------------------------------
# Corpo num quadro maior
# ---------------------------------------------------------------------------
def test_quadro_de_48_traz_o_corpo_de_32_centrado_e_no_chao_do_quadro(base: BaseDeConhecimento):
    linhas = montar_recorte(_spec(48, 48), base).splitlines()

    assert linhas[0] == (
        "humanóide, corpo 32×32 num quadro 48×48: cabeça y19–28 (10 px) · tronco y29–36 (8 px)"
        " · pernas y37–46 (10 px) · chão y=46 (pixel opaco mais baixo)"
        " · folga y17–18 acima da cabeça, para crista, penacho ou cabelo"
        " · larguras com contorno: cabeça 12, tronco 12, braço 5, perna 5"
        " · olho 2×2 com brilho de 1 px · 3 tons por material"
    )
    assert linhas[1] == (
        "quadro: corpo centrado entre x=23 e x=24, com braços em x12–35 (colunas contando o"
        " braço separado do tronco por 1 px, o que só vale com o membro à mostra); livre"
        " x1–11 e x36–46 dos lados e y1–16 acima, para arma, escudo, crista e animação"
    )
    assert linhas[-1].startswith("camadas: pernas, tronco, braco_dir, braco_esq, cabeca")


def test_quadro_sem_tabela_fica_sem_proporcoes(base: BaseDeConhecimento):
    recorte = montar_recorte(_spec(40, 40), base)
    assert recorte.startswith("luz: ") and "quadro:" not in recorte and "camadas:" not in recorte


def test_molde_no_quadro_de_48_vem_deslocado_e_desenha_o_mesmo_corpo(base: BaseDeConhecimento):
    molde = base.moldes[("humanoid", "32x32")]
    linhas = montar_recorte(_spec(48, 48), base, molde=True).splitlines()
    cabecalho = next(linha for linha in linhas if linha.startswith("molde "))
    receita = json.loads(next(linha for linha in linhas if linha.startswith("{")))

    assert cabecalho.startswith("molde humanoid_32x32 (deslocado +8, +16 para o quadro 48×48): ")
    assert receita["grade"] == [48, 48]
    assert molde.receita["grade"] == [32, 32], "o molde da base não pode ser alterado"

    grande = desenhar(ler_receita(receita), 48, 48).grade.linhas()
    pequeno = desenhar(ler_receita(dict(molde.receita)), 32, 32).grade.linhas()
    assert [linha[8:40] for linha in grande[16:48]] == pequeno
    opacas = [y for y, linha in enumerate(grande) if linha.strip(".")]
    assert opacas[-1] == 46, "pés no chão do quadro"


def test_deslocar_move_toda_operacao():
    receita = {
        "grade": [8, 8],
        "paleta": {"a": "#000000"},
        "camadas": [{"nome": "c", "ops": [
            {"ret": [0, 0, 2, 2], "cor": "a"},
            {"elipse": [1, 1, 3, 3], "cor": "a"},
            {"linha": [0, 0, 3, 3], "cor": "a"},
            {"poligono": [0, 0, 2, 0, 1, 2], "cor": "a"},
            {"balde": [5, 5], "cor": "a"},
            {"px": ["a"], "em": [4, 4]},
        ]}],
    }
    ops = _deslocar(receita, 2, 3, (12, 12))["camadas"][0]["ops"]

    assert [op.get("ret") or op.get("elipse") or op.get("linha") or op.get("poligono")
            or op.get("balde") or op.get("em") for op in ops] == [
        [2, 3, 2, 2], [3, 4, 3, 3], [2, 3, 5, 6], [2, 3, 4, 3, 3, 5], [7, 8], [6, 7],
    ]
    assert receita["camadas"][0]["ops"][0]["ret"] == [0, 0, 2, 2], "a original fica como era"


@pytest.mark.parametrize(
    ("bloco", "erro"),
    [
        ('"48x48":\n        corpo: "24x24"', "não está em tamanhos"),
        ('"47x48":\n        corpo: "32x32"', "é ímpar"),
        ('"32x32":\n        corpo: "16x16"', "já é um tamanho de corpo"),
    ],
)
def test_a_carga_recusa_quadro_torto(tmp_path: Path, bloco: str, erro: str):
    diretorio = _copia(tmp_path)
    arquivo = diretorio / "proporcoes.yaml"
    texto = arquivo.read_text(encoding="utf-8")
    original = '"48x48":\n        corpo: "32x32"'
    assert original in texto
    arquivo.write_text(texto.replace(original, bloco, 1), encoding="utf-8")

    problemas = BaseDeConhecimento.do_diretorio(diretorio).problemas

    assert len(problemas) == 1 and erro in problemas[0]
