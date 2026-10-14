// Whether guided versions are switched on, asked once per page load and shared by every caller.
import { useEffect, useState } from 'react';
import { getGuidedStatus } from '../forkApi';

let cached = null;      // the answer, once we have it
let pending = null;     // the request in flight

function load() {
  if (cached) return Promise.resolve(cached);
  if (!pending) {
    pending = getGuidedStatus()
      .then((status) => { cached = status; return status; })
      .finally(() => { pending = null; });  // a failed request is asked again by the next caller
  }
  return pending;
}

export default function useGuidedStatus() {
  const [status, setStatus] = useState(cached);
  useEffect(() => {
    if (cached) return undefined;
    let alive = true;
    load().then((s) => { if (alive) setStatus(s); }).catch(() => {});
    return () => { alive = false; };
  }, []);
  return status;  // null until known; then {enabled, configured, model, can_change_settings}
}
