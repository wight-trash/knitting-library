// Dialogs for the stash in grams: Bought more, Correct, and Ball details. Fork-only (FORK.md).
// One dialog at a time, never one on top of another. The dialog follows the part of the screen the keyboard leaves
// free (visualViewport), so the Save button stays in sight on an iPhone.
import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { ft } from '../strings';
import { stashPurchase, stashCorrect, getYarnSpec, saveYarnSpec } from '../forkApi';
import { putStashItem, specSaved } from './stashStore';
import { amountText, formToSpec, parseNumber, specToForm, sameForm, EMPTY_BALL_FORM } from './stashNumbers';
import BallDetailsFields from './BallDetailsFields';
import './Stash.css';

function plainError(e, fallback = 'couldNotSave') {
  return e && e.fromServer ? e.message : ft(fallback);
}

// ---------------------------------------------------------------- the shell
function useVisibleArea() {
  const [area, setArea] = useState(null);
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return undefined;
    const update = () => setArea({ top: vv.offsetTop, height: vv.height });
    update();
    vv.addEventListener('resize', update);
    vv.addEventListener('scroll', update);
    return () => { vv.removeEventListener('resize', update); vv.removeEventListener('scroll', update); };
  }, []);
  return area;
}

export function StashDialog({ title, subtitle, onClose, children, footer, wide = false }) {
  const titleId = useId();
  const area = useVisibleArea();
  const boxRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = overflow; };
  }, [onClose]);

  // Keep the box being typed in visible when the keyboard opens.
  useEffect(() => {
    const el = document.activeElement;
    if (el && boxRef.current?.contains(el) && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
  }, [area?.height]);

  const style = area ? { top: `${area.top}px`, height: `${area.height}px`, bottom: 'auto' } : undefined;
  return createPortal(
    <div className="st-overlay" style={style}>
      <div ref={boxRef} className={`st-dialog ${wide ? 'st-dialog--wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="st-dialog-head">
          <div className="st-dialog-titles">
            <h2 id={titleId} className="st-dialog-title">{title}</h2>
            {subtitle && <p className="st-dialog-sub">{subtitle}</p>}
          </div>
          <button type="button" className="st-icon-btn" onClick={onClose} aria-label={ft('close')}><X size={22} /></button>
        </div>
        <div className="st-dialog-body">{children}</div>
        {footer && <div className="st-dialog-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

function Footer({ onCancel, onSave, saving, disabled, saveLabel }) {
  return (
    <>
      <button type="button" className="st-btn st-btn--secondary" onClick={onCancel} disabled={saving}>{ft('cancel')}</button>
      <button type="button" className="st-btn st-btn--primary" onClick={onSave} disabled={saving || disabled}>
        {saving ? ft('saving') : (saveLabel || ft('save'))}
      </button>
    </>
  );
}

function UnitChoice({ unit, setUnit, gramsAllowed }) {
  if (!gramsAllowed) return null;
  return (
    <div className="st-segment" role="radiogroup" aria-label={ft('unitChoice')}>
      {['balls', 'grams'].map((u) => (
        <button
          key={u} type="button" role="radio" aria-checked={unit === u}
          className={`st-segment-btn ${unit === u ? 'active' : ''}`}
          onClick={() => setUnit(u)}
        >
          {ft(u)}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- Bought more / Correct
export function AmountDialog({ kind, item, onClose, onDone }) {
  const inputId = useId();
  const noteId = useId();
  const gpb = item.spec?.grams_per_ball || null;
  const gramsMode = item.mode === 'grams' && gpb;
  const [unit, setUnit] = useState('balls');
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const purchase = kind === 'purchase';

  const n = parseNumber(amount);
  const valid = n != null && !Number.isNaN(n) && (purchase ? n > 0 : n >= 0);
  const wholeOnly = !gramsMode && valid && n !== Math.floor(n);

  let after = null;
  if (valid && !wholeOnly) {
    const nowG = gramsMode ? item.grams || 0 : null;
    if (gramsMode) {
      const g = unit === 'grams' ? n : n * gpb;
      const total = purchase ? nowG + g : g;
      after = amountText(Math.floor((total / gpb) * 10 + 0.0001) / 10, total);
    } else {
      after = amountText(purchase ? (item.quantity || 0) + n : n, null);
    }
  }

  const save = async () => {
    if (!valid) { setError(ft('giveAmount')); return; }
    if (wholeOnly) { setError(ft('wholeBallsOnly')); return; }
    setSaving(true); setError('');
    const body = { [unit === 'grams' ? 'grams' : 'balls']: n, note: note.trim() };
    try {
      const res = await (purchase ? stashPurchase(item.id, body) : stashCorrect(item.id, body));
      if (res.item) putStashItem(res.item);
      onDone?.(res.item);
      onClose();
    } catch (e) {
      setError(plainError(e));
      setSaving(false);
    }
  };

  const unitLabel = unit === 'grams' ? ft('gramsUnit') : ft('ballsUnit');
  const now = item.mode === 'grams' ? amountText(item.balls, item.grams) : amountText(item.quantity, null);
  return (
    <StashDialog
      title={purchase ? ft('boughtMore') : ft('correct')}
      subtitle={item.name}
      onClose={onClose}
      footer={<Footer onCancel={onClose} onSave={save} saving={saving} disabled={!amount.trim()} />}
    >
      <form className="st-form" onSubmit={(e) => { e.preventDefault(); save(); }}>
        <p className="st-text">{ft('stashNow', { amount: now })}</p>
        <div className="st-field">
          <label className="st-label st-label--big" htmlFor={inputId}>{purchase ? ft('howMany') : ft('howMuchNow')}</label>
          {!purchase && <p className="st-hint">{gramsMode ? ft('howMuchNowHint') : ft('wholeBallsOnly')}</p>}
          <UnitChoice unit={unit} setUnit={setUnit} gramsAllowed={Boolean(gramsMode)} />
          <div className="st-amount-row">
            <input
              id={inputId}
              className="st-input st-input--amount"
              inputMode={gramsMode ? 'decimal' : 'numeric'}
              enterKeyHint="done"
              value={amount}
              onChange={(e) => { setAmount(e.target.value); setError(''); }}
              placeholder={unit === 'grams' ? '50' : '1'}
              autoComplete="off"
            />
            <span className="st-amount-unit">{unitLabel}</span>
          </div>
          {purchase && unit === 'balls' && (
            <div className="st-quick" aria-label={ft('howMany')}>
              {[1, 2, 5, 10].map((q) => (
                <button key={q} type="button" className="st-chip" onClick={() => { setAmount(String(q)); setError(''); }}>{q}</button>
              ))}
            </div>
          )}
        </div>
        <div className="st-field">
          <label className="st-label" htmlFor={noteId}>{ft('note')}</label>
          <input
            id={noteId}
            className="st-input"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={purchase ? ft('notePurchase') : ft('noteCorrect')}
            maxLength={300}
            enterKeyHint="done"
            autoCapitalize="sentences"
          />
        </div>
        {after && <p className="st-text st-after" role="status">{ft('stashAfter', { amount: after })}</p>}
        {error && <p className="st-error" role="alert">{error}</p>}
      </form>
    </StashDialog>
  );
}

// ---------------------------------------------------------------- Ball details of one yarn
export function BallDetailsDialog({ yarnId, yarnName, onClose, onSaved }) {
  const [loaded, setLoaded] = useState(null);   // the form as loaded, to know whether anything changed
  const [form, setForm] = useState(EMPTY_BALL_FORM);
  const [loadError, setLoadError] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoadError('');
    getYarnSpec(yarnId)
      .then((res) => { if (!alive) return; const f = specToForm(res.spec); setLoaded(f); setForm(f); })
      .catch((e) => { if (alive) setLoadError(plainError(e, 'couldNotLoad')); });
    return () => { alive = false; };
  }, [yarnId, attempt]);

  const save = async () => {
    const { spec, error: problem } = formToSpec(form);
    if (problem) { setError(problem); return; }
    setSaving(true); setError('');
    try {
      const res = await saveYarnSpec(yarnId, { ...spec, source: 'manual' });
      specSaved(yarnId);
      onSaved?.(res.spec);
      onClose();
    } catch (e) {
      setError(plainError(e));
      setSaving(false);
    }
  };

  return (
    <StashDialog
      title={ft('ballDetails')}
      subtitle={yarnName}
      onClose={onClose}
      wide
      footer={<Footer onCancel={onClose} onSave={save} saving={saving} disabled={!loaded || sameForm(form, loaded)} />}
    >
      {loadError ? (
        <div className="st-form">
          <p className="st-error" role="alert">{loadError}</p>
          <button type="button" className="st-btn st-btn--secondary" onClick={() => setAttempt((a) => a + 1)}>{ft('tryAgainShort')}</button>
        </div>
      ) : !loaded ? (
        <p className="st-text">{ft('loading')}</p>
      ) : (
        <form className="st-form" onSubmit={(e) => { e.preventDefault(); save(); }}>
          <p className="st-hint">{ft('ballDetailsHint')}</p>
          <BallDetailsFields value={form} heading={false} onChange={(k, v) => { setForm((f) => ({ ...f, [k]: v })); setError(''); }} />
          {error && <p className="st-error" role="alert">{error}</p>}
        </form>
      )}
    </StashDialog>
  );
}
