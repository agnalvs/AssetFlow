import { useEffect, useState } from "react";

import { lerServidores } from "../services/generationApi";

/** De quanto em quanto tempo a tela pergunta (o código muda devagar). */
const INTERVALO_MS = 60_000;

/**
 * O aviso de servidor desatualizado (lote 11).
 *
 * A API e o servidor MCP gravam o commit em que subiram; quando um deles está
 * num commit mais antigo que o código — ou o código mudou depois que ele subiu
 * —, a faixa diz o que fazer: reconectar pelo `/mcp` no Claude Code, ou
 * reiniciar a API. Sem aviso (ou com `ASSETFLOW_AVISO_SERVIDOR=0`), nada aparece.
 */
export function AvisoDeServidor() {
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    const ler = () => {
      lerServidores()
        .then((estado) => {
          if (vivo) setAviso(estado.aviso);
        })
        .catch(() => {
          /* sem resposta, a tela continua valendo; o aviso só some */
        });
    };
    ler();
    const relogio = window.setInterval(ler, INTERVALO_MS);
    return () => {
      vivo = false;
      window.clearInterval(relogio);
    };
  }, []);

  if (!aviso) return null;
  return (
    <div className="aviso-servidor" role="alert">
      <strong>Servidor desatualizado.</strong> {aviso}
    </div>
  );
}
