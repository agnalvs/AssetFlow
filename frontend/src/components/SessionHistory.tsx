import type { UseCreationCatalog } from "../hooks/useCreationCatalog";
import { MODES, type HistoryEntry } from "../types";

interface SessionHistoryProps {
  entries: readonly HistoryEntry[];
  activeJobId: string | null;
  /** Os nomes de método, motor e agente, vindos do catálogo do backend. */
  catalog: UseCreationCatalog;
  onSelect: (entry: HistoryEntry) => void;
}

/**
 * Histórico da sessão (plano da tela §25; plano de motores §15).
 *
 * Vive só em memória: recarregar a página limpa. A biblioteca persistente do
 * projeto é outra história, e o backend já guarda o histórico de verdade.
 *
 * Cada miniatura mostra **quem** a gerou — o motor ou o agente, conforme o
 * método. É a forma mais simples de comparação que a tela oferece: gerar a
 * mesma descrição por dois caminhos e ver os resultados lado a lado, cada um
 * com o nome de quem o produziu. Sem o rótulo, as duas miniaturas são
 * indistinguíveis — e a comparação, impossível (plano de correção §43).
 */
export function SessionHistory({
  entries,
  activeJobId,
  catalog,
  onSelect,
}: SessionHistoryProps) {
  if (entries.length === 0) return null;

  return (
    <section className="history" aria-label="Gerações desta sessão">
      <h2 className="history__title">Resultados desta sessão</h2>
      <ul className="history__list">
        {entries.map((entry) => {
          const mode = MODES[entry.mode];
          const thumbnail = entry.variant.thumbnail_url ?? entry.variant.url;
          // O rótulo nomeia **quem produziu**, e isso agora tem dois
          // formatos: motor ou agente. Mostrar sempre "motor" faria a
          // miniatura de um asset desenhado pelo agente mentir.
          const producer = producerOf(entry, catalog);
          return (
            <li key={entry.jobId}>
              <button
                type="button"
                className={`history__item${
                  entry.jobId === activeJobId ? " history__item--active" : ""
                }`}
                onClick={() => onSelect(entry)}
                title={producer ? `${entry.prompt} — ${producer}` : entry.prompt}
                aria-label={
                  producer
                    ? `Ver geração: ${entry.prompt}, gerada por ${producer}`
                    : `Ver geração: ${entry.prompt}`
                }
              >
                {thumbnail ? (
                  <img
                    className={`history__thumb${
                      mode.pixelated ? " history__thumb--pixelated" : ""
                    }`}
                    src={thumbnail}
                    alt=""
                    loading="lazy"
                  />
                ) : null}
                {producer ? (
                  <span className="history__engine">{producer}</span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Quem produziu esta entrada: o agente, quando foi ele; o motor, quando foi. */
function producerOf(
  entry: HistoryEntry,
  catalog: UseCreationCatalog,
): string | null {
  const selection = entry.engine;
  if (!selection) return null;
  if (selection.resolved_strategy === "pixel_agent") {
    return selection.agent ? catalog.agentNameOf(selection.agent.id) : null;
  }
  return selection.resolved_engine_id
    ? catalog.engineNameOf(selection.resolved_engine_id)
    : null;
}
