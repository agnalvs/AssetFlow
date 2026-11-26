import { useEffect, useState } from "react";

import { lerCusto } from "../services/generationApi";
import type { PainelDeCusto as Painel } from "../types";

const INTERVALO_MS = 60_000;

function milhar(n: number): string {
  return n.toLocaleString("pt-BR");
}

function diaCurto(iso: string): string {
  const [, mes, dia] = iso.split("-");
  return `${dia}/${mes}`;
}

const SITUACAO: Record<string, string> = {
  pendente: "na fila",
  em_desenho: "desenhando",
  em_revisao: "olhando",
  escolhendo: "escolhendo conceito",
  concluido: "pronto",
  falhou: "não aprovado",
  cancelado: "cancelado",
};

/** Lê o painel a cada minuto; `null` enquanto não há resposta ou com o painel desligado. */
function usePainelDeCusto(): Painel | null {
  const [painel, setPainel] = useState<Painel | null>(null);
  useEffect(() => {
    let vivo = true;
    const ler = () => {
      lerCusto(7)
        .then((lido) => {
          if (vivo) setPainel(lido);
        })
        .catch(() => {
          if (vivo) setPainel(null);
        });
    };
    ler();
    const relogio = window.setInterval(ler, INTERVALO_MS);
    return () => {
      vivo = false;
      window.clearInterval(relogio);
    };
  }, []);
  return painel;
}

/**
 * A faixa do topo quando o limite diário de tokens foi atingido (lote 12).
 * Só avisa: nada é bloqueado. O servidor MCP põe o mesmo aviso nas respostas.
 */
export function AvisoDeLimite() {
  const painel = usePainelDeCusto();
  if (!painel?.hoje.atingido || !painel.hoje.limite) return null;
  return (
    <div className="aviso-servidor" role="alert">
      <strong>⚠ Limite diário de tokens atingido.</strong> Hoje passaram ~
      {milhar(painel.hoje.tokens)} tokens estimados pela conversa, para um limite de{" "}
      {milhar(painel.hoje.limite)} (ASSETFLOW_LIMITE_DIARIO_TOKENS).
    </div>
  );
}

/**
 * O painel de custo (lote 12): tokens estimados de hoje contra o limite, os
 * últimos sete dias e os pedidos que mais gastaram no período.
 *
 * A conta é estimada pelos caracteres e imagens que passam pelo servidor MCP;
 * o raciocínio do Claude não passa por ele e não entra.
 */
export function PainelDeCusto() {
  const painel = usePainelDeCusto();
  const [tabela, setTabela] = useState(false);
  if (!painel) return null;

  const { hoje, dias, pedidos } = painel;
  const maior = Math.max(1, ...dias.map((d) => d.tokens), hoje.limite ?? 0);
  const fracao = hoje.limite ? Math.min(1, hoje.tokens / hoje.limite) : 0;
  const cronologia = [...dias].reverse();

  return (
    <section className="custo" aria-labelledby="custo-titulo">
      <h2 id="custo-titulo" className="custo__titulo">
        Custo estimado (tokens)
      </h2>

      <div className="custo__hoje">
        <p className="custo__numero">
          Hoje: ~{milhar(hoje.tokens)}
          {hoje.limite ? <span className="custo__de"> de {milhar(hoje.limite)}</span> : null}
        </p>
        {hoje.limite ? (
          <div
            className="custo__medidor"
            role="meter"
            aria-valuemin={0}
            aria-valuemax={hoje.limite}
            aria-valuenow={hoje.tokens}
            aria-label="Tokens de hoje contra o limite diário"
          >
            <div className="custo__preenchido" style={{ width: `${fracao * 100}%` }} />
          </div>
        ) : null}
        {hoje.atingido ? (
          <p className="custo__alerta" role="status">
            ⚠ Limite diário atingido — o Claude recebe o mesmo aviso nas respostas.
          </p>
        ) : null}
      </div>

      <div className="custo__dias" aria-hidden={tabela}>
        {cronologia.map((dia, i) => {
          const ehHoje = i === cronologia.length - 1;
          return (
            <div
              key={dia.data}
              className="custo__dia"
              title={`${diaCurto(dia.data)}: ~${milhar(dia.tokens)} tokens · ${dia.consultas} consultas`}
            >
              <span className="custo__valor">{ehHoje && dia.tokens ? milhar(dia.tokens) : " "}</span>
              <div className="custo__trilho">
                <div className="custo__barra" style={{ height: `${(dia.tokens / maior) * 100}%` }} />
              </div>
              <span className="custo__rotulo">{ehHoje ? "hoje" : diaCurto(dia.data)}</span>
            </div>
          );
        })}
      </div>

      <button type="button" className="button button--ghost custo__botao" onClick={() => setTabela((t) => !t)}>
        {tabela ? "Esconder a tabela" : "Ver em tabela"}
      </button>
      {tabela ? (
        <table className="custo__tabela">
          <thead>
            <tr>
              <th scope="col">Dia</th>
              <th scope="col">Tokens</th>
              <th scope="col">Consultas</th>
            </tr>
          </thead>
          <tbody>
            {dias.map((dia) => (
              <tr key={dia.data}>
                <td>{diaCurto(dia.data)}</td>
                <td>{milhar(dia.tokens)}</td>
                <td>{dia.consultas}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      {pedidos.length > 0 ? (
        <table className="custo__tabela">
          <caption>Pedidos que mais gastaram nos últimos 7 dias</caption>
          <thead>
            <tr>
              <th scope="col">Pedido</th>
              <th scope="col">Situação</th>
              <th scope="col">Tokens no período</th>
            </tr>
          </thead>
          <tbody>
            {pedidos.map((pedido) => (
              <tr key={pedido.id}>
                <td title={pedido.id}>{pedido.texto}</td>
                <td>{SITUACAO[pedido.situacao] ?? pedido.situacao}</td>
                <td>{milhar(pedido.tokens)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <p className="custo__nota">
        {painel.avulso ? `Consultas sem pedido: ~${milhar(painel.avulso)} tokens. ` : ""}
        Estimativa: {painel.estimativa}; o raciocínio do Claude não entra.
      </p>
    </section>
  );
}
