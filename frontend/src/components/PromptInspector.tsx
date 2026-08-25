import { useState } from "react";

import type { PreviewError } from "../hooks/usePromptPreview";
import { diffSpec } from "../specOverrides";
import {
  assetTypeLabel,
  capitalize,
  categoryLabel,
  isUserChoice,
  sourceLabel,
  viewLabel,
} from "../labels";
import type {
  FinalResolvedSpec,
  PromptPreview,
  SemanticPrompt,
  SpecOverrides,
  SpecSource,
} from "../types";

type Tab = "reading" | "spec" | "prompt";

interface PromptInspectorProps {
  preview: PromptPreview | null;
  loading: boolean;
  error: PreviewError | null;
  /** Há uma correção manual do spec em vigor. */
  specEdited: boolean;
  /** Há uma semântica corrigida à mão em vigor. */
  semanticEdited: boolean;
  stale: boolean;
  disabled?: boolean;
  onEditSpec: (overrides: SpecOverrides | null) => void;
  onEditSemantic: (semantic: SemanticPrompt | null) => void;
}

/**
 * O que o AssetFlow entendeu da descrição — e onde discordar.
 *
 * O painel tem três abas, e a divisão não é cosmética (plano T→J §32):
 *
 *   Interpretação   o contrato em português, para quem quer conferir
 *   JSON final      o mesmo contrato, cru e editável (plano T→J §33)
 *   Prompt          a semântica enviada ao motor, para quem quer ajustar
 *
 * A primeira existe porque a versão anterior deste painel mostrava JSON e
 * mais nada. Quem pedia uma árvore e recebia um personagem tinha a resposta
 * na tela — `"asset_type": "character"` — e nenhuma chance de notar.
 *
 * O que a aba "JSON final" mostra é literalmente o objeto que a geração vai
 * executar, com ``spec_hash`` e tudo. Editar ali vira uma correção manual, o
 * nível de precedência mais alto que existe: nenhuma camada posterior desfaz.
 */
