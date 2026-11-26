import { useEffect, useState } from "react";

import { criarCopia, listarCopias } from "../services/generationApi";
import type { CopiaDeSeguranca as Copia } from "../types";

function mb(tamanho: number): string {
  return `${(tamanho / 1_048_576).toFixed(1)} MB`;
}

function quando(iso: string): string {
  const data = new Date(iso);
  return Number.isNaN(data.getTime()) ? iso : data.toLocaleString("pt-BR");
}

/**
 * A cópia de segurança de `backend/data/` (lote 9).
 *
 * Um botão que grava um zip datado fora do repositório, com os desenhos, a
 * fila, as lições, as opiniões e a banca. Restaurar fica no comando
 * `python -m assetflow.backup restaurar`, porque exige a API fechada. Com a
 * cópia desligada (`ASSETFLOW_BACKUP=0`), o bloco não aparece.
 */
export function CopiaDeSeguranca() {
  const [pasta, setPasta] = useState<string | null>(null);
  const [ultima, setUltima] = useState<Copia | null>(null);
  const [ligada, setLigada] = useState(true);
  const [gravando, setGravando] = useState(false);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    listarCopias()
      .then((lista) => {
        if (!vivo) return;
        setPasta(lista.pasta);
        setUltima(lista.items[0] ?? null);
      })
      .catch(() => {
        if (vivo) setLigada(false);
      });
    return () => {
      vivo = false;
    };
  }, []);

  if (!ligada) return null;

  const gravar = async () => {
    setGravando(true);
    setErro(null);
    setMensagem(null);
    try {
      const copia = await criarCopia();
      setUltima(copia);
      setMensagem(`Cópia gravada: ${copia.arquivo} (${copia.arquivos} arquivos, ${mb(copia.tamanho)}).`);
    } catch (caught) {
      setErro(caught instanceof Error ? caught.message : "A cópia não foi gravada.");
    } finally {
      setGravando(false);
    }
  };

  return (
    <div className="copia" aria-label="Cópia de segurança">
      <button type="button" className="button button--ghost" disabled={gravando} onClick={() => void gravar()}>
        {gravando ? "Gravando a cópia…" : "Fazer cópia de segurança"}
      </button>
      <p className="copia__estado">
        {ultima
          ? `Última cópia: ${quando(ultima.criada_em)} (${mb(ultima.tamanho)}).`
          : "Nenhuma cópia ainda."}{" "}
        {pasta ? `Ficam em ${pasta}, fora do repositório.` : null}
      </p>
      {mensagem ? <p className="copia__estado" role="status">{mensagem}</p> : null}
      {erro ? (
        <p className="opiniao__erro" role="alert">
          {erro}
        </p>
      ) : null}
    </div>
  );
}
