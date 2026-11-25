import type {
  AssetTypeId,
  BodyTypeId,
  DetailLevelId,
  FinalResolvedSpec,
  OutlineModeId,
  OutputSelection,
  ShadingModeId,
} from "../types";
import {
  ASSET_TYPE_OPTIONS,
  assetTypeLabel,
  bodyTypeLabel,
  detailLabel,
  outlineLabel,
  shadingLabel,
  viewLabel,
  viewOptionsFor,
} from "../labels";

/**
 * O que a pessoa escolhe explicitamente sobre o asset (plano T→J §18).
 *
 * Tudo aqui é opcional, e "opcional" tem um significado preciso: um controle
 * em **Automático** não envia valor nenhum. Ele não manda "64" nem manda o
 * padrão do estilo — ele se cala, e a resolução acontece nas camadas de
 * baixo. É essa diferença que o plano T→J §23 pede: o sistema precisa saber
 * separar "a pessoa pediu 64" de "ninguém disse nada".
 */
export interface AssetSelection {
  /** `null` = automático: o classificador semântico decide. */
  assetType: AssetTypeId | null;
  /** `null` = automático: vale a resolução do estilo escolhido. */
  logicalSize: number | null;
  /** `null` = automático: vale a paleta do estilo. */
  paletteSize: number | null;
  /** `null` = automático: vale o fundo do estilo. */
  transparent: boolean | null;
  /** `null` = automático: o builder decide a vista, como inferência. */
  view: string | null;
  /** `null` = automático: a descrição decide ("um lobo" já diz quadrúpede). */
  bodyType: BodyTypeId | null;
  /** Estilo — os três são orientação ao motor, não garantia. */
  detail: DetailLevelId | null;
  outline: OutlineModeId | null;
  shading: ShadingModeId | null;
}

export const EMPTY_SELECTION: AssetSelection = {
  assetType: null,
  logicalSize: null,
  paletteSize: null,
  transparent: null,
  view: null,
  bodyType: null,
  detail: null,
  outline: null,
  shading: null,
};

/** As resoluções do §18. Quadradas: é o formato de sprite e de tile. */
const RESOLUTIONS = [16, 32, 48, 64, 96, 128] as const;

/** As topologias oferecidas. `unknown` não entra: ele é o "Automático". */
const BODY_TYPE_OPTIONS = [
  "humanoid",
  "quadruped",
  "avian",
  "aquatic",
  "serpentine",
  "amorphous",
] as const;
const DETAIL_OPTIONS = ["low", "medium", "high"] as const;
const OUTLINE_OPTIONS = [
  "none",
  "black",
  "single_color",
  "selective",
  "adaptive_dark",
] as const;
const SHADING_OPTIONS = ["flat", "basic", "medium", "detailed"] as const;
const PALETTES = [8, 16, 32, 64] as const;

/**
 * Converte a seleção no `output` do pedido.
 *
 * Campos em automático somem do objeto — e não viram `null` — porque o
 * backend trata ausência como "não opino" e `null` como valor. Mandar `null`
 * seria dizer algo.
 */
export function selectionToOutput(
  selection: AssetSelection,
  variations = 1,
): OutputSelection {
  const output: OutputSelection = { variations };
  if (selection.logicalSize !== null) {
    output.logical_width = selection.logicalSize;
    output.logical_height = selection.logicalSize;
  }
  if (selection.paletteSize !== null) output.palette_size = selection.paletteSize;
  if (selection.transparent !== null) output.transparent = selection.transparent;
  if (selection.view !== null) output.view = selection.view;
  if (selection.bodyType !== null) output.body_type = selection.bodyType;
  if (selection.detail !== null) output.detail = selection.detail;
  if (selection.outline !== null) output.outline = selection.outline;
  if (selection.shading !== null) output.shading = selection.shading;
  return output;
}

interface AssetControlsProps {
  selection: AssetSelection;
  /** O contrato resolvido, para mostrar o que "Automático" está resolvendo. */
  resolved: FinalResolvedSpec | null;
  /** Pixel Art tem resolução lógica e paleta; 2D convencional não tem. */
  pixel: boolean;
  disabled?: boolean;
  onChange: (selection: AssetSelection) => void;
}

/**
 * Os controles explícitos do gerador.
 *
 * Eles são deliberadamente poucos e dependentes do tipo (plano T→J §19):
 * paleta e resolução lógica só existem em Pixel Art, e mostrá-las no modo 2D
 * criaria um campo que o backend recusa — que é pior do que não ter o campo.
 *
 * O rótulo "Automático" de cada controle mostra, entre parênteses, o valor
 * que está sendo resolvido no lugar. Sem isso, "Automático" é uma caixa preta
 * e a pessoa precisa gerar para descobrir o que ele significava.
 */
