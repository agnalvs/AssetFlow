# Lote 9 — cópia de segurança

> Nono lote da sessão (pedido da autora em 2026-11-26; SUGESTOES_DE_MELHORIA
> §16). Proposta seguida sem consulta; decisões e dúvidas também no
> [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md). Código: `assetflow/backup/`.

## 1. O que entrou

```bash
python -m assetflow.backup criar                 # grava o zip datado
python -m assetflow.backup listar                # as cópias da pasta
python -m assetflow.backup restaurar <zip>       # ensaio: confere e diz o que voltaria
python -m assetflow.backup restaurar <zip> --sim # restaura (feche a API e o MCP antes)
```

Na tela, no rodapé: **"Fazer cópia de segurança"**, com a data da última
cópia e a pasta. Rotas: `GET /api/backup` (a lista) e `POST /api/backup`
(grava uma). Restaurar fica só no comando: exige a API fechada.

**O zip** (`assetflow-dados-AAAAMMDD-HHMMSS.zip`) vai para
`~/AssetFlow-copias` (`ASSETFLOW_BACKUP_DIR`), **sempre fora do
repositório** — uma pasta dentro dele é recusada. Leva:

| No zip | O que é |
|---|---|
| `assets/` | os PNG e os relatórios de cada job |
| `history/` | o histórico de gerações (a receita de cada asset) |
| `pedidos/pedidos.sqlite3` | a fila |
| `aprendizado/aprendizado.sqlite3` | lições, opiniões, exemplos mostrados |
| `banca/banca.sqlite3` | rodadas e votos (quando existe) |
| `referencias/` | os pacotes importados à mão (`ASSETFLOW_BACKUP_REFERENCIAS=0` tira) |
| `copia.json` | data, commit, e tamanho e sha256 de cada arquivo |

Ficam de fora `cache/` e `engines/` (modelos da era da difusão, 2,6 GB e
14 GB nesta máquina), os logs e os relatórios de diagnóstico, que se refazem.

**Os bancos, de forma consistente.** Um SQLite em WAL é três arquivos: o
banco, o `-wal` (o que foi gravado e ainda não voltou para o banco) e o `-shm`
(um índice do `-wal`). Copiar os três soltos enquanto a API ou o MCP escrevem
pode pegar um deles no meio de uma gravação. Por isso cada banco sai pela cópia
do próprio SQLite (`Connection.backup`): um arquivo só, de um instante só, que
**já traz o conteúdo do `-wal`**. O `-shm` não guarda dado; o SQLite o refaz
ao abrir. O teste grava pedidos que ainda estão no `-wal` e confere que a cópia
os tem.

**Restaurar** confere o sha256 de cada arquivo, recusa se algum banco estiver
em uso (tenta a trava exclusiva) e **não apaga nada**: o que havia vai para
`data/antes-da-restauracao-<data>/`, inclusive o `-wal` e o `-shm` antigos.

Na máquina da autora, em 2026-11-26: 2.827 arquivos, 20,7 MB; os 8 pedidos e
as 3 lições da cópia conferiram com os bancos ao vivo.

## 2. Interruptor

`ASSETFLOW_BACKUP` (`settings.backup.ligado`, ligado): desligado, o botão some
e as rotas recusam; o comando continua valendo.

## 3. Decisões tomadas sem consulta

1. **O `-wal` e o `-shm` não vão soltos**: a cópia do SQLite os incorpora, que
   é o jeito consistente de levar os três. Levá-los como arquivos exigiria
   parar quem escreve.
2. **Pasta padrão no perfil do usuário** (`~/AssetFlow-copias`), não ao lado do
   projeto: assim a cópia sobrevive mesmo se a pasta do projeto se perder.
3. **Restaurar só pelo comando**, com ensaio por padrão e `--sim` para valer.
4. **Referências entram por padrão** (13 MB): reimportá-las dá trabalho à mão.

## 4. Dúvidas para a autora

1. **Cópia automática** (todo dia, ou antes de cada lote) não entrou; dá para
   somar um agendamento do Windows chamando o comando.
2. **Cópias antigas não são apagadas**: cada uma tem ~21 MB; uma limpeza das
   mais velhas pode entrar quando incomodar.
