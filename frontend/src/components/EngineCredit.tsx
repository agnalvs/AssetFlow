import type { EngineSelectionView } from "../types";

interface EngineCreditProps {
  selection: EngineSelectionView | null;
  nameOf: (engineId: string | null | undefined) => string;
}

/**
 * Quem gerou este asset (plano de motores §25, regra 3).
 *
 * A regra 3 pede três informações na tela: o motor solicitado, o motor
 * realmente usado e a versão/modelo carregado. Este componente é onde elas
 * aparecem — e a razão de ele existir é o caso em que as duas primeiras
 * divergem.
 *
 * Nota sobre uma regra que mudou de forma
 * ---------------------------------------
 * A versão anterior deste aviso era deliberadamente **anônima**: dizia que
 * houve substituição sem dizer por quem, porque a interface não podia
 * conhecer o nome de um motor (plano da tela §32/§46). Isso deixava a pessoa
 * sabendo que algo tinha acontecido e sem saber o quê.
 *
 * Com o seletor de motores, a restrição perdeu o sentido: a pessoa **escolheu**
 * um motor pelo nome, e esconder dela qual motor atendeu seria absurdo. O
 * espírito da regra continua valendo — nenhum nome de motor está escrito neste
 * arquivo. Todos vêm do catálogo servido pelo backend, via `nameOf`.
 */
export function EngineCredit({ selection, nameOf }: EngineCreditProps) {
  if (!selection?.resolved_engine_id) return null;

  const used = nameOf(selection.resolved_engine_id);
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
              O motor <strong>{nameOf(requested)}</strong> não pôde atender, e este
              asset foi gerado por <strong>{used}</strong>.
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
        Gerado por <strong>{used}</strong>
        {selection.mode === "auto" ? " (escolha automática)" : ""}
      </p>
      <ModelLine selection={selection} />
    </div>
  );
}

/**
 * Versão do motor e modelo carregado — a terceira parte da regra 3.
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
