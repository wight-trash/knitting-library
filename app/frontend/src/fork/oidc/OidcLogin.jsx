// The sign-in screen while signing in with Keycloak is on (FORK.md). Falls back to upstream's LoginPage when it is off.
import React, { useState } from 'react';
import AppBrand from '../../components/AppBrand';
import LoginPage from '../../pages/LoginPage';
import '../../pages/LoginPage.css';
import { ft } from '../strings';
import useOidcConfig from './useOidcConfig';

function takeError() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('oidc_error');
  if (!code) return '';
  params.delete('oidc_error');
  const rest = params.toString();
  window.history.replaceState(null, '', window.location.pathname + (rest ? `?${rest}` : '') + window.location.hash);
  return ft(`oidcError_${code}`) === `oidcError_${code}` ? ft('oidcError_failed') : ft(`oidcError_${code}`);
}

export default function OidcLogin() {
  const cfg = useOidcConfig();
  const [error] = useState(takeError);
  const [going, setGoing] = useState(false);

  if (!cfg) return null;  // a moment, so the password form never flashes up
  if (!cfg.enabled) return <LoginPage />;

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <AppBrand variant="login" />
        </div>
        <p className="login-subtitle">{ft('oidcSubtitle')}</p>
        <div className="login-form">
          {error && <p className="login-error">{error}</p>}
          <a
            className="login-btn"
            href="/api/auth/oidc/start"
            onClick={() => setGoing(true)}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', textDecoration: 'none' }}
            aria-busy={going}
          >
            {going ? ft('oidcSigningIn') : cfg.label}
          </a>
        </div>
      </div>
    </div>
  );
}
