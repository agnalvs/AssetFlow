"""``python -m assetflow.referencias``: importar, medir, listar e calibrar.

    importar <zip|pasta> --pacote ID --fonte URL --autor NOME --licenca SPDX
             --licenca-url URL [--licenca-verificada-em AAAA-MM-DD]
             (--parte PADRAO:TIPO[:CORPO][:QUADRO] ... | --tipo TIPO [--corpo C] [--quadro LxA])
             [--excluir PADRAO ...]
             [--nome NOME] [--obs TEXTO] [--substituir]
    medir [PACOTE ...]
    listar
    calibrar

Pacotes ficam em ``data/referencias/``; quais estão ativos é
``config/pixel_knowledge/referencias.yaml``. Nada é baixado da internet.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ..pixel_knowledge import BaseDeConhecimento
from ..settings import load_settings
from .calibracao import gerar_relatorio
from .colecao import ReferenciasAtivas
from .importador import importar, medir_pacote
from .pacote import (
    Parte,
    ReferenciaInvalida,
    ler_configuracao,
    ler_manifesto,
    ler_quadro,
)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    argumentos = _parser().parse_args(argv)
    settings = load_settings()
    raiz = settings.referencias_dir
    try:
        return argumentos.acao(argumentos, raiz, settings)
    except ReferenciaInvalida as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2


def _importar(a: argparse.Namespace, raiz: Path, _settings) -> int:
    if a.parte:
        partes = tuple(Parte.de_texto(texto) for texto in a.parte)
    elif a.tipo:
        quadro = ler_quadro(a.quadro, "--quadro")
        partes = (Parte(padrao="**", tipo=a.tipo, corpo=a.corpo, quadro=quadro),)
    else:
        raise ReferenciaInvalida("informe --parte (uma ou mais) ou --tipo para o pacote inteiro")
    relatorio = importar(
        Path(a.origem),
        raiz,
        pacote=a.pacote,
        excluir=tuple(a.excluir or ()),
        nome=a.nome or "",
        fonte=a.fonte,
        autor=a.autor,
        licenca=a.licenca,
        licenca_url=a.licenca_url,
        verificada_em=a.licenca_verificada_em,
        partes=partes,
        observacoes=a.obs or "",
        substituir=a.substituir,
    )
    manifesto = ler_manifesto(raiz / a.pacote)
    print(f"pacote '{a.pacote}' importado em {raiz / a.pacote}")
    print(f"  licença {manifesto.license_id} (verificada em {manifesto.license_verified_at}) "
          f"-> coleção {manifesto.colecao}"
          + (" · attribution_required" if manifesto.attribution_required else ""))
    print(f"  {relatorio.copiados} PNG e {relatorio.textos} texto(s) de licença copiados")
    if relatorio.excluidos:
        print(f"  excluídos por --excluir: {relatorio.excluidos} PNG")
    if relatorio.ignorados:
        print("  ignorados: " + ", ".join(f"{n} {ext}" for ext, n in relatorio.ignorados.most_common()))
    if relatorio.recusados:
        print(f"  RECUSADOS por caminho inseguro: {len(relatorio.recusados)}")
    m = relatorio.medicao
    print(f"  medidos: {m['quadros']} quadros únicos ({m['repetidos']} repetidos), "
          f"{m['animacoes']} animações, por tipo {m['por_tipo']}")
    print("  para usar como referência, acrescente o id em config/pixel_knowledge/referencias.yaml")
    return 0


def _medir(a: argparse.Namespace, raiz: Path, _settings) -> int:
    pacotes = a.pacotes
    if not pacotes and raiz.is_dir():
        pacotes = sorted(p.name for p in raiz.iterdir() if (p / "manifesto.yaml").is_file())
    for pacote in pacotes:
        m = medir_pacote(raiz / pacote)
        print(f"{pacote}: {m['quadros']} quadros, {m['repetidos']} repetidos, {m['animacoes']} animações")
    return 0


def _listar(_a: argparse.Namespace, raiz: Path, settings) -> int:
    config = ler_configuracao(settings.referencias_config)
    ativos = {ativo.pacote: ativo for ativo in config.ativos}
    pastas = sorted(p for p in raiz.iterdir() if p.is_dir()) if raiz.is_dir() else []
    if not pastas:
        print(f"nenhum pacote em {raiz}")
    for pasta in pastas:
        try:
            m = ler_manifesto(pasta)
        except ReferenciaInvalida as exc:
            print(f"{pasta.name}: manifesto inválido ({exc})")
            continue
        ativo = ativos.get(m.id)
        if ativo is None:
            estado = "inativo"
        elif m.attribution_required and not ativo.aceitar_atribuicao:
            estado = "ATIVO, mas fora: falta aceitar_atribuicao"
        else:
            estado = "ativo"
        print(f"{m.id}: {m.license_id} ({m.colecao}) · {estado} · {m.autor} · {m.source_url}")
    colecao = ReferenciasAtivas.carregar(raiz, settings.referencias_config)
    print(f"\nem uso: {len(colecao.pacotes)} pacote(s), {len(colecao.quadros)} quadros")
    for aviso in colecao.avisos:
        print(f"aviso: {aviso}")
    return 0


def _calibrar(_a: argparse.Namespace, raiz: Path, settings) -> int:
    base = BaseDeConhecimento.do_diretorio(settings.pixel_knowledge_dir)
    colecao = ReferenciasAtivas.carregar(raiz, settings.referencias_config)
    texto = gerar_relatorio(base, colecao)
    raiz.mkdir(parents=True, exist_ok=True)
    destino = raiz / "calibracao.md"
    destino.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"(gravado em {destino}; nenhum YAML foi alterado)")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m assetflow.referencias", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("importar", help="importa um zip ou pasta baixado à mão, e mede")
    p.add_argument("origem")
    p.add_argument("--pacote", required=True, help="id em minúsculas e hífen, como ninja-adventure")
    p.add_argument("--fonte", required=True, help="a página de onde veio (source_url)")
    p.add_argument("--autor", required=True)
    p.add_argument("--licenca", required=True, help="identificador SPDX: CC0-1.0, CC-BY-4.0…")
    p.add_argument("--licenca-url", required=True)
    p.add_argument("--licenca-verificada-em", help="AAAA-MM-DD; padrão: hoje")
    p.add_argument("--parte", action="append", help="PADRAO:TIPO[:CORPO][:QUADRO], repetível")
    p.add_argument("--excluir", action="append",
                   help="PADRAO de arquivo que não entra em parte nenhuma, repetível")
    p.add_argument("--tipo", help="tipo do pacote inteiro, se não houver --parte")
    p.add_argument("--corpo")
    p.add_argument("--quadro", help="LxA das folhas, se não houver --parte")
    p.add_argument("--nome")
    p.add_argument("--obs")
    p.add_argument("--substituir", action="store_true")
    p.set_defaults(acao=_importar)

    p = sub.add_parser("medir", help="refaz medidas.json")
    p.add_argument("pacotes", nargs="*")
    p.set_defaults(acao=_medir)

    p = sub.add_parser("listar", help="pacotes, licença e o que está ativo")
    p.set_defaults(acao=_listar)

    p = sub.add_parser("calibrar", help="compara com os números a_calibrar e propõe ajustes")
    p.set_defaults(acao=_calibrar)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
