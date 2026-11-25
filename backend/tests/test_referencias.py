"""Biblioteca de referências: medidor, importador, coleção, recorte e calibração.

Tudo com imagens pequenas criadas aqui mesmo — nenhum pacote baixado entra na
suíte. Os sprites de teste são retângulos com contorno e três tons, o bastante
para cada medida ter resposta conhecida.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from assetflow.generation.schemas import AssetType
from assetflow.generation.schemas.resolved_spec import (
    BodyType,
    LogicalResolution,
    ResolvedPalette,
)
from assetflow.pixel_knowledge import BaseDeConhecimento, montar_recorte
from assetflow.referencias import (
    LICENCA_PRINCIPAL,
    Parte,
    ReferenciaInvalida,
    ReferenciasAtivas,
    gerar_relatorio,
    importar,
    ler_configuracao,
    ler_manifesto,
    normalizar_licenca,
)
from assetflow.referencias.medidor import (
    detectar_escala,
    fatiar,
    medir_quadro,
    quadro_do_nome,
)
from tests.conftest import BACKEND_ROOT

CONHECIMENTO = BACKEND_ROOT / "config" / "pixel_knowledge"

ESCURO = (16, 16, 24)
VERMELHO = ((224, 96, 96), (160, 48, 48), (112, 32, 32))  # luz, base, sombra
AZUL = ((96, 128, 224), (48, 72, 160), (32, 48, 112))


# ---------------------------------------------------------------------------
# Sprites de teste
# ---------------------------------------------------------------------------
def _figura(
    altura: int,
    largura: int,
    quadro: tuple[int, int] | None = None,
    *,
    contorno: str = "escuro",
    tons: tuple = VERMELHO,
) -> np.ndarray:
    """Um retângulo de ``largura × altura`` com contorno e três tons, de pé no quadro."""
    ql, qa = quadro or (largura + 2, altura + 2)
    rgba = np.zeros((qa, ql, 4), dtype=np.uint8)
    x0, y0 = (ql - largura) // 2, qa - 1 - altura
    corpo = rgba[y0 : y0 + altura, x0 : x0 + largura]
    corpo[..., 3] = 255
    corpo[..., :3] = tons[1]
    corpo[:, 1, :3] = tons[0]
    corpo[:, -2, :3] = tons[2]
    if contorno == "escuro":
        borda = ESCURO
        for fatia in (corpo[0], corpo[-1], corpo[:, 0], corpo[:, -1]):
            fatia[..., :3] = borda
    elif contorno == "colorido":
        # Metade de cima contornada em vinho, metade de baixo em azul-escuro:
        # mais escuro que o miolo, mas sem cor dominante.
        meio = altura // 2
        for y in range(altura):
            cor = (64, 16, 16) if y < meio else (16, 24, 64)
            corpo[y, 0, :3] = cor
            corpo[y, -1, :3] = cor
        corpo[0, :, :3] = (64, 16, 16)
        corpo[-1, :, :3] = (16, 24, 64)
    return rgba


def _png(rgba: np.ndarray, caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(caminho)
    return caminho


def _lado_a_lado(*quadros: np.ndarray) -> np.ndarray:
    return np.concatenate(quadros, axis=1)


def _pacote(raiz: Path, origem: Path, pacote: str, partes: tuple[Parte, ...], **extra) -> None:
    importar(
        origem,
        raiz,
        pacote=pacote,
        fonte=extra.pop("fonte", "https://exemplo.invalid/pacote"),
        autor=extra.pop("autor", "Fulano"),
        licenca=extra.pop("licenca", "CC0-1.0"),
        licenca_url=extra.pop("licenca_url", "https://creativecommons.org/publicdomain/zero/1.0/"),
        partes=partes,
        **extra,
    )


def _config(caminho: Path, ativos: str, *, porte: bool = True) -> Path:
    texto = f"ativos: {ativos}\n"
    if porte:
        texto += (
            "porte:\n"
            "  faixa_altura: {valor: 0.2, classe: style, secao: \"§2\", a_calibrar: true}\n"
            "  minimo_de_quadros: {valor: 1, classe: style, secao: \"§2\", a_calibrar: true}\n"
        )
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def _spec(tipo=AssetType.CHARACTER, corpo=BodyType.HUMANOID, largura=32, altura=32):
    return SimpleNamespace(
        logical_resolution=LogicalResolution(width=largura, height=altura),
        asset=SimpleNamespace(type=tipo),
        character=SimpleNamespace(body_type=corpo),
        palette=ResolvedPalette(max_colors=8),
        style=SimpleNamespace(shading=SimpleNamespace(light_direction=None)),
    )


@pytest.fixture
def colecao(tmp_path: Path) -> ReferenciasAtivas:
    """Dois pacotes CC0: personagens de 28 px (porte do humanóide 32) e de 14 px."""
    origem = tmp_path / "baixado"
    for i, altura in enumerate((26, 28, 30)):
        _png(_figura(altura, 12, (32, 32)), origem / "Grandes" / f"heroi_{i}.png")
    for i, altura in enumerate((12, 13, 14)):
        _png(_figura(altura, 8, (16, 16), tons=AZUL), origem / "Pequenos" / f"mini_{i}.png")
    _png(_figura(10, 10, (16, 16)), origem / "Itens" / "pocao.png")
    raiz = tmp_path / "referencias"
    _pacote(
        raiz,
        origem,
        "grandes",
        (
            Parte("Grandes/**", "character", "humanoid"),
            Parte("Pequenos/**", "character", "humanoid"),
            Parte("Itens/**", "prop"),
        ),
    )
    return ReferenciasAtivas.carregar(raiz, _config(tmp_path / "referencias.yaml", "[grandes]"))


# ---------------------------------------------------------------------------
# Medidor
# ---------------------------------------------------------------------------
def test_mede_conteudo_cores_e_contorno_escuro():
    medidas = medir_quadro(_figura(14, 10, (16, 16)), conhecido=True)

    assert (medidas["altura"], medidas["largura"]) == (14, 10)
    assert medidas["cores"] == 4
    assert medidas["contorno"]["tipo"] == "escuro único"
    assert medidas["contorno"]["cor"] == "#101018"
    assert medidas["preenchimento"] == 1.0
    assert medidas["ocupacao"] == round(140 / 256, 4)
    assert (medidas["chao"], medidas["folga_topo"]) == (14, 1)


def test_contorno_colorido_e_sem_contorno():
    assert medir_quadro(_figura(14, 10, (16, 16), contorno="colorido"), conhecido=True)[
        "contorno"
    ]["tipo"] == "colorido"
    assert medir_quadro(_figura(14, 10, (16, 16), contorno="nenhum"), conhecido=True)[
        "contorno"
    ]["tipo"] == "nenhum"


def test_grupo_de_matiz_e_rampa_provavel():
    medidas = medir_quadro(_figura(14, 10, (16, 16)), conhecido=True)

    assert medidas["tons_por_grupo"] == 3, "o contorno escuro único sai dos grupos"
    assert medidas["rampas"][0] == {"cores": ["#702020", "#a03030", "#e06060"], "provavel": True}


def test_arquivo_ampliado_mede_igual_ao_original():
    original = _figura(14, 10, (16, 16))
    ampliado = np.repeat(np.repeat(original, 4, axis=0), 4, axis=1)

    assert detectar_escala(ampliado) == 4
    assert detectar_escala(original) == 1
    a = medir_quadro(ampliado[::4, ::4], conhecido=True)
    b = medir_quadro(original, conhecido=True)
    assert a == b


def test_grade_informada_fatia_e_conta_por_linha():
    vazio = np.zeros((16, 16, 4), dtype=np.uint8)
    q = _figura(12, 8, (16, 16))
    folha = np.concatenate([_lado_a_lado(q, q, q), _lado_a_lado(q, q, vazio)], axis=0)

    recortes = fatiar(folha, (16, 16))

    assert len(recortes) == 5
    assert all(r.conhecido for r in recortes)
    assert [r.linha for r in recortes] == [0, 0, 0, 1, 1]


def test_sem_grade_separa_por_colunas_transparentes():
    q = _figura(12, 8, (12, 16))
    tira = _lado_a_lado(q, q, q)

    recortes = fatiar(tira, None)

    assert len(recortes) == 3
    assert all(type(v) is int for r in recortes for v in (r.x, r.y, r.largura, r.altura)), "vai para JSON"
    assert not any(r.conhecido for r in recortes), "a caixa do conteúdo não é o quadro"
    assert fatiar(q, None)[0].conhecido, "imagem de um quadro só é o próprio quadro"


def test_folha_sem_transparencia_perde_o_fundo_solido(tmp_path: Path):
    from assetflow.referencias.medidor import carregar_com_fundo

    rgba = _figura(14, 10, (16, 16))
    rgb = rgba[..., :3].copy()
    rgb[rgba[..., 3] == 0] = (40, 200, 120)  # fundo verde, sem alpha
    caminho = tmp_path / "folha.png"
    Image.fromarray(rgb, "RGB").save(caminho)

    lido, fundo = carregar_com_fundo(caminho)

    assert fundo == "#28c878"
    assert medir_quadro(lido, conhecido=True) == medir_quadro(rgba, conhecido=True)


def test_tamanho_do_quadro_escrito_no_nome():
    assert quadro_do_nome("Idle (78x58).png") == (78, 58)
    assert quadro_do_nome("idle.png") is None


# ---------------------------------------------------------------------------
# Importador
# ---------------------------------------------------------------------------
def test_importa_so_as_partes_e_os_textos_de_licenca(tmp_path: Path):
    origem = tmp_path / "baixado"
    _png(_figura(14, 8, (16, 16)), origem / "Personagens" / "heroi.png")
    _png(_figura(10, 10, (16, 16)), origem / "Itens" / "pocao.png")
    _png(_figura(30, 30, (38, 38)), origem / "Retratos" / "rosto.png")
    (origem / "LICENSE.txt").write_text("CC0", encoding="utf-8")
    (origem / "som.wav").write_bytes(b"RIFF")

    relatorio = importar(
        origem,
        tmp_path / "referencias",
        pacote="exemplo",
        fonte="https://exemplo.invalid",
        autor="Fulano",
        licenca="cc0",
        licenca_url="https://creativecommons.org/publicdomain/zero/1.0/",
        verificada_em="2026-11-25",
        partes=(Parte("Personagens/**", "character", "humanoid"), Parte("Itens/*.png", "prop")),
    )

    pasta = tmp_path / "referencias" / "exemplo"
    assert (relatorio.copiados, relatorio.textos) == (2, 1)
    assert not (pasta / "original" / "Retratos").exists(), "fora das partes não entra"
    assert relatorio.ignorados[".png"] == 1 and relatorio.ignorados[".wav"] == 1
    manifesto = ler_manifesto(pasta)
    assert manifesto.license_id == LICENCA_PRINCIPAL and manifesto.colecao == "principal"
    assert manifesto.license_verified_at == "2026-11-25"
    assert relatorio.medicao["por_tipo"] == {"character": 1, "prop": 1}


def test_zip_com_caminho_inseguro_e_lixo_de_sistema(tmp_path: Path):
    buffer = io.BytesIO()
    Image.fromarray(_figura(14, 8, (16, 16)), "RGBA").save(buffer, format="PNG")
    png = buffer.getvalue()
    zip_ = tmp_path / "pacote.zip"
    with zipfile.ZipFile(zip_, "w") as z:
        z.writestr("Pacote/Personagens/heroi.png", png)
        z.writestr("../fora.png", png)
        z.writestr("/absoluto.png", png)
        z.writestr("__MACOSX/Pacote/Personagens/._heroi.png", b"lixo")

    raiz = tmp_path / "referencias"
    relatorio = importar(
        zip_,
        raiz,
        pacote="zipado",
        fonte="https://exemplo.invalid",
        autor="Fulano",
        licenca="CC0-1.0",
        licenca_url="https://exemplo.invalid/licenca",
        partes=(Parte("**", "character"),),
    )

    assert relatorio.copiados == 1
    assert sorted(relatorio.recusados) == ["../fora.png", "/absoluto.png"]
    assert not (tmp_path / "fora.png").exists()
    assert ler_manifesto(raiz / "zipado").origem_sha256


def test_licenca_decide_a_colecao(tmp_path: Path):
    origem = tmp_path / "baixado"
    _png(_figura(14, 8, (16, 16)), origem / "a.png")
    raiz = tmp_path / "referencias"
    _pacote(raiz, origem, "com-atribuicao", (Parte("**", "character"),), licenca="CC-BY-4.0")

    manifesto = ler_manifesto(raiz / "com-atribuicao")
    assert manifesto.colecao == "atribuicao" and manifesto.attribution_required
    assert normalizar_licenca("CC0 1.0") == LICENCA_PRINCIPAL


def test_importacao_recusa_o_que_falta_e_o_que_nao_casa(tmp_path: Path):
    origem = tmp_path / "baixado"
    _png(_figura(14, 8, (16, 16)), origem / "a.png")
    raiz = tmp_path / "referencias"

    with pytest.raises(ReferenciaInvalida, match="falta license_url"):
        _pacote(raiz, origem, "sem-url", (Parte("**", "character"),), licenca_url="")
    with pytest.raises(ReferenciaInvalida, match="nenhum PNG casou"):
        _pacote(raiz, origem, "nada-casa", (Parte("Outra/**", "character"),))
    assert not (raiz / "nada-casa").exists()
    with pytest.raises(ReferenciaInvalida, match="tipo 'heroi' desconhecido"):
        Parte.de_texto("**:heroi")
    assert Parte.de_texto("Tiles/*.png:tile:16x16") == Parte("Tiles/*.png", "tile", None, (16, 16))
    assert Parte.de_texto("A/**:character::32x32").quadro == (32, 32)

    _pacote(raiz, origem, "duas-vezes", (Parte("**", "character"),))
    with pytest.raises(ReferenciaInvalida, match="já existe"):
        _pacote(raiz, origem, "duas-vezes", (Parte("**", "character"),))


def test_excluir_tira_arquivos_de_qualquer_parte_na_importacao_e_na_medicao(tmp_path: Path):
    origem = tmp_path / "baixado"
    _png(_figura(14, 8, (16, 16)), origem / "Monstros" / "Slime" / "SpriteSheet.png")
    _png(_figura(30, 30, (38, 38)), origem / "Monstros" / "Slime" / "Faceset.png")
    _png(_figura(10, 4, (16, 16)), origem / "Itens" / "Espada" / "Sprite.png")
    _png(_figura(12, 4, (16, 16)), origem / "Itens" / "Espada" / "SpriteInHand.png")
    _png(_figura(30, 30, (38, 38)), origem / "Retratos" / "Faceset.png")  # fora das partes
    raiz = tmp_path / "referencias"

    relatorio = importar(
        origem,
        raiz,
        pacote="com-exclusao",
        fonte="https://exemplo.invalid",
        autor="Fulano",
        licenca="CC0-1.0",
        licenca_url="https://exemplo.invalid/licenca",
        partes=(Parte("Monstros/**", "character"), Parte("Itens/*/**", "prop")),
        excluir=("**/Faceset.png", "**/SpriteInHand.png"),
    )

    assert (relatorio.copiados, relatorio.excluidos) == (2, 2)
    manifesto = ler_manifesto(raiz / "com-exclusao")
    assert manifesto.excluir == ("**/Faceset.png", "**/SpriteInHand.png")
    assert manifesto.parte_de("Monstros/Slime/Faceset.png") is None
    assert manifesto.parte_de("Monstros/Slime/SpriteSheet.png").tipo == "character"

    # Um arquivo excluído que esteja em original/ (copiado à mão, por exemplo)
    # também fica fora da medição.
    _png(_figura(30, 30, (38, 38)), raiz / "com-exclusao" / "original" / "Monstros" / "Boss" / "Faceset.png")
    from assetflow.referencias import medir_pacote

    assert medir_pacote(raiz / "com-exclusao")["por_tipo"] == {"character": 1, "prop": 1}


def test_quadro_individual_ganha_do_mesmo_quadro_no_atlas(tmp_path: Path):
    origem = tmp_path / "baixado"
    f0 = _figura(12, 8, (16, 16))
    f1 = _figura(13, 8, (16, 16))
    _png(f0, origem / "frames" / "andar_f0.png")
    _png(f1, origem / "frames" / "andar_f1.png")
    _png(_lado_a_lado(f0, f1), origem / "atlas.png")
    raiz = tmp_path / "referencias"
    _pacote(raiz, origem, "atlas", (Parte("**", "character", quadro=(16, 16)),))

    import json

    medidas = json.loads((raiz / "atlas" / "medidas.json").read_text(encoding="utf-8"))
    assert medidas["repetidos"] == 2
    assert sorted(q["arquivo"] for q in medidas["quadros"]) == ["frames/andar_f0.png", "frames/andar_f1.png"]
    animacoes = {a["nome"]: a["frames"] for a in medidas["animacoes"]}
    assert animacoes == {"atlas": 2, "andar": 2}


# ---------------------------------------------------------------------------
# Coleção ativa e linha do recorte
# ---------------------------------------------------------------------------
def test_linha_em_duas_partes_estilo_e_porte(colecao: ReferenciasAtivas):
    linha = colecao.linha("character", "humanoid", 28)

    assert linha.startswith("referências: estilo de 6 quadros (1 pacote): contorno ")
    assert "· 3 tons por grupo de matiz (mediana)" in linha
    assert "; porte de 23–33 px de altura, 3 quadros (1 pacote): 4–4 cores (mediana 4)" in linha
    assert "chão" not in linha and "margem" not in linha


def test_cada_pacote_pesa_igual_nas_somas(tmp_path: Path):
    """Um pacote grande não decide o estilo sozinho."""
    raiz = tmp_path / "referencias"
    grande, pequeno = tmp_path / "grande", tmp_path / "pequeno"
    for i in range(9):
        _png(_figura(10 + i, 8, (32, 32)), grande / f"g{i}.png")
    _png(_figura(20, 8, (32, 32), contorno="nenhum"), pequeno / "p.png")
    _png(_figura(21, 8, (32, 32), contorno="nenhum"), pequeno / "q.png")
    _pacote(raiz, grande, "grande", (Parte("**", "character"),))
    _pacote(raiz, pequeno, "pequeno", (Parte("**", "character"),))
    colecao = ReferenciasAtivas.carregar(raiz, _config(tmp_path / "r.yaml", "[grande, pequeno]"))

    linha = colecao.linha("character", None, None)

    assert "estilo de 11 quadros (2 pacotes, peso igual): contorno " in linha
    assert " em 50% " in linha, "9 contra 2 quadros, mas um pacote contra outro"


def test_cada_parte_da_linha_some_sozinha(colecao: ReferenciasAtivas):
    sem_altura = colecao.linha("prop", None, None)
    assert sem_altura.startswith("referências: estilo de 1 quadros") and "porte" not in sem_altura
    fora_da_faixa = colecao.linha("character", "humanoid", 60)
    assert "estilo" in fora_da_faixa and "porte" not in fora_da_faixa
    assert colecao.linha("tile", None, 28) == ""
    assert colecao.linha("character", "quadruped", 28) == "", "corpo conhecido filtra"


def test_so_pacote_ativo_e_autorizado_entra(tmp_path: Path):
    origem = tmp_path / "baixado"
    _png(_figura(28, 12, (32, 32)), origem / "a.png")
    raiz = tmp_path / "referencias"
    _pacote(raiz, origem, "livre", (Parte("**", "character"),))
    _pacote(raiz, origem, "atribuido", (Parte("**", "character"),), licenca="CC-BY-4.0")
    _pacote(raiz, origem, "inativo", (Parte("**", "character"),))

    sem_aceite = ReferenciasAtivas.carregar(raiz, _config(tmp_path / "a.yaml", "[livre, atribuido, sumido]"))
    assert [p.id for p in sem_aceite.pacotes] == ["livre"]
    assert any("exige atribuição" in aviso for aviso in sem_aceite.avisos)
    assert any("'sumido'" in aviso for aviso in sem_aceite.avisos)

    com_aceite = ReferenciasAtivas.carregar(
        raiz, _config(tmp_path / "b.yaml", "[livre, {atribuido: {aceitar_atribuicao: true}}]")
    )
    assert [p.id for p in com_aceite.pacotes] == ["livre", "atribuido"]


def test_sem_pasta_nem_configuracao_tudo_some(tmp_path: Path):
    vazia = ReferenciasAtivas.carregar(tmp_path / "nao-existe", tmp_path / "nao-existe.yaml")
    assert vazia.esta_vazia and vazia.avisos == ()
    assert vazia.linha("character", "humanoid", 28) == ""
    assert vazia.exemplo("character", "humanoid", 28) is None


def test_sem_faixa_configurada_nao_ha_parte_de_porte(tmp_path: Path, colecao: ReferenciasAtivas):
    sem_porte = ReferenciasAtivas.carregar(colecao.raiz, _config(tmp_path / "c.yaml", "[grandes]", porte=False))
    linha = sem_porte.linha("character", "humanoid", 28)
    assert "estilo" in linha and "porte" not in linha


def test_configuracao_recusa_numero_sem_a_calibrar(tmp_path: Path):
    caminho = tmp_path / "r.yaml"
    caminho.write_text("ativos: []\nporte:\n  faixa_altura: {valor: 0.2}\n", encoding="utf-8")
    config = ler_configuracao(caminho)
    assert config.faixa_altura is None
    assert any("a_calibrar" in problema for problema in config.problemas)


def test_a_configuracao_real_carrega_sem_problema():
    config = ler_configuracao(CONHECIMENTO / "referencias.yaml")
    assert config.problemas == ()
    assert config.faixa_altura == 0.2 and config.minimo_de_quadros == 3


def test_exemplo_e_um_quadro_tipico_ampliado(colecao: ReferenciasAtivas):
    png, legenda = colecao.exemplo("character", "humanoid", 28)

    imagem = Image.open(io.BytesIO(png))
    assert imagem.size == (32 * 8, 32 * 8), "quadro 32×32 ampliado 8×"
    assert "não para copiar" in legenda and "CC0-1.0" in legenda and "Fulano" in legenda
    assert "Grandes/heroi_1.png" in legenda, "o mais perto das medianas do mesmo porte"


# ---------------------------------------------------------------------------
# Recorte e serviço MCP
# ---------------------------------------------------------------------------
def test_recorte_ganha_a_linha_por_ultimo_e_ela_sai_primeiro(colecao: ReferenciasAtivas):
    base = BaseDeConhecimento.do_diretorio(CONHECIMENTO)
    completo = montar_recorte(_spec(), base, referencias=colecao)
    assert completo.splitlines()[-1].startswith("referências: estilo de 6 quadros")

    teto = len(completo) - 10
    cortado = montar_recorte(_spec(), base, referencias=colecao, teto=teto)
    assert cortado.endswith(f"omitido pelo teto de {teto} caracteres: referências")
    assert montar_recorte(_spec(), base) == completo.rsplit("\n", 1)[0], "sem referências, nada muda"


def test_quadro_de_48_usa_a_altura_do_corpo_de_32(colecao: ReferenciasAtivas):
    base = BaseDeConhecimento.do_diretorio(CONHECIMENTO)
    recorte = montar_recorte(_spec(largura=48, altura=48), base, referencias=colecao)
    assert "porte de 23–33 px de altura" in recorte


def test_servico_mostra_a_referencia_e_poe_a_linha_na_consulta(container, colecao):
    from assetflow.mcp.servico import MOTOR, ServicoDesenhista

    container.registry.enable(MOTOR)
    container.referencias = colecao
    servico = ServicoDesenhista(container)

    assert "referências: estilo de 6 quadros" in servico.consultar("cavaleiro 32x32, 8 cores")
    png, legenda = servico.ver_referencia("cavaleiro 32x32, 8 cores")
    assert png.startswith(b"\x89PNG") and "grandes" in legenda


# ---------------------------------------------------------------------------
# Calibração
# ---------------------------------------------------------------------------
def test_relatorio_propoe_sem_alterar_a_base(colecao: ReferenciasAtivas):
    antes = {p: p.read_bytes() for p in CONHECIMENTO.rglob("*.yaml")}
    base = BaseDeConhecimento.do_diretorio(CONHECIMENTO)

    relatorio = gerar_relatorio(base, colecao)

    assert {p: p.read_bytes() for p in CONHECIMENTO.rglob("*.yaml")} == antes
    assert "## humanóide 32x32" in relatorio
    assert "| altura_px | 28 | — | (manter) | circular" in relatorio
    assert "| chao_y | 30 | — | — | não comparável" in relatorio
    assert "| cabeca_px | 10 | — | — | não medida" in relatorio
    assert "| tons_por_material | 3 | 3–3–3 (n=6, 1 pac.) | (manter) |" in relatorio
    assert "## humanóide 48x48 (corpo 32x32)" in relatorio
    assert "| chao_y | 46 |" in relatorio
    assert "## O validador atual sobre as referências" in relatorio
    assert "| `grandes` | 7 |" in relatorio
