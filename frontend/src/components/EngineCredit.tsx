import type { UseEngineCatalog } from "../hooks/useEngineCatalog";
import type { EngineSelectionView, PixelOptimization } from "../types";
import { optimizationLabel } from "../labels";

interface EngineCreditProps {
  selection: EngineSelectionView | null;
  /** O que o Pixel Optimizer fez com esta variação (plano Optimizer §30). */
  optimization: PixelOptimization | null;
  catalog: UseEngineCatalog;
}

/**
 * Como este asset foi criado (plano Optimizer §30; plano de motores §25.3).
 *
 * Duas linhas, e o §30 é explícito sobre quais:
 *
 *     Motor        FLUX Pixel
 *     Otimização   14 pixels corrigidos · qualidade 68 → 81
 *
 * A segunda linha existe porque a primeira, sozinha, credita ao motor um
 * resultado que não é só dele. Todo asset Pixel passa pelo Optimizer (§46), e
 * quando ele corrige algo isso muda o arquivo entregue — atribuí-lo
 * inteiramente ao motor tornaria impossível comparar motores de verdade.
 *
 * O caso que este bloco existe para cobrir continua sendo o do §25.3: quando
 * o motor pedido e o que rodou **não** são a mesma coisa. Um fallback
 * silencioso é o que ele impede.
 *
 * Nenhum nome de motor está escrito neste arquivo: todos vêm do catálogo
 * servido pelo backend.
 */
export function EngineCredit({
  selection,
  optimization,
  catalog,
}: EngineCreditProps) {
  if (!selection) return null;
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
        <OptimizationLine optimization={optimization} />
      </div>
    );
  }

  return (
    <div className="result__engine">
      <p>
        <span className="result__engine-key">Motor</span> <strong>{used}</strong>
        {selection.mode === "auto" ? " (escolha automática)" : ""}
      </p>
      <ModelLine selection={selection} />
      <OptimizationLine optimization={optimization} />
    </div>
  );
}

/**
 * O que o Optimizer fez, em uma linha (plano Optimizer §30).
 *
 * Ela aparece **sempre** que houver laudo, inclusive quando nada foi
 * corrigido. "Nenhuma correção necessária" é informação: diz que o sprite
 * chegou bom, o que é elogio ao motor. Esconder a linha nesse caso faria
 * parecer que o estágio às vezes não roda — e ele sempre roda (§46).
 */
function OptimizationLine({
  optimization,
}: {
  optimization: PixelOptimization | null;
}) {
  if (!optimization) return null;
  return (
    <p>
      <span className="result__engine-key">Otimização</span>{" "}
      <strong>{optimizationLabel(optimization)}</strong>
    </p>
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
