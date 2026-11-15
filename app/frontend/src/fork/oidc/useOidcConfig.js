// Whether signing in with Keycloak is on (FORK.md "Signing in with Keycloak"). Asked once per page load.
import { useEffect, useState } from 'react';
import { getOidcConfig } from '../forkApi';

let cached = null;
let pending = null;

function load() {
  if (cached) return Promise.resolve(cached);
  if (!pending) {
    pending = getOidcConfig()
      .catch(() => ({ enabled: false }))  // an older server, or offline: fall back to upstream's screens
      .then((cfg) => { cached = cfg; return cfg; })
      .finally(() => { pending = null; });
  }
  return pending;
}

export default function useOidcConfig() {
  const [cfg, setCfg] = useState(cached);
  useEffect(() => {
    if (cached) return undefined;
    let alive = true;
    load().then((c) => { if (alive) setCfg(c); });
    return () => { alive = false; };
  }, []);
  return cfg;  // null until known; then {enabled, label?, account_url?}
}
