import { MODES, type HistoryEntry } from "../types";

interface SessionHistoryProps {
  entries: readonly HistoryEntry[];
  activeJobId: string | null;
  /** Nome de exibição de um motor, vindo do catálogo do backend. */
  nameOf: (engineId: string | null | undefined) => string;
  onSelect: (entry: HistoryEntry) => void;
}

/**
 * Histórico da sessão (plano da tela §25; plano de motores §15).
 *
 * Vive só em memória: recarregar a página limpa. A biblioteca persistente do
 * projeto é outra história, e o backend já guarda o histórico de verdade.
 *
 * Cada miniatura mostra o motor que a gerou. É a forma mais simples de
 * comparação entre motores que a tela oferece: gerar a mesma descrição em
 * dois motores e ver os dois resultados lado a lado, cada um com o nome de
 * quem o produziu. Sem o rótulo, as duas miniaturas são indistinguíveis — e a
 * comparação, impossível.
 */
export function SessionHistory({
  entries,
  activeJobId,
  nameOf,
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
          const engineId = entry.engine?.resolved_engine_id ?? null;
          const engineName = engineId ? nameOf(engineId) : null;
          return (
            <li key={entry.jobId}>
              <button
                type="button"
                className={`history__item${
                  entry.jobId === activeJobId ? " history__item--active" : ""
                }`}
                onClick={() => onSelect(entry)}
                title={engineName ? `${entry.prompt} — ${engineName}` : entry.prompt}
                aria-label={
                  engineName
                    ? `Ver geração: ${entry.prompt}, gerada por ${engineName}`
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
                {engineName ? (
                  <span className="history__engine">{engineName}</span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
