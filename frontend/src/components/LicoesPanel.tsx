import { useCallback, useEffect, useState } from "react";

import { apagarLicao, editarLicao, listarLicoes } from "../services/generationApi";
import type { Licao } from "../types";

/** De quanto em quanto tempo a lista relê as lições (o Claude as registra pela conversa). */
const INTERVALO_MS = 15000;

/**
 * As lições do desenho (Fase B2 do plano do app).
 *
 * O Claude registra uma lição a cada olhar que achou algo feio, e as suas
 * opiniões com motivo viram lições da autora, com o seu texto ao lado. Aqui
 * cada uma aparece com o contador e pode ser editada, desligada ou apagada.
 * As ligadas entram no recorte dos pedidos parecidos, as mais repetidas
 * primeiro.
 */
export function LicoesPanel() {
  const [licoes, setLicoes] = useState<Licao[]>([]);
  const [temas, setTemas] = useState<Record<string, string>>({});
  const [erro, setErro] = useState<string | null>(null);
  const [editando, setEditando] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const [ocupada, setOcupada] = useState<string | null>(null);

  const ler = useCallback(async () => {
    try {
      const lista = await listarLicoes();
      setLicoes(lista.items);
      setTemas(lista.temas);
      setErro(null);
    } catch (caught) {
      setErro(caught instanceof Error ? caught.message : "As lições não responderam.");
    }
  }, []);

  useEffect(() => {
    void ler();
    const timer = window.setInterval(() => void ler(), INTERVALO_MS);
    const aoFocar = () => void ler();
    window.addEventListener("focus", aoFocar);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", aoFocar);
    };
  }, [ler]);

  const mudar = async (licao: Licao, acao: () => Promise<unknown>) => {
    setOcupada(licao.id);
    try {
      await acao();
      await ler();
    } catch (caught) {
      setErro(caught instanceof Error ? caught.message : "A lição não foi alterada.");
    } finally {
      setOcupada(null);
    }
  };

  if (licoes.length === 0 && !erro) return null;

  return (
    <section className="licoes" aria-label="Lições do desenho">
      <h2 className="pedidos__titulo">Lições</h2>
      <p className="pedidos__dica">
        O que o Claude aprendeu olhando os desenhos, e o que você disse. As ligadas entram nos
        próximos pedidos parecidos, as mais repetidas primeiro.
      </p>
      {erro ? (
        <p className="pedidos__erro" role="alert">
          {erro}
        </p>
      ) : null}
      <ul className="pedidos__lista">
        {licoes.map((licao) => (
          <li key={licao.id} className={`licao${licao.ligada ? "" : " licao--desligada"}`}>
            <span className="licao__contador" title="Quantas vezes apareceu">
              ×{licao.contador}
            </span>
            <div className="licao__textos">
              {editando === licao.id ? (
                <div className="licao__edicao">
                  <input
                    className="licao__input"
                    value={texto}
                    maxLength={140}
                    onChange={(evento) => setTexto(evento.target.value)}
                  />
                  <button
                    type="button"
                    className="button button--primary"
                    disabled={ocupada === licao.id}
                    onClick={() =>
                      void mudar(licao, async () => {
                        await editarLicao(licao.id, { regra: texto });
                        setEditando(null);
                      })
                    }
                  >
                    Salvar
                  </button>
                  <button type="button" className="button button--ghost" onClick={() => setEditando(null)}>
                    Desistir
                  </button>
                </div>
              ) : (
                <span className="licao__regra">
                  {licao.id}: {licao.regra}
                </span>
              )}
              {licao.origem === "autora" && licao.texto_da_autora ? (
                <span className="licao__autora">Você escreveu: “{licao.texto_da_autora}”</span>
              ) : (
                <span className="licao__autora">
                  Errou: {licao.errou} · Por quê: {licao.porque}
                </span>
              )}
              <span className="pedido__meta">
                {licao.origem === "autora" ? "sua · " : ""}
                {[licao.tipo, licao.corpo, licao.porte].join(" · ")}
              </span>
            </div>
            <span className="pedido__acoes">
              <select
                className="licao__tema"
                value={licao.tema}
                disabled={ocupada === licao.id}
                aria-label="Tema"
                onChange={(evento) =>
                  void mudar(licao, () => editarLicao(licao.id, { tema: evento.target.value }))
                }
              >
                {Object.entries(temas).map(([tema, natureza]) => (
                  <option key={tema} value={tema}>
                    {tema} ({natureza === "tecnica" ? "técnica" : "forma"})
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="button button--ghost"
                disabled={ocupada === licao.id}
                onClick={() => {
                  setEditando(licao.id);
                  setTexto(licao.regra);
                }}
              >
                Editar
              </button>
              <button
                type="button"
                className="button button--ghost"
                disabled={ocupada === licao.id}
                onClick={() =>
                  void mudar(licao, () => editarLicao(licao.id, { ligada: !licao.ligada }))
                }
              >
                {licao.ligada ? "Desligar" : "Ligar"}
              </button>
              <button
                type="button"
                className="button button--ghost"
                disabled={ocupada === licao.id}
                onClick={() => {
                  if (window.confirm(`Apagar a lição ${licao.id}?`)) {
                    void mudar(licao, () => apagarLicao(licao.id));
                  }
                }}
              >
                Apagar
              </button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
