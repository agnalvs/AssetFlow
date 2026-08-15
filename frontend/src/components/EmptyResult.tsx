/** Estado inicial vazio (plano da tela §37): ensina o fluxo sem texto extra. */
export function EmptyResult() {
  return (
    <div className="empty">
      <span className="empty__icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" strokeWidth="1.4">
          <rect x="3" y="4" width="18" height="16" rx="3" />
          <circle cx="8.5" cy="9.5" r="1.6" />
          <path d="M4 17l5-5 4 4 3-2.5 4 3.5" />
        </svg>
      </span>
      <p className="empty__text">Sua criação aparecerá aqui</p>
    </div>
  );
}
