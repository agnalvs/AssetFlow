import type { UseCreationCatalog } from "../hooks/useCreationCatalog";
import type { EngineSelectionView } from "../types";

interface EngineCreditProps {
  selection: EngineSelectionView | null;
  catalog: UseCreationCatalog;
}

/**
 * Como este asset foi criado (plano de correção §42; plano de motores §25.3).
 *
 * O §42 pede duas linhas discretas, e o que elas dizem depende do método:
 *
 *     Método   Modelo de imagem        Método   Agente Pixel
 *     Motor    FLUX Pixel              Agente   AssetFlow Pixel Agent
 *
 * A separação não é cosmética. Antes de existir método, este bloco só sabia
 * dizer "gerado por X", e X tanto podia ser um modelo quanto um agente — o
 * mesmo achatamento que o plano de correção veio desfazer, agora na tela do
 * resultado.
 *
 * O caso que ele existe para cobrir continua sendo o do §25.3: quando o que
 * foi pedido e o que rodou **não** são a mesma coisa. Um fallback silencioso
 * é o que ele impede.
 *
 * Nenhum nome de motor, agente ou método está escrito neste arquivo: todos
 * vêm do catálogo servido pelo backend.
 */
export function EngineCredit({ selection, catalog }: EngineCreditProps) {
  if (!selection) return null;

  const isAgent = selection.resolved_strategy === "pixel_agent";
  const method = catalog.strategyNameOf(selection.resolved_strategy);

  if (isAgent) {
    if (!selection.agent) return null;
    return (
      <div className="result__engine">
        <p>
          <span className="result__engine-key">Método</span>{" "}
          <strong>{method}</strong>
        </p>
        <p>
          <span className="result__engine-key">Agente</span>{" "}
          <strong>{catalog.agentNameOf(selection.agent.id)}</strong>
        </p>
        <p className="result__engine-model">versão {selection.agent.version}</p>
      </div>
    );
  }

  if (!selection.resolved_engine_id) return null;

  const used = catalog.engineNameOf(selection.resolved_engine_id);
  const requested = selection.requested_engine_id;
  const substituted =
    selection.fallback_used ||
    (requested !== null && requested !== selection.resolved_engine_id);

  if (substituted) {
    return (
      <div className="result__engine result__engine--fallback" role="status">
        <p>
          <span aria-hidden="true">⚠</span>{" "}
          {requested ? (
            <>
              O motor <strong>{catalog.engineNameOf(requested)}</strong> não pôde
              atender, e este asset foi gerado por <strong>{used}</strong>.
            </>
          ) : (
            <>
              O motor preferido não estava disponível, e este asset foi gerado por{" "}
              <strong>{used}</strong>.
            </>
          )}{" "}
          O resultado pode ser bem diferente do esperado — vale gerar de novo.
        </p>
        <ModelLine selection={selection} />
      </div>
    );
  }

  return (
    <div className="result__engine">
      <p>
        <span className="result__engine-key">Método</span> <strong>{method}</strong>
      </p>
      <p>
        <span className="result__engine-key">Motor</span> <strong>{used}</strong>
        {selection.mode === "auto" ? " (escolha automática)" : ""}
      </p>
      <ModelLine selection={selection} />
    </div>
  );
}

/**
 * Versão do motor e modelo carregado — a terceira parte da regra 3 do §25.
 *
 * Parece detalhe técnico demais para a tela, e é justamente o que responde
 * "por que a mesma descrição saiu diferente da semana passada?". Sem esta
 * linha, a resposta exige abrir o histórico no servidor.
 */
function ModelLine({ selection }: { selection: EngineSelectionView }) {
  const parts: string[] = [];
  if (selection.resolved_engine_version) {
    parts.push(`versão ${selection.resolved_engine_version}`);
  }
  if (selection.resolved_model_id) {
    parts.push(selection.resolved_model_id);
  }
  if (parts.length === 0) return null;
  return <p className="result__engine-model">{parts.join(" · ")}</p>;
}
