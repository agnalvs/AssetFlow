import { ConceitosDoPedido } from "./ConceitosDoPedido";
import { pedidoAtivo } from "../hooks/usePedidos";
import { etapaLabel, liberdadeLabel } from "../labels";
import type { Pedido } from "../types";

interface PedidosListProps {
  pedidos: readonly Pedido[];
  erro: string | null;
  selecionadoId: string | null;
  /** Um cancelar ou devolver em andamento, para não clicar duas vezes. */
  emAcao: string | null;
  onSelect: (pedido: Pedido) => void;
  onCancelar: (pedido: Pedido) => void;
  onDevolver: (pedido: Pedido) => void;
  /** Depois de escolher conceito ou pedir outros: relê a fila. */
  onConceito: () => void;
}

/** As etapas em que o pedido está reservado por uma conversa. */
const EM_DESENHO = new Set(["na_vez", "desenhando", "corrigindo", "olhando", "conceituando"]);

/**
 * A fila de pedidos (Fase B do plano do app).
 *
 * Mostra o que ainda não ficou pronto: na fila, na vez do Claude, sendo
 * desenhado, não aprovado e cancelado. Os prontos saem daqui e entram na
 * faixa "Prontos" — a lista é sobre andamento.
 */
export function PedidosList({
  pedidos,
  erro,
  selecionadoId,
  emAcao,
  onSelect,
  onCancelar,
  onDevolver,
  onConceito,
}: PedidosListProps) {
  const fila = pedidos.filter((pedido) => pedido.etapa !== "pronto");
  const esperando = fila.some((pedido) => pedido.etapa === "na_fila");

  return (
    <section className="pedidos" aria-label="Fila de pedidos">
      <h2 className="pedidos__titulo">Fila de pedidos</h2>
      {erro ? <p className="pedidos__erro" role="alert">{erro}</p> : null}
      {esperando ? (
        <p className="pedidos__dica">
          No chat do Claude Code (não no campo de descrição), diga:{" "}
          <strong>“desenhe os pedidos pendentes do AssetFlow”</strong>.
        </p>
      ) : null}
      {fila.length === 0 && !erro ? (
        <p className="pedidos__vazio">Nenhum pedido esperando desenho.</p>
      ) : null}
      <ul className="pedidos__lista">
        {fila.map((pedido) => {
          const miniatura = pedido.asset?.variants?.[0];
          const ativo = pedidoAtivo(pedido);
          const meta = [
            pedido.banca ? `banca ${pedido.banca.rodada} · ${pedido.banca.ordem}/${pedido.banca.total}` : null,
            pedido.resumo.grade,
            pedido.resumo.cores ? `${pedido.resumo.cores} cores` : null,
            liberdadeLabel(pedido.liberdade),
          ].filter(Boolean);
          return (
            <li
              key={pedido.id}
              className={`pedido pedido--${pedido.etapa}${
                pedido.id === selecionadoId ? " pedido--selecionado" : ""
              }`}
            >
              <button
                type="button"
                className="pedido__corpo"
                disabled={!miniatura}
                onClick={() => onSelect(pedido)}
                title={pedido.texto}
              >
                {miniatura ? (
                  <img
                    className="pedido__miniatura"
                    src={miniatura.thumbnail_url ?? miniatura.url ?? undefined}
                    alt=""
                  />
                ) : (
                  <span className="pedido__miniatura pedido__miniatura--vazia" aria-hidden="true" />
                )}
                <span className="pedido__textos">
                  <span className="pedido__texto">
                    {pedido.tipo === "ajuste" ? `Ajuste de ${pedido.origem_asset_id}: ` : ""}
                    {pedido.texto}
                  </span>
                  <span className="pedido__meta">{meta.join(" · ")}</span>
                  {pedido.direcao_de_arte ? (
                    <span className="pedido__direcao">“{pedido.direcao_de_arte}”</span>
                  ) : null}
                  <span className={`pedido__etapa pedido__etapa--${pedido.etapa}`}>
                    {etapaLabel(pedido)}
                    {pedido.etapa === "nao_aprovado" && pedido.motivo ? ` — ${pedido.motivo}` : ""}
                  </span>
                </span>
              </button>
              {pedido.etapa === "escolha_conceito" ||
              (pedido.modo_conceito === "claude_escolhe" && pedido.conceitos.length > 0) ? (
                <ConceitosDoPedido pedido={pedido} onMudou={onConceito} />
              ) : null}
              {ativo ? (
                <span className="pedido__acoes">
                  {EM_DESENHO.has(pedido.etapa) ? (
                    <button
                      type="button"
                      className="button button--ghost"
                      disabled={emAcao === pedido.id}
                      onClick={() => onDevolver(pedido)}
                    >
                      Devolver à fila
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="button button--ghost"
                    disabled={emAcao === pedido.id}
                    onClick={() => onCancelar(pedido)}
                  >
                    Cancelar
                  </button>
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
