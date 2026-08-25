/**
 * Carrega o catálogo de motores do backend (plano de motores §6).
 *
 * O catálogo depende da **capacidade**: Pixel Art e 2D convencional não são
 * atendidos pelos mesmos motores, e oferecer um motor que o backend vai
 * recusar é pior do que não oferecer nenhum. Por isso o hook recarrega quando
 * o modo muda.
 *
 * Ele também é o dono de uma decisão pequena e importante: quando a pessoa
 * troca de modo e o motor escolhido não existe mais na lista nova, a escolha
 * volta para **Automático** em vez de ficar apontando para um motor
 * indisponível. Um seletor que mostra um motor que não pode ser usado é uma
 * promessa que a geração vai quebrar.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { GenerationApiError, listEngineCatalog } from "../services/generationApi";
import type { EngineCatalogEntry } from "../types";

export interface UseEngineCatalog {
  engines: EngineCatalogEntry[];
  loading: boolean;
  /** `true` quando o backend respondeu, mas nenhum motor está disponível. */
  empty: boolean;
  error: string | null;
  /** Procura pelo id — usado para descrever o motor de um resultado. */
  find: (engineId: string | null | undefined) => EngineCatalogEntry | null;
  /** O nome de exibição, com o id como último recurso. */
  nameOf: (engineId: string | null | undefined) => string;
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
        setError("Não foi possível carregar a lista de motores.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [capability]);

  const byId = useMemo(() => {
    const map = new Map<string, EngineCatalogEntry>();
    for (const engine of engines) map.set(engine.engine_id, engine);
    return map;
  }, [engines]);

  const find = useCallback(
    (engineId: string | null | undefined) =>
      engineId ? byId.get(engineId) ?? null : null,
    [byId],
  );

  const nameOf = useCallback(
    (engineId: string | null | undefined) => {
      if (!engineId) return "Automático";
      // O id como fallback não é preguiça: um motor pode ter saído do
      // catálogo desde que o job rodou (desabilitado, removido), e mostrar o
      // id é mais honesto do que mostrar "desconhecido".
      return byId.get(engineId)?.display_name ?? engineId;
    },
    [byId],
  );

  return {
    engines,
    loading,
    empty: !loading && error === null && engines.length === 0,
    error,
    find,
    nameOf,
  };
}
