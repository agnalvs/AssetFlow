import type { UseCreationCatalog } from "../hooks/useCreationCatalog";
import type {
  AgentQualityMode,
  CreationSelection,
  EngineCatalogEntry,
  GenerationStrategyId,
  ResolvedEngine,
  ResolvedStrategy,
} from "../types";
import {
  engineBadgeLabel,
  familyLabel,
  qualityLabel,
  qualityModeLabel,
  speedLabel,
} from "../labels";

interface CreationMethodSelectorProps {
  selection: CreationSelection;
  catalog: UseCreationCatalog;
  /** O que o backend resolveu para este pedido, quando já sabemos. */
  resolvedStrategy: ResolvedStrategy | null;
  resolvedEngine: ResolvedEngine | null;
  disabled?: boolean;
  onChange: (selection: CreationSelection) => void;
}

/**
 * O seletor de **método de criação** (plano de correção §4, §5 e §52).
 *
 * A mudança que este componente representa:
 *
 *     antes                          depois
 *     MOTOR                          MÉTODO DE CRIAÇÃO
 *     ├─ Automático                  ├─ Automático
 *     ├─ FLUX Pixel                  ├─ Modelo de imagem  ─> MOTOR
 *     ├─ SD-πXL                      └─ Agente Pixel      ─> AGENTE + QUALIDADE
 *     ├─ Pixel Forge
 *     └─ Texel-style Agent
 *
 * O seletor antigo misturava três conceitos. FLUX e SDXL são motores;
 * SD-πXL e Pixel Forge são motores especializados; o agente é uma
 * **estratégia inteira**, com outro tempo de resposta e outros controles.
 * Oferecê-los juntos dizia que os cinco eram intercambiáveis.
 *
 * Qual controle aparece depois do método **não** é decidido aqui: vem do
 * backend, em `selects_engine` e `selects_agent` (§5). Um `if id ===
 * "pixel_agent"` neste arquivo poria uma regra de arquitetura no React.
 */
export function CreationMethodSelector({
  selection,
  catalog,
  resolvedStrategy,
  resolvedEngine,
  disabled = false,
  onChange,
}: CreationMethodSelectorProps) {
  const current = catalog.strategyOf(selection.strategy);
  const busy = disabled || catalog.loading;

  return (
    <div className="creation" role="group" aria-label="Método de criação">
      <label className="creation__control">
        <span className="creation__label">Método de criação</span>
        <select
          className="controls__field"
          value={selection.strategy}
          disabled={busy}
          onChange={(event) =>
            onChange({
              ...selection,
              strategy: event.target.value as GenerationStrategyId,
            })
          }
        >
          {catalog.strategies.map((strategy) => (
            <option
              key={strategy.id}
              value={strategy.id}
              // Um método indisponível continua **visível** e desabilitado:
              // quem procura "Agente Pixel" precisa descobrir que ele existe
              // e não está pronto, não concluir que o AssetFlow não o tem.
              disabled={!strategy.available}
            >
              {strategy.display_name}
              {strategy.available ? "" : " (indisponível)"}
            </option>
          ))}
        </select>
      </label>

      {catalog.error ? <p className="engine__error">{catalog.error}</p> : null}

      {selection.strategy === "auto" ? (
        <AutoNote resolved={resolvedStrategy} catalog={catalog} />
      ) : null}

      {current && selection.strategy !== "auto" ? (
        <MethodCard strategy={current} />
      ) : null}

      {current?.selects_engine ? (
        <EnginePicker
          selection={selection}
          catalog={catalog}
          resolvedEngine={resolvedEngine}
          disabled={busy}
          onChange={onChange}
        />
      ) : null}

      {current?.selects_agent ? (
        <AgentPicker
          selection={selection}
          catalog={catalog}
          disabled={busy}
          onChange={onChange}
        />
      ) : null}
    </div>
  );
}

/**
 * O que "Automático" significa para **este** pedido (plano de correção §5).
 *
 * Antes de o backend responder, uma promessa genérica. Depois, o método
 * escolhido e o motivo — que é o que transforma o Auto de caixa preta em
 * decisão explicada.
 */
