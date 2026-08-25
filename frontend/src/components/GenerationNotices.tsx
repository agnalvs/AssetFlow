interface GenerationNoticesProps {
  warnings: readonly string[];
  /** O aviso de substituição de motor já é mostrado pelo `EngineCredit`. */
  fallbackUsed: boolean;
}

/**
 * O que o backend tem a dizer sobre esta geração.
 *
 * Este componente existe por causa de um caso concreto: alguém pediu uma casa
 * e recebeu uma forma genérica salpicada. O backend **sabia** o que tinha
 * acontecido — o agente de desenho não conhecia o objeto e caiu na receita
 * genérica — e dizia isso em `warnings`. Só que os avisos nunca chegavam à
 * tela, e o que a pessoa via era um sistema quebrado.
 *
 * A regra da interface continua sendo não exibir mensagem técnica crua (plano
 * da tela §40), e ela não é violada aqui: os avisos que o backend produz são
 * escritos em português, para serem lidos, e falam de limitação e de
 * consequência — "não sei desenhar isto", "este motor ignora a seed". O que
 * fica de fora é erro, que tem caminho próprio.
 */
export function GenerationNotices({
  warnings,
  fallbackUsed,
}: GenerationNoticesProps) {
  // A substituição de motor tem um aviso próprio, maior e com consequência
  // explicada. Repeti-la aqui seria dizer a mesma coisa duas vezes.
  const visible = warnings.filter(
    (warning) => !(fallbackUsed && warning.includes("fallback")),
  );
  if (visible.length === 0) return null;

  return (
    <ul className="result__notices" role="status">
      {visible.map((warning) => (
        <li key={warning} className="result__notice">
          <span aria-hidden="true">ⓘ</span> {warning}
        </li>
      ))}
    </ul>
  );
}