export function PromptInspector({
  preview,
  loading,
  error,
  specEdited,
  semanticEdited,
  stale,
  disabled = false,
  onEditSpec,
  onEditSemantic,
}: PromptInspectorProps) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("reading");

  if (!preview && !loading && !error) return null;

  const edited = specEdited || semanticEdited;

  return (
    <section className={`inspector${open ? " inspector--open" : ""}`}>
      <button
        type="button"
        className="inspector__toggle"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="inspector__chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="inspector__title">O que o AssetFlow entendeu</span>
        {preview ? <Headline resolved={preview.resolved} /> : null}
        {edited ? <span className="inspector__badge">editado</span> : null}
        {stale ? (
          <span className="inspector__badge inspector__badge--warn">desatualizado</span>
        ) : null}
        {loading ? <span className="inspector__loading">lendo…</span> : null}
      </button>

      {open ? (
        <div className="inspector__body">
          {stale ? (
            <p className="inspector__notice">
              A descrição mudou depois da sua correção. O que está abaixo é o que será
              enviado — a frase nova só entra se você voltar ao automático.
            </p>
          ) : null}

          {error ? (
            <div className="inspector__error" role="alert">
              <p>{error.message}</p>
              {error.fields.length > 0 ? (
                <ul className="inspector__fields">
                  {error.fields.map((field) => (
                    <li key={`${field.campo}:${field.erro}`}>
                      <code>{field.campo}</code> — {field.erro}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {preview ? (
            <>
              <div className="inspector__tabs" role="tablist">
                <TabButton current={tab} value="reading" onSelect={setTab}>
                  Interpretação
                </TabButton>
                <TabButton current={tab} value="spec" onSelect={setTab}>
                  JSON final
                </TabButton>
                <TabButton current={tab} value="prompt" onSelect={setTab}>
                  Prompt
                </TabButton>
              </div>

              {tab === "reading" ? (
                <Reading preview={preview} />
              ) : tab === "spec" ? (
                <JsonEditor
                  title="Contrato final"
                  note={
                    <>
                      É este objeto que o pipeline executa — o mesmo{" "}
                      <code>spec_hash</code> fica gravado junto do asset. O que você
                      mudar aqui ganha de tudo: da descrição, dos controles e do
                      estilo escolhido.
                    </>
                  }
                  value={preview.resolved}
                  edited={specEdited}
                  disabled={disabled}
                  onApply={(parsed) => onEditSpec(diffSpec(preview.resolved, parsed))}
                  onReset={() => onEditSpec(null)}
                />
              ) : (
                <JsonEditor
                  title="Semântica enviada ao motor"
                  note={
                    <>
                      A leitura do prompt, campo a campo. Corrigir aqui{" "}
                      <strong>substitui</strong> o builder inteiro: os padrões do
                      AssetFlow não são reaplicados por cima — tirar{" "}
                      <code>sprite sheet</code> da lista de <code>avoid</code> tira
                      mesmo, com a consequência junto.
                    </>
                  }
                  value={preview.semantic}
                  edited={semanticEdited}
                  disabled={disabled}
                  onApply={(parsed) => onEditSemantic(parsed as unknown as SemanticPrompt)}
                  onReset={() => onEditSemantic(null)}
                />
              )}
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

/** O resumo de uma linha que aparece no cabeçalho fechado. */
function Headline({ resolved }: { resolved: FinalResolvedSpec }) {
  const size = resolved.logical_resolution;
  return (
    <span className="inspector__headline">
      {assetTypeLabel(resolved.asset.type)}
      {size ? ` · ${size.width}×${size.height}` : null}
    </span>
  );
}

function TabButton({
  current,
  value,
  onSelect,
  children,
}: {
  current: Tab;
  value: Tab;
  onSelect: (tab: Tab) => void;
  children: React.ReactNode;
}) {
  const active = current === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={`inspector__tab${active ? " inspector__tab--active" : ""}`}
      onClick={() => onSelect(value)}
    >
      {children}
    </button>
  );
}

/**
 * O contrato em português (plano T→J §17 e §45).
 *
 * Cada linha traz a origem do valor junto. É a informação que faltava: o
 * painel antigo mostrava "64 × 64" sem dizer que aquilo era o padrão do
 * estilo, e por isso ninguém percebia que o 32 × 32 pedido tinha sumido.
 */
function Reading({ preview }: { preview: PromptPreview }) {
  const { resolved } = preview;
  const size = resolved.logical_resolution;
  const palette = resolved.palette;
  const category = categoryLabel(resolved.asset.category);
  const view = viewLabel(resolved.composition.view);

  return (
    <div className="reading">
      <dl className="reading__grid">
        <Row
          label="Tipo"
          value={assetTypeLabel(resolved.asset.type)}
          source={resolved.sources["asset.type"]}
        />
        <Row
          label="Objeto"
          value={capitalize(resolved.asset.subject)}
          source={resolved.sources["asset.subject"]}
        />
        {category ? (
          <Row
            label="Categoria"
            value={category}
            source={resolved.sources["asset.category"]}
          />
        ) : null}
        <Row
          label="Modo"
          value={resolved.asset.mode === "pixel" ? "Pixel Art" : "2D convencional"}
          source={resolved.sources["asset.mode"]}
        />
        {size ? (
          <Row
            label="Resolução"
            value={`${size.width} × ${size.height}`}
            source={resolved.sources["logical_resolution"]}
          />
        ) : null}
        {palette?.max_colors ? (
          <Row
            label="Paleta"
            value={`${palette.max_colors} cores`}
            source={resolved.sources["palette"]}
          />
        ) : null}
        <Row
          label="Fundo"
          value={resolved.background.mode === "transparent" ? "Transparente" : "Sólido"}
          source={resolved.sources["background"]}
        />
        {view ? (
          <Row
            label="Vista"
            value={view}
            source={resolved.sources["composition.view"]}
          />
        ) : null}
        <Row
          label="Variações"
          value={String(resolved.generation.variations)}
          source={resolved.sources["generation.variations"]}
        />
        <Row
          label="Motor"
          value={engineValue(resolved)}
          source={resolved.sources["engine"]}
        />
        <Row
          label="Otimização"
          value={pipelineValue(resolved)}
          showSource={false}
        />
      </dl>

      {resolved.notes.length > 0 ? (
        <ul className="reading__notes">
          {resolved.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}

      <NeutralReading preview={preview} />
    </div>
  );
}

/**
 * O estágio que vem depois do motor (plano Optimizer §32).
 *
 * A linha aparece **sem** origem, e é a única do painel assim. Origem
 * responde "quem escolheu este valor?", e aqui ninguém escolheu: a otimização
 * é parte do pipeline, não uma das seis camadas de precedência (§33 e §46).
 * Mostrar `global_default` ao lado dela sugeriria que outra camada poderia
 * ter falado — e nenhuma pode.
 */
function pipelineValue(resolved: FinalResolvedSpec): string {
  const pipeline = resolved.pixel_pipeline;
  if (!pipeline?.optimize) return "desligada nesta instalação";
  return `${pipeline.optimizer_id} · até ${pipeline.max_iterations} passadas`;
}

/**
 * O motor, em uma linha (plano de motores §5 e §17).
 *
 * O id cru é o que aparece, e é o certo aqui: esta aba mostra o **contrato**,
 * campo por campo, com a origem de cada valor. Trocar o id pelo nome de
 * exibição faria a aba deixar de casar com o JSON da aba ao lado — que é
 * literalmente o mesmo objeto, e onde o id é o que se edita.
 *
 * O nome bonito fica no seletor e no crédito do resultado, que é onde ele
 * serve para escolher e para reconhecer.
 */
function engineValue(resolved: FinalResolvedSpec): string {
  const engine = resolved.engine;
  if (!engine.engine_id) return "Automático";
  if (engine.selection_mode === "manual") return `${engine.engine_id} (escolhido)`;
  return `${engine.engine_id} (automático)`;
}

/**
 * Uma linha do contrato, com a origem do valor ao lado.
 *
 * `showSource={false}` existe para **um** campo: a otimização, que nenhuma
 * camada de precedência decide. Um selo ali — mesmo "padrão do sistema" —
 * sugeriria que alguma camada poderia ter falado, e nenhuma pode (§33 e §46).
 * Note que isso é diferente de `source` ausente, que continua significando
 * "ninguém opinou" e mostra o selo (ver `pipelineValue`).
 */
function Row({
  label,
  value,
  source,
  showSource = true,
}: {
  label: string;
  value: string;
  source?: SpecSource | undefined;
  showSource?: boolean;
}) {
  return (
    <>
      <dt className="reading__label">{label}</dt>
      <dd className="reading__value">
        {value}
        {showSource ? (
          <span
            className={`reading__source${
              isUserChoice(source) ? " reading__source--user" : ""
            }`}
          >
            {sourceLabel(source)}
          </span>
        ) : null}
      </dd>
    </>
  );
}

/**
 * Editor de JSON compartilhado pelas duas abas editáveis.
 *
 * O rascunho vive aqui dentro e só sai daqui em "Aplicar": digitar JSON
 * inválido no meio da edição é normal, e revalidar a cada tecla encheria a
 * tela de erro enquanto a pessoa ainda está escrevendo.
 */
function JsonEditor({
  title,
  note,
  value,
  edited,
  disabled,
  onApply,
  onReset,
}: {
  title: string;
  note: React.ReactNode;
  value: unknown;
  edited: boolean;
  disabled: boolean;
  onApply: (parsed: Record<string, unknown>) => void;
  onReset: () => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const editing = draft !== null;

  const apply = () => {
    if (draft === null) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(draft);
    } catch (caught) {
      setParseError(
        caught instanceof Error ? `JSON inválido: ${caught.message}` : "JSON inválido.",
      );
      return;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setParseError("O conteúdo precisa ser um objeto JSON.");
      return;
    }
    // O contrato de campos quem confere é o backend, na pré-visualização:
    // duplicar a validação aqui só criaria duas versões da mesma regra.
    onApply(parsed as Record<string, unknown>);
    setDraft(null);
    setParseError(null);
  };

  return (
    <div className="editor">
      <p className="editor__note">{note}</p>

      {editing ? (
        <>
          <textarea
            className="inspector__editor"
            value={draft}
            spellCheck={false}
            rows={20}
            aria-label={title}
            onChange={(event) => setDraft(event.target.value)}
          />
          {parseError ? (
            <p className="inspector__error" role="alert">
              {parseError}
            </p>
          ) : null}
        </>
      ) : (
        <pre className="inspector__json">{JSON.stringify(value, null, 2)}</pre>
      )}

      <div className="inspector__actions">
        {editing ? (
          <>
            <button type="button" className="inspector__action" onClick={apply}>
              Aplicar
            </button>
            <button
              type="button"
              className="inspector__action inspector__action--ghost"
              onClick={() => {
                setDraft(null);
                setParseError(null);
              }}
            >
              Cancelar
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className="inspector__action"
              disabled={disabled}
              onClick={() => {
                setDraft(JSON.stringify(value, null, 2));
                setParseError(null);
              }}
            >
              Editar
            </button>
            {edited ? (
              <button
                type="button"
                className="inspector__action inspector__action--ghost"
                disabled={disabled}
                onClick={onReset}
              >
                Voltar ao automático
              </button>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

/**
 * A renderização textual neutra, em segundo plano e rotulada como tal.
 *
 * Ela ajuda a conferir a leitura com olho humano, mas **não** é a string que
 * chega ao modelo: um motor com dialeto próprio relê a semântica e monta o
 * texto dele. Apresentá-la como "o prompt enviado" faria alguém concluir que
 * o modelo ignorou uma palavra que ele nunca recebeu.
 */
function NeutralReading({ preview }: { preview: PromptPreview }) {
  return (
    <dl className="inspector__neutral">
      <dt>Leitura neutra</dt>
      <dd>{preview.positive}</dd>
      {preview.negative ? (
        <>
          <dt>Evitar</dt>
          <dd>{preview.negative}</dd>
        </>
      ) : null}
      <dd className="inspector__neutral-note">
        Texto de conferência. Um motor com dialeto próprio relê a estrutura acima e
        monta o prompt dele.
      </dd>
    </dl>
  );
}