function AutoNote({
  resolved,
  catalog,
}: {
  resolved: ResolvedStrategy | null;
  catalog: UseCreationCatalog;
}) {
  if (!resolved) {
    return (
      <p className="engine__auto">
        O AssetFlow escolherá automaticamente a melhor estratégia.
      </p>
    );
  }

  return (
    <div className="engine__auto engine__auto--resolved">
      <p>
        <strong>Estratégia escolhida:</strong>{" "}
        {catalog.strategyNameOf(resolved.mode)}
      </p>
      {resolved.reason ? (
        <p className="engine__reason">Motivo: {resolved.reason}</p>
      ) : null}
    </div>
  );
}

/** O resumo do método escolhido — os métodos não são equivalentes. */
function MethodCard({ strategy }: { strategy: { summary: string; highlights: string[] } }) {
  return (
    <div className="engine__card">
      <p className="engine__summary">{strategy.summary}</p>
      {strategy.highlights.length > 0 ? (
        <ul className="engine__highlights">
          {strategy.highlights.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** O seletor de motor — só existe dentro de "Modelo de imagem" (§8). */
function EnginePicker({
  selection,
  catalog,
  resolvedEngine,
  disabled,
  onChange,
}: {
  selection: CreationSelection;
  catalog: UseCreationCatalog;
  resolvedEngine: ResolvedEngine | null;
  disabled: boolean;
  onChange: (selection: CreationSelection) => void;
}) {
  const chosen = selection.engineId
    ? catalog.engines.find((engine) => engine.engine_id === selection.engineId) ?? null
    : null;

  return (
    <div className="creation__nested">
      <label className="creation__control">
        <span className="creation__label">Motor de geração</span>
        <select
          className="controls__field"
          value={selection.engineId ?? ""}
          disabled={disabled}
          onChange={(event) =>
            onChange({ ...selection, engineId: event.target.value || null })
          }
        >
          <option value="">Automático</option>
          {catalog.engines.map((engine) => (
            <option
              key={engine.engine_id}
              value={engine.engine_id}
              disabled={!engine.available}
            >
              {engine.display_name}
              {engine.available ? "" : " (indisponível)"}
            </option>
          ))}
        </select>
      </label>

      {catalog.engines.length === 0 ? (
        <p className="engine__error">
          Nenhum motor habilitado atende este modo. A geração ainda funciona em
          Automático, com o motor que o backend encontrar.
        </p>
      ) : null}

      {selection.engineId === null && resolvedEngine?.engine_id ? (
        <div className="engine__auto engine__auto--resolved">
          <p>
            <strong>Motor resolvido:</strong>{" "}
            {catalog.engineNameOf(resolvedEngine.engine_id)}
          </p>
          {resolvedEngine.reason ? (
            <p className="engine__reason">Motivo: {resolvedEngine.reason}</p>
          ) : null}
        </div>
      ) : null}

      {chosen ? <EngineCard engine={chosen} /> : null}
    </div>
  );
}

/** O agente e o modo de qualidade — só dentro de "Agente Pixel" (§5). */
function AgentPicker({
  selection,
  catalog,
  disabled,
  onChange,
}: {
  selection: CreationSelection;
  catalog: UseCreationCatalog;
  disabled: boolean;
  onChange: (selection: CreationSelection) => void;
}) {
  const agent =
    catalog.agents.find((item) => item.id === selection.agentId) ?? catalog.agents[0];

  return (
    <div className="creation__nested">
      <label className="creation__control">
        <span className="creation__label">Agente</span>
        <select
          className="controls__field"
          value={selection.agentId ?? agent?.id ?? ""}
          disabled={disabled || catalog.agents.length <= 1}
          onChange={(event) =>
            onChange({ ...selection, agentId: event.target.value || null })
          }
        >
          {catalog.agents.map((item) => (
            <option key={item.id} value={item.id}>
              {item.display_name}
            </option>
          ))}
        </select>
      </label>

      <label className="creation__control">
        <span className="creation__label">Qualidade</span>
        <select
          className="controls__field"
          value={selection.quality}
          disabled={disabled}
          onChange={(event) =>
            onChange({
              ...selection,
              quality: event.target.value as AgentQualityMode,
            })
          }
        >
          {catalog.qualityModes.map((mode) => (
            <option key={mode} value={mode}>
              {qualityModeLabel(mode)}
            </option>
          ))}
        </select>
      </label>

      {agent ? <p className="engine__summary">{agent.summary}</p> : null}
    </div>
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
