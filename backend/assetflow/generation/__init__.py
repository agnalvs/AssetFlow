"""Infraestrutura de geração do AssetFlow.

    assetflow/generation/
    ├── schemas/        # contratos universais (request, result, manifest, job)
    ├── kernel/         # a estante: contract, registry, resolver, kernel
    ├── engines/        # as gavetas (descobertas por manifesto)
    ├── prompting/      # SemanticPrompt, PromptBuilders e adapters
    ├── profiles/       # Generation Profiles (o que gerar, não com o quê)
    ├── pipelines/      # lógica de produto: Pixel (o app só gera Pixel Art)
    ├── postprocessing/ # regras proprietárias do AssetFlow
    └── service.py      # fachada única para o resto do sistema
"""
