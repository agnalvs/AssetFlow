import { useCallback, useEffect, useState } from "react";

import { comparar, criarRodada, lerBanca, votar } from "../services/generationApi";
import type { BancaResumo, Comparacao, LadoDoPar, ModoConceito, ParDaBanca } from "../types";

const MODOS: readonly { id: ModoConceito; rotulo: string }[] = [
  { id: "sem_conceito", rotulo: "Sem conceito" },
  { id: "claude_escolhe", rotulo: "O Claude escolhe" },
  { id: "eu_escolho", rotulo: "Eu escolho" },
];

/**
 * A banca de teste (lote 1; etapa K1 do plano da base de conhecimento).
 *
 * Os seis pedidos de `config/banca.yaml` viram uma rodada na fila. "Comparar"
 * mostra duas rodadas lado a lado, par a par, sem dizer qual lado é qual; a
 * autora escolhe o melhor e dá uma nota de 1 a 5 a cada imagem. O resumo, que
 * revela os lados, só aparece com todos os pares avaliados.
 */
export function BancaPage() {
  const [banca, setBanca] = useState<BancaResumo | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [rotulo, setRotulo] = useState("");
  const [modo, setModo] = useState<ModoConceito>("sem_conceito");
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [comparacao, setComparacao] = useState<Comparacao | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const ler = useCallback(async () => {
    try {
      const lida = await lerBanca();
      setBanca(lida);
      setErro(null);
      const [maisNova, anterior] = lida.rodadas;
      if (maisNova && anterior) {
        setA((atual) => atual || anterior.id);
        setB((atual) => atual || maisNova.id);
      }
    } catch (caught) {
      setErro(caught instanceof Error ? caught.message : "A banca não respondeu.");
    }
  }, []);

  useEffect(() => {
    void ler();
  }, [ler]);

  const abrirComparacao = useCallback(async () => {
    if (!a || !b || a === b) return;
    try {
      setComparacao(await comparar(a, b));
      setErro(null);
    } catch (caught) {
      setErro(caught instanceof Error ? caught.message : "A comparação não abriu.");
    }
  }, [a, b]);

  const novaRodada = async () => {
    setOcupado(true);
    try {
      await criarRodada(rotulo, modo);
      setRotulo("");
      await ler();
    } catch (caught) {
      setErro(caught instanceof Error ? caught.message : "A rodada não foi criada.");
    } finally {
      setOcupado(false);
    }
  };

  return (
    <section className="banca" aria-label="Banca de teste">
      <h2 className="pedidos__titulo">Banca de teste</h2>
      <p className="pedidos__dica">
        Os mesmos seis pedidos, antes e depois de cada mudança na base. Uma rodada vai para a
        fila; peça ao Claude, numa conversa nova, para desenhar os pedidos pendentes.
      </p>
      {erro ? (
        <p className="pedidos__erro" role="alert">
          {erro}
        </p>
      ) : null}

      <div className="banca__nova">
        <input
          className="licao__input"
          placeholder="Rótulo da rodada (ex.: referência)"
          value={rotulo}
          onChange={(evento) => setRotulo(evento.target.value)}
        />
        <select
          className="licao__tema"
          value={modo}
          onChange={(evento) => setModo(evento.target.value as ModoConceito)}
          aria-label="Modo de conceito da rodada"
        >
          {MODOS.map((m) => (
            <option key={m.id} value={m.id}>
              {m.rotulo}
            </option>
          ))}
        </select>
        <button type="button" className="button button--primary" disabled={ocupado} onClick={() => void novaRodada()}>
          Nova rodada
        </button>
      </div>

      <ul className="pedidos__lista">
        {banca?.rodadas.map((rodada) => {
          const prontos = rodada.itens.filter((i) => i.etapa === "pronto").length;
          return (
            <li key={rodada.id} className="licao">
              <span className="licao__contador">{rodada.id}</span>
              <div className="licao__textos">
                <span className="licao__regra">{rodada.rotulo}</span>
                <span className="pedido__meta">
                  {rodada.modo_conceito} · base {rodada.versao_base}
                  {rodada.git_commit ? ` · ${rodada.git_commit}` : ""} · {prontos}/{rodada.itens.length}{" "}
                  prontos{rodada.pronta ? " · fechada" : ""} · ~{rodada.tokens_estimados} tokens
                </span>
              </div>
            </li>
          );
        })}
      </ul>

      <h2 className="pedidos__titulo">Comparar</h2>
      <div className="banca__nova">
        <select className="licao__tema" value={a} onChange={(e) => setA(e.target.value)} aria-label="Rodada A">
          <option value="">rodada…</option>
          {banca?.rodadas.map((r) => (
            <option key={r.id} value={r.id}>
              {r.id} · {r.rotulo}
            </option>
          ))}
        </select>
        <span>×</span>
        <select className="licao__tema" value={b} onChange={(e) => setB(e.target.value)} aria-label="Rodada B">
          <option value="">rodada…</option>
          {banca?.rodadas.map((r) => (
            <option key={r.id} value={r.id}>
              {r.id} · {r.rotulo}
            </option>
          ))}
        </select>
        <button type="button" className="button button--ghost" onClick={() => void abrirComparacao()}>
          Abrir
        </button>
        {comparacao ? (
          <span className="pedido__meta">
            avaliados: {comparacao.avaliados} de {comparacao.pares.length}
          </span>
        ) : null}
      </div>

      {comparacao
        ? comparacao.pares.map((par) => (
            <CartaoDoPar key={par.item} par={par} a={comparacao.a} b={comparacao.b} onVotou={abrirComparacao} />
          ))
        : null}

      {comparacao?.resumo ? <Resumo resumo={comparacao.resumo} /> : null}
    </section>
  );
}

