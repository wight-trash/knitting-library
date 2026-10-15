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

async function request(path, { method = 'GET', signal, body, form, timeout = TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
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
      headers: method === 'GET' || form ? {} : { 'Content-Type': 'application/json' },
      body: method === 'GET' ? undefined : (form || JSON.stringify(body || {})),
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

// ---------------------------------------------------------------- the stash in grams (docs/guided-knitting/PHASE2-STASH.md)
export function getStashStatus(options) {
  return request('/stash/status', options);
}

export function getStashItems(options) {
  return request('/stash/items', options);
}

export function getStashItem(itemId, options) {
  return request(`/stash/items/${encodeURIComponent(itemId)}`, options);
}

// amount: { balls } or { grams }, plus an optional note
export function stashPurchase(itemId, amount) {
  return request(`/stash/items/${encodeURIComponent(itemId)}/purchase`, { method: 'POST', body: amount });
}

export function stashCorrect(itemId, amount) {
  return request(`/stash/items/${encodeURIComponent(itemId)}/correct`, { method: 'POST', body: amount });
}

export function getYarnSpec(yarnId, options) {
  return request(`/stash/yarns/${encodeURIComponent(yarnId)}/spec`, options);
}

export function saveYarnSpec(yarnId, spec) {
  return request(`/stash/yarns/${encodeURIComponent(yarnId)}/spec`, { method: 'PUT', body: spec });
}

// A colour (shade) of a yarn, by name only (JSON, as the server expects).
export function addYarnColourName(yarnId, name) {
  return request(`/yarns/${encodeURIComponent(yarnId)}/colours`, { method: 'POST', body: { name } });
}

// One photo of a ball band; the AI reads it and the server converts the units. Saves nothing. Can take a minute.
export function readBallBand(file) {
  const form = new FormData();
  form.append('image', file, file.name || 'ball-band.jpg');
  return request('/stash/ballband', { method: 'POST', form, timeout: 150000 });
}

// The address of a shop's picture, fetched by our own server (the page may not fetch other sites itself).
export function stashImageUrl(url) {
  return `${API_BASE}/stash/image?url=${encodeURIComponent(url)}`;
}

export async function fetchStashImage(url) {
  const res = await fetch(stashImageUrl(url), { cache: 'no-store' });
  if (!res.ok) throw new Error(`Picture not fetched (${res.status})`);
  return res;
}

// Admin: the fork's switches (guided versions, stash in grams) and the model.
export function getForkSettings() {
  return request('/fork/settings');
}

export function saveForkSettings(values) {
  return request('/fork/settings', { method: 'PUT', body: values });
}
