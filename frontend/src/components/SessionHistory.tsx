import { MODES, type HistoryEntry } from "../types";

interface SessionHistoryProps {
  entries: readonly HistoryEntry[];
  activeJobId: string | null;
  onSelect: (entry: HistoryEntry) => void;
}

/**
 * Histórico da sessão (plano da tela §25 — opcional nesta etapa).
 *
 * Vive só em memória: recarregar a página limpa. A biblioteca persistente do
 * projeto é outra história, e o backend já guarda o histórico de verdade.
 */
export function SessionHistory({ entries, activeJobId, onSelect }: SessionHistoryProps) {
  if (entries.length === 0) return null;

  return (
    <section className="history" aria-label="Gerações desta sessão">
      <h2 className="history__title">Resultados desta sessão</h2>
      <ul className="history__list">
        {entries.map((entry) => {
          const mode = MODES[entry.mode];
          const thumbnail = entry.variant.thumbnail_url ?? entry.variant.url;
          return (
            <li key={entry.jobId}>
              <button
                type="button"
                className={`history__item${
                  entry.jobId === activeJobId ? " history__item--active" : ""
                }`}
                onClick={() => onSelect(entry)}
                title={entry.prompt}
                aria-label={`Ver geração: ${entry.prompt}`}
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
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
