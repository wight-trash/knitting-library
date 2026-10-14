// Keeps the guided version and its build progress up to date, so the page never looks frozen.
//
// - While a build is waiting or running, ask the server every 2 seconds (otherwise every 30 seconds).
// - The moment the page is seen again (iPad unlocked, tab switched back, app reopened), ask straight away,
//   dropping any request left hanging from before the iPad slept.
// - While the page is hidden, stop asking (the build carries on on the server).
// - If a request fails, keep what we had, say "Reconnecting…" and keep trying.
// - A once-a-second watchdog notices a missed timer or a long gap (a sleep that sent no event) and asks again.
import { useCallback, useEffect, useRef, useState } from 'react';
import { getRecipeGuide } from '../forkApi';

const POLL_MS = 2000;
const IDLE_POLL_MS = 30000;    // nothing building: look now and then, in case a build was started elsewhere
const RETRY_MIN_MS = 2000;
const RETRY_MAX_MS = 10000;
const SLOW_MS = 600;           // show "Checking…" when an answer takes longer than this
const STALE_MS = 6000;         // while building, ask again if nothing was asked for this long
const WAKE_GAP_MS = 4000;      // a watchdog tick this late means the page was asleep

export function isActiveJob(job) {
  return Boolean(job && (job.status === 'queued' || job.status === 'running'));
}

function pageVisible() {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}

function serverOffset(job, receivedAt) {
  const server = Date.parse(job?.server_time || '');
  return Number.isFinite(server) ? server - receivedAt : 0;
}

export default function useLiveGuide(recipeId) {
  const [data, setData] = useState(null);         // { enabled, guide, job, offsetMs }
  const [lastOkAt, setLastOkAt] = useState(0);
  const [failures, setFailures] = useState(0);
  const [checking, setChecking] = useState(false);

  const seqRef = useRef(0);
  const controllerRef = useRef(null);
  const pollTimerRef = useRef(null);
  const slowTimerRef = useRef(null);
  const lastAttemptRef = useRef(0);
  const inFlightRef = useRef(false);
  const failuresRef = useRef(0);
  const dataRef = useRef(null);
  const mountedRef = useRef(true);

  const clearPoll = () => {
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    pollTimerRef.current = null;
  };

  const refresh = useCallback((reason = 'poll') => {
    clearPoll();
    // A newer request always wins: drop one still waiting (it may be stuck from before a sleep).
    if (controllerRef.current) controllerRef.current.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const seq = ++seqRef.current;
    inFlightRef.current = true;
    lastAttemptRef.current = Date.now();

    if (slowTimerRef.current) clearTimeout(slowTimerRef.current);
    if (reason === 'resume') setChecking(true);
    else slowTimerRef.current = setTimeout(() => { if (seq === seqRef.current) setChecking(true); }, SLOW_MS);

    const schedule = (ms) => {
      clearPoll();
      if (!mountedRef.current || ms == null || !pageVisible()) return;
      pollTimerRef.current = setTimeout(() => refresh('poll'), ms);
    };

    getRecipeGuide(recipeId, { signal: controller.signal })
      .then((res) => {
        if (!mountedRef.current || seq !== seqRef.current) return;
        const receivedAt = Date.now();
        const next = { enabled: res.enabled, guide: res.guide || null, job: res.job || null,
          offsetMs: serverOffset(res.job, receivedAt) };
        dataRef.current = next;
        failuresRef.current = 0;
        setData(next);
        setLastOkAt(receivedAt);
        setFailures(0);
        schedule(isActiveJob(next.job) ? POLL_MS : IDLE_POLL_MS);
      })
      .catch(() => {
        if (!mountedRef.current || seq !== seqRef.current) return;
        failuresRef.current += 1;
        setFailures(failuresRef.current);
        const wait = Math.min(RETRY_MAX_MS, RETRY_MIN_MS * 2 ** Math.max(0, failuresRef.current - 1));
        schedule(wait);
      })
      .finally(() => {
        if (!mountedRef.current || seq !== seqRef.current) return;
        inFlightRef.current = false;
        if (slowTimerRef.current) clearTimeout(slowTimerRef.current);
        setChecking(false);
      });
  }, [recipeId]);

  /** Use a job the server just sent back (after starting or stopping a build) and keep watching it. */
  const applyJob = useCallback((job) => {
    if (!job) return;
    const receivedAt = Date.now();
    const next = { ...(dataRef.current || { enabled: true, guide: null }), job, offsetMs: serverOffset(job, receivedAt) };
    dataRef.current = next;
    setData(next);
    setLastOkAt(receivedAt);
    if (isActiveJob(job)) {
      clearPoll();
      pollTimerRef.current = setTimeout(() => refresh('poll'), POLL_MS);
    }
  }, [refresh]);

  // First load, and a fresh start when the pattern changes.
  useEffect(() => {
    mountedRef.current = true;
    dataRef.current = null;
    setData(null);
    setFailures(0);
    failuresRef.current = 0;
    refresh('first');
    return () => {
      mountedRef.current = false;
      clearPoll();
      if (slowTimerRef.current) clearTimeout(slowTimerRef.current);
      if (controllerRef.current) controllerRef.current.abort();
    };
  }, [refresh]);

  // Coming back to the page: ask at once. Leaving it: stop asking.
  useEffect(() => {
    let lastResume = 0;
    const resume = () => {
      if (!pageVisible()) return;
      const now = Date.now();
      if (now - lastResume < 400) return;  // visibilitychange, focus and pageshow often arrive together
      lastResume = now;
      refresh('resume');
    };
    const onVisibility = () => {
      if (pageVisible()) resume();
      else clearPoll();
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('focus', resume);
    window.addEventListener('pageshow', resume);
    window.addEventListener('online', resume);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('focus', resume);
      window.removeEventListener('pageshow', resume);
      window.removeEventListener('online', resume);
    };
  }, [refresh]);

  // Watchdog: catches a sleep that sent no event, and a poll timer that the browser dropped.
  useEffect(() => {
    let lastTick = Date.now();
    const id = setInterval(() => {
      const now = Date.now();
      const gap = now - lastTick;
      lastTick = now;
      if (!pageVisible()) return;
      if (gap > WAKE_GAP_MS) { refresh('resume'); return; }
      const building = isActiveJob(dataRef.current?.job);
      const waitingForRetry = failuresRef.current > 0;
      const overdue = now - lastAttemptRef.current > (waitingForRetry ? RETRY_MAX_MS + 2000 : STALE_MS);
      if ((building || waitingForRetry) && !inFlightRef.current && overdue) {
        refresh('poll');
      }
    }, 1000);
    return () => clearInterval(id);
  }, [refresh]);

  return { data, lastOkAt, failures, checking, refresh, applyJob };
}
