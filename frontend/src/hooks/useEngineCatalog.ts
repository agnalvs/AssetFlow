/**
 * Carrega os motores oferecíveis (plano de motores §6, plano Optimizer §26).
 *
 * Este hook substituiu o `useCreationCatalog`, que carregava três listas —
 * métodos de criação, motores e agentes — porque a tela precisava das três
 * para decidir qual seletor mostrar. Não precisa mais: existe uma pergunta de
 * tecnologia, e é "qual motor?" (§25). O que vinha depois do motor —
 * a otimização pixel a pixel — não é escolha de ninguém, é o pipeline (§46).
 *
 * O catálogo depende da **capacidade** — Pixel Art e 2D convencional não são
 * atendidos pelos mesmos motores —, então ele recarrega quando o modo muda. E
 * o hook é o dono de uma decisão pequena e importante: quando o motor
 * escolhido deixa de existir na lista nova, ele volta para **Automático** em
 * vez de apontar para algo indisponível. Um seletor que mostra o que não pode
 * ser usado é uma promessa que a geração vai quebrar.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { GenerationApiError, listEngineCatalog } from "../services/generationApi";
import type { CreationSelection, EngineCatalogEntry } from "../types";
import { AUTO_CREATION } from "../types";

export interface UseEngineCatalog {
  engines: EngineCatalogEntry[];
  loading: boolean;
  error: string | null;
  /** Nome de exibição de um motor, com o id como último recurso. */
  engineNameOf: (engineId: string | null | undefined) => string;
  /** A escolha, corrigida para o que o catálogo atual comporta. */
  reconcile: (selection: CreationSelection) => CreationSelection;
}

export function useEngineCatalog(capability: string): UseEngineCatalog {
  const [engines, setEngines] = useState<EngineCatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setLoading(true);
    listEngineCatalog(capability, controller.signal)
      .then((response) => {
        if (!active) return;
        setEngines(response.items);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!active) return;
        // Requisição abortada é operação normal aqui: trocar de modo cancela
        // a busca anterior. Só o resto vira erro na tela.
        if (caught instanceof GenerationApiError && caught.code === "aborted") return;
        setEngines([]);
        setError("Não foi possível carregar os motores disponíveis.");
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
    for (const engine of engines) map.set(engine.engine_id, engine);
    return map;
  }, [engines]);

  const engineNameOf = useCallback(
    (engineId: string | null | undefined) => {
      if (!engineId) return "Automático";
      // O id como último recurso não é preguiça: um motor pode ter saído do
      // catálogo desde que o job rodou, e mostrar o id é mais honesto do que
      // mostrar "desconhecido".
      return enginesById.get(engineId)?.display_name ?? engineId;
    },
    [enginesById],
  );

  const reconcile = useCallback(
    (selection: CreationSelection): CreationSelection => {
      if (loading || engines.length === 0) return selection;
      if (selection.engineId === null) return selection;
      const engine = enginesById.get(selection.engineId);
      if (!engine || !engine.available) return AUTO_CREATION;
      return selection;
    },
    [engines.length, enginesById, loading],
  );

  return { engines, loading, error, engineNameOf, reconcile };
}
