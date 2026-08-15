# Gavetas (Engines) do AssetFlow

Cada subpasta deste diretório é uma **gaveta**: uma implementação concreta do
Engine Contract capaz de operar alguma tecnologia de geração de imagem.

O AssetFlow é a estante. As gavetas entram e saem.

## Regra de ouro

> Nenhuma classe fora de `generation/engines/<gaveta>/` pode conhecer
> `StableDiffusionXLPipeline`, `FluxPipeline`, workflows de ComfyUI, SDKs de
> fornecedor ou qualquer API específica de modelo.

O teste `tests/test_architecture_boundaries.py` falha o build se essa regra for
violada. Se a sua gaveta precisar vazar um conceito para fora, o conceito está
no lugar errado — provavelmente pertence ao manifesto ou a `engine_options`.

## Anatomia de uma gaveta

```text
engines/minha_gaveta/
├── __init__.py
├── manifest.json      # o que a gaveta sabe fazer (lido pelo AssetFlow)
├── config.py          # config tipada, construída a partir de engines.yaml
├── loader.py          # carregamento do modelo/cliente (opcional)
├── mapper.py          # Result Mapper: saída nativa -> formato do AssetFlow
├── prompt_adapter.py  # tradução do SemanticPrompt (opcional)
└── engine.py          # a classe que implementa ImageGenerationEngine
```

## Como adicionar uma gaveta nova

1. Crie a pasta e implemente `ImageGenerationEngine` (ou herde de
   `BaseImageGenerationEngine`, que já resolve manifesto e boilerplate).
2. Escreva o `manifest.json` declarando `capabilities`, `supports`, `limits`,
   `resources`, `timeouts` e o `entrypoint` (`pacote.modulo:Classe`).
3. Acrescente o `engine_id` à `discovery.allowlist` em `config/engines.yaml`
   e configure o bloco `engines.<id>` (habilitação, modelo, device, opções).
4. Se quiser que ela seja preferida para alguma capacidade, coloque o id no
   topo da lista correspondente em `config/capabilities.yaml`.
5. Rode a suíte de contrato:
   `pytest tests/contract/test_engine_contract.py`.

Nenhum dos passos acima exige alterar código do kernel, dos pipelines, da API
ou do frontend.

## Como remover ou substituir uma gaveta

- **Desligar:** `enabled: false` em `config/engines.yaml` (ou
  `POST /api/generation/engines/{id}/disable` em runtime).
- **Substituir:** registre a nova gaveta, coloque-a acima da antiga em
  `config/capabilities.yaml` e desligue a antiga. O fallback garante que a
  geração continue funcionando durante a transição.

## Gavetas atuais

| id | Descrição | Estado padrão |
|---|---|---|
| `mock-image-v1` | Gaveta de referência sem IA. Valida toda a arquitetura sem GPU. | habilitada |
| `mock-pixel-alt-v1` | Segunda gaveta, existe para provar a substituição (§67). | desabilitada |
| `diffusers-sdxl-v1` | Primeira gaveta real (Diffusers/SDXL). Exige GPU e extras. | desabilitada |

## O que a gaveta **não** deve fazer

- salvar arquivos (isso é do `AssetStorageService` — plano §39);
- conhecer projeto, usuário, job ou fila;
- aplicar regras de Pixel Art do AssetFlow (isso é do pós-processamento —
  plano §23 e §58);
- expor parâmetros próprios no contrato universal (use `engine_options`).
