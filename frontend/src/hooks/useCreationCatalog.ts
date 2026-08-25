/**
 * Carrega os métodos de criação, motores e agentes (plano de correção §32).
 *
 * Uma chamada só para os três, porque a tela precisa dos três ao mesmo tempo:
 * o método decide qual dos outros dois seletores aparece.
 *
 * O catálogo depende da **capacidade** — Pixel Art e 2D convencional não são
 * atendidos pelos mesmos motores —, então ele recarrega quando o modo muda. E
 * o hook é o dono de uma decisão pequena e importante: quando a escolha atual
 * deixa de existir na lista nova, ela volta para **Automático** em vez de
 * apontar para algo indisponível. Um seletor que mostra o que não pode ser
 * usado é uma promessa que a geração vai quebrar.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { GenerationApiError, listStrategyCatalog } from "../services/generationApi";
import type {
  AgentSummary,
  CreationSelection,
  EngineCatalogEntry,
  GenerationStrategyId,
  StrategyDescriptor,
} from "../types";
import { AUTO_CREATION } from "../types";

export interface UseCreationCatalog {
  strategies: StrategyDescriptor[];
  engines: EngineCatalogEntry[];
  agents: AgentSummary[];
  qualityModes: string[];
  loading: boolean;
  error: string | null;
  /** O descritor de um método — usado para saber qual seletor mostrar. */
  strategyOf: (id: GenerationStrategyId) => StrategyDescriptor | null;
  /** Nome de exibição de um motor, com o id como último recurso. */
  engineNameOf: (engineId: string | null | undefined) => string;
  /** Nome de exibição de um agente. */
  agentNameOf: (agentId: string | null | undefined) => string;
  /** Nome de exibição de um método. */
  strategyNameOf: (id: string | null | undefined) => string;
  /** A escolha, corrigida para o que o catálogo atual comporta. */
  reconcile: (selection: CreationSelection) => CreationSelection;
}

export function useCreationCatalog(capability: string): UseCreationCatalog {
  const [catalog, setCatalog] = useState<{
    strategies: StrategyDescriptor[];
    engines: EngineCatalogEntry[];
    agents: AgentSummary[];
    qualityModes: string[];
  }>({ strategies: [], engines: [], agents: [], qualityModes: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setLoading(true);
    listStrategyCatalog(capability, controller.signal)
      .then((response) => {
        if (!active) return;
        setCatalog({
          strategies: response.items,
          engines: response.engines,
          agents: response.agents,
          qualityModes: response.quality_modes,
        });
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!active) return;
        // Requisição abortada é operação normal aqui: trocar de modo cancela
        // a busca anterior. Só o resto vira erro na tela.
        if (caught instanceof GenerationApiError && caught.code === "aborted") return;
        setCatalog({ strategies: [], engines: [], agents: [], qualityModes: [] });
        setError("Não foi possível carregar os métodos de criação.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [capability]);

  const enginesById = useMemo(() => {
    const map = new Map<string, EngineCatalogEntry>();
    for (const engine of catalog.engines) map.set(engine.engine_id, engine);
    return map;
  }, [catalog.engines]);

  const strategiesById = useMemo(() => {
    const map = new Map<string, StrategyDescriptor>();
    for (const strategy of catalog.strategies) map.set(strategy.id, strategy);
    return map;
  }, [catalog.strategies]);

  const strategyOf = useCallback(
    (id: GenerationStrategyId) => strategiesById.get(id) ?? null,
    [strategiesById],
  );

  const engineNameOf = useCallback(
    (engineId: string | null | undefined) => {
      if (!engineId) return "Automático";
      // O id como fallback não é preguiça: um motor pode ter saído do
      // catálogo desde que o job rodou, e mostrar o id é mais honesto do que
      // mostrar "desconhecido".
      return enginesById.get(engineId)?.display_name ?? engineId;
    },
    [enginesById],
  );

  const agentNameOf = useCallback(
    (agentId: string | null | undefined) => {
      if (!agentId) return "";
      return (
        catalog.agents.find((agent) => agent.id === agentId)?.display_name ?? agentId
      );
    },
    [catalog.agents],
  );

  const strategyNameOf = useCallback(
    (id: string | null | undefined) => {
      if (!id) return "";
      return strategiesById.get(id)?.display_name ?? id;
    },
    [strategiesById],
  );

  const reconcile = useCallback(
    (selection: CreationSelection): CreationSelection => {
      if (loading || catalog.strategies.length === 0) return selection;

      const strategy = strategiesById.get(selection.strategy);
      if (!strategy || !strategy.available) return AUTO_CREATION;

      // Motor que não atende mais este modo volta para "Automático" dentro do
      // método — e não derruba o método junto, que seria perder mais do que
      // a escolha inválida.
      if (
        selection.engineId !== null &&
        !enginesById.has(selection.engineId)
      ) {
        return { ...selection, engineId: null };
      }
      return selection;
    },
    [catalog.strategies.length, enginesById, loading, strategiesById],
  );

  return {
    strategies: catalog.strategies,
    engines: catalog.engines,
    agents: catalog.agents,
    qualityModes: catalog.qualityModes,
    loading,
    error,
    strategyOf,
    engineNameOf,
    agentNameOf,
    strategyNameOf,
    reconcile,
  };
}
