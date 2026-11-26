"""Fase B2 pelo MCP: ver, corrigir e aprender.

O ``desenhar`` devolve a imagem e o olho do app; aprovado no validador não é
pronto; o olhar pede até 2 remendos; o olho só informa (a exceção é a guarda
"repete o exemplo"); o recorte traz exemplo e lições, cada um com o seu
interruptor; ``registrar_licao`` e as opiniões da autora.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assetflow.aprendizado import Origem, SituacaoDaOpiniao
from assetflow.bootstrap import AppContainer
from assetflow.generation.engines.desenhista.rasterizador import desenhar
from assetflow.generation.engines.desenhista.receita import ler_receita
from assetflow.mcp.servico import MOTOR, ErroDoPedido, ServicoDesenhista
from assetflow.pedidos import CorpoDoPedido, Situacao
from tests.conftest import BACKEND_ROOT, run
from tests.test_olhar import _figura

POCAO = BACKEND_ROOT / "assetflow" / "generation" / "engines" / "desenhista" / "exemplos" / "pocao_16x16.json"


def _pocao() -> dict:
    return json.loads(POCAO.read_text(encoding="utf-8"))


@pytest.fixture
def servico(container: AppContainer) -> ServicoDesenhista:
    container.registry.enable(MOTOR)
    return ServicoDesenhista(container)


def _pedido(container: AppContainer, texto: str = "poção azul 16x16", perfil: str = "pixel_prop_64", **campos):
    campos.setdefault("modo_conceito", "sem_conceito")
    return run(container.pedidos.criar(CorpoDoPedido(prompt=texto, profile=perfil, **campos)))


def _asset(laudo: str) -> str:
    return next(linha for linha in laudo.splitlines() if " · asset_" in linha).split(" · ")[1]


def _avulso(servico: ServicoDesenhista) -> str:
    return _asset(run(servico.desenhar(pedido="poção vermelha 16x16", receita=_pocao(), perfil="pixel_prop_64")))


# ---------------------------------------------------------------------------
# Ver e corrigir
# ---------------------------------------------------------------------------
def test_desenho_avulso_traz_imagem_olho_lista_e_instrucao(servico):
    laudo = run(servico.desenhar(pedido="poção vermelha 16x16", receita=_pocao(), perfil="pixel_prop_64"))

    assert laudo.imagem.startswith(b"\x89PNG") and laudo.ampliacao == 24
    assert "olho do app (sem referências ativas de prop; só o contraste entre partes)" in laudo
    # Lote F1: o ombro do frasco tem 4 cantos em L, acima do p90 dos props.
    assert "4 canto(s) em L no contorno" in laudo and "(4,6) (11,6) (4,13) (11,13)" in laudo
    assert "olhar — na imagem: à esquerda ampliada 24×" in laudo and "\n1. silhueta: " in laudo
    assert laudo.splitlines()[-2].endswith("Se estiver bom, diga que está e pare.")
    assert laudo.splitlines()[-1].startswith("arquivo: ")


def test_primeiro_olhar_traz_a_lista_e_o_remendo_so_o_lembrete(servico, container):
    pedido = _pedido(container)
    primeiro = run(servico.desenhar(pedido_id=pedido.id, receita=_pocao()))
    asset = _asset(primeiro)
    assert "\n1. silhueta: em preto, dá para reconhecer o objeto num relance?" in primeiro

    remendo = run(servico.desenhar(pedido_id=pedido.id, base=asset, receita={"paleta": {"r": "#2e8b57"}}))

    novo = _asset(remendo)
    assert remendo.splitlines()[0] == (
        f"pedido {pedido.id}: remendo aprovado no validador com {novo}; falta o seu olhar "
        "(remendos: 1 de 2)"
    )
    assert "1. silhueta" not in remendo
    assert "olhar — confira de novo a lista do primeiro olhar (silhueta, uma ideia, faces, luz, limpeza)." in remendo
    assert f"o remendo saiu sem lição registrada para {asset}" in remendo
    assert container.pedidos.fila.obter(pedido.id).candidatos == (asset, novo)


def test_remendos_tem_teto_e_o_concluir_escolhe_a_versao(servico, container):
    pedido = _pedido(container)
    primeiro = _asset(run(servico.desenhar(pedido_id=pedido.id, receita=_pocao())))
    segundo = _asset(run(servico.desenhar(pedido_id=pedido.id, base=primeiro, receita={"paleta": {"r": "#2e8b57"}})))
    terceiro = run(servico.desenhar(pedido_id=pedido.id, base=segundo, receita={"paleta": {"r": "#3050c0"}}))

    assert "(remendos: 2 de 2)" in terceiro.splitlines()[0]
    assert "Os 2 remendos do pedido acabaram" in terceiro
    with pytest.raises(ErroDoPedido, match="já usou os 2 remendos"):
        run(servico.desenhar(pedido_id=pedido.id, base=segundo, receita={"paleta": {"r": "#000000"}}))

    resposta = run(servico.concluir(pedido.id, "a primeira lia melhor", asset_id=primeiro))
    assert resposta.startswith(f"pedido {pedido.id}: concluído com {primeiro} depois do olhar")
    assert "remendo sem lição registrada" in resposta


def test_concluir_valida_a_linha_do_olhar(servico, container):
    pedido = _pedido(container)
    run(servico.desenhar(pedido_id=pedido.id, receita=_pocao()))
    with pytest.raises(ErroDoPedido, match="falta 'olhar'"):
        run(servico.concluir(pedido.id, "  "))
    with pytest.raises(ErroDoPedido, match="o teto é 240"):
        run(servico.concluir(pedido.id, "x" * 241))


#: Dois retângulos vermelhos lado a lado, cada um numa camada, com contorno.
MESMO_VALOR = {
    "grade": [16, 16],
    "paleta": {"k": "#181425", "r": "#b03a2e"},
    "camadas": [
        {"nome": "esquerda", "ops": [{"ret": [2, 3, 6, 11], "cor": "r"}]},
        {"nome": "direita", "ops": [{"ret": [8, 3, 6, 11], "cor": "r"}]},
        {"nome": "contorno", "ops": [{"ret": [1, 2, 14, 13], "cor": "k", "contorno": True}]},
    ],
}


def test_o_olho_do_app_so_informa(servico, container):
    """Um desvio do olho não reprova: o pedido segue para o olhar."""
    pedido = _pedido(container, "caixa vermelha 16x16")

    laudo = run(servico.desenhar(pedido_id=pedido.id, receita=MESMO_VALOR))

    assert "- partes vizinhas com o mesmo valor: esquerda × direita (ΔL* 0)" in laudo
    assert laudo.splitlines()[1].startswith("APROVADO · ")
    assert container.pedidos.fila.obter(pedido.id).situacao is Situacao.EM_REVISAO


def test_desenho_que_repete_o_exemplo_e_nao_aprovado(servico, container):
    """A única exceção ao "o olho só informa": o exemplo nunca é base de um asset."""
    pedido = _pedido(container, "poção vermelha 16x16")
    silhueta = list(desenhar(ler_receita(_pocao()), 16, 16).grade.linhas())
    container.pedidos.fila.gravar_envio(pedido.id, {"exemplo": {"px": silhueta}})

    laudo = run(servico.desenhar(pedido_id=pedido.id, receita=_pocao()))

    assert laudo.splitlines()[0].startswith(f"pedido {pedido.id}: não aprovado (tentativa 1 de 3)")
    assert laudo.splitlines()[1].startswith("NÃO APROVADO (repete o exemplo de construção)")
    assert "- repete o exemplo de construção (silhueta com IoU" not in laudo  # isso é do avulso
    assert "repete o exemplo de construção (IoU 1,00)" in laudo
    depois = container.pedidos.fila.obter(pedido.id)
    assert depois.situacao is Situacao.EM_DESENHO and depois.tentativas == 1
    assert depois.motivo == "repete o exemplo de construção (IoU 1,00)"


def test_olhar_json_grava_o_envio_e_o_olho_no_asset(servico, container):
    pedido = _pedido(container)
    run(servico.pedidos_pendentes())
    run(servico.desenhar(pedido_id=pedido.id, receita=_pocao()))

    depois = container.pedidos.fila.obter(pedido.id)
    arquivo = (
        container.settings.storage_root / "projects" / depois.asset_projeto / "jobs" / depois.job_id / "000_olhar.json"
    )
    documento = json.loads(arquivo.read_text(encoding="utf-8"))
    assert documento["pedido_id"] == pedido.id and documento["primeiro_olhar"] is True
    assert documento["olho"]["cabecalho"].startswith("olho do app")
    # O exemplo nasce desligado (settings); as lições, ligadas.
    assert documento["envio"]["exemplo_ligado"] is False and documento["envio"]["licoes_ligadas"] is True
    assert documento["envio"]["exemplo"] is None
    assert depois.envio == documento["envio"], "o mesmo envio no pedido e no asset"


# ---------------------------------------------------------------------------
# Exemplo de construção e lições no recorte
# ---------------------------------------------------------------------------
def _referencias_de_dois_pacotes(tmp_path: Path):
    from assetflow.referencias import Parte, ReferenciasAtivas
    from tests.test_olhar import _config
    from tests.test_referencias import _pacote, _png

    raiz = tmp_path / "referencias"
    for nome, largura in (("pacote-a", 12), ("pacote-b", 9)):
        origem = tmp_path / nome
        _png(_figura(28, largura, (32, 32)), origem / "Idle/heroi.png")
        _pacote(raiz, origem, nome, (Parte("**", "character", "humanoid"),))
    return ReferenciasAtivas.carregar(raiz, _config(tmp_path / "r.yaml", "[pacote-a, pacote-b]"))


def test_exemplo_nasce_desligado(servico, container, tmp_path):
    """Desligado por padrão: com pacotes ativos, o recorte sai sem exemplo."""
    assert container.settings.aprendizado.exemplo is False
    container.referencias = _referencias_de_dois_pacotes(tmp_path)
    pedido = _pedido(container, "cavaleiro 32x32", "pixel_character_32")

    texto = run(servico.pedidos_pendentes())

    assert "exemplo de construção" not in texto
    envio = container.pedidos.fila.obter(pedido.id).envio
    assert envio["exemplo_ligado"] is False and envio["exemplo"] is None


@pytest.fixture
def com_exemplo(container: AppContainer) -> ServicoDesenhista:
    """O exemplo ligado, como ``ASSETFLOW_EXEMPLO=1``."""
    container.registry.enable(MOTOR)
    container.settings.aprendizado.exemplo = True
    return ServicoDesenhista(container)


def test_exemplo_entra_no_recorte_e_roda_entre_pacotes(com_exemplo, container, tmp_path):
    servico = com_exemplo
    container.referencias = _referencias_de_dois_pacotes(tmp_path)
    primeiro = _pedido(container, "cavaleiro 32x32", "pixel_character_32")
    texto = run(servico.pedidos_pendentes())
    assert "exemplo de construção (CC0 · pacote-a · " in texto
    assert container.pedidos.fila.obter(primeiro.id).envio["exemplo"]["pacote"] == "pacote-a"

    segundo = _pedido(container, "arqueiro 32x32", "pixel_character_32")
    run(servico.pedidos_pendentes())
    assert container.pedidos.fila.obter(segundo.id).envio["exemplo"]["pacote"] == "pacote-b"


def test_pedidos_seguidos_na_mesma_resposta_recebem_pacotes_diferentes(com_exemplo, container, tmp_path):
    servico = com_exemplo
    container.referencias = _referencias_de_dois_pacotes(tmp_path)
    a = _pedido(container, "cavaleiro 32x32", "pixel_character_32")
    b = _pedido(container, "arqueiro 32x32", "pixel_character_32")
    run(servico.pedidos_pendentes())
    pacotes = {container.pedidos.fila.obter(p.id).envio["exemplo"]["pacote"] for p in (a, b)}
    assert pacotes == {"pacote-a", "pacote-b"}


def test_interruptores_desligam_o_exemplo_e_as_licoes(container, tmp_path):
    container.registry.enable(MOTOR)
    container.referencias = _referencias_de_dois_pacotes(tmp_path)
    container.aprendizado.registrar(
        errou="corpo e capa no mesmo valor", porque="mesmo tom", regra="roupa e capa em valores diferentes",
        tema="valor", tipo="character", corpo="humanoid", porte="32x32",
    )
    container.settings.aprendizado.exemplo = False
    container.settings.aprendizado.licoes = False
    pedido = _pedido(container, "cavaleiro 32x32", "pixel_character_32")

    texto = run(ServicoDesenhista(container).pedidos_pendentes())

    assert "exemplo de construção" not in texto and "lições" not in texto
    envio = container.pedidos.fila.obter(pedido.id).envio
    assert (envio["exemplo_ligado"], envio["licoes_ligadas"]) == (False, False)
    assert envio["exemplo"] is None and envio["licoes"] == []


def test_licoes_entram_no_recorte_e_em_ousado_so_as_de_tecnica(servico, container):
    caixa = container.aprendizado
    comum = {"tipo": "prop", "corpo": "qualquer", "porte": "16x16", "porque": "faltou cuidado"}
    caixa.registrar(errou="silhueta confusa", regra="um objeto, uma silhueta limpa", tema="silhueta", **comum)
    caixa.registrar(errou="luz dos dois lados", regra="luz só de cima e da esquerda", tema="luz", **comum)
    equilibrado = _pedido(container, "poção azul 16x16")
    ousado = _pedido(container, "poção verde 16x16", liberdade="ousado")

    texto = run(servico.pedidos_pendentes())
    bloco_e = texto[texto.index(f"== {equilibrado.id}") : texto.index(f"== {ousado.id}")]
    bloco_o = texto[texto.index(f"== {ousado.id}") :]

    assert "lições (de desenhos anteriores; as mais repetidas primeiro):" in bloco_e
    assert "- L1 ×1: um objeto, uma silhueta limpa" in bloco_e and "- L2 ×1: luz só de cima" in bloco_e
    assert "lições de técnica (a forma é livre em ousado" in bloco_o
    assert "L2 ×1" in bloco_o and "L1 ×1" not in bloco_o
    assert [l["id"] for l in container.pedidos.fila.obter(ousado.id).envio["licoes"]] == ["L2"]


# ---------------------------------------------------------------------------
# Aprender: registrar_licao e as opiniões da autora
# ---------------------------------------------------------------------------
def test_registrar_licao_pelo_mcp(servico):
    asset = _avulso(servico)

    nova = run(servico.registrar_licao(asset, "luz", "brilho dos dois lados", "esqueci a direção", "brilho só do lado da luz"))
    assert nova == "lição L1 registrada (luz) · prop · qualquer · 16x16"
    repetida = run(servico.registrar_licao(asset, "luz", "de novo", "de novo", "brilho só do lado da luz"))
    assert "lição L1 já existia: contador agora 2" in repetida
    geral = run(servico.registrar_licao(asset, "limpeza", "pixel solto", "pressa", "sem pixel solto", geral=True))
    assert geral.endswith("· qualquer · qualquer · qualquer")

    with pytest.raises(ErroDoPedido, match="tema 'brilho' não existe"):
        run(servico.registrar_licao(asset, "brilho", "x", "y", "z"))
    with pytest.raises(ErroDoPedido, match="não há opinião pendente da autora"):
        run(servico.registrar_licao(asset, "luz", "x", "y", "z", da_autora=True))


def test_opiniao_da_autora_chega_no_pendentes_e_vira_licao_dela(servico, container):
    asset = _avulso(servico)
    outro = _avulso(servico)
    container.aprendizado.opinar(asset, gostei=False, motivo="a rolha some no frasco")
    container.aprendizado.opinar(outro, gostei=False)  # sem motivo: só nota

    texto = run(servico.pedidos_pendentes())
    assert texto.startswith("opiniões novas da autora (1): converta cada uma em lição")
    assert f'- {asset} (poção vermelha 16x16): "a rolha some no frasco"' in texto
    assert outro not in texto
    assert texto.endswith("nenhum pedido esperando desenho na fila do AssetFlow.")

    resposta = run(
        servico.registrar_licao(
            asset, "contorno", "rolha sem contorno próprio", "pintei rolha e vidro juntos",
            "rolha com contorno e cor distintos do vidro", da_autora=True,
        )
    )
    assert "da autora, com o texto original guardado ao lado" in resposta
    licao = container.aprendizado.obter("L1")
    assert licao.origem is Origem.AUTORA and licao.texto_da_autora == "a rolha some no frasco"
    assert container.aprendizado.opiniao(asset).situacao is SituacaoDaOpiniao.CONVERTIDA
    assert "opiniões novas" not in run(servico.pedidos_pendentes())
    with pytest.raises(ErroDoPedido, match="já virou a lição L1"):
        run(servico.registrar_licao(asset, "luz", "x", "y", "z", da_autora=True))
