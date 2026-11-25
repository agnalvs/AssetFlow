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
    TETO_CARACTERES,
    USO_DO_MOLDE,
    BaseDeConhecimento,
    Estilo,
    Molde,
    luminancia,
    montar_recorte,
)
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
        'braco_px:          {valor: 2,      classe: style,    secao: "§9", a_calibrar: true}',
        'braco_px:          {valor: 2,      classe: style,    secao: "§9"}',
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


def test_a_altura_em_cabecas_cai_na_faixa_da_fonte(base: BaseDeConhecimento):
    for tamanho, m in _humanoides(base):
        minimo, maximo = m["cabecas"]
        assert minimo <= m["altura_px"] / m["cabeca_px"] <= maximo, tamanho


def test_chao_e_topo_cabem_na_grade_com_margem(base: BaseDeConhecimento):
    for forma in base.formas.values():
        for tamanho, medidas in forma.tamanhos.items():
            altura_da_grade = int(tamanho.split("x")[1])
            chao = medidas["chao_y"].valor
            assert chao <= altura_da_grade - 2, f"{forma.id} {tamanho}: sem margem embaixo"
            if "altura_px" in medidas:
                assert chao - medidas["altura_px"].valor + 1 >= 1, f"{forma.id} {tamanho}: topo"


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
def test_recorte_do_cavaleiro(base: BaseDeConhecimento):
    recorte = montar_recorte(_spec(), base)
    linhas = recorte.splitlines()

    assert linhas[0].startswith(
        "humanóide 32×32: altura 28 = cabeça 8 + tronco 9 + pernas 11 · topo y=3, chão y=30"
    )
    assert "olho 2×2 com brilho de 1 px" in linhas[0]
    assert linhas[1].startswith("luz: de cima e da esquerda (padrão da base; o pedido não definiu)")
    assert linhas[2].startswith("cores: até 8, contorno incluído · paleta-mestra endesga-32")
    assert "  contorno #181425" in linhas
    assert any(linha.startswith("silhueta: arma e escudo fora do corpo") for linha in linhas)
    assert any(linha.startswith("molde humanoid_32x32: ") for linha in linhas)
    assert linhas[-1] == USO_DO_MOLDE
    assert len(recorte) <= TETO_CARACTERES


def test_recorte_de_objeto_traz_o_molde_de_prop(base: BaseDeConhecimento):
    recorte = montar_recorte(_spec(tipo=AssetType.PROP, corpo=BodyType.UNKNOWN), base)

    assert recorte.startswith("objeto 32×32: chão y=30 (pixel opaco mais baixo) · margem 1 px")
    assert "molde prop_32x32: " in recorte


def test_corpo_desconhecido_nao_vira_humanoide(base: BaseDeConhecimento):
    recorte = montar_recorte(_spec(corpo=BodyType.UNKNOWN), base)

    assert "humanóide" not in recorte and "molde" not in recorte
    assert recorte.startswith("luz: "), "paleta e luz valem para qualquer forma"


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
    assert "paleta-mestra" not in recorte and "#181425" not in recorte.split("{", 1)[0]


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
    completo = montar_recorte(_spec(), base)
    # Cabe tudo até a silhueta, mais a linha que diz o que saiu (~45 caracteres).
    teto = completo.index("molde humanoid_32x32") + 50

    cortado = montar_recorte(_spec(), base, teto=teto)

    assert len(cortado) <= teto
    assert cortado.endswith(f"omitido pelo teto de {teto} caracteres: molde")
    assert "silhueta: " in cortado and "{" not in cortado


def test_teto_corta_na_ordem_de_prioridade(base: BaseDeConhecimento):
    cortado = montar_recorte(_spec(), base, teto=600)

    assert cortado.startswith("humanóide 32×32: ")
    assert cortado.splitlines()[-1] == (
        "omitido pelo teto de 600 caracteres: cores, silhueta, molde"
    )
