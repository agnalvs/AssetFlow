import { type KeyboardEvent, type PointerEvent, useEffect, useMemo, useRef, useState } from "react";

import { abrirEditor, salvarEdicao } from "../services/generationApi";
import type { EdicaoResultado, EditorDados } from "../types";

interface EditorDePixelsProps {
  pedidoId: string;
  onFechar: () => void;
}

type Ferramenta = "lapis" | "apagar" | "conta_gotas";
/** "x,y" -> chave da paleta, ou null (apagado). */
type Trocas = Map<string, string | null>;

const LADO = 384;
const XADREZ_A = "#2a3040";
const XADREZ_B = "#1f2430";

/**
 * O editor de pixels da tela (lote 5).
 *
 * Troca alguns pixels de um asset pronto com as cores do próprio desenho e
 * salva como remendo: uma camada `retoque_N` no fim da receita, que passa pelo
 * caminho de sempre (Optimizer e validador incluídos). Sai um asset novo, como
 * um pedido de ajuste pronto; o original fica como era. Não chama o Claude.
 */
export function EditorDePixels({ pedidoId, onFechar }: EditorDePixelsProps) {
  const [dados, setDados] = useState<EditorDados | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [trocas, setTrocas] = useState<Trocas>(new Map());
  const [desfazer, setDesfazer] = useState<Trocas[]>([]);
  const [refazer, setRefazer] = useState<Trocas[]>([]);
  const [ferramenta, setFerramenta] = useState<Ferramenta>("lapis");
  const [cor, setCor] = useState<string | null>(null);
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [resultado, setResultado] = useState<EdicaoResultado | null>(null);
  const pintando = useRef(false);
  const tela = useRef<HTMLCanvasElement>(null);
  const real = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let vivo = true;
    abrirEditor(pedidoId)
      .then((lidos) => {
        if (!vivo) return;
        setDados(lidos);
        setCor(Object.keys(lidos.paleta)[0] ?? null);
      })
      .catch((caught) => {
        if (vivo) setErro(caught instanceof Error ? caught.message : "O editor não abriu.");
      });
    return () => {
      vivo = false;
    };
  }, [pedidoId]);

  const celula = dados ? Math.max(4, Math.min(24, Math.floor(LADO / Math.max(dados.largura, dados.altura)))) : 1;

  /** A cor que cada pixel mostra agora: a troca, ou o original. */
  const corEm = useMemo(() => {
    return (x: number, y: number): string | null => {
      if (!dados) return null;
      const chave = `${x},${y}`;
      if (trocas.has(chave)) {
        const valor = trocas.get(chave);
        return valor == null ? null : (dados.paleta[valor] ?? null);
      }
      return dados.pixels[y]?.[x] ?? null;
    };
  }, [dados, trocas]);

  useEffect(() => {
    if (!dados) return;
    const ampliada = tela.current?.getContext("2d");
    const pequena = real.current?.getContext("2d");
    if (!ampliada || !pequena) return;
    pequena.clearRect(0, 0, dados.largura * 2, dados.altura * 2);
    for (let y = 0; y < dados.altura; y += 1) {
      for (let x = 0; x < dados.largura; x += 1) {
        const valor = corEm(x, y);
        ampliada.fillStyle = valor ?? ((x + y) % 2 === 0 ? XADREZ_A : XADREZ_B);
        ampliada.fillRect(x * celula, y * celula, celula, celula);
        if (valor) {
          pequena.fillStyle = valor;
          pequena.fillRect(x * 2, y * 2, 2, 2);
        }
      }
    }
    if (celula >= 8) {
      ampliada.strokeStyle = "rgba(255, 255, 255, 0.06)";
      ampliada.lineWidth = 1;
      for (let i = 0; i <= Math.max(dados.largura, dados.altura); i += 1) {
        ampliada.beginPath();
        ampliada.moveTo(i * celula + 0.5, 0);
        ampliada.lineTo(i * celula + 0.5, dados.altura * celula);
        ampliada.moveTo(0, i * celula + 0.5);
        ampliada.lineTo(dados.largura * celula, i * celula + 0.5);
        ampliada.stroke();
      }
    }
  }, [dados, corEm, celula]);

  if (erro) {
    return (
      <div className="editor" aria-label="Editor de pixels">
        <p className="opiniao__erro" role="alert">
          {erro}
        </p>
        <button type="button" className="button button--ghost" onClick={onFechar}>
          Fechar
        </button>
      </div>
    );
  }
  if (!dados) return <p className="editor__estado">Abrindo o editor…</p>;

  const posicao = (evento: PointerEvent<HTMLCanvasElement>) => {
    const caixa = evento.currentTarget.getBoundingClientRect();
    const x = Math.floor(((evento.clientX - caixa.left) / caixa.width) * dados.largura);
    const y = Math.floor(((evento.clientY - caixa.top) / caixa.height) * dados.altura);
    return x >= 0 && y >= 0 && x < dados.largura && y < dados.altura ? { x, y } : null;
  };

  const aplicar = (x: number, y: number) => {
    if (ferramenta === "conta_gotas") {
      const vista = corEm(x, y);
      const chave = Object.entries(dados.paleta).find(([, hex]) => hex === vista)?.[0];
      if (chave) {
        setCor(chave);
        setFerramenta("lapis");
      }
      return;
    }
    const valor = ferramenta === "apagar" ? null : cor;
    if (ferramenta === "lapis" && valor == null) return;
    setTrocas((atuais) => {
      const novas = new Map(atuais);
      const original = dados.pixels[y]?.[x] ?? null;
      const hex = valor == null ? null : dados.paleta[valor];
      if (hex === original) novas.delete(`${x},${y}`);
      else novas.set(`${x},${y}`, valor);
      return novas;
    });
  };

  const comecar = (evento: PointerEvent<HTMLCanvasElement>) => {
    const ponto = posicao(evento);
    if (!ponto) return;
    if (ferramenta !== "conta_gotas") {
      setDesfazer((pilha) => [...pilha, trocas]);
      setRefazer([]);
      pintando.current = true;
      evento.currentTarget.setPointerCapture(evento.pointerId);
    }
    setResultado(null);
    aplicar(ponto.x, ponto.y);
  };

  const mover = (evento: PointerEvent<HTMLCanvasElement>) => {
    if (!pintando.current) return;
    const ponto = posicao(evento);
    if (ponto) aplicar(ponto.x, ponto.y);
  };

  const voltar = () => {
    const anterior = desfazer[desfazer.length - 1];
    if (!anterior) return;
    setRefazer((pilha) => [...pilha, trocas]);
    setDesfazer((pilha) => pilha.slice(0, -1));
    setTrocas(anterior);
  };

  const avancar = () => {
    const seguinte = refazer[refazer.length - 1];
    if (!seguinte) return;
    setDesfazer((pilha) => [...pilha, trocas]);
    setRefazer((pilha) => pilha.slice(0, -1));
    setTrocas(seguinte);
  };

  const teclas = (evento: KeyboardEvent<HTMLDivElement>) => {
    if (!(evento.ctrlKey || evento.metaKey)) return;
    const tecla = evento.key.toLowerCase();
    if (tecla === "z" && !evento.shiftKey) {
      evento.preventDefault();
      voltar();
    } else if (tecla === "y" || (tecla === "z" && evento.shiftKey)) {
      evento.preventDefault();
      avancar();
    }
  };

  const salvar = async () => {
    setSalvando(true);
    setErro(null);
    try {
      const pixels = [...trocas.entries()].map(([chave, valor]) => {
        const [x, y] = chave.split(",").map(Number);
        return { x: x ?? 0, y: y ?? 0, cor: valor };
      });
      const salvo = await salvarEdicao(pedidoId, pixels, motivo);
      setResultado(salvo);
      if (salvo.aprovado) {
        setTrocas(new Map());
        setDesfazer([]);
        setRefazer([]);
        setMotivo("");
      }
    } catch (caught) {
      setErro(caught instanceof Error ? caught.message : "A edição não foi salva.");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="editor" aria-label="Editor de pixels" tabIndex={0} onKeyDown={teclas}>
      <div className="editor__ferramentas">
        {(
          [
            ["lapis", "Lápis"],
            ["apagar", "Apagar"],
            ["conta_gotas", "Conta-gotas"],
          ] as const
        ).map(([valor, rotulo]) => (
          <button
            key={valor}
            type="button"
            className={`button button--ghost${ferramenta === valor ? " opiniao__escolhido" : ""}`}
            onClick={() => setFerramenta(valor)}
          >
            {rotulo}
          </button>
        ))}
        <button type="button" className="button button--ghost" disabled={!desfazer.length} onClick={voltar}>
          Desfazer
        </button>
        <button type="button" className="button button--ghost" disabled={!refazer.length} onClick={avancar}>
          Refazer
        </button>
      </div>
      <div className="editor__paleta" role="radiogroup" aria-label="Cores do desenho">
        {Object.entries(dados.paleta).map(([chave, hex]) => (
          <button
            key={chave}
            type="button"
            role="radio"
            aria-checked={cor === chave}
            title={`${chave} · ${hex}`}
            className={`editor__cor${cor === chave ? " editor__cor--escolhida" : ""}`}
            style={{ background: hex }}
            onClick={() => {
              setCor(chave);
              setFerramenta("lapis");
            }}
          >
            <span>{chave}</span>
          </button>
        ))}
      </div>
      <div className="editor__area">
        <canvas
          ref={tela}
          className="editor__tela"
          width={dados.largura * celula}
          height={dados.altura * celula}
          onPointerDown={comecar}
          onPointerMove={mover}
          onPointerUp={() => {
            pintando.current = false;
          }}
          onPointerCancel={() => {
            pintando.current = false;
          }}
        />
        <div className="editor__previa">
          <canvas ref={real} width={dados.largura * 2} height={dados.altura * 2} />
          <span>2×</span>
        </div>
      </div>
      <p className="editor__estado">
        {trocas.size === 1 ? "1 pixel mudado" : `${trocas.size} pixels mudados`}
      </p>
      <textarea
        className="liberdade__texto"
        rows={2}
        maxLength={240}
        placeholder="O que estava errado? (opcional; vira lição na próxima conversa com o Claude)"
        value={motivo}
        onChange={(evento) => setMotivo(evento.target.value)}
      />
      <div className="editor__ferramentas">
        <button
          type="button"
          className="button button--primary"
          disabled={salvando || trocas.size === 0}
          onClick={() => void salvar()}
        >
          {salvando ? "Salvando…" : "Salvar como remendo"}
        </button>
        <button type="button" className="button button--ghost" disabled={salvando} onClick={onFechar}>
          {resultado?.aprovado ? "Fechar" : "Cancelar"}
        </button>
      </div>
      {resultado ? <ResultadoDaEdicao resultado={resultado} /> : null}
    </div>
  );
}

function ResultadoDaEdicao({ resultado }: { resultado: EdicaoResultado }) {
  if (!resultado.aprovado) {
    return (
      <p className="opiniao__erro" role="alert">
        O desenho editado não foi aprovado: {resultado.motivo}. Nada foi salvo na fila.
      </p>
    );
  }
  return (
    <div className="editor__estado" role="status">
      <p>
        Salvo como remendo ({resultado.camada}): {resultado.ficaram} de {resultado.mudados} pixels
        ficaram. O ajuste aparece em Prontos.
      </p>
      {resultado.avisos.map((aviso) => (
        <p key={aviso}>{aviso}</p>
      ))}
    </div>
  );
}
