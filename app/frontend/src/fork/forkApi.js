// Fork-only API calls (see FORK.md). Its own small fetch wrapper, copied from utils/api.js so upstream files stay untouched.
const API_BASE = '/api';
function getToken() { return localStorage.getItem('knitting_token') || ''; }
function getCookie(name) {
  return document.cookie
    .split('; ')
    .find(row => row.startsWith(`${name}=`))
    ?.split('=')[1] || '';
}
function authHeaders() {
  const headers = {};
  const legacyToken = getToken();
  if (legacyToken) headers['X-Session-Token'] = legacyToken;
  const csrf = getCookie('knitting_csrf');
  if (csrf) headers['X-CSRF-Token'] = decodeURIComponent(csrf);
  return headers;
}
function fetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const auth = authHeaders();
  for (const [key, value] of Object.entries(auth)) {
    if (!headers[key]) headers[key] = value;
  }
  return window.fetch(url, { ...options, headers, credentials: 'include' });
}

// Requests give up after this long, so a request left hanging while the iPad slept never blocks the next one.
const TIMEOUT_MS = 12000;

async function request(path, { method = 'GET', signal, body } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const onAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', onAbort, { once: true });
  }
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      cache: 'no-store',
      signal: controller.signal,
      headers: method === 'GET' ? {} : { 'Content-Type': 'application/json' },
      body: method === 'GET' ? undefined : JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : '';
      const err = new Error(detail || `Request failed (${res.status})`);
      err.status = res.status;
      err.fromServer = Boolean(detail);
      throw err;
    }
    return data;
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', onAbort);
  }
}

export function getGuidedStatus(options) {
  return request('/guided/status', options);
}

export function getRecipeGuide(recipeId, options) {
  return request(`/guided/recipes/${encodeURIComponent(recipeId)}`, options);
}

export function startGuideBuild(recipeId) {
  return request(`/guided/recipes/${encodeURIComponent(recipeId)}/build`, { method: 'POST' });
}

export function cancelGuideBuild(jobId) {
  return request(`/guided/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
}

// Admin: switch guided versions on or off, and choose the model that builds them.
export function getGuidedSettings() {
  return request('/guided/settings');
}

export function saveGuidedSettings(values) {
  return request('/guided/settings', { method: 'PUT', body: values });
}
