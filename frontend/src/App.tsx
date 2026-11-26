import { useCallback, useEffect, useRef, useState } from "react";

import {
  type AssetSelection,
  AssetControls,
  EMPTY_SELECTION,
} from "./components/AssetControls";
import { EmptyResult } from "./components/EmptyResult";
import { GenerateButton } from "./components/GenerateButton";
import { GenerationResult } from "./components/GenerationResult";
import { GeneratorHero } from "./components/GeneratorHero";
import { Header } from "./components/Header";
import { LiberdadeControls } from "./components/LiberdadeControls";
import { BancaPage } from "./components/BancaPage";
import { LicoesPanel } from "./components/LicoesPanel";
import { PedidosList } from "./components/PedidosList";
import { PromptInput } from "./components/PromptInput";
import { PromptInspector } from "./components/PromptInspector";
import { SessionHistory } from "./components/SessionHistory";
import { usePedidos } from "./hooks/usePedidos";
import { type PromptEdit, usePromptPreview } from "./hooks/usePromptPreview";
import { buildPedidoPayload, detalharPedido } from "./services/generationApi";
import {
  type GenerationMode,
  type GenerationOutcome,
  type HistoryEntry,
  type Liberdade,
  MODES,
  type ModoConceito,
  type Pedido,
} from "./types";

/** O app só gera Pixel Art. */
const MODE: GenerationMode = "pixel";

const DICA_DO_PEDIDO =
  "O pedido vai para a fila. Depois, no chat do Claude Code (não neste campo), " +
  "diga: “desenhe os pedidos pendentes do AssetFlow”.";

/**
 * Página do gerador (plano da tela §28 e §29; Fase B do plano do app).
 *
 * A tela monta **pedidos**: "Gerar" cria um pedido na fila, o Claude o desenha
 * pela conversa, e o resultado aparece aqui sozinho — a lista consulta a API
 * enquanto houver pedido ativo. Nada de motor: o app tem um gerador só.
 */
