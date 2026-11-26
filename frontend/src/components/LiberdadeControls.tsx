import type { Liberdade, ModoConceito } from "../types";

interface LiberdadeControlsProps {
  liberdade: Liberdade;
  direcao: string;
  disabled: boolean;
  onLiberdade: (value: Liberdade) => void;
  onDirecao: (value: string) => void;
  modoConceito: ModoConceito;
  onModoConceito: (value: ModoConceito) => void;
}

const MODOS: readonly { id: ModoConceito; rotulo: string; frase: string }[] = [
  { id: "eu_escolho", rotulo: "Eu escolho", frase: "O Claude propõe três conceitos; você escolhe na fila." },
  {
    id: "claude_escolhe",
    rotulo: "O Claude escolhe",
    frase: "Ele propõe três, escolhe o mais forte e desenha; você vê os três.",
  },
  { id: "sem_conceito", rotulo: "Sem conceito", frase: "Direto ao desenho, para itens simples." },
];

const OPCOES: readonly { id: Liberdade; rotulo: string; frase: string }[] = [
  { id: "fiel", rotulo: "Fiel", frase: "Segue as medidas e as paletas da base." },
  {
    id: "equilibrado",
    rotulo: "Equilibrado",
    frase: "A base como ponto de partida; desvia quando o pedido pedir.",
  },
  {
    id: "ousado",
    rotulo: "Ousado",
    frase: "Só grade, cores e fundo são fixos; proporção, pose e ideia livres.",
  },
];

/**
 * Liberdade criativa e direção de arte (Fase B do plano do app).
 *
 * Os dois vão para o Claude, não para o spec: grade, cores, fundo e a
 * validação são os mesmos nas três posições. Por isso nenhum deles muda o
 * painel "O que o AssetFlow entendeu".
 */
export function LiberdadeControls({
  liberdade,
  direcao,
  disabled,
  onLiberdade,
  onDirecao,
  modoConceito,
  onModoConceito,
}: LiberdadeControlsProps) {
  return (
    <fieldset className="liberdade" disabled={disabled}>
      <legend className="liberdade__titulo">Liberdade criativa</legend>
      <div className="liberdade__opcoes" role="radiogroup" aria-label="Liberdade criativa">
        {OPCOES.map((opcao) => (
          <label
            key={opcao.id}
            className={`liberdade__opcao${liberdade === opcao.id ? " liberdade__opcao--ativa" : ""}`}
          >
            <input
              type="radio"
              name="liberdade"
              value={opcao.id}
              checked={liberdade === opcao.id}
              onChange={() => onLiberdade(opcao.id)}
            />
            <span className="liberdade__rotulo">{opcao.rotulo}</span>
            <span className="liberdade__frase">{opcao.frase}</span>
          </label>
        ))}
      </div>
      <div className="liberdade__opcoes" role="radiogroup" aria-label="Conceito antes do desenho">
        {MODOS.map((modo) => (
          <label
            key={modo.id}
            className={`liberdade__opcao${modoConceito === modo.id ? " liberdade__opcao--ativa" : ""}`}
          >
            <input
              type="radio"
              name="modo_conceito"
              value={modo.id}
              checked={modoConceito === modo.id}
              onChange={() => onModoConceito(modo.id)}
            />
            <span className="liberdade__rotulo">{modo.rotulo}</span>
            <span className="liberdade__frase">{modo.frase}</span>
          </label>
        ))}
      </div>
      <label className="liberdade__direcao">
        <span className="liberdade__titulo">Direção de arte (opcional)</span>
        <textarea
          className="liberdade__texto"
          value={direcao}
          maxLength={2000}
          rows={2}
          placeholder="Ex.: silhueta angulosa, como xilogravura; poucas cores quentes."
          onChange={(event) => onDirecao(event.target.value)}
        />
      </label>
    </fieldset>
  );
}
