"""Endpoint de diagnóstico do Pixel Exact (plano Pixel §78).

``POST /api/dev/pixel/analyze`` existe para **pesquisa**: mandar uma imagem
qualquer e receber o veredito técnico sem passar por um job de geração. É o
que permite medir "quão longe do Pixel Exact" está a saída de um motor novo
antes de integrá-lo.

O que estes testes protegem, e por quê:

1. **Desligado por padrão.** O plano Pixel §77 é explícito: o fluxo normal
   continua sendo ``POST /api/generation/jobs``. Um endpoint que aceita
   imagem arbitrária não pode virar porta paralela de processamento em
   produção só porque alguém esqueceu de conferir a configuração.
2. **Ele analisa, não fabrica.** Nenhum arquivo entra no storage, nenhum
   registro entra no histórico — a resposta é o relatório e mais nada.
3. **``process`` decide o que é medido.** Desligado, o relatório descreve a
   imagem exatamente como ela chegou (é assim que se mede o motor cru);
   ligado, o relatório descreve o resultado depois do pós-processamento e vem
   acompanhado da decisão de aceitação.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from assetflow.api import create_app
from assetflow.bootstrap import AppContainer
from tests.conftest import run

ROTA = "/api/dev/pixel/analyze"

#: Profile de referência: 64×64, alpha binário com limiar 128, até 16 cores.
PROFILE = "pixel_character_64_strict"

#: Quatro cores fixas, bem separadas entre si. Fixas de propósito: um sprite
#: sorteado faria a contagem de cores e a nota de qualidade variarem entre
#: execuções, e aí o teste passaria a medir o sorteio, não o endpoint.
_CORES = ((28, 32, 44), (79, 121, 66), (201, 178, 124), (139, 171, 90))


def _sprite(lado: int, *, alpha: int = 255) -> Image.Image:
    """Sprite determinístico em xadrez, centralizado e sem tocar a borda.

    Com ``lado=64`` e ``alpha=255`` ele já cumpre o contrato do profile:
    dimensão exata, alpha binário, 4 cores e margem transparente em volta.
    Mudar o lado ou o alpha quebra um requisito de cada vez.
    """
    imagem = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    pixels = imagem.load()
    modulo = lado // 8
    for x in range(2 * modulo, 6 * modulo):
        for y in range(modulo, 7 * modulo):
            vermelho, verde, azul = _CORES[((x // modulo) + (y // modulo)) % 4]
            pixels[x, y] = (vermelho, verde, azul, alpha)
    return imagem


def _base64_png(imagem: Image.Image) -> str:
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _hard_checks(payload: dict) -> dict[str, str]:
    return {check["code"]: check["status"] for check in payload["validation"]["hard_checks"]}


def _arquivos(container: AppContainer) -> set[tuple[str, int]]:
    """Retrato do que existe em disco: caminho relativo + tamanho.

    O tamanho entra junto porque o histórico é um arquivo que **cresce** por
    append: comparar só a lista de caminhos deixaria passar um registro novo.
    """
    raiz = Path(container.settings.data_dir)
    if not raiz.exists():
        return set()
    return {
        (caminho.relative_to(raiz).as_posix(), caminho.stat().st_size)
        for caminho in raiz.rglob("*")
        if caminho.is_file()
    }


@pytest.fixture
def client(container: AppContainer):
    """Aplicação com a configuração padrão — ou seja, sem endpoints de dev."""
    with TestClient(create_app(container=container)) as test_client:
        yield test_client


@pytest.fixture
def dev_client(container: AppContainer):
    """Aplicação com ``ASSETFLOW_DEV_ENDPOINTS=1`` (plano Pixel §78).

    O worker continua desligado (fixture ``container``): o endpoint não
    depende de job algum, e um worker rodando escreveria em disco por conta
    própria, contaminando a verificação de que nada é persistido.
    """
    container.settings.api.dev_endpoints = True
    with TestClient(create_app(container=container)) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# O interruptor
# ---------------------------------------------------------------------------
def test_analyze_is_absent_when_dev_endpoints_are_off(client: TestClient):
    """Padrão desligado: 404 e nem aparece na documentação (plano Pixel §78).

    O endpoint aceita imagem arbitrária e não pertence ao fluxo de produção
    (plano Pixel §77). Deixá-lo respondendo por engano criaria uma segunda
    porta de processamento, fora do controle do JobManager.
    """
    resposta = client.post(
        ROTA, json={"image_base64": _base64_png(_sprite(64)), "profile": PROFILE}
    )
    assert resposta.status_code == 404

    caminhos = set(client.get("/openapi.json").json()["paths"])
    assert not [caminho for caminho in caminhos if caminho.startswith("/api/dev")]
    # E o caminho oficial de geração continua documentado.
    assert "/api/generation/jobs" in caminhos


def test_analyze_answers_when_dev_endpoints_are_on(dev_client: TestClient):
    """Ligado, o mesmo pedido passa a responder — só a configuração mudou."""
    resposta = dev_client.post(
        ROTA, json={"image_base64": _base64_png(_sprite(64)), "profile": PROFILE}
    )
    assert resposta.status_code == 200
    assert ROTA in dev_client.get("/openapi.json").json()["paths"]


# ---------------------------------------------------------------------------
# O relatório
# ---------------------------------------------------------------------------
def test_analyze_returns_the_validation_report(dev_client: TestClient):
    """A resposta é o veredito técnico do profile pedido (plano Pixel §78).

    Uma imagem que já cumpre o contrato sai com ``pixel_exact`` verdadeiro e
    com o mapa de hard checks do plano Pixel §46 — o relatório inteiro, não
    um booleano solto.
    """
    payload = dev_client.post(
        ROTA, json={"image_base64": _base64_png(_sprite(64)), "profile": PROFILE}
    ).json()

    assert payload["spec_id"] == PROFILE
    assert payload["pixel_exact"] is True
    assert 0 <= payload["quality_score"] <= 100
    assert payload["validation"]["technical"]["size"] == "64x64"
    assert payload["validation"]["technical"]["alpha_values"] == [0, 255]

    checks = _hard_checks(payload)
    assert checks["PX-DIM-001"] == "pass"
    assert checks["PX-ALPHA-001"] == "pass"
    assert checks["PX-COLOR-001"] == "pass"
    assert "fail" not in checks.values()


def test_analyze_measures_the_image_exactly_as_it_arrived(dev_client: TestClient):
    """Sem ``process``, o endpoint mede o bruto — não conserta nada.

    É o caso de uso que justifica o endpoint (plano Pixel §78): saber quanto
    a saída crua de um motor desvia do contrato. Se ele processasse por baixo
    dos panos, a medição passaria a ser do pós-processador, não do motor.
    """
    imagem = _sprite(128, alpha=180)  # dimensão errada e alpha parcial
    payload = dev_client.post(
        ROTA, json={"image_base64": _base64_png(imagem), "profile": PROFILE}
    ).json()

    assert payload["pixel_exact"] is False
    tecnico = payload["validation"]["technical"]
    assert tecnico["size"] == "128x128", "o relatório descreve a imagem que chegou"
    assert tecnico["alpha_values"] == [0, 180], "o alpha parcial continua parcial"

    falhas = {
        check["code"]: (check["expected"], check["actual"])
        for check in payload["validation"]["hard_checks"]
        if check["status"] == "fail"
    }
    # Plano Pixel §62: a falha diz o esperado e o obtido, sem exigir decodificação.
    assert falhas["PX-DIM-001"] == ("64x64", "128x128")
    assert "PX-ALPHA-001" in falhas

    # Nada foi processado, então não há o que relatar nem o que decidir.
    assert payload["processing"] is None
    assert payload["acceptance"] is None
    assert payload["status"] is None


def test_process_true_adds_the_processing_report_and_the_decision(dev_client: TestClient):
    """Com ``process``, roda o caminho real do pipeline e a decisão aparece.

    A mesma imagem reprovada acima passa a ser medida **depois** do
    pós-processamento: 128×128 vira a resolução lógica do profile e o alpha
    vira binário. Processamento, validação e decisão chegam em blocos
    separados — quem altera pixels, quem só mede e quem decide são peças
    distintas (plano Pixel §6 e §59).
    """
    imagem = _sprite(128, alpha=180)
    payload = dev_client.post(
        ROTA,
        json={"image_base64": _base64_png(imagem), "profile": PROFILE, "process": True},
    ).json()

    assert payload["pixel_exact"] is True
    assert payload["validation"]["technical"]["size"] == "64x64"
    assert payload["validation"]["technical"]["alpha_values"] == [0, 255]

    processamento = payload["processing"]
    assert processamento is not None
    assert processamento["spec_id"] == PROFILE
    assert processamento["source_size"] == [128, 128]
    assert processamento["logical_size"] == [64, 64]
    assert [passo["name"] for passo in processamento["steps"]] == [
        "pixel.input_normalizer",
        "pixel.canvas_normalizer",
        "pixel.logical_reducer",
        "pixel.alpha_normalizer",
        "pixel.palette_quantizer",
        "pixel.conservative_cleaner",
    ]

    aceitacao = payload["acceptance"]
    assert aceitacao is not None
    assert aceitacao["status"] in {"approved", "quality_warning"}
    assert payload["status"] == aceitacao["status"], "o status do topo é o da decisão"
    assert aceitacao["reasons"], "a decisão precisa vir explicada (plano Pixel §62)"

    # As métricas do plano Pixel §93 acompanham a análise, versões inclusive.
    metricas = payload["metrics"]
    assert metricas["raw_dimensions"] == [128, 128]
    assert metricas["logical_dimensions"] == [64, 64]
    assert metricas["profile_version"].startswith(f"{PROFILE}@")
    assert metricas["validator_version"] and metricas["postprocessor_version"]


def test_inline_spec_replaces_the_profile(dev_client: TestClient):
    """Um spec inline dispensa o YAML — a porta para testar um contrato novo.

    O plano Pixel §66 quer profile novo entrando em
    ``config/pixel_profiles.yaml``; antes disso, o pesquisador precisa poder
    experimentar um contrato candidato sem versionar nada.
    """
    payload = dev_client.post(
        ROTA,
        json={
            "image_base64": _base64_png(_sprite(64)),
            "spec": {"id": "experimento", "logical_size": {"width": 32, "height": 32}},
        },
    ).json()

    assert payload["spec_id"] == "experimento"
    assert payload["pixel_exact"] is False, "64×64 não cumpre um contrato de 32×32"
    assert _hard_checks(payload)["PX-DIM-001"] == "fail"


# ---------------------------------------------------------------------------
# Erros de entrada
# ---------------------------------------------------------------------------
def test_invalid_base64_returns_400(dev_client: TestClient):
    """Entrada malformada é erro do cliente, não stack trace de 500."""
    resposta = dev_client.post(
        ROTA, json={"image_base64": "isto não é base64!!", "profile": PROFILE}
    )
    assert resposta.status_code == 400
    assert "base64" in resposta.json()["detail"]


def test_valid_base64_that_is_not_an_image_returns_400(dev_client: TestClient):
    """Base64 legítimo com lixo dentro também para na porta."""
    lixo = base64.b64encode(b"nao sou um png").decode("ascii")
    resposta = dev_client.post(ROTA, json={"image_base64": lixo, "profile": PROFILE})
    assert resposta.status_code == 400


def test_unknown_profile_returns_404_listing_the_available_ones(dev_client: TestClient):
    """Profile inexistente devolve 404 dizendo quais existem.

    O endpoint é ferramenta de pesquisa: quem erra o nome do profile precisa
    da lista na própria resposta, não de uma ida ao YAML.
    """
    resposta = dev_client.post(
        ROTA, json={"image_base64": _base64_png(_sprite(64)), "profile": "nao_existe"}
    )
    assert resposta.status_code == 404
    detalhe = resposta.json()["detail"]
    assert "nao_existe" in detalhe
    assert PROFILE in detalhe


def test_request_without_profile_or_spec_returns_400(dev_client: TestClient):
    """Sem contrato não há o que validar: a imagem sozinha não basta."""
    resposta = dev_client.post(ROTA, json={"image_base64": _base64_png(_sprite(64))})
    assert resposta.status_code == 400


# ---------------------------------------------------------------------------
# A regra que separa diagnóstico de produção
# ---------------------------------------------------------------------------
def test_analyze_persists_nothing(dev_client: TestClient, container: AppContainer):
    """Analisar não é gerar: nada entra no storage nem no histórico (§78).

    O endpoint devolve relatório e ponto. Se ele gravasse o resultado, o
    módulo Pixel ganharia uma segunda porta de entrada de assets — sem job,
    sem projeto e sem registro de proveniência (plano §41) —, exatamente o
    que o plano Pixel §77 evita ao manter ``POST /api/generation/jobs`` como
    caminho único.
    """
    imagem = _base64_png(_sprite(128, alpha=180))
    antes = _arquivos(container)

    for processa in (False, True):
        resposta = dev_client.post(
            ROTA,
            json={"image_base64": imagem, "profile": PROFILE, "process": processa},
        )
        assert resposta.status_code == 200
        # A chamada realmente fez trabalho — senão o teste não provaria nada.
        assert resposta.json()["validation"]["hard_checks"]

    assert _arquivos(container) == antes, "o endpoint de diagnóstico gravou arquivo"
    assert run(container.service.history()) == [], "nada pode entrar no histórico"
