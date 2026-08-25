import type {
  EngineCatalogEntry,
  EngineSelection,
  ResolvedEngine,
} from "../types";
import { engineBadgeLabel, familyLabel, speedLabel, qualityLabel } from "../labels";

interface EngineSelectorProps {
  selection: EngineSelection;
  engines: EngineCatalogEntry[];
  loading: boolean;
  /** O backend respondeu e não há motor nenhum para este modo. */
  empty: boolean;
  error: string | null;
  /** A decisão que o backend tomou para este pedido, quando já a conhecemos. */
  resolved: ResolvedEngine | null;
  /** Nome de exibição de um id — vem do catálogo. */
  nameOf: (engineId: string | null | undefined) => string;
  disabled?: boolean;
  onChange: (selection: EngineSelection) => void;
}

/**
 * O seletor de motor (plano de motores §4.1, §4.2 e §17).
 *
 * Duas coisas que este componente existe para deixar explícitas:
 *
 * **Os motores não são equivalentes** (§4.2). Um resumo e três ou quatro
 * tópicos aparecem embaixo do motor escolhido. Sem isso, o seletor sugere que
 * a diferença entre eles é de gosto — quando é de tempo, de exatidão e de
 * tipo de asset.
 *
 * **"Automático" não é uma caixa preta** (§17). Escolhido Auto, a tela mostra
 * qual motor o AssetFlow resolveu e por quê, **antes** de gerar. O motivo vem
 * pronto do backend, do mesmo `FinalResolvedSpec` que a geração vai executar.
 *
 * O componente não conhece nenhum motor: ele recebe a lista pronta do
 * catálogo. Uma gaveta nova aparece aqui sem que este arquivo mude.
 */
export function EngineSelector({
  selection,
  engines,
  loading,
  empty,
  error,
  resolved,
  nameOf,
  disabled = false,
  onChange,
}: EngineSelectorProps) {
  const chosen = selection.engineId
    ? engines.find((engine) => engine.engine_id === selection.engineId) ?? null
    : null;
  const isAuto = selection.engineId === null;

  return (
    <div className="engine" role="group" aria-label="Motor de geração">
      <label className="engine__control">
        <span className="engine__label">Motor</span>
        <select
          className="controls__field"
          value={selection.engineId ?? ""}
          disabled={disabled || loading}
          onChange={(event) =>
            onChange({ engineId: event.target.value || null })
          }
        >
          <option value="">Automático</option>
          {engines.map((engine) => (
            <option
              key={engine.engine_id}
              value={engine.engine_id}
              // Um motor indisponível continua **visível** e desabilitado, em
              // vez de sumir da lista: quem procura "SD-πXL" precisa
              // descobrir que ele existe e não está ligado, não concluir que
              // o AssetFlow não o tem.
              disabled={!engine.available}
            >
              {engine.display_name}
              {engine.available ? "" : " (indisponível)"}
            </option>
          ))}
        </select>
      </label>

      {error ? <p className="engine__error">{error}</p> : null}
      {empty ? (
        // Sem isto, um seletor com só "Automático" pareceria um bug. Ele é a
        // resposta correta quando nenhuma gaveta atende o modo escolhido — e
        // dizer isso é melhor do que deixar a pessoa procurar o que falta.
        <p className="engine__error">
          Nenhum motor habilitado atende este modo. A geração ainda funciona em
          Automático, com o motor que o backend encontrar.
        </p>
      ) : null}

      {isAuto ? <AutoNote resolved={resolved} nameOf={nameOf} /> : null}
      {chosen ? <EngineCard engine={chosen} /> : null}
    </div>
  );
}

/**
 * O que "Automático" significa para **este** pedido (plano de motores §17).
 *
 * Antes de o backend responder, a frase é uma promessa genérica. Depois, ela
 * vira o motor resolvido e o motivo — que é a informação que transforma o
 * Auto de caixa preta em decisão explicada.
 */
function AutoNote({
  resolved,
  nameOf,
}: {
  resolved: ResolvedEngine | null;
  nameOf: (engineId: string | null | undefined) => string;
}) {
  if (!resolved || resolved.selection_mode !== "auto" || !resolved.engine_id) {
    return (
      <p className="engine__auto">
        O AssetFlow selecionará automaticamente o motor mais adequado.
      </p>
    );
  }

  return (
    <div className="engine__auto engine__auto--resolved">
      <p>
        <strong>Motor resolvido:</strong> {nameOf(resolved.engine_id)}
      </p>
      {resolved.reason ? (
        <p className="engine__reason">Motivo: {resolved.reason}</p>
      ) : null}
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
