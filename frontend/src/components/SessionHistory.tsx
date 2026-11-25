import { MODES, type HistoryEntry } from "../types";

interface SessionHistoryProps {
  entries: readonly HistoryEntry[];
  activeJobId: string | null;
  onSelect: (entry: HistoryEntry) => void;
}

/**
 * Os pedidos prontos (plano da tela §25; Fase B do plano do app).
 *
 * Vêm da fila de pedidos, gravada no backend: recarregar a página não os
 * perde. A galeria permanente da Fase C do plano do app
 * (backend/docs/PLANO_APP_DESENHISTA.md) toma o lugar deste componente.
 */
export function SessionHistory({ entries, activeJobId, onSelect }: SessionHistoryProps) {
  if (entries.length === 0) return null;

  return (
    <section className="history" aria-label="Pedidos prontos">
      <h2 className="history__title">Prontos</h2>
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
