import { useState } from "react";

import { escolherConceito, outrosConceitos } from "../services/generationApi";
import type { Conceito, Pedido } from "../types";

const CAMPOS: readonly { id: keyof Conceito; rotulo: string }[] = [
  { id: "traco", rotulo: "Traço marcante" },
  { id: "silhueta", rotulo: "Silhueta" },
  { id: "objeto", rotulo: "Objeto" },
  { id: "pose", rotulo: "Pose" },
  { id: "simplificar", rotulo: "Se faltar espaço" },
];

/**
 * Os três conceitos de um pedido (lote 1).
 *
 * No modo "eu escolho", o pedido espera aqui: escolha um, edite se quiser, ou
 * peça outros três. No modo "o Claude escolhe", mostra os três e qual ele
 * escolheu, com o motivo.
 */
export function ConceitosDoPedido({ pedido, onMudou }: { pedido: Pedido; onMudou: () => void }) {
  const [escolhido, setEscolhido] = useState<number | null>(null);
  const [editado, setEditado] = useState<Partial<Conceito>>({});
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const escolhendo = pedido.etapa === "escolha_conceito";
  const doClaude = pedido.conceito?.indice ?? null;

  const agir = async (acao: () => Promise<unknown>) => {
    setOcupado(true);
    setErro(null);
    try {
      await acao();
      setEscolhido(null);
      setEditado({});
      onMudou();
    } catch (caught) {
      setErro(caught instanceof Error ? caught.message : "A escolha não foi gravada.");
    } finally {
      setOcupado(false);
    }
  };

  return (
    <div className="conceitos" aria-label="Conceitos do pedido">
      {pedido.motivo_conceito ? (
        <p className="conceitos__motivo">
          O Claude escolheu o conceito {doClaude}: {pedido.motivo_conceito}
        </p>
      ) : null}
      <ol className="conceitos__lista">
        {pedido.conceitos.map((conceito, n) => {
          const indice = n + 1;
          const editando = escolhendo && escolhido === indice;
          return (
            <li
              key={indice}
              className={`conceito${doClaude === indice || editando ? " conceito--escolhido" : ""}`}
            >
              {CAMPOS.map((campo) => (
                <label key={campo.id} className="conceito__campo">
                  <span className="conceito__rotulo">{campo.rotulo}</span>
                  {editando ? (
                    <input
                      className="licao__input"
                      maxLength={campo.id === "simplificar" ? 80 : 120}
                      value={editado[campo.id] ?? conceito[campo.id]}
                      onChange={(evento) =>
                        setEditado({ ...editado, [campo.id]: evento.target.value })
                      }
                    />
                  ) : (
                    <span>{conceito[campo.id]}</span>
                  )}
                </label>
              ))}
              {escolhendo ? (
                editando ? (
                  <button
                    type="button"
                    className="button button--primary"
                    disabled={ocupado}
                    onClick={() =>
                      void agir(() =>
                        escolherConceito(
                          pedido.id,
                          indice,
                          Object.keys(editado).length ? editado : undefined,
                        ),
                      )
                    }
                  >
                    Usar este conceito
                  </button>
                ) : (
                  <button
                    type="button"
                    className="button button--ghost"
                    disabled={ocupado}
                    onClick={() => {
                      setEscolhido(indice);
                      setEditado({});
                    }}
                  >
                    Escolher (e editar)
                  </button>
                )
              ) : null}
            </li>
          );
        })}
      </ol>
      {escolhendo ? (
        <button
          type="button"
          className="button button--ghost"
          disabled={ocupado}
          onClick={() => void agir(() => outrosConceitos(pedido.id))}
        >
          Pedir outros três
        </button>
      ) : null}
      {erro ? (
        <p className="opiniao__erro" role="alert">
          {erro}
        </p>
      ) : null}
    </div>
  );
}