export function App() {
  const [prompt, setPrompt] = useState("");
  // Os controles explícitos (tipo, resolução, paleta, fundo). Começam todos
  // em automático: quem só quer um sprite não deve precisar preencher nada.
  const [selection, setSelection] = useState<AssetSelection>(EMPTY_SELECTION);
  // A correção da leitura mora aqui, e não dentro do painel: ela precisa
  // sobreviver ao painel fechado e acompanhar o pedido até a criação.
  const [edit, setEdit] = useState<PromptEdit | null>(null);
  const [liberdade, setLiberdade] = useState<Liberdade>("equilibrado");
  const [modoConceito, setModoConceito] = useState<ModoConceito>("eu_escolho");
  const [pagina, setPagina] = useState<"pedidos" | "banca">("pedidos");
  const [direcao, setDirecao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);
  const [selecionadoId, setSelecionadoId] = useState<string | null>(null);
  const [emAcao, setEmAcao] = useState<string | null>(null);

  const promptRef = useRef<HTMLTextAreaElement>(null);
  const fila = usePedidos();
  const inspector = usePromptPreview(MODE, prompt, selection, edit, setEdit);

  const canGenerate = prompt.trim().length > 0 && !enviando;

  // Um pedido que acabou de ficar pronto (ou de falhar com desenho) abre na
  // área de resultado sozinho, sem recarregar a página.
  const etapas = useRef<Map<string, string> | null>(null);
  useEffect(() => {
    const anteriores = etapas.current;
    etapas.current = new Map(fila.pedidos.map((pedido) => [pedido.id, pedido.etapa]));
    if (anteriores === null) return;
    const terminou = fila.pedidos.find(
      (pedido) =>
        pedido.asset !== null &&
        (pedido.etapa === "pronto" || pedido.etapa === "nao_aprovado") &&
        anteriores.get(pedido.id) !== pedido.etapa,
    );
    if (terminou) setSelecionadoId(terminou.id);
  }, [fila.pedidos]);

  const pedirDesenho = useCallback(async () => {
    const descricao = prompt.trim();
    if (!descricao || enviando) return;
    setEnviando(true);
    setAviso(null);
    try {
      await fila.criar(
        buildPedidoPayload({
          mode: MODE,
          prompt: descricao,
          selection,
          spec: edit?.spec ?? null,
          semantic: edit?.semantic ?? null,
          liberdade,
          direcaoDeArte: direcao,
          modoConceito,
        }),
      );
      // A descrição, a correção e a direção são deste pedido; os controles e a
      // liberdade ficam, para o próximo pedido parecido sair rápido.
      setPrompt("");
      setEdit(null);
      setDirecao("");
      setAviso({ tipo: "ok", texto: DICA_DO_PEDIDO });
      promptRef.current?.focus();
    } catch (caught) {
      setAviso({
        tipo: "erro",
        texto: caught instanceof Error ? caught.message : "Não foi possível criar o pedido.",
      });
    } finally {
      setEnviando(false);
    }
  }, [direcao, edit, enviando, fila, liberdade, modoConceito, prompt, selection]);

  const pedirDeNovo = useCallback(
    async (pedido: Pedido) => {
      setAviso(null);
      try {
        const detalhe = await detalharPedido(pedido.id);
        await fila.criar(detalhe.corpo);
        setAviso({ tipo: "ok", texto: DICA_DO_PEDIDO });
      } catch (caught) {
        setAviso({
          tipo: "erro",
          texto: caught instanceof Error ? caught.message : "Não foi possível repetir o pedido.",
        });
      }
    },
    [fila],
  );

  const agir = useCallback(
    async (pedido: Pedido, acao: (id: string) => Promise<void>) => {
      setEmAcao(pedido.id);
      try {
        await acao(pedido.id);
      } catch (caught) {
        setAviso({
          tipo: "erro",
          texto: caught instanceof Error ? caught.message : "A fila de pedidos não respondeu.",
        });
      } finally {
        setEmAcao(null);
      }
    },
    [],
  );

  const handleNewPrompt = useCallback(() => {
    setPrompt("");
    setSelection(EMPTY_SELECTION);
    setEdit(null);
    setDirecao("");
    setSelecionadoId(null);
    promptRef.current?.focus();
  }, []);

  const comDesenho = fila.pedidos.filter((pedido) => varianteDe(pedido) !== null);
  const selecionado =
    comDesenho.find((pedido) => pedido.id === selecionadoId) ??
    (selecionadoId === null ? comDesenho.find((pedido) => pedido.etapa === "pronto") : undefined);
  const resultado = selecionado ? outcomeOf(selecionado) : null;
  const prontos: HistoryEntry[] = comDesenho
    .filter((pedido) => pedido.etapa === "pronto" && !pedido.banca)
    .flatMap((pedido) => {
      const outcome = outcomeOf(pedido);
      return outcome ? [{ ...outcome, createdAt: Date.parse(pedido.atualizado_em) }] : [];
    });

  return (
    <div className="page">
      <Header />

      <nav className="paginas" aria-label="Páginas">
        <button
          type="button"
          className={`button button--ghost${pagina === "pedidos" ? " paginas__ativa" : ""}`}
          onClick={() => setPagina("pedidos")}
        >
          Pedidos
        </button>
        <button
          type="button"
          className={`button button--ghost${pagina === "banca" ? " paginas__ativa" : ""}`}
          onClick={() => setPagina("banca")}
        >
          Banca e Comparar
        </button>
      </nav>

      {pagina === "banca" ? (
        <main className="page__main">
          <BancaPage />
        </main>
      ) : (
      <main className="page__main">
        <GeneratorHero />

        <section className="generator" aria-label="Pedido de asset">
          <PromptInput
            ref={promptRef}
            value={prompt}
            placeholder={MODES[MODE].placeholder}
            disabled={enviando}
            onChange={setPrompt}
            onSubmit={() => void pedirDesenho()}
          />

          <AssetControls
            selection={selection}
            resolved={inspector.preview?.resolved ?? null}
            pixel
            disabled={enviando}
            onChange={setSelection}
          />

          <LiberdadeControls
            liberdade={liberdade}
            direcao={direcao}
            disabled={enviando}
            onLiberdade={setLiberdade}
            onDirecao={setDirecao}
            modoConceito={modoConceito}
            onModoConceito={setModoConceito}
          />

          <PromptInspector
            preview={inspector.preview}
            loading={inspector.loading}
            error={inspector.error}
            specEdited={inspector.specEdited}
            semanticEdited={inspector.semanticEdited}
            stale={inspector.stale}
            disabled={enviando}
            onEditSpec={inspector.setSpecEdit}
            onEditSemantic={inspector.setSemanticEdit}
          />

          <GenerateButton
            disabled={!canGenerate}
            busy={enviando}
            note={aviso?.tipo === "erro" ? null : aviso?.texto ?? DICA_DO_PEDIDO}
            error={aviso?.tipo === "erro" ? aviso.texto : null}
            onClick={() => void pedirDesenho()}
          />
        </section>

        <section className="outcome" aria-live="polite">
          {resultado && selecionado ? (
            <GenerationResult
              outcome={resultado}
              busy={false}
              onRegenerate={() => void pedirDeNovo(selecionado)}
              onNewPrompt={handleNewPrompt}
            />
          ) : (
            <EmptyResult />
          )}
        </section>

        <PedidosList
          pedidos={fila.pedidos}
          erro={fila.erro}
          selecionadoId={selecionado?.id ?? null}
          emAcao={emAcao}
          onSelect={(pedido) => setSelecionadoId(pedido.id)}
          onCancelar={(pedido) => void agir(pedido, fila.cancelar)}
          onDevolver={(pedido) => void agir(pedido, fila.devolver)}
          onConceito={fila.atualizar}
        />

        <SessionHistory
          entries={prontos}
          activeJobId={selecionado?.id ?? null}
          onSelect={(entry) => setSelecionadoId(entry.jobId)}
        />

        <LicoesPanel />
      </main>
      )}

      <footer className="page__footer">
        <p>
          O AssetFlow tem um gerador só: o <strong>desenhista</strong>, em que o Claude
          desenha o sprite na grade lógica a partir de uma receita. Todo desenho passa
          pelo <strong>Pixel Exact</strong> e pelo <strong>Pixel Optimizer</strong>{" "}
          antes de ser entregue.
        </p>
      </footer>
    </div>
  );
}

/** A variação desenhada de um pedido, se houver. */
function varianteDe(pedido: Pedido) {
  return pedido.asset?.variants?.[0] ?? null;
}

/** Um pedido com desenho, no formato da área de resultado. */
function outcomeOf(pedido: Pedido): GenerationOutcome | null {
  const variant = varianteDe(pedido);
  if (!variant) return null;
  const warnings =
    pedido.etapa === "nao_aprovado"
      ? [`Não aprovado${pedido.motivo ? ` — ${pedido.motivo}` : ""}. Este é o último desenho.`]
      : pedido.etapa === "olhando"
        ? ["Aprovado no validador; o Claude ainda vai olhar e pode remendar."]
        : [];
  const pronto = pedido.etapa === "pronto";
  return {
    jobId: pedido.id,
    mode: MODE,
    prompt: pedido.texto,
    variant,
    preview: null,
    warnings,
    assetId: pronto ? (pedido.asset?.id ?? null) : null,
    olhar: pronto ? pedido.olhar : null,
    pedidoId: pronto ? pedido.id : null,
  };
}
