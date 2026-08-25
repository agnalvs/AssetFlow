/**
 * Correções manuais do contrato — como calculá-las (plano T→J §9 e §11).
 *
 * Duas operações, e as duas produzem o mesmo tipo esparso: um `SpecOverrides`
 * com **só** o que foi decidido por alguém. "Esparso" é a propriedade que
 * importa: um override completo congelaria também os campos que ninguém
 * tocou, e mudar a descrição depois deixaria de ter efeito.
 *
 *     diffSpec        o que a pessoa mudou ao editar o JSON final
 *     userChoicesOf   o que ela já tinha decidido em uma geração passada
 */

import type { FinalResolvedSpec, SpecOverrides, SpecSource } from "./types";

/**
 * Origens que sobrevivem a reabrir uma geração do histórico.
 *
 * `explicit_prompt` fica de fora, e a ausência é a parte pensada: o que estava
 * escrito na descrição volta junto com a descrição, e reenviá-lo como correção
 * manual o tornaria mais forte do que era. Quem reabrisse "tree 32x32" e
 * digitasse 64x64 continuaria recebendo 32×32 — o número da frase perderia
 * para um fantasma da geração anterior.
 */
const RESTORABLE_SOURCES: readonly SpecSource[] = ["manual_override", "ui_selection"];

function chosen(resolved: FinalResolvedSpec, field: string): boolean {
  const source = resolved.sources[field];
  // Campo ausente do mapa é campo que ninguém decidiu — o backend só registra
  // origem para o que resolveu.
  return source !== undefined && RESTORABLE_SOURCES.includes(source);
}

/**
 * O que mudou entre o spec resolvido e o que a pessoa editou.
 *
 * `null` significa "nada mudou" e desfaz a correção. Só valores presentes
 * viram override: a correção manual **acrescenta** uma decisão, e não existe
 * "decidir que ninguém decidiu" — apagar um campo no JSON é voltar ao
 * automático dele, que é o que omitir já faz.
 */
export function diffSpec(
  original: FinalResolvedSpec,
  edited: Record<string, unknown>,
): SpecOverrides | null {
  const spec = edited as unknown as FinalResolvedSpec;
  const overrides: SpecOverrides = {};

  const asset = spec.asset ?? ({} as FinalResolvedSpec["asset"]);
  if (asset.type && asset.type !== original.asset.type) overrides.asset_type = asset.type;
  if (typeof asset.subject === "string" && asset.subject !== original.asset.subject) {
    overrides.subject = asset.subject;
  }
  if (asset.category && asset.category !== original.asset.category) {
    overrides.category = asset.category;
  }
  if (asset.mode && asset.mode !== original.asset.mode) overrides.mode = asset.mode;

  const logical = spec.logical_resolution;
  const originalLogical = original.logical_resolution;
  if (
    logical &&
    (logical.width !== originalLogical?.width || logical.height !== originalLogical?.height)
  ) {
    // Os dois lados andam juntos: mandar só um produziria uma proporção que
    // ninguém pediu, e o backend recusa exatamente esse caso.
    overrides.logical_width = logical.width;
    overrides.logical_height = logical.height;
  }

  const render = spec.render_resolution;
  if (
    render &&
    (render.width !== original.render_resolution.width ||
      render.height !== original.render_resolution.height)
  ) {
    overrides.render_width = render.width;
    overrides.render_height = render.height;
  }

  const colors = spec.palette?.max_colors ?? null;
  if (colors !== null && colors !== (original.palette?.max_colors ?? null)) {
    overrides.palette_max_colors = colors;
  }

  if (spec.background?.mode && spec.background.mode !== original.background.mode) {
    overrides.background = spec.background.mode;
  }

  const view = spec.composition?.view ?? null;
  if (view && view !== original.composition.view) overrides.view = view;

  const variations = spec.generation?.variations;
  if (variations && variations !== original.generation.variations) {
    overrides.variations = variations;
  }

  // O motor também se corrige por aqui (plano de motores §5). Editar o id no
  // JSON é seleção manual — o nível mais alto da precedência —, e por isso o
  // modo vai junto: sem ele, o backend receberia um id em modo `auto` e leria
  // como preferência, que é outra coisa.
  const engine = spec.engine;
  if (engine && engine.engine_id !== original.engine.engine_id) {
    overrides.engine_id = engine.engine_id;
    overrides.engine_mode = engine.engine_id ? "manual" : "auto";
  } else if (
    engine &&
    engine.selection_mode &&
    engine.selection_mode !== original.engine.selection_mode
  ) {
    overrides.engine_mode = engine.selection_mode;
    if (engine.selection_mode === "manual") overrides.engine_id = engine.engine_id;
  }

  return Object.keys(overrides).length > 0 ? overrides : null;
}

/**
 * As decisões de quem pediu, extraídas de um spec já resolvido.
 *
 * Serve a reabrir uma geração do histórico exatamente como ela foi feita.
 * Recriar o spec inteiro seria mais simples e erraria: os valores que vieram
 * do profile voltariam como se tivessem sido escolhidos, e trocar de estilo
 * depois não mudaria mais nada. É o campo `sources` que permite separar as
 * duas coisas — foi para isto que ele existe.
 */
export function userChoicesOf(resolved: FinalResolvedSpec): SpecOverrides | null {
  const overrides: SpecOverrides = {};

  if (chosen(resolved, "asset.type")) overrides.asset_type = resolved.asset.type;
  if (chosen(resolved, "asset.category") && resolved.asset.category) {
    overrides.category = resolved.asset.category;
  }
  if (chosen(resolved, "asset.mode")) overrides.mode = resolved.asset.mode;
  if (chosen(resolved, "logical_resolution") && resolved.logical_resolution) {
    overrides.logical_width = resolved.logical_resolution.width;
    overrides.logical_height = resolved.logical_resolution.height;
  }
  if (chosen(resolved, "palette") && resolved.palette?.max_colors) {
    overrides.palette_max_colors = resolved.palette.max_colors;
  }
  if (chosen(resolved, "background")) overrides.background = resolved.background.mode;
  if (chosen(resolved, "composition.view") && resolved.composition.view) {
    overrides.view = resolved.composition.view;
  }

  // `asset.subject` fica de fora de propósito: ele é sempre `explicit_prompt`
  // (é a frase da pessoa) e reenviá-lo travaria o sujeito, fazendo com que
  // editar a descrição na volta não tivesse efeito nenhum.

  // O motor também fica de fora, por outro motivo: quem o restaura é o
  // seletor da tela, que já reabre no motor da geração antiga. Devolvê-lo
  // aqui *também* mandaria a mesma decisão por dois caminhos — e o de cima,
  // sendo correção manual, sobreviveria a trocar o seletor para Automático.

  return Object.keys(overrides).length > 0 ? overrides : null;
}
