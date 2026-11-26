import { useEffect, useState } from "react";

import { lerOpiniao, opinar } from "../services/generationApi";
import type { Opiniao } from "../types";

interface OpiniaoControlsProps {
  assetId: string;
}

/**
 * "Gostei" e "não gostei" de um asset pronto (Fase B2 do plano do app).
 *
 * Um "não gostei" com motivo fica guardado como opinião pendente: na próxima
 * conversa, o Claude a recebe e a converte em lição, mantendo o texto ao lado.
 * Sem motivo, é só nota do asset. "Gostei" faz o asset poder virar exemplo de
 * construção nos pedidos parecidos.
 */
export function OpiniaoControls({ assetId }: OpiniaoControlsProps) {
  const [opiniao, setOpiniao] = useState<Opiniao | null>(null);
  const [escrevendo, setEscrevendo] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    setOpiniao(null);
    setEscrevendo(false);
    setMotivo("");
    setErro(null);
    lerOpiniao(assetId)
      .then((lida) => {
        if (vivo) setOpiniao(lida);
      })
      .catch(() => {
        /* sem opinião lida, os botões continuam valendo */
      });
    return () => {
      vivo = false;
    };
  }, [assetId]);

  const enviar = async (gostei: boolean, texto?: string) => {
    setEnviando(true);
    setErro(null);
    try {
      setOpiniao(await opinar(assetId, gostei, texto));
      setEscrevendo(false);
      setMotivo("");
    } catch (caught) {
      setErro(caught instanceof Error ? caught.message : "A opinião não foi gravada.");
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="opiniao" aria-label="Sua opinião sobre este desenho">
      <div className="opiniao__botoes">
        <button
          type="button"
          className={`button button--ghost${opiniao?.gostei ? " opiniao__escolhido" : ""}`}
          disabled={enviando}
          onClick={() => void enviar(true)}
        >
          Gostei
        </button>
        <button
          type="button"
          className={`button button--ghost${
            opiniao && !opiniao.gostei ? " opiniao__escolhido" : ""
          }`}
          disabled={enviando}
          onClick={() => setEscrevendo(true)}
        >
          Não gostei
        </button>
      </div>
      {escrevendo ? (
        <div className="opiniao__motivo">
          <textarea
            className="liberdade__texto"
            rows={2}
            maxLength={280}
            placeholder="Por quê? (opcional; com motivo, vira lição na próxima conversa)"
            value={motivo}
            onChange={(evento) => setMotivo(evento.target.value)}
          />
          <button
            type="button"
            className="button button--primary"
            disabled={enviando}
            onClick={() => void enviar(false, motivo)}
          >
            Enviar
          </button>
        </div>
      ) : null}
      {opiniao ? <p className="opiniao__estado">{estado(opiniao)}</p> : null}
      {erro ? (
        <p className="opiniao__erro" role="alert">
          {erro}
        </p>
      ) : null}
    </div>
  );
}

function estado(opiniao: Opiniao): string {
  if (opiniao.gostei) return "Você gostou: ele pode virar exemplo nos pedidos parecidos.";
  if (!opiniao.motivo) return "Você não gostou (sem motivo: fica só como nota do asset).";
  if (opiniao.situacao === "convertida" && opiniao.licao)
    return `Você não gostou: “${opiniao.motivo}” — virou a lição ${opiniao.licao}.`;
  return `Você não gostou: “${opiniao.motivo}” — o Claude vai convertê-lo em lição na próxima conversa.`;
}
