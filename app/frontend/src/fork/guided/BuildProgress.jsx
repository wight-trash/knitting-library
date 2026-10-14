// The progress card shown while a guided version is being made. It ticks every second so it always looks alive.
import React, { useEffect, useState } from 'react';
import { Check, Loader2, Circle, WifiOff, RefreshCw } from 'lucide-react';
import { ft } from '../strings';

const STAGES = ['read', 'pictures', 'outline', 'sections', 'checks'];
const LATE_SECONDS = 45;  // no news from the build for this long: say it is taking longer

function stageIndex(stage) {
  if (stage === 'repair') return STAGES.indexOf('checks');
  if (stage === 'done') return STAGES.length;
  return STAGES.indexOf(stage);  // -1 for queued
}

function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m > 0 ? ft('minSec', { m, s: String(s).padStart(2, '0') }) : ft('secOnly', { s });
}

function freshness(now, lastOkAt, failures, checking) {
  if (failures > 0) return { kind: 'error', text: ft('reconnecting') };
  if (checking) return { kind: 'checking', text: ft('checking') };
  const ago = Math.max(0, Math.round((now - lastOkAt) / 1000));
  if (ago < 5) return { kind: 'ok', text: ft('updatedJustNow') };
  if (ago < 60) return { kind: 'ok', text: ft('updatedSecondsAgo', { n: ago }) };
  return { kind: 'ok', text: ft('updatedMinutesAgo', { n: Math.round(ago / 60) }) };
}

export function LiveIndicator({ lastOkAt, failures, checking }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    const onVisible = () => setNow(Date.now());
    document.addEventListener('visibilitychange', onVisible);
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', onVisible); };
  }, []);
  const f = freshness(now, lastOkAt, failures, checking);
  return (
    <span className={`gp-live gp-live--${f.kind}`}>
      {f.kind === 'error' ? <WifiOff size={16} aria-hidden="true" />
        : f.kind === 'checking' ? <RefreshCw size={16} className="gp-spin" aria-hidden="true" />
          : <span className="gp-live-dot" aria-hidden="true" />}
      <span>{f.text}</span>
    </span>
  );
}

export default function BuildProgress({ job, offsetMs, lastOkAt, failures, checking, onStop }) {
  const [now, setNow] = useState(() => Date.now());
  const [confirming, setConfirming] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState('');

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    const onVisible = () => setNow(Date.now());   // jump the clock forward the moment the page is seen again
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('pageshow', onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('pageshow', onVisible);
    };
  }, []);

  const ev = job.last_event || {};
  const queued = job.status === 'queued' || !ev.stage || ev.stage === 'queued';
  const current = queued ? -1 : stageIndex(ev.stage);
  const percent = Math.max(0, Math.min(100, Number(ev.percent) || 0));
  const serverNow = now + (offsetMs || 0);
  const startedAt = Date.parse(job.started_at || job.created_at || '');
  const elapsed = Number.isFinite(startedAt) ? serverNow - startedAt : null;
  const late = !queued && Number(ev.at) > 0 && serverNow / 1000 - Number(ev.at) > LATE_SECONDS;
  const cancelling = job.cancel_requested || stopping;
  const message = queued ? ft('waitingToStart') : (ev.message || ev.title || '');

  const stop = async () => {
    setStopping(true);
    setStopError('');
    try {
      await onStop();
      setConfirming(false);
    } catch (e) {
      setStopError(e.message);
      setStopping(false);
    }
  };

  return (
    <section className="gp-card gp-progress" aria-labelledby="gp-progress-title">
      <div className="gp-progress-head">
        <h2 id="gp-progress-title" className="gp-h2">{ft('buildingTitle')}</h2>
        <LiveIndicator lastOkAt={lastOkAt} failures={failures} checking={checking} />
      </div>

      <div className="gp-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}
        aria-label={ft('percentDone', { percent })}>
        <div className="gp-bar-fill" style={{ width: `${Math.max(percent, 3)}%` }} />
      </div>
      <div className="gp-progress-numbers">
        <span className="gp-percent">{ft('percentDone', { percent })}</span>
        {elapsed != null && <span className="gp-elapsed">{ft('timeSoFar', { time: formatElapsed(elapsed) })}</span>}
      </div>

      <p className="gp-message" aria-live="polite">{cancelling ? ft('stopping') : message}</p>
      {late && !cancelling && <p className="gp-note">{ft('takingLonger')}</p>}
      {failures > 0 && <p className="gp-note gp-note--warn">{ft('reconnectingHint')}</p>}

      <ol className="gp-stages">
        {STAGES.map((stage, i) => {
          const state = i < current ? 'done' : i === current ? 'now' : 'waiting';
          return (
            <li key={stage} className={`gp-stage gp-stage--${state}`}>
              <span className="gp-stage-mark" aria-hidden="true">
                {state === 'done' ? <Check size={18} strokeWidth={3} />
                  : state === 'now' ? <Loader2 size={18} className="gp-spin" />
                    : <Circle size={14} />}
              </span>
              <span className="gp-stage-name">{ft(`stage_${stage}`)}</span>
              <span className="gp-sr">
                {state === 'done' ? ft('stageDone') : state === 'now' ? ft('stageNow') : ft('stageWaiting')}
              </span>
            </li>
          );
        })}
      </ol>

      <p className="gp-hint">{ft('buildingHint')}</p>

      {!cancelling && !confirming && (
        <div className="gp-actions">
          <button type="button" className="gp-btn gp-btn--secondary" onClick={() => setConfirming(true)}>
            {ft('stop')}
          </button>
        </div>
      )}
      {!cancelling && confirming && (
        <div className="gp-confirm" role="group" aria-label={ft('stop')}>
          <p>{ft('stopConfirm')}</p>
          <div className="gp-actions">
            <button type="button" className="gp-btn gp-btn--danger" onClick={stop}>{ft('stopYes')}</button>
            <button type="button" className="gp-btn gp-btn--secondary" onClick={() => setConfirming(false)}>{ft('stopNo')}</button>
          </div>
        </div>
      )}
      {stopError && <p className="gp-note gp-note--warn" role="alert">{stopError}</p>}
    </section>
  );
}
