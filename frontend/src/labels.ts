/**
 * Rótulos em português do contrato resolvido (plano T→J §17 e §45).
 *
 * O painel antigo mostrava JSON cru e mais nada. Funcionava para quem
 * escreveu o backend e para mais ninguém: `"asset_type": "prop"` não é uma
 * resposta para quem só quer saber se o AssetFlow entendeu que era uma
 * árvore.
 *
 * Este módulo é a tradução, e ele é **só** tradução: nenhum valor é
 * calculado, inferido ou corrigido aqui. Quando um termo novo aparecer no
 * backend sem entrada nesta tabela, a interface mostra o próprio termo — feio,
 * mas verdadeiro, que é a ordem de prioridade certa para um painel cuja razão
 * de existir é não mentir.
 */

import type { AssetTypeId, SpecSource } from "./types";

/** Tipos oferecidos no dropdown, na ordem em que aparecem (§18). */
export const ASSET_TYPE_OPTIONS: readonly AssetTypeId[] = [
  "character",
  "prop",
  "background",
  "tileset",
  "effect",
  "icon",
  "ui",
];

const ASSET_TYPES: Record<string, string> = {
  character: "Personagem",
  prop: "Prop / objeto",
  background: "Cenário",
  tile: "Tile",
  tileset: "Tileset",
  spritesheet: "Sprite sheet",
  icon: "Ícone",
  effect: "Efeito",
  ui: "Interface",
  raw: "Bruto",
};

const CATEGORIES: Record<string, string> = {
  vegetation: "Vegetação",
  mineral: "Mineral",
  container: "Recipiente",
  item: "Item",
  weapon: "Arma",
  furniture: "Mobília",
  structure: "Estrutura",
  decoration: "Decoração",
  vehicle: "Veículo",
  humanoid: "Humanoide",
  creature: "Criatura",
  mechanical: "Mecânico",
  nature: "Natureza",
  urban: "Urbano",
  interior: "Interior",
  ruins: "Ruínas",
  space: "Espaço",
  terrain: "Terreno",
  combat: "Combate",
  elemental: "Elemental",
  magic: "Magia",
  control: "Controle",
  display: "Exibição",
  inventory: "Inventário",
  emblem: "Emblema",
  symbol: "Símbolo",
};

const VIEWS: Record<string, string> = {
  front: "Frontal",
  side: "Lateral",
  back: "Traseira",
  top_down: "Top-down",
  isometric: "Isométrica",
  three_quarter: "3/4",
};

/**
 * A origem de um valor, dita como se diria em voz alta.
 *
 * "padrão do estilo" e "definido por você" são a mesma informação que
 * `profile_default` e `manual_override`, mas são a diferença entre o painel
 * responder à pergunta que a pessoa tem — "isso foi o que eu pedi?" — e
 * repetir o nome interno do campo.
 */
const SOURCES: Record<SpecSource, string> = {
  manual_override: "definido por você",
  explicit_prompt: "pedido na descrição",
  ui_selection: "escolhido nos controles",
  inference: "leitura do AssetFlow",
  profile_default: "padrão do estilo",
  global_default: "padrão do sistema",
};

/** Origens que representam uma decisão de quem pediu, e não um padrão. */
const USER_SOURCES: readonly SpecSource[] = [
  "manual_override",
  "explicit_prompt",
  "ui_selection",
];

/**
 * As vistas oferecidas para cada tipo de asset (plano T→J §19).
 *
 * A lista muda com o tipo porque a pergunta muda: um personagem é visto de
 * frente ou de lado; um prop de cenário também pode ser visto de cima ou em
 * isométrico, que é como ele encaixa no mapa. Um cenário não tem "vista" —
 * ele *é* a vista —, e por isso a entrada dele é vazia e o controle some.
 *
 * Oferecer a mesma lista para tudo pareceria mais simples e seria pior: o
 * campo passaria a aceitar combinações que o produto não sabe produzir.
 */
export const VIEW_OPTIONS: Record<string, readonly string[]> = {
  character: ["front", "side", "back", "three_quarter"],
  prop: ["front", "side", "top_down", "isometric", "three_quarter"],
  tile: ["top_down", "isometric"],
  tileset: ["top_down", "isometric"],
  icon: ["front"],
  ui: ["front"],
  effect: ["front", "side"],
  background: [],
};

export function viewOptionsFor(assetType: string): readonly string[] {
  return VIEW_OPTIONS[assetType] ?? [];
}

export function assetTypeLabel(value: string): string {
  return ASSET_TYPES[value] ?? value;
}

export function categoryLabel(value: string | null): string | null {
  if (!value) return null;
  return CATEGORIES[value] ?? value;
}

export function viewLabel(value: string | null): string | null {
  if (!value) return null;
  return VIEWS[value] ?? value;
}

export function sourceLabel(value: SpecSource | undefined): string {
  return value ? SOURCES[value] ?? value : SOURCES.global_default;
}

export function isUserChoice(value: SpecSource | undefined): boolean {
  return value !== undefined && USER_SOURCES.includes(value);
}

/** Primeira letra maiúscula, para exibir o sujeito escrito pela pessoa. */
export function capitalize(text: string): string {
  if (!text) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// ---------------------------------------------------------------------------
// Motores (plano de motores §4.2)
//
// Só rótulos: família, faixa de velocidade, faixa de qualidade e selos. Os
// **nomes** dos motores nunca aparecem aqui — eles vêm do catálogo servido
// pelo backend, e é isso que permite acrescentar uma gaveta sem tocar no
// frontend (§24).
// ---------------------------------------------------------------------------

const ENGINE_FAMILIES: Record<string, string> = {
  diffusion: "difusão",
  native_sprite: "sprites nativos",
  optimization: "otimização",
  agentic: "agente de desenho",
  procedural: "procedural",
};

const SPEED_TIERS: Record<string, string> = {
  instant: "instantâneo",
  fast: "rápido",
  moderate: "tempo médio",
  slow: "lento",
  very_slow: "muito lento",
};

const QUALITY_TIERS: Record<string, string> = {
  draft: "qualidade de rascunho",
  standard: "qualidade padrão",
  high: "alta qualidade",
  reference: "qualidade de referência",
};

const ENGINE_BADGES: Record<string, string> = {
  experimental: "experimental",
  lento: "lento",
  mvp: "primeira versão",
  especializado: "especializado",
  referência: "referência",
};

export function familyLabel(value: string): string {
  return ENGINE_FAMILIES[value] ?? value;
}

export function speedLabel(value: string): string {
  return SPEED_TIERS[value] ?? value;
}

export function qualityLabel(value: string): string {
  return QUALITY_TIERS[value] ?? value;
}

export function engineBadgeLabel(value: string): string {
  return ENGINE_BADGES[value] ?? value;
}

/** Modos de qualidade do agente (plano de correção §5 e §25). */
const AGENT_QUALITY: Record<string, string> = {
  auto: "Automático",
  fast: "Rápido",
  balanced: "Balanceado",
  detailed: "Detalhado",
};

export function qualityModeLabel(value: string): string {
  return AGENT_QUALITY[value] ?? value;
}
