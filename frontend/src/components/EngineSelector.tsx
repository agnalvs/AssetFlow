import type { UseEngineCatalog } from "../hooks/useEngineCatalog";
import type {
  CreationSelection,
  EngineCatalogEntry,
  ResolvedEngine,
  ResolvedPixelPipeline,
} from "../types";
import {
  engineBadgeLabel,
  familyLabel,
  qualityLabel,
  speedLabel,
} from "../labels";

interface EngineSelectorProps {
  selection: CreationSelection;
  catalog: UseEngineCatalog;
  /** O que o backend resolveu para este pedido, quando já sabemos. */
  resolvedEngine: ResolvedEngine | null;
  /** O que virá depois do motor. Mostrado, nunca escolhido (§30). */
  pipeline: ResolvedPixelPipeline | null;
  disabled?: boolean;
  onChange: (selection: CreationSelection) => void;
}

/**
 * O seletor de **motor** (plano Optimizer §25, §26 e §27).
 *
 * A mudança que este componente representa:
 *
 *     antes                              depois
 *     MÉTODO DE CRIAÇÃO                  MOTOR
 *     ├─ Automático                      ├─ Automático
 *     ├─ Modelo de imagem ─> MOTOR       ├─ FLUX Pixel
 *     └─ Agente Pixel ─> AGENTE          ├─ SD-πXL
 *                                        └─ Pixel Forge
 *
 * O seletor de método perguntava qual das duas metades do pipeline usar. Não
 * são alternativas: o motor produz a imagem, e o AssetFlow Pixel Optimizer
 * corrige a imagem produzida — em **toda** geração (§46). Perguntar era pedir
 * uma escolha que não existe, e a resposta errada custava um asset.
 *
 * Por isso o Optimizer não aparece em lista nenhuma aqui (§76). Ele aparece
 * na nota de rodapé deste bloco, contando o que **vai** acontecer, e no
 * resultado, contando o que aconteceu (§30).
 */
export function EngineSelector({
  selection,
  catalog,
  resolvedEngine,
  pipeline,
  disabled = false,
  onChange,
}: EngineSelectorProps) {
  const busy = disabled || catalog.loading;
  const chosen = selection.engineId
    ? catalog.engines.find((engine) => engine.engine_id === selection.engineId) ?? null
    : null;

  return (
    <div className="engine" role="group" aria-label="Motor de geração">
      <label className="engine__control">
        <span className="engine__label">Motor de geração</span>
        <select
          className="controls__field"
          value={selection.engineId ?? ""}
          disabled={busy}
          onChange={(event) =>
            onChange({ ...selection, engineId: event.target.value || null })
          }
        >
          <option value="">Automático</option>
          {catalog.engines.map((engine) => (
            <option
              key={engine.engine_id}
              value={engine.engine_id}
              // Um motor indisponível continua **visível** e desabilitado:
              // quem procura por ele precisa descobrir que existe e não está
              // pronto, não concluir que o AssetFlow não o tem.
              disabled={!engine.available}
            >
              {engine.display_name}
              {engine.available ? "" : " (indisponível)"}
            </option>
          ))}
        </select>
      </label>

      {catalog.error ? <p className="engine__error">{catalog.error}</p> : null}

      {!catalog.loading && !catalog.error && catalog.engines.length === 0 ? (
        <p className="engine__error">
          Nenhum motor habilitado atende este modo. A geração ainda funciona em
          Automático, com o motor que o backend encontrar.
        </p>
      ) : null}

      {selection.engineId === null ? (
        <AutoNote resolved={resolvedEngine} catalog={catalog} />
      ) : null}

      {chosen ? <EngineCard engine={chosen} /> : null}

      <PipelineNote pipeline={pipeline} />
    </div>
  );
}

/**
 * O que "Automático" significa para **este** pedido (plano de motores §17).
 *
 * Antes de o backend responder, uma promessa genérica. Depois, o motor
 * escolhido e o motivo — que é o que transforma o Auto de caixa preta em
 * decisão explicada.
 */
function AutoNote({
  resolved,
  catalog,
}: {
  resolved: ResolvedEngine | null;
  catalog: UseEngineCatalog;
}) {
  if (!resolved?.engine_id) {
    return (
      <p className="engine__auto">
        O AssetFlow escolherá automaticamente o motor mais adequado.
      </p>
    );
  }

  return (
    <div className="engine__auto engine__auto--resolved">
      <p>
        <strong>Motor resolvido:</strong> {catalog.engineNameOf(resolved.engine_id)}
      </p>
      {resolved.reason ? (
        <p className="engine__reason">Motivo: {resolved.reason}</p>
      ) : null}
    </div>
  );
}

/**
 * O que vem **depois** do motor (plano Optimizer §29 e §30).
 *
 * Uma linha, sem controle nenhum, e é essa a mensagem: a otimização acontece
 * independentemente do motor escolhido. Sem ela, quem lembra do seletor
 * antigo procuraria o "Agente Pixel" e concluiria que ele sumiu — quando o
 * que ele fazia de melhor passou a acontecer sempre.
 */
function PipelineNote({ pipeline }: { pipeline: ResolvedPixelPipeline | null }) {
  if (!pipeline) return null;

  if (!pipeline.optimize) {
    return (
      <p className="engine__auto">
        A otimização pixel a pixel está <strong>desligada</strong> nesta
        instalação. O asset sai como o motor e o pós-processamento o
        entregarem.
      </p>
    );
  }

  return (
    <p className="engine__auto">
      Depois de gerar, o <strong>AssetFlow Pixel Optimizer</strong> revisa o
      sprite na grade final e corrige o que tiver correção segura — em até{" "}
      {pipeline.max_iterations} passadas. Isso vale para qualquer motor.
    </p>
  );
}

/** O resumo do motor escolhido (plano de motores §4.2). */
function EngineCard({ engine }: { engine: EngineCatalogEntry }) {
  return (
    <div className="engine__card">
      <p className="engine__summary">{engine.summary || engine.description}</p>

      <ul className="engine__tags">
        <li className="engine__tag">{familyLabel(engine.engine_family)}</li>
        <li className="engine__tag">{speedLabel(engine.speed_tier)}</li>
        <li className="engine__tag">{qualityLabel(engine.quality_tier)}</li>
        {engine.supports_exact_resolution ? (
          <li className="engine__tag">resolução exata</li>
        ) : null}
        {engine.supports_palette_control ? (
          <li className="engine__tag">controla a paleta</li>
        ) : null}
        {engine.badges.map((badge) => (
          <li key={badge} className="engine__tag engine__tag--badge">
            {engineBadgeLabel(badge)}
          </li>
        ))}
      </ul>

      {engine.highlights.length > 0 ? (
        <ul className="engine__highlights">
          {engine.highlights.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}

      {!engine.available && engine.unavailable_reason ? (
        <p className="engine__error">{engine.unavailable_reason}</p>
      ) : null}
    </div>
  );
}
