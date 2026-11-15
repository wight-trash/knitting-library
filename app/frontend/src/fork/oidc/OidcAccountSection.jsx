// Settings, Account, while signing in with Keycloak is on (FORK.md). Upstream's password and two-step sign-in
// forms are replaced by a link to the Keycloak account page; admins also see which accounts are linked.
import React, { useEffect, useState } from 'react';
import { ExternalLink, LogOut } from 'lucide-react';
import { useApp } from '../../utils/AppContext';
import { getOidcLinks } from '../forkApi';
import { ft } from '../strings';
import useOidcConfig from './useOidcConfig';

function LinkedAccounts() {
  const [links, setLinks] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { getOidcLinks().then(setLinks).catch((e) => setError(e.message)); }, []);

  return (
    <>
      <h4 className="subsection-heading" style={{ marginTop: '2rem' }}>{ft('oidcLinksTitle')}</h4>
      <p className="settings-row-sub" style={{ margin: '0 0 12px' }}>{ft('oidcLinksText')}</p>
      {error && <p className="status-error">{error}</p>}
      {links && links.length === 0 && <p className="settings-row-sub">{ft('oidcLinksNone')}</p>}
      {links && links.length > 0 && (
        <table className="fork-oidc-links" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
          <thead>
            <tr style={{ textAlign: 'left' }}>
              <th>{ft('oidcLinksLibrary')}</th><th>{ft('oidcLinksKeycloak')}</th><th>{ft('oidcLinksLast')}</th>
            </tr>
          </thead>
          <tbody>
            {links.map((l) => (
              <tr key={l.keycloak_user_id}>
                <td>{l.library_username}{!l.exists && <span className="status-error"> ({ft('oidcLinksMissing')})</span>}</td>
                <td><code style={{ fontSize: '0.8rem', wordBreak: 'break-all' }}>{l.keycloak_user_id}</code></td>
                <td>{l.last_login ? new Date(`${l.last_login}Z`).toLocaleString() : ft('oidcLinksNever')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

export default function OidcAccountSection({ fallback }) {
  const cfg = useOidcConfig();
  const { user, t, logout } = useApp();
  if (!cfg) return null;
  if (!cfg.enabled) return fallback;

  return (
    <div className="settings-section">
      <h3 className="section-heading">{t('account')}</h3>
      <div className="user-badge">
        <div className="user-badge-avatar">{user?.username?.[0]?.toUpperCase()}</div>
        <div>
          <p className="user-badge-name">{user?.username}</p>
          <p className="user-badge-role">{user?.is_admin ? t('admin') : t('member')}</p>
        </div>
      </div>

      <h4 className="subsection-heading">{ft('oidcAccountTitle')}</h4>
      <p className="settings-row-sub" style={{ margin: '0 0 12px' }}>{ft('oidcAccountText')}</p>
      <a className="btn-secondary" href={cfg.account_url} target="_blank" rel="noopener noreferrer"
         style={{ display: 'inline-flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}>
        <ExternalLink size={15} /> {ft('oidcAccountLink')}
      </a>

      {user?.is_admin && <LinkedAccounts />}

      <div style={{ marginTop: '2rem' }}>
        <button className="btn-logout" onClick={logout}><LogOut size={16} />{t('logout')}</button>
      </div>
    </div>
  );
}