export function AssetControls({
  selection,
  resolved,
  pixel,
  disabled = false,
  onChange,
}: AssetControlsProps) {
  const update = (patch: Partial<AssetSelection>) =>
    onChange({ ...selection, ...patch });

  const autoType = resolved ? assetTypeLabel(resolved.asset.type) : null;
  const autoSize = resolved?.logical_resolution
    ? `${resolved.logical_resolution.width} × ${resolved.logical_resolution.height}`
    : null;
  const autoPalette = resolved?.palette?.max_colors ?? null;
  const autoBackground = resolved
    ? resolved.background.mode === "transparent"
      ? "transparente"
      : "sólido"
    : null;

  // As vistas dependem do tipo **resolvido**, e não do tipo escolhido no
  // dropdown: quem deixou o tipo em automático continua vendo as opções que
  // fazem sentido para o que o AssetFlow entendeu (plano T→J §19).
  const assetType = selection.assetType ?? resolved?.asset.type ?? "character";
  const views = viewOptionsFor(assetType);
  const autoView = resolved?.composition.view
    ? viewLabel(resolved.composition.view)
    : null;

  // Topologia só faz sentido em personagem: um tileset não tem corpo, e um
  // controle que não se aplica é pior do que um controle ausente. É a mesma
  // regra que já esconde resolução lógica no modo 2D.
  const isCharacter = assetType === "character";
  const resolvedBody = resolved?.character?.body_type ?? "unknown";
  const autoBody = resolvedBody !== "unknown" ? bodyTypeLabel(resolvedBody) : null;

  const autoDetail =
    resolved && resolved.style.detail !== "auto"
      ? detailLabel(resolved.style.detail)
      : null;
  const autoOutline =
    resolved && resolved.style.outline.mode !== "auto"
      ? outlineLabel(resolved.style.outline.mode)
      : null;
  const autoShading =
    resolved && resolved.style.shading.mode !== "auto"
      ? shadingLabel(resolved.style.shading.mode)
      : null;

  return (
    <div className="controls" role="group" aria-label="Configuração do asset">
      <Control label="Tipo">
        <select
          className="controls__field"
          value={selection.assetType ?? ""}
          disabled={disabled}
          onChange={(event) =>
            update({ assetType: (event.target.value || null) as AssetTypeId | null })
          }
        >
          <option value="">{auto(autoType)}</option>
          {ASSET_TYPE_OPTIONS.map((type) => (
            <option key={type} value={type}>
              {assetTypeLabel(type)}
            </option>
          ))}
        </select>
      </Control>

      {pixel ? (
        <>
          <Control label="Resolução">
            <select
              className="controls__field"
              value={selection.logicalSize ?? ""}
              disabled={disabled}
              onChange={(event) =>
                update({
                  logicalSize: event.target.value ? Number(event.target.value) : null,
                })
              }
            >
              <option value="">{auto(autoSize)}</option>
              {RESOLUTIONS.map((size) => (
                <option key={size} value={size}>
                  {size} × {size}
                </option>
              ))}
            </select>
          </Control>

          <Control label="Cores">
            <select
              className="controls__field"
              value={selection.paletteSize ?? ""}
              disabled={disabled}
              onChange={(event) =>
                update({
                  paletteSize: event.target.value ? Number(event.target.value) : null,
                })
              }
            >
              <option value="">{auto(autoPalette)}</option>
              {PALETTES.map((size) => (
                <option key={size} value={size}>
                  {size} cores
                </option>
              ))}
            </select>
          </Control>
        </>
      ) : null}

      {views.length > 1 ? (
        <Control label="Vista">
          <select
            className="controls__field"
            value={selection.view ?? ""}
            disabled={disabled}
            onChange={(event) => update({ view: event.target.value || null })}
          >
            <option value="">{auto(autoView)}</option>
            {views.map((view) => (
              <option key={view} value={view}>
                {viewLabel(view)}
              </option>
            ))}
          </select>
        </Control>
      ) : null}

      {isCharacter ? (
        <Control label="Tipo corporal">
          <select
            className="controls__field"
            value={selection.bodyType ?? ""}
            disabled={disabled}
            onChange={(event) =>
              update({ bodyType: (event.target.value || null) as BodyTypeId | null })
            }
          >
            <option value="">{auto(autoBody)}</option>
            {BODY_TYPE_OPTIONS.map((body) => (
              <option key={body} value={body}>
                {bodyTypeLabel(body)}
              </option>
            ))}
          </select>
        </Control>
      ) : null}

      {pixel ? (
        <>
          <Control label="Detalhe">
            <select
              className="controls__field"
              value={selection.detail ?? ""}
              disabled={disabled}
              onChange={(event) =>
                update({ detail: (event.target.value || null) as DetailLevelId | null })
              }
            >
              <option value="">{auto(autoDetail)}</option>
              {DETAIL_OPTIONS.map((level) => (
                <option key={level} value={level}>
                  {detailLabel(level)}
                </option>
              ))}
            </select>
          </Control>

          <Control label="Contorno">
            <select
              className="controls__field"
              value={selection.outline ?? ""}
              disabled={disabled}
              onChange={(event) =>
                update({
                  outline: (event.target.value || null) as OutlineModeId | null,
                })
              }
            >
              <option value="">{auto(autoOutline)}</option>
              {OUTLINE_OPTIONS.map((mode) => (
                <option key={mode} value={mode}>
                  {outlineLabel(mode)}
                </option>
              ))}
            </select>
          </Control>

          <Control label="Sombreamento">
            <select
              className="controls__field"
              value={selection.shading ?? ""}
              disabled={disabled}
              onChange={(event) =>
                update({
                  shading: (event.target.value || null) as ShadingModeId | null,
                })
              }
            >
              <option value="">{auto(autoShading)}</option>
              {SHADING_OPTIONS.map((mode) => (
                <option key={mode} value={mode}>
                  {shadingLabel(mode)}
                </option>
              ))}
            </select>
          </Control>
        </>
      ) : null}

      <Control label="Fundo">
        <select
          className="controls__field"
          value={selection.transparent === null ? "" : String(selection.transparent)}
          disabled={disabled}
          onChange={(event) =>
            update({
              transparent: event.target.value === "" ? null : event.target.value === "true",
            })
          }
        >
          <option value="">{auto(autoBackground)}</option>
          <option value="true">Transparente</option>
          <option value="false">Sólido</option>
        </select>
      </Control>
    </div>
  );
}

function Control({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="controls__control">
      <span className="controls__label">{label}</span>
      {children}
    </label>
  );
}

function auto(value: string | number | null): string {
  return value === null || value === "" ? "Automático" : `Automático (${value})`;
}
