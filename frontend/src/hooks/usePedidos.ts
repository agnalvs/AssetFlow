/**
 * A fila de pedidos na tela (Fase B do plano do app).
 *
 * Os pedidos vêm da API (`/api/pedidos`), que os lê de um SQLite que o
 * servidor MCP também escreve: quando o Claude desenha um pedido pela
 * conversa, a próxima leitura já o traz pronto. Por isso a lista sobrevive a
 * recarregar a página.
 *
 * A atualização é por consulta: a cada 2 s enquanto houver pedido ativo (na
 * fila, na vez do Claude, sendo desenhado, corrigido ou olhado). Sem nenhum ativo, a
 * consulta para — não há o que mudar — e volta quando a tela cria, cancela ou
 * devolve um pedido, ou quando a janela volta a ter foco.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  GenerationApiError,
  cancelarPedido,
  criarPedido,
  devolverPedido,
  listarPedidos,
} from "../services/generationApi";
import type { Pedido, PedidoCorpo, PedidoDetalhe, PedidoEtapa } from "../types";

const INTERVALO_MS = 2000;

const ATIVAS: ReadonlySet<PedidoEtapa> = new Set([
  "na_fila",
  "na_vez",
  "desenhando",
  "corrigindo",
  "olhando",
  "conceituando",
]);

export function pedidoAtivo(pedido: Pedido): boolean {
  return ATIVAS.has(pedido.etapa);
}

export interface UsePedidos {
  pedidos: Pedido[];
  /** A lista não pôde ser lida (a mensagem do backend, quando é para ler). */
  erro: string | null;
  carregado: boolean;
  /** Cria o pedido; em erro, lança `GenerationApiError` com a frase pronta. */
  criar: (corpo: PedidoCorpo) => Promise<PedidoDetalhe>;
  cancelar: (id: string) => Promise<void>;
  devolver: (id: string) => Promise<void>;
  atualizar: () => void;
}

export function usePedidos(): UsePedidos {
  const [pedidos, setPedidos] = useState<Pedido[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [carregado, setCarregado] = useState(false);
  const [rodada, setRodada] = useState(0);
  const timer = useRef<number | null>(null);

  const atualizar = useCallback(() => setRodada((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    let vivo = true;

    listarPedidos(controller.signal)
      .then((lista) => {
        if (!vivo) return;
        setPedidos(lista.items);
        setErro(null);
        setCarregado(true);
        if (lista.items.some(pedidoAtivo)) {
          timer.current = window.setTimeout(atualizar, INTERVALO_MS);
        }
      })
      .catch((caught: unknown) => {
        if (!vivo) return;
        if (caught instanceof GenerationApiError && caught.code === "aborted") return;
        setErro(caught instanceof Error ? caught.message : "A fila de pedidos não respondeu.");
        setCarregado(true);
        // Tenta de novo, mais devagar: a fila pode estar só ocupada.
        timer.current = window.setTimeout(atualizar, INTERVALO_MS * 3);
      });

    return () => {
      vivo = false;
      controller.abort();
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, [rodada, atualizar]);

  useEffect(() => {
    window.addEventListener("focus", atualizar);
    return () => window.removeEventListener("focus", atualizar);
  }, [atualizar]);

  const criar = useCallback(
    async (corpo: PedidoCorpo) => {
      const criado = await criarPedido(corpo);
      atualizar();
      return criado;
    },
    [atualizar],
  );

  const cancelar = useCallback(
    async (id: string) => {
      try {
        await cancelarPedido(id);
      } finally {
        // Se ele terminou no meio do caminho (409), a lista mostra como ficou.
        atualizar();
      }
    },
    [atualizar],
  );

  const devolver = useCallback(
    async (id: string) => {
      try {
        await devolverPedido(id);
      } finally {
        atualizar();
      }
    },
    [atualizar],
  );

  return { pedidos, erro, carregado, criar, cancelar, devolver, atualizar };
}
