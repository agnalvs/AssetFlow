/**
 * Header mínimo (plano da tela §4).
 *
 * Login, créditos, biblioteca e configurações entram depois. Nesta etapa o
 * foco é um só: prompt → motor → imagem.
 */
export function Header() {
  return (
    <header className="header">
      <div className="header__brand">
        <span className="header__mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none">
            <rect x="3" y="3" width="8" height="8" rx="2" fill="currentColor" />
            <rect x="13" y="3" width="8" height="8" rx="2" opacity="0.55" fill="currentColor" />
            <rect x="3" y="13" width="8" height="8" rx="2" opacity="0.55" fill="currentColor" />
            <rect x="13" y="13" width="8" height="8" rx="2" opacity="0.25" fill="currentColor" />
          </svg>
        </span>
        <span className="header__name">AssetFlow</span>
      </div>
    </header>
  );
}
