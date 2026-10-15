// Shared state for the stash in grams: whether it is switched on (asked once per page load), the yarn items with
// their grams (loaded once and shared by every card), and a note when a yarn's ball details change. Fork-only.
import { useEffect, useState, useSyncExternalStore } from 'react';
import { getStashStatus, getStashItems } from '../forkApi';

// ---------------------------------------------------------------- is it switched on?
let statusCache = null;
let statusPending = null;

function loadStatus() {
  if (statusCache) return Promise.resolve(statusCache);
  if (!statusPending) {
    statusPending = getStashStatus()
      .then((s) => { statusCache = s; return s; })
      .finally(() => { statusPending = null; });   // a failed request is asked again by the next caller
  }
  return statusPending;
}

/** Called after the switch changes in Settings, so the next screen asks again. */
export function forgetStashStatus() {
  statusCache = null;
  items = { loaded: false, byId: {} };
}

/** null until known; then { enabled, ballband_available, can_change_settings } */
export function useStashStatus() {
  const [status, setStatus] = useState(statusCache);
  useEffect(() => {
    if (statusCache) { setStatus(statusCache); return undefined; }
    let alive = true;
    loadStatus().then((s) => { if (alive) setStatus(s); }).catch(() => {});
    return () => { alive = false; };
  }, []);
  return status;
}

// ---------------------------------------------------------------- the yarn items with grams
let items = { loaded: false, byId: {} };
let itemsPending = null;
let fetchedAt = 0;
let refreshTimer = null;
const listeners = new Set();

function emit() { listeners.forEach((fn) => fn()); }

function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

let fetchAgain = false;

function fetchItems() {
  if (itemsPending) { fetchAgain = true; return itemsPending; }   // asked while a request was on its way
  itemsPending = getStashItems()
    .then((data) => {
      const byId = {};
      (data.items || []).forEach((it) => { byId[it.id] = it; });
      items = { loaded: true, byId };
      fetchedAt = Date.now();
      emit();
    })
    .catch(() => {})
    .finally(() => {
      itemsPending = null;
      if (fetchAgain) { fetchAgain = false; fetchItems(); }
    });
  return itemsPending;
}

/** A card appeared: ask the server unless the answer is a moment old and has this item. */
export function ensureStashItems(itemId) {
  if (!items.loaded || !items.byId[itemId] || Date.now() - fetchedAt > 3000) refreshStashItems();
}

/** Ask again soon; several cards asking at once make one request. */
export function refreshStashItems() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(fetchItems, 60);
}

/** Put one item from a purchase or correction answer straight in, without asking again. */
export function putStashItem(item) {
  items = { ...items, byId: { ...items.byId, [item.id]: item } };
  emit();
}

export function useStashItem(itemId) {
  return useSyncExternalStore(subscribe, () => items.byId[itemId] || null);
}

// ---------------------------------------------------------------- ball details changed somewhere
const specListeners = new Set();

export function specSaved(yarnId) {
  specListeners.forEach((fn) => fn(yarnId));
  refreshStashItems();
}

export function onSpecSaved(fn) {
  specListeners.add(fn);
  return () => specListeners.delete(fn);
}
