"""O MCP e a fila: pedidos_pendentes, desenhar(pedido_id) e a liberdade.

Os pedidos são criados pelo serviço de pedidos — o mesmo que a API usa — e
desenhados pelo :class:`ServicoDesenhista`, como na conversa. O marco da fase
(três pedidos na tela, desenhados pela conversa, prontos na tela) roda no
fim, com a API e o MCP em dois containers sobre a mesma pasta de dados.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import assetflow.mcp.servico as modulo_servico
from assetflow.api.app import create_app
from assetflow.bootstrap import AppContainer, build_container
from assetflow.generation.spec import AssetTaxonomy, AssetTypeClassifier
from assetflow.mcp.laudo import FORMATO_RECEITA, LIBERDADE_EQUILIBRADO
from assetflow.mcp.servico import MOTOR, ErroDoPedido, ServicoDesenhista
from assetflow.pedidos import CorpoDoPedido, Etapa, Situacao, agora_utc
from assetflow.pixel_knowledge import CONVITE_OUSADO, rampas_da_base
from tests.conftest import BACKEND_ROOT, run
from tests.test_mcp import RUIDO

POCAO = BACKEND_ROOT / "assetflow" / "generation" / "engines" / "desenhista" / "exemplos" / "pocao_16x16.json"


def _pocao() -> dict:
    return json.loads(POCAO.read_text(encoding="utf-8"))


@pytest.fixture
def servico(container: AppContainer) -> ServicoDesenhista:
    container.registry.enable(MOTOR)
    return ServicoDesenhista(container)


def _pedido(container: AppContainer, texto: str = "poção azul 16x16", **campos):
    # Estes testes cobram o desenho: sem a etapa de conceito (ver test_conceito.py).
    campos.setdefault("modo_conceito", "sem_conceito")
    corpo = CorpoDoPedido(prompt=texto, profile="pixel_prop_64", **campos)
    return run(container.pedidos.criar(corpo))


def _id_do_asset(laudo: str) -> str:
    linha = next(linha for linha in laudo.splitlines() if " · asset_" in linha)
    return linha.split(" · ")[1]


# ---------------------------------------------------------------------------
# pedidos_pendentes
# ---------------------------------------------------------------------------
def test_pendentes_traz_o_comum_uma_vez_e_cada_pedido(servico, container):
    a = _pedido(container, "poção azul 16x16", direcao_de_arte="frasco torto")
    b = _pedido(container, "espada curta 32x32", liberdade="ousado")

    texto = run(servico.pedidos_pendentes())

    assert texto.startswith("2 pedidos da tela, reservados para você por 30 min (mais 0 na fila).")
    assert texto.count(FORMATO_RECEITA) == 1
    rampas = rampas_da_base(container.conhecimento)
    assert rampas and texto.count(rampas) == 1, "as rampas vêm uma vez só"
    assert texto.index(f"== {a.id} · desenho · liberdade equilibrado") < texto.index(f"== {b.id}")
    assert 'direção de arte (como escrita no pedido): "frasco torto"' in texto
    bloco_b = texto[texto.index(f"== {b.id}") :]
    assert "liberdade: ousado — os limites duros são grade 32×32" in bloco_b
    assert CONVITE_OUSADO in bloco_b
    assert "(no topo da lista)" in bloco_b
    assert LIBERDADE_EQUILIBRADO in texto[: texto.index(f"== {b.id}")]


def test_pendentes_reserva_o_que_entregou(servico, container):
    pedido = _pedido(container)
    run(servico.pedidos_pendentes())

    assert container.pedidos.fila.obter(pedido.id).etapa(agora_utc()) is Etapa.NA_VEZ
    assert run(servico.pedidos_pendentes()) == "nenhum pedido esperando desenho na fila do AssetFlow."


def test_pendentes_cabe_no_teto_e_deixa_o_resto_na_fila(servico, container, monkeypatch):
    pedidos = [_pedido(container, f"poção {n} 16x16") for n in range(4)]
    um = len(run(ServicoDesenhista(container)._bloco(pedidos[0], agora_utc(), set()))[0])
    # A parte fixa é a que o serviço reserva (cabeçalho, formato e rampas);
    # cabem ela e dois pedidos, não três.
    fixo = 1000 + len(rampas_da_base(container.conhecimento))
    monkeypatch.setattr(modulo_servico, "TETO_PENDENTES", fixo + 2 * (um + 2) + um // 2)

    texto = run(servico.pedidos_pendentes(limite=10))

    assert texto.startswith("2 pedidos da tela") and "(mais 2 na fila)" in texto
    situacoes = [container.pedidos.fila.obter(p.id).situacao for p in pedidos]
    assert situacoes == [Situacao.EM_DESENHO] * 2 + [Situacao.PENDENTE] * 2


def test_tamanho_com_um_e_com_cinco_pedidos(servico, container):
    """Os números do pedido da fase, cobrados: um pedido cabe com folga, cinco
    pedidos típicos ficam bem abaixo do teto de 16 mil caracteres."""
    _pedido(container, "poção azul 16x16")
    um = run(servico.pedidos_pendentes())
    for texto in ("cavaleiro 48x48, 12 cores", "lobo cinzento 32x32", "espada curta 32x32",
                  "arqueira de capuz verde 48x48", "baú de madeira 32x32"):
        _pedido(container, texto)
    cinco = run(servico.pedidos_pendentes())

    # A primeira resposta da conversa traz o formato dos comandos opcionais
    # (lotes F1 a F4, ~1.900 caracteres); as seguintes, uma linha com os nomes.
    assert 2_000 < len(um) < 6_000
    assert cinco.startswith("5 pedidos da tela")
    assert len(cinco) < modulo_servico.TETO_PENDENTES
    assert "comandos opcionais ligados:" in cinco and '"limpar_linha"' not in cinco
    assert '"limpar_linha"' in um


def test_limite_vai_de_1_a_10(servico, container):
    for n in range(12):
        _pedido(container, f"poção {n} 16x16")
    assert run(servico.pedidos_pendentes(limite=50)).startswith("10 pedidos")
    assert run(servico.pedidos_pendentes(limite=0)).startswith("1 pedido da tela")


# ---------------------------------------------------------------------------
# desenhar(pedido_id)
# ---------------------------------------------------------------------------
def test_aprovado_espera_o_olhar_e_o_concluir_fecha(servico, container):
    """Fase B2: aprovado no validador não é pronto; o pedido conclui depois do olhar."""
    pedido = _pedido(container)
    run(servico.pedidos_pendentes())

    laudo = run(servico.desenhar(pedido_id=pedido.id, receita=_pocao()))
    asset = _id_do_asset(laudo)

    assert laudo.splitlines()[0] == (
        f"pedido {pedido.id}: aprovado no validador com {asset}; falta o seu olhar "
        "(remendos: 0 de 2)"
    )
    assert laudo.splitlines()[1].startswith("APROVADO · ")
    assert f"concluir_pedido(pedido_id={pedido.id}, olhar=" in laudo
    assert laudo.imagem.startswith(b"\x89PNG"), "a imagem do olhar vem junto do laudo"
    revisao = container.pedidos.fila.obter(pedido.id)
    assert revisao.situacao is Situacao.EM_REVISAO and revisao.etapa(agora_utc()) is Etapa.OLHANDO

    resposta = run(servico.concluir(pedido.id, "o frasco e o líquido se leem bem"))

    assert resposta.startswith(f"pedido {pedido.id}: concluído com {asset} depois do olhar")
    depois = container.pedidos.fila.obter(pedido.id)
    assert (depois.situacao, depois.asset_id, depois.asset_projeto) == (
        Situacao.CONCLUIDO,
        asset,
        "principal",
    )
    assert depois.olhar == "o frasco e o líquido se leem bem"
    gerado = run(container.pedidos.asset(depois.asset_projeto, depois.job_id))
    assert gerado is not None and gerado.id == asset


def test_o_desenho_executa_o_spec_gravado_mesmo_com_a_taxonomia_mudada(servico, container):
    """O spec é resolvido uma vez, na criação. Aqui a taxonomia muda entre
    criar e desenhar — resolver de novo daria outro tipo —, e o job executa
    exatamente o spec gravado."""
    pedido = _pedido(container, "poção azul 16x16")
    gravado = pedido.spec
    assert gravado.asset.type.value == "prop"

    container.service._constraints._classifier = AssetTypeClassifier(AssetTaxonomy.empty())
    agora = container.service.resolve_spec(
        run(container.pedidos.requisicao_do_pedido(pedido, _pocao()))
    )
    assert agora.spec_hash != gravado.spec_hash, "o teste precisa de uma resolução diferente"

    capturados = []
    original = container.service.submit

    async def espiao(requisicao, *, resolved=None):
        job = await original(requisicao, resolved=resolved)
        capturados.append(job)
        return job

    container.service.submit = espiao
    run(servico.desenhar(pedido_id=pedido.id, receita=_pocao()))

    (job,) = capturados
    assert job.resolved_spec.spec_hash == gravado.spec_hash
    assert job.resolved_spec.model_dump(mode="json") == pedido.leitura["resolved"]


def test_desenho_nao_aprovado_conta_tentativas_ate_falhar(servico, container):
    pedido = _pedido(container, "fagulhas 16x16")

    primeiro = run(servico.desenhar(pedido_id=pedido.id, receita=RUIDO))
    asset = _id_do_asset(primeiro)
    assert primeiro.splitlines()[0] == (
        f"pedido {pedido.id}: não aprovado (tentativa 1 de 3); corrija com "
        f"desenhar(pedido_id={pedido.id}, base={asset}, receita=<só o que muda>)"
    )
    assert container.pedidos.fila.obter(pedido.id).etapa(agora_utc()) is Etapa.CORRIGINDO

    run(servico.desenhar(pedido_id=pedido.id, receita=RUIDO))
    terceiro = run(servico.desenhar(pedido_id=pedido.id, receita=RUIDO))

    assert terceiro.splitlines()[0] == (
        f"pedido {pedido.id}: falhou — 3 desenhos sem aprovação; o último fica na tela"
    )
    final = container.pedidos.fila.obter(pedido.id)
    assert final.situacao is Situacao.FALHOU and final.asset_id == _id_do_asset(terceiro)
    with pytest.raises(ErroDoPedido, match="terminou sem aprovação"):
        run(servico.desenhar(pedido_id=pedido.id, receita=_pocao()))


def test_corrigir_com_base_mantem_o_pedido(servico, container):
    pedido = _pedido(container, "fagulhas 16x16")
    asset = _id_do_asset(run(servico.desenhar(pedido_id=pedido.id, receita=RUIDO)))

    laudo = run(
        servico.desenhar(
            pedido_id=pedido.id,
            base=asset,
            receita={"camadas": [{"nome": "ruido", "ops": [{"elipse": [3, 3, 10, 10], "cor": "a"}]}]},
        )
    )

    assert laudo.splitlines()[1] == f"remendo de {asset}: trocou camada ruido"
    assert container.pedidos.fila.obter(pedido.id).tentativas >= 1


def test_receita_invalida_nao_conta_tentativa(servico, container):
    pedido = _pedido(container)

    with pytest.raises(ErroDoPedido, match=f"o pedido {pedido.id} continua com você"):
        run(servico.desenhar(pedido_id=pedido.id, receita={"paleta": {"k": "#000"}, "camadas": []}))

    depois = container.pedidos.fila.obter(pedido.id)
    assert depois.situacao is Situacao.EM_DESENHO and depois.tentativas == 0
    assert depois.desenhando_desde is None
    assert depois.eventos[-1].nota.startswith("desenho sem asset:")


def test_cancelado_antes_nao_e_desenhado(servico, container):
    pedido = _pedido(container)
    container.pedidos.fila.cancelar(pedido.id)

    with pytest.raises(ErroDoPedido, match="cancelado na tela: não desenhe"):
        run(servico.desenhar(pedido_id=pedido.id, receita=_pocao()))


def test_cancelado_durante_o_desenho_deixa_o_asset_avulso(servico, container, monkeypatch):
    pedido = _pedido(container)
    original = servico._executar

    async def cancela_no_meio(requisicao, *, resolved=None):
        container.pedidos.fila.cancelar(pedido.id)  # a pessoa clicou enquanto o job rodava
        return await original(requisicao, resolved=resolved)

    monkeypatch.setattr(servico, "_executar", cancela_no_meio)
    laudo = run(servico.desenhar(pedido_id=pedido.id, receita=_pocao()))

    asset = _id_do_asset(laudo)
    assert laudo.splitlines()[0] == (
        f"pedido {pedido.id}: foi cancelado na tela durante o desenho; {asset} ficou avulso, "
        "fora do pedido"
    )
    assert container.pedidos.fila.obter(pedido.id).asset_id is None


def test_pedido_ja_concluido_nao_recebe_outro_desenho(servico, container):
    pedido = _pedido(container)
    asset = _id_do_asset(run(servico.desenhar(pedido_id=pedido.id, receita=_pocao())))
    run(servico.concluir(pedido.id, "bom"))

    with pytest.raises(ErroDoPedido, match=f"já foi concluído com {asset}"):
        run(servico.desenhar(pedido_id=pedido.id, receita=_pocao()))


def test_com_pedido_id_texto_e_perfil_vem_do_pedido(servico, container):
    pedido = _pedido(container)
    with pytest.raises(ErroDoPedido, match="omita 'pedido' e 'perfil'"):
        run(servico.desenhar(pedido_id=pedido.id, pedido="outra coisa", receita=_pocao()))


def test_cada_desenho_renova_a_reserva_da_leva(servico, container):
    a, b = _pedido(container, "poção a 16x16"), _pedido(container, "poção b 16x16")
    run(servico.pedidos_pendentes())
    fila = container.pedidos.fila
    prazo_antes = fila.obter(b.id).reservado_ate

    run(servico.desenhar(pedido_id=a.id, receita=_pocao()))

    assert fila.obter(b.id).reservado_ate > prazo_antes
    assert fila.obter(b.id).leva == fila.obter(a.id).leva


def test_ajuste_remenda_o_asset_de_origem(servico, container):
    origem = _id_do_asset(
        run(servico.desenhar(pedido="poção vermelha 16x16", receita=_pocao(), perfil="pixel_prop_64"))
    )
    ajuste = run(
        container.pedidos.criar(CorpoDoPedido(origem_asset_id=origem, texto="líquido verde"))
    )

    texto = run(servico.pedidos_pendentes())
    assert f'== {ajuste.id} · ajuste de {origem}: "líquido verde"' in texto
    assert f"base: {origem} · 16×16" in texto and "camadas: silhueta, vidro" in texto

    laudo = run(
        servico.desenhar(pedido_id=ajuste.id, receita={"paleta": {"r": "#2e8b57", "R": "#4fbf7f"}})
    )
    assert laudo.splitlines()[1] == f"remendo de {origem}: paleta r, R"
    assert container.pedidos.fila.obter(ajuste.id).situacao is Situacao.EM_REVISAO
    run(servico.concluir(ajuste.id, "o líquido verde ficou claro"))
    assert container.pedidos.fila.obter(ajuste.id).situacao is Situacao.CONCLUIDO


# ---------------------------------------------------------------------------
# Liberdade nas ferramentas avulsas
# ---------------------------------------------------------------------------
PEDIDO = "arqueira de capuz verde 48x48, 12 cores, sem fundo"


def test_consultar_sem_liberdade_e_como_antes(servico):
    # formato=true: a segunda consulta da conversa viria com o formato curto.
    assert servico.consultar(PEDIDO, "pixel_character_48", formato=True) == servico.consultar(
        PEDIDO, "pixel_character_48", liberdade="fiel", formato=True
    )


def test_consultar_equilibrado(servico):
    fiel = servico.consultar(PEDIDO, "pixel_character_48", formato=True)
    texto = servico.consultar(PEDIDO, "pixel_character_48", liberdade="equilibrado", formato=True)
    recorte = texto.split("\nconhecimento:\n", 1)[1].splitlines()

    assert recorte[0] == LIBERDADE_EQUILIBRADO
    assert recorte[1].startswith("humanóide, corpo 32×32 num quadro 48×48 (ponto de partida): cabeça y19–28")
    assert any("rampas do escuro ao claro como ponto de partida; cada material costuma usar" in linha for linha in recorte)
    assert "silhueta:" in texto and "luz:" in texto
    assert len(texto) > len(fiel)


def test_consultar_ousado(servico):
    texto = servico.consultar(PEDIDO, "pixel_character_48", liberdade="ousado")
    recorte = texto.split("\nconhecimento:\n", 1)[1].splitlines()

    assert recorte[0] == (
        "liberdade: ousado — os limites duros são grade 48×48, até 12 cores com o contorno e "
        "fundo transparente; o resto é seu. Proponha uma silhueta e uma ideia próprias para "
        "o pedido, em vez da figura de sempre."
    )
    assert recorte[1] == CONVITE_OUSADO
    assert recorte[2] == (
        "quadro: grade 48×48 · chão em y=46 (pixel opaco mais baixo), para pisar na mesma "
        "linha que os outros personagens"
    )
    assert recorte[3].startswith("luz: de cima e da esquerda")
    assert recorte[4].startswith(
        "cores: até 12, contorno incluído · qualquer cor vale dentro do limite, desde que cada "
        "material tenha tons vizinhos (escuro, médio, claro); como sugestão, as rampas da "
        "paleta-mestra endesga-32, do escuro ao claro:"
    )
    assert recorte[-1].startswith("silhueta: arma e escudo fora do corpo")
    # Nenhuma medida do corpo, nenhum molde, nenhuma referência.
    assert "cabeça y" not in texto and "larguras" not in texto and "camadas:" not in texto
    assert "referências:" not in texto


def test_liberdade_nao_muda_os_limites_duros(servico):
    cabecalhos = {
        liberdade: servico.consultar(
            PEDIDO, "pixel_character_48", liberdade=liberdade, formato=True
        ).split(
            "\nconhecimento:\n"
        )[0]
        for liberdade in ("fiel", "equilibrado", "ousado")
    }
    assert len(set(cabecalhos.values())) == 1


def test_liberdade_desconhecida_e_recusada(servico):
    with pytest.raises(ErroDoPedido, match="use fiel, equilibrado ou ousado"):
        servico.consultar(PEDIDO, "pixel_character_48", liberdade="solta")


class _Referencias:
    """Anota com que porte o exemplo foi pedido."""

    def __init__(self):
        self.pedidos = []

    def exemplo(self, tipo, corpo, altura):
        self.pedidos.append((tipo, corpo, altura))
        return b"png", "legenda"

    def linha(self, tipo, corpo, altura):
        return ""


def test_ver_referencia_ousada_escolhe_so_pelo_estilo(servico, container):
    container.referencias = _Referencias()

    servico.ver_referencia(PEDIDO, "pixel_character_48")
    servico.ver_referencia(PEDIDO, "pixel_character_48", liberdade="ousado")

    (_, _, altura_fiel), (_, _, altura_ousada) = container.referencias.pedidos
    assert altura_fiel == 28, "fiel continua filtrando pelo porte do corpo"
    assert altura_ousada is None


# ---------------------------------------------------------------------------
# O marco: três pedidos na tela, desenhados pela conversa, prontos na tela
# ---------------------------------------------------------------------------
def test_marco_tres_pedidos_da_tela_ficam_prontos(container: AppContainer):
    """API e MCP em dois containers sobre a mesma pasta de dados — o mesmo
    arranjo do uvicorn e do servidor MCP, que são dois processos."""
    mcp = build_container(container.settings)
    mcp.registry.enable(MOTOR)
    conversa = ServicoDesenhista(mcp)

    with TestClient(create_app(container=container)) as tela:
        ids = [
            tela.post(
                "/api/pedidos",
                json={
                    "capability": "text_to_image.pixel",
                    "profile": "pixel_prop_64",
                    "prompt": texto,
                    "modo_conceito": "sem_conceito",
                },
            ).json()["id"]
            for texto in ("poção vermelha 16x16", "poção verde 16x16", "poção azul 16x16")
        ]

        lista = run(conversa.pedidos_pendentes())
        assert lista.startswith("3 pedidos da tela")
        for pedido_id in ids:
            laudo = run(conversa.desenhar(pedido_id=pedido_id, receita=_pocao()))
            assert laudo.splitlines()[0].startswith(f"pedido {pedido_id}: aprovado no validador com")
            # Aprovado não é pronto: na tela, o pedido espera o olhar.
            etapa = {i["id"]: i for i in tela.get("/api/pedidos").json()["items"]}[pedido_id]["etapa"]
            assert etapa == "olhando"
            run(conversa.concluir(pedido_id, "a poção se lê bem"))

        itens = {item["id"]: item for item in tela.get("/api/pedidos").json()["items"]}
        for pedido_id in ids:
            item = itens[pedido_id]
            assert item["etapa"] == "pronto"
            url = item["asset"]["variants"][0]["url"]
            imagem = tela.get(url)
            assert imagem.status_code == 200 and imagem.content.startswith(b"\x89PNG")
    run(mcp.shutdown())


def test_prazo_da_reserva_vem_do_settings(container: AppContainer):
    assert container.pedidos.fila.reserva == timedelta(minutes=container.settings.pedidos.reserva_min)
