# Lote 10 — um clique para abrir

> Décimo lote da sessão (pedido da autora em 2026-11-26; SUGESTOES_DE_MELHORIA
> §14). Proposta seguida sem consulta; decisões e dúvidas também no
> [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md). Código: `iniciar.bat` (raiz) e
> `backend/scripts/iniciar.py`.

## 1. O que entrou

Dois cliques no **`iniciar.bat`** da raiz:

1. **A API.** Se já há uma API do AssetFlow na 8000 (o `/api/health` cita a
   `desenhista-v1`), ela é usada. Se a 8000 está ocupada por outro programa, a
   API sobe na próxima porta livre, e a tela é apontada para ela
   (`ASSETFLOW_API_URL`, que o `vite.config.ts` já lia).
2. **A tela.** Se já há uma tela do AssetFlow na 5173, ela é usada. Senão,
   sobe na 5173 ou, ocupada, na próxima livre — sempre com `--strictPort`,
   para o Vite não trocar de porta sozinho.
3. **Espera as duas responderem** e confere que o endereço é o AssetFlow: o
   título da página **e** o `/api/health` pelo proxy da tela. Uma porta com
   outro app nunca é aberta.
4. **Abre o navegador** no endereço certo e fica na janela; Ctrl+C (ou fechar a
   janela) encerra o que ele subiu, com os filhos (`taskkill /T`). A saída de
   cada parte vai para `backend/data/iniciar/api.log` e `tela.log`.

Sem a instalação (`backend/.venv` ou `frontend/node_modules`), ele diz o que
falta e aponta o SETUP.md.

**O caso do primeiro teste.** No Windows, `localhost` costuma ser o IPv6: a tela
da autora escutava só em `[::1]:5173`, e `127.0.0.1:5173` não respondia. O
lançador procura a API e a tela nos dois endereços, e abre
`http://localhost:5173/` quando a tela é a do IPv6.

**Conferido ao vivo** (2026-11-26): com a API e a tela da autora de pé, ele as
reaproveitou e abriu o endereço certo; num ensaio com portas de teste, a
"5173" ocupada por outro app, a tela subiu na seguinte, o proxy chegou à API
de teste, o outro app ficou intacto, e tudo foi encerrado no fim.

## 2. Interruptor

Nenhum: o lançador é opcional por natureza — subir a API e a tela à mão
(SETUP.md §5) continua igual.

## 3. Decisões tomadas sem consulta

1. **O `.bat` é fino** e chama um Python: porta, espera e conferência ficam
   testáveis (`tests/test_iniciar.py`).
2. **Reaproveita o que já está rodando**, em vez de subir uma segunda cópia.
3. **`--strictPort`** e porta escolhida pelo lançador: o endereço aberto é o
   que o Vite usa de fato.

## 4. Dúvidas para a autora

1. **O servidor MCP não sobe pelo lançador**: ele é aberto pelo Claude Code
   (stdio), não por um terminal.
2. **Um atalho na área de trabalho** com ícone não entrou; o `.bat` pode ser
   arrastado para lá.
