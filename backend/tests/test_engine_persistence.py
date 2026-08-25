"""O dossiê obrigatório de cada geração (plano de motores §18).

O §18 lista sete arquivos e cinco campos de identidade que **toda** geração
precisa deixar para trás. A razão está escrita no próprio plano: sem eles não
há benchmark nem depuração — só a lembrança de que "semana passada estava
melhor".

Três já existiam (``resolved_spec.json``, ``processing.json``,
``validation.json``); quatro entraram com esta etapa, e são os que respondem
*com qual motor, a partir de qual frase*.
"""

from __future__ import annotations

import json

from assetflow.bootstrap import AppContainer
from assetflow.generation.schemas import (
    AssetGenerationRequest,
    AssetOutputOverrides,
    EngineSelector,
)
from tests.conftest import process_next_job, run


def _generate(container: AppContainer, **overrides):
    payload = {
        "project_id": "project_test",
        "profile": "pixel_character_64",
        "prompt": "a small green tree",
        "output": AssetOutputOverrides(variations=1),
        "seed": 4242,
    }
    payload.update(overrides)
    job = run(container.service.submit(AssetGenerationRequest.model_validate(payload)))
    run(process_next_job(container))
    return run(container.service.get_job(job.id))


def _artifact(container: AppContainer, job, name: str) -> bytes:
    uri = job.asset.variants[0].artifacts[name]
    return run(container.storage.read(uri))


def _document(container: AppContainer, job, name: str) -> dict:
    return json.loads(_artifact(container, job, name).decode("utf-8"))


def test_every_generation_leaves_the_required_files(container: AppContainer):
    job = _generate(container)
    files = set(job.asset.variants[0].artifacts)

    # Os do plano de motores §18 que esta etapa acrescentou...
    assert {
        "raw_prompt.txt",
        "parsed_spec.json",
        "engine_selection.json",
        "engine_output.json",
    } <= files
    # ...ao lado dos que o módulo Pixel já gravava.
    assert {"resolved_spec.json", "processing.json", "validation.json"} <= files


def test_raw_prompt_keeps_the_sentence_exactly_as_written(container: AppContainer):
    job = _generate(container, prompt="uma árvore com maçãs vermelhas")
    assert (
        _artifact(container, job, "raw_prompt.txt").decode("utf-8")
        == "uma árvore com maçãs vermelhas"
    )


def test_parsed_spec_keeps_the_reading_and_the_text_it_became(
    container: AppContainer,
):
    """Os dois, porque respondem perguntas diferentes.

    A semântica diz o que o AssetFlow entendeu; o texto diz o que o motor
    recebeu. Quando um resultado sai errado, o defeito costuma estar na
    distância entre um e outro — e com só um dos dois ela é invisível.
    """
    job = _generate(container)
    document = _document(container, job, "parsed_spec.json")

    assert document["semantic"]["subject"]
    assert document["positive"]
    assert document["capability"] == "text_to_image.pixel"


def test_engine_selection_records_requested_and_resolved(container: AppContainer):
    """O arquivo que responde "o motor que escolhi foi o que gerou isto?"."""
    job = _generate(
        container,
        engine=EngineSelector(mode="manual", engine_id="mock-image-v1"),
    )
    document = _document(container, job, "engine_selection.json")

    assert document["selection_mode"] == "manual"
    assert document["requested_engine_id"] == "mock-image-v1"
    assert document["resolved_engine_id"] == "mock-image-v1"
    assert document["fallback_used"] is False
    assert document["allow_fallback"] is False  # §25, regra 2
    assert document["attempted_engines"] == ["mock-image-v1"]
    assert document["source"] == "ui_selection"


def test_engine_output_records_the_full_identity(container: AppContainer):
    """Motor, versão, versão do adapter, modelo e LoRA (plano de motores §18).

    Os cinco, porque quatro não bastam: o mesmo modelo com outro adapter, ou
    com outra LoRA, produz outro asset.
    """
    job = _generate(container)
    document = _document(container, job, "engine_output.json")

    assert document["engine_id"]
    assert document["engine_version"]
    assert "adapter_version" in document
    assert "model_id" in document
    assert "lora_id" in document
    assert document["outputs"][0]["seed"] is not None
    assert document["timings_ms"]


def test_the_history_record_keeps_requested_and_used_engine(
    container: AppContainer,
):
    """O mesmo par no histórico — é por ele que o benchmark procura fallback."""
    job = _generate(
        container, engine=EngineSelector(mode="manual", engine_id="mock-image-v1")
    )
    records = run(container.records.list(project_id="project_test", limit=5))
    record = next(item for item in records if item.job_id == job.id)

    assert record.requested_engine_id == "mock-image-v1"
    assert record.engine_selection_mode == "manual"
    assert record.engine_id == "mock-image-v1"
    assert record.adapter_version is None or isinstance(record.adapter_version, str)
    assert record.metadata["engine_selection"]["selection_mode"] == "manual"


def test_the_resolved_spec_on_disk_carries_the_engine_decision(
    container: AppContainer,
):
    """O contrato gravado ao lado do arquivo inclui o motor (plano de motores §5)."""
    job = _generate(container)
    document = _document(container, job, "resolved_spec.json")

    assert "engine" in document
    assert document["engine"]["selection_mode"] == "auto"
    assert document["sources"]["engine"]