function CartaoDoPar({
  par,
  a,
  b,
  onVotou,
}: {
  par: ParDaBanca;
  a: string;
  b: string;
  onVotou: () => void;
}) {
  const [notaE, setNotaE] = useState(par.nota_esquerda ?? 3);
  const [notaD, setNotaD] = useState(par.nota_direita ?? 3);
  const [erro, setErro] = useState<string | null>(null);
  const semDesenho = !par.esquerda.asset || !par.direita.asset;

  const escolher = async (escolha: "esquerda" | "direita" | "empate") => {
    try {
      await votar({ a, b, item: par.item, escolha, nota_esquerda: notaE, nota_direita: notaD });
      onVotou();
    } catch (caught) {
      setErro(caught instanceof Error ? caught.message : "O voto não foi gravado.");
    }
  };

  return (
    <article className="par">
      <h3 className="par__titulo">{par.texto}</h3>
      <div className="par__lados">
        <Lado lado={par.esquerda} nota={notaE} onNota={setNotaE} rotulo="Esquerda" />
        <Lado lado={par.direita} nota={notaD} onNota={setNotaD} rotulo="Direita" />
      </div>
      {semDesenho ? (
        <p className="pedido__meta">Um lado não tem desenho: o par conta como derrota dele.</p>
      ) : (
        <div className="banca__nova">
          {(["esquerda", "empate", "direita"] as const).map((escolha) => (
            <button
              key={escolha}
              type="button"
              className={`button button--ghost${par.escolha === escolha ? " paginas__ativa" : ""}`}
              onClick={() => void escolher(escolha)}
            >
              {escolha === "empate" ? "Empate" : `${escolha === "esquerda" ? "Esquerda" : "Direita"} é melhor`}
            </button>
          ))}
        </div>
      )}
      {erro ? <p className="opiniao__erro">{erro}</p> : null}
    </article>
  );
}

function Lado({
  lado,
  nota,
  onNota,
  rotulo,
}: {
  lado: LadoDoPar;
  nota: number;
  onNota: (n: number) => void;
  rotulo: string;
}) {
  const url = lado.asset?.variants?.[0]?.url ?? null;
  return (
    <div className="par__lado">
      {url ? (
        <>
          <img className="par__imagem" src={url} alt={rotulo} />
          <img className="par__real" src={url} alt="" aria-hidden="true" />
        </>
      ) : (
        <div className="par__imagem par__imagem--vazia">{lado.etapa ?? "sem desenho"}</div>
      )}
      <div className="par__notas" role="radiogroup" aria-label={`Nota ${rotulo}`}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className={`button button--ghost${nota === n ? " paginas__ativa" : ""}`}
            onClick={() => onNota(n)}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}

function Resumo({ resumo }: { resumo: Record<string, unknown> }) {
  const vitorias = resumo.vitorias as Record<string, number>;
  const notas = resumo.nota_media as Record<string, number>;
  const por = resumo.por_rodada as Record<string, Record<string, number | string>>;
  const queda = resumo.maior_queda as { item: string; de: number; para: number } | null;
  const nova = String(resumo.nova);
  const ref = String(resumo.referencia);
  return (
    <section className="resumo" aria-label="Resumo da comparação">
      <h3 className="par__titulo">Resumo</h3>
      <p>
        {nova} (nova) venceu {vitorias[nova]} · {ref} venceu {vitorias[ref]} · empate {vitorias.empate}
      </p>
      <p>
        nota média {ref} {notas[ref]} · {nova} {notas[nova]}
        {queda ? ` · maior queda: ${queda.item} (${queda.de} → ${queda.para})` : ""}
      </p>
      {[ref, nova].map((id) => (
        <p key={id} className="pedido__meta">
          {id} · {String(por[id]?.rotulo)} · {String(por[id]?.modo_conceito)} · remendos {por[id]?.remendos} ·
          desvios do olho {por[id]?.desvios_do_olho} · ~{por[id]?.tokens_estimados} tokens
        </p>
      ))}
      <p>
        <strong>{String(resumo.veredito)}</strong>
      </p>
    </section>
  );
}
