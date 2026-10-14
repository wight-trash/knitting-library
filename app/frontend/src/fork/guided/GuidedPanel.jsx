// The "Guided" tab of a pattern: make a guided version, watch it being made, and read it. Fork-only (see FORK.md).
import React, { useEffect, useRef, useState } from 'react';
import { ListChecks, AlertCircle, CheckCircle2, Settings } from 'lucide-react';
import { startGuideBuild, cancelGuideBuild } from '../forkApi';
import { ft } from '../strings';
import useGuidedStatus from './useGuidedStatus';
import useLiveGuide, { isActiveJob } from './useLiveGuide';
import BuildProgress, { LiveIndicator } from './BuildProgress';
import GuideView from './GuideView';
import './GuidedPanel.css';

const hiddenNoticeKey = (jobId) => `fork_guided_notice_hidden_${jobId}`;
function noticeHidden(jobId) {
  try { return localStorage.getItem(hiddenNoticeKey(jobId)) === '1'; } catch { return false; }
}

function Intro({ status, showButton, starting, onStart, error }) {
  const configured = status ? status.configured : true;
  return (
    <section className="gp-card gp-intro">
      <span className="gp-intro-icon" aria-hidden="true"><ListChecks size={30} /></span>
      <h2 className="gp-h2">{ft('introTitle')}</h2>
      <p className="gp-lead">{ft('introText')}</p>
      {!configured ? (
        <div className="gp-notice gp-notice--info">
          <Settings size={22} aria-hidden="true" />
          <div>
            <p><strong>{ft('notSetUp')}</strong></p>
            <p>{status?.can_change_settings ? ft('notSetUpAdmin') : ft('notSetUpUser')}</p>
          </div>
        </div>
      ) : showButton ? (
        <button type="button" className="gp-btn gp-btn--primary gp-btn--big" onClick={onStart} disabled={starting}>
          <ListChecks size={22} aria-hidden="true" />
          {starting ? ft('starting') : ft('makeGuided')}
        </button>
      ) : null}
      {error && <p className="gp-note gp-note--warn" role="alert">{error}</p>}
    </section>
  );
}

function FinishedNotice({ job, hasGuide, canRetry, starting, onRetry, onHide, error }) {
  const failed = job.status === 'failed';
  return (
    <section className={`gp-card gp-notice-card ${failed ? 'gp-notice-card--failed' : ''}`} role="status">
      <AlertCircle size={26} className="gp-notice-icon" aria-hidden="true" />
      <div className="gp-notice-body">
        <h2 className="gp-h2">{failed ? ft('failedTitle') : ft('cancelledTitle')}</h2>
        <p>{failed ? (job.error || ft('failedDefault')) : ft('cancelledText')}</p>
        {hasGuide && <p className="gp-muted">{ft('keptEarlier')}</p>}
        <div className="gp-actions">
          {canRetry && (
            <button type="button" className="gp-btn gp-btn--primary" onClick={onRetry} disabled={starting}>
              {starting ? ft('starting') : ft('tryAgain')}
            </button>
          )}
          {hasGuide && (
            <button type="button" className="gp-btn gp-btn--ghost" onClick={onHide}>{ft('hideNotice')}</button>
          )}
        </div>
        {error && <p className="gp-note gp-note--warn" role="alert">{error}</p>}
      </div>
    </section>
  );
}

export default function GuidedPanel({ recipeId, recipe }) {
  const status = useGuidedStatus();
  const live = useLiveGuide(recipeId);
  const { data, failures, checking, lastOkAt } = live;
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState('');
  const [justFinished, setJustFinished] = useState(false);
  const [hiddenNotices, setHiddenNotices] = useState(() => new Set());
  const wasActiveRef = useRef(false);

  const job = data?.job || null;
  const guideRow = data?.guide || null;
  const active = isActiveJob(job);
  const enabled = data ? data.enabled !== false : true;
  const configured = status ? status.configured : true;

  // Say "ready" when a build we watched (or came back to) has just finished.
  useEffect(() => {
    if (active) { wasActiveRef.current = true; setJustFinished(false); return; }
    if (wasActiveRef.current && job?.status === 'done') setJustFinished(true);
    wasActiveRef.current = false;
  }, [active, job?.status]);

  const start = async () => {
    setStarting(true);
    setStartError('');
    try {
      const res = await startGuideBuild(recipeId);
      live.applyJob(res.job);
      return true;
    } catch (e) {
      if (e.status === 409) { live.refresh('resume'); return true; }  // already being made: just show it
      setStartError(e.fromServer ? e.message : ft('loadFailed'));
      return false;
    } finally {
      setStarting(false);
    }
  };

  const stop = async () => {
    const res = await cancelGuideBuild(job.id);
    live.applyJob(res.job);
    live.refresh('poll');
  };

  const hideNotice = () => {
    if (!job) return;
    try { localStorage.setItem(hiddenNoticeKey(job.id), '1'); } catch { /* not remembered */ }
    setHiddenNotices(prev => new Set(prev).add(job.id));
  };

  let body;
  if (!data) {
    // Never a blank page or a spinner on its own: say what is happening.
    body = (
      <section className="gp-card gp-loading" aria-busy="true">
        <p className="gp-lead">{failures > 0 ? ft('loadFailed') : ft('loadingGuide')}</p>
        <div className="gp-skeleton" />
        <div className="gp-skeleton gp-skeleton--short" />
        {failures > 0 && <LiveIndicator lastOkAt={lastOkAt} failures={failures} checking={checking} />}
      </section>
    );
  } else if (!enabled && !guideRow) {
    body = <section className="gp-card"><p className="gp-lead">{ft('switchedOff')}</p></section>;
  } else {
    const ended = job && (job.status === 'failed' || job.status === 'cancelled');
    const showNotice = ended && !(guideRow && (hiddenNotices.has(job.id) || noticeHidden(job.id)))
      && !(guideRow && job.created_at && guideRow.built_at && guideRow.built_at > job.created_at);
    const canBuild = enabled && configured;
    body = (
      <>
        {active && (
          <BuildProgress job={job} offsetMs={data.offsetMs} lastOkAt={lastOkAt} failures={failures}
            checking={checking} onStop={stop} />
        )}
        {justFinished && guideRow && (
          <div className="gp-card gp-ready" role="status">
            <CheckCircle2 size={24} aria-hidden="true" />
            <span>{ft('readyBanner')}</span>
          </div>
        )}
        {!active && showNotice && (
          <FinishedNotice job={job} hasGuide={Boolean(guideRow)} canRetry={canBuild} starting={starting}
            onRetry={start} onHide={hideNotice} error={startError} />
        )}
        {!active && !guideRow && (
          <Intro status={status} showButton={!showNotice} starting={starting} onStart={start}
            error={showNotice ? '' : startError} />
        )}
        {guideRow && (
          <GuideView key={`${guideRow.version}-${guideRow.built_at}`} recipeId={recipeId} recipe={recipe} guideRow={guideRow} canRemake={canBuild}
            building={active} onRemake={start} remakeError={showNotice ? '' : startError} />
        )}
      </>
    );
  }

  return (
    <div className="gp-panel">
      <div className="gp-inner">{body}</div>
    </div>
  );
}
