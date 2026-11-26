import { useEffect, useState } from "react";

import { lerFicha } from "../services/generationApi";
import type { Ficha, FichaLinha } from "../types";

interface FichaDoPedidoProps {
  pedidoId: string;
}

const MARCA: Record<FichaLinha["resultado"], string> = {
  passou: "✓",
  nao_passou: "✗",
  sem_resposta: "?",
  nao_se_aplica: "–",
};

const RESULTADO: Record<FichaLinha["resultado"], string> = {
  passou: "passou",
  nao_passou: "não passou",
  sem_resposta: "sem resposta",
  nao_se_aplica: "não se aplica",
};

/**
 * A ficha de verificação de um asset pronto (lote F5).
 *
 * Uma linha por regra da base que vale para o pedido: quem a conferiu (o app,
 * o Claude, a receita ou você) e o resultado. Uma **divergência** — o Claude
 * respondeu "sim" e a medida acusou o problema — aparece destacada, fora da
 * dobra. Asset sem ficha (de antes do lote, ou com a ficha desligada) não
 * mostra nada.
 */
export function FichaDoPedido({ pedidoId }: FichaDoPedidoProps) {
  const [ficha, setFicha] = useState<Ficha | null>(null);

  useEffect(() => {
    let vivo = true;
    setFicha(null);
    lerFicha(pedidoId)
      .then((lida) => {
        if (vivo) setFicha(lida);
      })
      .catch(() => {
        /* sem ficha lida, o resultado continua valendo */
      });
    return () => {
      vivo = false;
    };
  }, [pedidoId]);

  if (!ficha || ficha.linhas.length === 0) return null;
  const passaram = ficha.linhas.filter((linha) => linha.resultado === "passou").length;

  return (
    <div className="ficha" aria-label="Ficha de verificação">
      {ficha.divergencias.map((divergencia) => (
        <p key={divergencia.pergunta} className="ficha__divergencia">
          Divergência em <strong>{divergencia.pergunta}</strong>: o Claude respondeu "
          {divergencia.resposta}", e o app mediu {divergencia.detalhe}.
        </p>
      ))}
      <details>
        <summary>
          Ficha de verificação — {passaram} de {ficha.linhas.length} regras passaram
          {ficha.sem_resposta.length > 0
            ? `; sem resposta: ${ficha.sem_resposta.join(", ")}`
            : ""}
        </summary>
        <ul className="ficha__lista">
          {ficha.linhas.map((linha) => (
            <li key={`${linha.verificacao}|${linha.regra}`} className="ficha__linha">
              <span aria-label={RESULTADO[linha.resultado]}>{MARCA[linha.resultado]}</span>
              <span title={linha.detalhe || undefined}>{linha.regra}</span>
              <span className="ficha__quem">{linha.quem}</span>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
