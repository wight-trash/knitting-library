// The gram history of one stash item, newest first. Fork-only (FORK.md).
import { useEffect, useState } from 'react';
import { ft } from '../strings';
import { getStashItem } from '../forkApi';
import { putStashItem } from './stashStore';
import { StashDialog } from './StashDialogs';
import { formatGrams, formatNumber } from './stashNumbers';
import './Stash.css';

const REASONS = new Set(['opening', 'purchase', 'correction', 'ball_count', 'project_reserve', 'project_release',
  'project_use', 'leftover']);

function when(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const date = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  return `${date}, ${time}`;
}

function signed(n, text) {
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}${text}`;
}

export default function StashHistory({ item, onClose }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const gpb = item.spec?.grams_per_ball || null;

  useEffect(() => {
    let alive = true;
    setError('');
    getStashItem(item.id)
      .then((res) => {
        if (!alive) return;
        setRows(res.ledger || []);
        if (res.item) putStashItem(res.item);
      })
      .catch((e) => { if (alive) setError(e?.fromServer ? e.message : ft('couldNotLoad')); });
    return () => { alive = false; };
  }, [item.id, attempt]);

  return (
    <StashDialog
      title={ft('gramHistory')}
      subtitle={item.name}
      onClose={onClose}
      footer={<button type="button" className="st-btn st-btn--secondary" onClick={onClose}>{ft('close')}</button>}
    >
      {error ? (
        <div className="st-form">
          <p className="st-error" role="alert">{error}</p>
          <button type="button" className="st-btn st-btn--secondary" onClick={() => setAttempt((a) => a + 1)}>{ft('tryAgainShort')}</button>
        </div>
      ) : rows == null ? (
        <p className="st-text">{ft('loading')}</p>
      ) : rows.length === 0 ? (
        <p className="st-text">{ft('historyEmpty')}</p>
      ) : (
        <ol className="st-history">
          {rows.map((r) => {
            const g = Number(r.change_g) || 0;
            const balls = gpb ? g / gpb : null;
            return (
              <li key={r.id} className={`st-history-row ${g >= 0 ? 'up' : 'down'}`}>
                <div className="st-history-change">
                  <span className="st-history-g">{signed(g, `${formatGrams(Math.abs(g))} g`)}</span>
                  {balls != null && (
                    <span className="st-history-balls">
                      {signed(g, `${formatNumber(Math.abs(balls), 1)} ${Math.abs(balls) === 1 ? 'ball' : 'balls'}`)}
                    </span>
                  )}
                </div>
                <div className="st-history-detail">
                  <span className="st-history-reason">{ft(REASONS.has(r.reason) ? `reason_${r.reason}` : 'reason_other')}</span>
                  {r.note && <span className="st-history-note">{r.note}</span>}
                  <span className="st-history-meta">
                    {when(r.created_at)}
                    {r.created_by ? ` · ${ft('historyBy', { name: r.created_by })}` : ''}
                    {r.balance_g != null ? ` · ${ft('historyThen', { amount: `${formatGrams(r.balance_g)} g` })}` : ''}
                  </span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </StashDialog>
  );
}
