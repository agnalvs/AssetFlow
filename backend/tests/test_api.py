"""Testes da API web (planos §51 a §55).

O ponto que estes testes protegem: **nada na superfície HTTP revela qual
tecnologia gerou a imagem**. O cliente fala em capability, profile e job.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from assetflow.api import create_app
from assetflow.bootstrap import AppContainer


@pytest.fixture
def client(container: AppContainer):
    # Worker embutido ligado: a API precisa se comportar como em produção.
    container.settings.worker.embedded = True
    with TestClient(create_app(container=container)) as test_client:
        yield test_client


def _wait_for_terminal(client: TestClient, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    payload: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/generation/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job não terminou a tempo: {payload}")


def test_health(client: TestClient):
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert "mock-image-v1" in payload["engines"]


def test_list_engines(client: TestClient):
    payload = client.get("/api/generation/engines").json()
    ids = {item["id"] for item in payload["items"]}
    assert {"mock-image-v1", "mock-pixel-alt-v1", "diffusers-sdxl-v1"} <= ids
    assert payload["engine_api_version"] == "1"

    mock = next(item for item in payload["items"] if item["id"] == "mock-image-v1")
    assert mock["enabled"] is True
    assert "text_to_image.pixel" in mock["capabilities"]
    assert mock["health"]["status"] == "healthy"
    assert set(mock["supports"]) >= {"seed", "lora", "controlnet", "image_reference"}


def test_engine_catalog_is_what_the_selector_draws(
    container: AppContainer, client: TestClient
):
    """O catálogo do plano de motores §6, servido pronto para a tela.

    A tela desenha o seletor a partir desta resposta. Se ela não trouxer nome,
    resumo e disponibilidade, o frontend precisaria completar a informação por
    conta própria — e para isso teria de conhecer os motores pelo nome, que é
    justamente o que o §24 proíbe.
    """
    # A suíte roda com as gavetas de referência; habilitar esta é o que faz o
    # caso exercitar também o caminho "motor disponível".
    container.registry.enable("texel-style-v1")

    payload = client.get("/api/generation/engines/catalog").json()
    ids = {item["engine_id"] for item in payload["items"]}

    # Os quatro motores do §4.1 aparecem na vitrine...
    assert {"flux-pixel-v1", "sdpixl-v1", "pixel-forge-v1", "texel-style-v1"} <= ids
    # ...e as gavetas de referência, não: elas continuam resolvendo por
    # capacidade, só não são oferecidas.
    assert "mock-image-v1" not in ids

    texel = next(item for item in payload["items"] if item["engine_id"] == "texel-style-v1")
    assert texel["display_name"] == "Texel-style Agent"
    assert texel["engine_family"] == "agentic"
    assert texel["summary"], "sem resumo, o seletor não tem o que mostrar (§4.2)"
    assert texel["highlights"], "o §4.2 pede os pontos fortes em tópicos"
    assert texel["available"] is True
    assert texel["supports_exact_resolution"] is True


def test_engine_catalog_explains_an_unavailable_engine(client: TestClient):
    """Motor indisponível continua listado, com o motivo — não some da lista.

    Quem procura o SD-πXL precisa descobrir que ele existe e não está ligado,
    e não concluir que o AssetFlow não o tem.
    """
    payload = client.get("/api/generation/engines/catalog").json()
    sdpixl = next(item for item in payload["items"] if item["engine_id"] == "sdpixl-v1")

    assert sdpixl["available"] is False
    assert sdpixl["unavailable_reason"]
    assert "experimental" in sdpixl["badges"]


def test_engine_catalog_filters_by_capability(client: TestClient):
    payload = client.get(
        "/api/generation/engines/catalog", params={"capability": "text_to_image.general"}
    ).json()

    assert payload["capability"] == "text_to_image.general"
    for item in payload["items"]:
        assert "text_to_image.general" in item["capabilities"]


def test_get_engine_and_toggle(client: TestClient):
    assert client.get("/api/generation/engines/mock-pixel-alt-v1").json()["enabled"] is False
    assert client.post("/api/generation/engines/mock-pixel-alt-v1/enable").json()["enabled"] is True
    assert client.post("/api/generation/engines/mock-pixel-alt-v1/disable").json()["enabled"] is False
    assert client.get("/api/generation/engines/inexistente").status_code == 404


def test_capabilities_endpoint_does_not_leak_technology(client: TestClient):
    items = client.get("/api/generation/capabilities").json()
    by_capability = {item["capability"]: item for item in items}

    pixel = by_capability["text_to_image.pixel"]
    assert pixel["available"] is True
    assert pixel["mode"] == "pixel"
    assert "mock-image-v1" in pixel["engines"]

    # Capacidades futuras aparecem como não disponíveis, não somem.
    assert by_capability["inpainting.general"]["available"] is False
    assert by_capability["animation.pixel"]["experimental"] is True


def test_profiles_endpoint(client: TestClient):
    profiles = {item["id"]: item for item in client.get("/api/generation/profiles").json()}
    assert profiles["pixel_character_64"]["logical_size"] == [64, 64]
    assert profiles["pixel_character_64"]["capability"] == "text_to_image.pixel"
    assert profiles["studio_character"]["logical_size"] is None
    # Nenhum profile cita um motor.
    assert all("engine" not in item for item in profiles.values())


def test_create_job_returns_202_and_queued(client: TestClient):
    response = client.post(
        "/api/generation/jobs",
        json={
            "project_id": "project_001",
            "profile": "pixel_character_64",
            "prompt": "young warrior with blue armor",
            "output": {"variations": 2},
            "engine": {"mode": "auto"},
        },
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["capability"] == "text_to_image.pixel"
    assert payload["pipeline"] == "pixel.character"
    assert "job_id" in payload


def test_full_generation_flow_over_http(client: TestClient):
    created = client.post(
        "/api/generation/jobs",
        json={
            "project_id": "project_001",
            "profile": "pixel_character_64",
            "prompt": "young warrior with blue armor",
            "attributes": {"view": "side", "pose": "idle"},
            "output": {"variations": 2},
            "seed": 777,
        },
    ).json()

    job = _wait_for_terminal(client, created["job_id"])
    assert job["status"] == "completed", job.get("error")
    assert job["progress"] == 1.0

    asset = job["asset"]
    assert asset["type"] == "character"
    assert asset["mode"] == "pixel"
    assert len(asset["variants"]) == 2

    variant = asset["variants"][0]
    assert variant["width"] == 64 and variant["logical_width"] == 64
    assert variant["uri"].startswith("assetflow-local://")
    assert variant["palette"]

    # A resposta já traz a URL pronta: o cliente não precisa resolver URI.
    assert variant["url"] == f"/api/assets/files/{variant['uri'].split('://', 1)[1]}"
    assert variant["thumbnail_url"]

    image = client.get(variant["url"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content[:8] == b"\x89PNG\r\n\x1a\n"

    # O caminho antigo (resolve explícito) continua valendo.
    resolved = client.get("/api/assets/resolve", params={"uri": variant["uri"]}).json()
    assert resolved["url"] == variant["url"]


def test_manual_engine_selection_over_http(client: TestClient):
    client.post("/api/generation/engines/mock-pixel-alt-v1/enable")
    created = client.post(
        "/api/generation/jobs",
        json={
            "project_id": "project_001",
            "profile": "pixel_character_64",
            "prompt": "goblin scout",
            "output": {"variations": 1},
            "engine": {"mode": "manual", "engine_id": "mock-pixel-alt-v1"},
        },
    ).json()

    job = _wait_for_terminal(client, created["job_id"])
    assert job["status"] == "completed", job.get("error")
    assert job["engine"]["id"] == "mock-pixel-alt-v1"


def test_cancel_endpoint(client: TestClient):
    created = client.post(
        "/api/generation/jobs",
        json={
            "project_id": "project_001",
            "profile": "pixel_character_64",
            "prompt": "slow asset",
            "output": {"variations": 4},
            "engine_options": {"mock-image-v1": {"simulated_latency_ms": 200}},
        },
    ).json()

    cancelled = client.post(f"/api/generation/jobs/{created['job_id']}/cancel").json()
    assert cancelled["status"] in {"cancelled", "cancel_requested"}

    final = _wait_for_terminal(client, created["job_id"])
    assert final["status"] == "cancelled"


def test_unknown_profile_returns_404_with_normalized_error(client: TestClient):
    response = client.post(
        "/api/generation/jobs",
        json={"project_id": "p", "profile": "nao_existe", "prompt": "x"},
    )
    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "profile_not_found"
    assert "available" in str(payload["detail"])


def test_capability_without_engine_returns_503(client: TestClient):
    response = client.post(
        "/api/generation/jobs",
        json={"project_id": "p", "capability": "inpainting.general", "prompt": "x"},
    )
    # O job é criado; a indisponibilidade aparece no job (não no POST),
    # porque a resolução acontece no worker.
    assert response.status_code == 202
    job = _wait_for_terminal(client, response.json()["job_id"])
    assert job["status"] == "failed"
    assert job["error"]["code"] == "no_engine_available"


def test_job_listing_and_events(client: TestClient):
    created = client.post(
        "/api/generation/jobs",
        json={
            "project_id": "project_listing",
            "profile": "pixel_character_32",
            "prompt": "tiny mage",
            "output": {"variations": 1},
        },
    ).json()
    _wait_for_terminal(client, created["job_id"])

    listing = client.get("/api/generation/jobs", params={"project_id": "project_listing"}).json()
    assert listing["total"] == 1

    detailed = client.get(
        f"/api/generation/jobs/{created['job_id']}", params={"include_events": True}
    ).json()
    assert detailed["events"]
    assert detailed["events"][0]["status"] == "queued"


def test_history_endpoint(client: TestClient):
    created = client.post(
        "/api/generation/jobs",
        json={
            "project_id": "project_history",
            "profile": "pixel_prop_64",
            "prompt": "treasure chest",
            "output": {"variations": 1},
        },
    ).json()
    _wait_for_terminal(client, created["job_id"])

    history = client.get("/api/assets/history", params={"project_id": "project_history"}).json()
    assert history
    assert history[0]["engine_id"]
    assert history[0]["model_id"]
    assert history[0]["capability"] == "text_to_image.pixel"


def test_openapi_documents_the_public_contract(client: TestClient):
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    assert {
        "/api/generation/engines",
        "/api/generation/engines/catalog",
        "/api/generation/engines/{engine_id}",
        "/api/generation/capabilities",
        "/api/generation/jobs",
        "/api/generation/jobs/{job_id}",
        "/api/generation/jobs/{job_id}/cancel",
    } <= paths
