"""Pré-visualização e correção do prompt (planos §26, §28 e §52).

O problema que este caminho resolve: entre a frase que a pessoa escreve e a
imagem que sai existe uma interpretação — o ``SemanticPrompt`` — e até agora
ela era invisível. Um asset errado não dizia se o erro foi do modelo ou da
leitura da frase, e a única ferramenta disponível era reescrever a descrição
até acertar por tentativa.

São dois movimentos, e os testes daqui cobrem os dois:

    POST /api/generation/prompt/preview   -> o que o AssetFlow entendeu
    POST /api/generation/jobs             -> com `semantic_prompt` corrigido

E um invariante que vale mais que os dois: **a pré-visualização e a geração
não podem discordar**. Se elas divergirem, a tela mostra uma coisa, o motor
recebe outra, e o recurso passa a mentir com credibilidade — pior do que não
existir.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from assetflow.api import create_app
from assetflow.bootstrap import AppContainer

PROMPT = "cavaleiro medieval com armadura azul"


@pytest.fixture
def client(container: AppContainer):
    container.settings.worker.embedded = True
    with TestClient(create_app(container=container)) as test_client:
        yield test_client


def _preview(client: TestClient, **overrides) -> dict:
    payload = {
        "project_id": "project_preview",
        "profile": "pixel_character_64",
        "prompt": PROMPT,
    }
    payload.update(overrides)
    response = client.post("/api/generation/prompt/preview", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _wait_for_terminal(client: TestClient, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    payload: dict = {}
    while time.monotonic() < deadline:
        payload = client.get(f"/api/generation/jobs/{job_id}").json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job não terminou a tempo: {payload}")


# ---------------------------------------------------------------------------
# Ver
# ---------------------------------------------------------------------------
def test_preview_shows_the_reading_the_builder_made(client: TestClient):
    """A leitura completa, incluindo o que a pessoa nunca escreveu.

    ``view``, ``pose`` e a lista de ``avoid`` não estão na frase: são decisões
    de produto do PromptBuilder. Justamente por isso precisam aparecer — são
    elas que explicam por que a imagem saiu de lado, ou por que o modelo não
    devolveu uma folha de sprite.
    """
    preview = _preview(client)

    assert preview["profile"] == "pixel_character_64"
    assert preview["capability"] == "text_to_image.pixel"
    assert preview["source"] == "builder"

    semantic = preview["semantic"]
    assert semantic["subject"] == PROMPT
    assert semantic["medium"] == "pixel_art"
    assert semantic["view"] == "side"
    assert "sprite sheet" in semantic["avoid"]
    assert semantic["technical"]["limited_palette"] == 16
    assert semantic["composition"]["single_subject"] is True

    # O texto neutro existe para conferência humana; quem manda é o semantic.
    assert PROMPT in preview["positive"]
    assert "sprite sheet" in (preview["negative"] or "")


def test_attributes_still_feed_the_reading(client: TestClient):
    """O caminho antigo (``attributes``) não foi substituído, só ficou visível."""
    preview = _preview(client, attributes={"view": "front", "style": "dark fantasy"})

    assert preview["semantic"]["view"] == "front"
    assert preview["semantic"]["style"] == "dark fantasy"
    assert preview["source"] == "builder"


def test_preview_generates_nothing(client: TestClient):
    """Pré-visualizar não pode custar um job — nem uma linha de histórico.

    É o que separa este endpoint de uma geração: ele responde a pergunta "o
    que aconteceria?" sem que nada aconteça.
    """
    before = client.get("/api/generation/jobs").json()["total"]

    _preview(client)
    _preview(client, prompt="outra ideia qualquer")

    assert client.get("/api/generation/jobs").json()["total"] == before
    assert client.get("/api/assets/history").json() == []


def test_preview_accepts_a_half_written_description(client: TestClient):
    """A tela pede a leitura enquanto a pessoa digita.

    ``POST /jobs`` recusa descrição vazia, e deve mesmo. Aqui não: recusar o
    pedido pela metade transformaria cada tecla em uma mensagem de erro
    vermelha, e a pré-visualização existe para acompanhar a digitação.
    """
    preview = _preview(client, prompt="")

    assert preview["semantic"]["subject"] == ""
    assert preview["semantic"]["avoid"]  # os padrões de produto continuam lá


# ---------------------------------------------------------------------------
# Corrigir
# ---------------------------------------------------------------------------
def test_edited_semantic_replaces_the_builder(client: TestClient):
    """A semântica escrita no pedido ganha do builder (plano §26).

    O laço inteiro do recurso: leia, discorde, devolva corrigido. Aqui a
    correção é a que mais dói na prática — o builder decidiu ``side`` porque é
    o padrão do profile, e quem pediu queria ``front``.
    """
    semantic = _preview(client)["semantic"]
    semantic["view"] = "front"
    semantic["avoid"] = [item for item in semantic["avoid"] if item != "sprite sheet"]

    created = client.post(
        "/api/generation/jobs",
        json={
            "project_id": "project_preview",
            "profile": "pixel_character_64",
            "prompt": PROMPT,
            "semantic_prompt": semantic,
            "output": {"variations": 1},
        },
    )
    assert created.status_code == 202, created.text

    job = _wait_for_terminal(client, created.json()["job_id"])
    assert job["status"] == "completed", job.get("error")

    prompt = job["prompt"]
    assert prompt["source"] == "request"
    assert prompt["semantic"]["view"] == "front"
    assert "sprite sheet" not in prompt["semantic"]["avoid"]
    assert "front view" in prompt["positive"]
    assert "sprite sheet" not in (prompt["negative"] or "")


def test_the_job_echoes_the_reading_that_produced_the_asset(client: TestClient):
    """Sem edição, o job devolve a leitura do builder — não uma reconstrução.

    A tela mostra este objeto ao lado do asset. Se ele fosse remontado pelo
    cliente, envelheceria em silêncio no dia em que o builder mudasse, e o
    painel passaria a descrever uma geração que não aconteceu.
    """
    created = client.post(
        "/api/generation/jobs",
        json={
            "project_id": "project_preview",
            "profile": "pixel_character_64",
            "prompt": PROMPT,
            "output": {"variations": 1},
        },
    ).json()

    job = _wait_for_terminal(client, created["job_id"])
    assert job["status"] == "completed", job.get("error")
    assert job["prompt"]["source"] == "builder"
    assert job["prompt"]["semantic"]["subject"] == PROMPT


def test_preview_and_generation_cannot_disagree(client: TestClient):
    """O invariante do recurso, verificado nos dois modos.

    Mesmo corpo, mesma resposta: o que a pré-visualização mostrou é o que a
    geração usou. Se um dia alguém duplicar a regra de precedência em vez de
    chamar ``resolve_semantic_prompt``, é este teste que cai.
    """
    for extra in ({}, {"attributes": {"view": "top_down", "pose": "walk"}}):
        body = {
            "project_id": "project_preview",
            "profile": "pixel_character_64",
            "prompt": PROMPT,
            "output": {"variations": 1},
            **extra,
        }
        preview = client.post("/api/generation/prompt/preview", json=body).json()
        created = client.post("/api/generation/jobs", json=body).json()
        job = _wait_for_terminal(client, created["job_id"])

        assert job["status"] == "completed", job.get("error")
        assert job["prompt"]["semantic"] == preview["semantic"]
        assert job["prompt"]["positive"] == preview["positive"]


def test_studio_mode_has_its_own_reading(client: TestClient):
    """A leitura é do profile, não do modo Pixel.

    Arte 2D convencional passa por outro builder: nada de paleta limitada,
    nada de borda dura, e a lista de ``avoid`` inclui "pixel art". Se o painel
    mostrasse a leitura Pixel aqui, ele estaria descrevendo outro produto.
    """
    preview = _preview(client, profile="studio_character")

    assert preview["capability"] == "text_to_image.general"
    assert preview["semantic"]["medium"] == "cartoon_2d"
    assert preview["semantic"]["technical"]["limited_palette"] is None
    assert "pixel art" in preview["semantic"]["avoid"]


def test_unknown_profile_fails_the_same_way_as_generation(client: TestClient):
    """Erro normalizado, igual ao do POST de job — a tela já sabe tratar."""
    response = client.post(
        "/api/generation/prompt/preview",
        json={"project_id": "p", "profile": "nao_existe", "prompt": PROMPT},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "profile_not_found"
