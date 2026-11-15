// Settings, AI / Text recognition: reasoning effort per feature, and guidance for the selected model (FORK.md "AI tuning").
// Fork-only. Mounted by SettingsPage.jsx after the Generation settings card; `cfg` is that page's unsaved form state,
// so the facts follow the model as it is picked, before Save.
import React, { useEffect, useMemo, useState } from 'react';
import { getAiTuning, saveAiTuning } from '../forkApi';
import { ft } from '../strings';
import './AiTuningSection.css';

const FEATURES = ['scan', 'cleanup', 'guide', 'ballband'];
const STRONG = ['high', 'xhigh', 'max'];
const EFFORT_ORDER = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'];

function nearest(want, offered) {
  if (!want || offered.includes(want)) return want;
  const choices = offered.filter((e) => e !== 'none');
  if (!choices.length) return '';
  const rank = EFFORT_ORDER.indexOf(want);
  return choices.reduce((best, e) => {
    const d = Math.abs(EFFORT_ORDER.indexOf(e) - rank);
    const bd = Math.abs(EFFORT_ORDER.indexOf(best) - rank);
    return d < bd || (d === bd && EFFORT_ORDER.indexOf(e) > EFFORT_ORDER.indexOf(best)) ? e : best;
  }, choices[0]);
}

function Fact({ ok, children }) {
  return <span className={`fork-tune-fact ${ok ? 'ok' : 'no'}`}>{ok ? '✓' : '✗'} {children}</span>;
}

export default function AiTuningSection({ cfg }) {
  const [data, setData] = useState(null);
  const [efforts, setEfforts] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [saving, setSaving] = useState(false);

  const model = cfg.ai_model || '';
  const baseUrl = cfg.ai_base_url || '';

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    const timer = setTimeout(() => {
      getAiTuning(model, baseUrl, { signal: controller.signal })
        .then((d) => { setData(d); setEfforts((e) => e || d.settings); })
        .catch((e) => { if (e.name !== 'AbortError') setError(e.message); })
        .finally(() => setLoading(false));
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [model, baseUrl]);

  const info = data?.info;
  const offered = info?.reasoning?.efforts || [];
  // Scanning and cleanup use the page's max output tokens; guided versions and ball bands set their own room.
  const strongestOf = (features) => {
    if (!efforts || !info) return '';
    const used = features.map((f) => nearest(efforts[f], offered) || '').filter((e) => STRONG.includes(e));
    return used.sort((a, b) => EFFORT_ORDER.indexOf(b) - EFFORT_ORDER.indexOf(a))[0] || '';
  };
  const strongScan = useMemo(() => strongestOf(['scan', 'cleanup']), [efforts, info]); // eslint-disable-line react-hooks/exhaustive-deps
  const strongGuide = useMemo(() => strongestOf(['guide']), [efforts, info]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = data && efforts && FEATURES.some((f) => (efforts[f] || '') !== (data.settings[f] || ''));

  const save = async () => {
    setSaving(true); setStatus(''); setError('');
    try {
      const r = await saveAiTuning(efforts);
      setData((d) => ({ ...d, settings: r.settings }));
      setEfforts(r.settings);
      setStatus(ft('tuneSaved'));
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const maxTokens = Number(cfg.ai_max_output_tokens) || 0;
  const timeout = Number(cfg.ai_timeout) || 0;

  const effortSelect = (feature) => {
    const value = efforts?.[feature] || '';
    const reasoning = info?.reasoning;
    let disabledLabel = '';
    if (info && !reasoning?.supported) disabledLabel = ft('tuneNoReasoning');
    else if (info && reasoning?.supported && offered.length === 0) disabledLabel = ft('tuneNoLevels');
    const used = info ? nearest(value, offered) : value;
    return (
      <div className="form-field" key={feature}>
        <label className="form-label" htmlFor={`fork-effort-${feature}`}>{ft(`feature_${feature}`)}</label>
        {disabledLabel ? (
          <select id={`fork-effort-${feature}`} className="form-input" disabled value=""><option value="">{disabledLabel}</option></select>
        ) : (
          <select
            id={`fork-effort-${feature}`}
            className="form-input"
            value={value}
            onChange={(e) => setEfforts((cur) => ({ ...cur, [feature]: e.target.value }))}
            disabled={!efforts}
          >
            <option value="">{reasoning?.default ? ft('tuneDefault', { effort: reasoning.default }) : ft('tuneDefaultPlain')}</option>
            {(info ? offered : EFFORT_ORDER).map((e) => (
              <option key={e} value={e}>{e === 'none' ? ft('tuneOff') : e}</option>
            ))}
            {info && value && !offered.includes(value) && <option value={value}>{value}</option>}
          </select>
        )}
        <p className="settings-row-sub ai-inline-help">{ft(`feature_${feature}_hint`)}</p>
        {info && value && used !== value && !disabledLabel && (
          <p className="settings-row-sub ai-inline-help fork-tune-warn">{ft('tuneWillUse', { saved: value, used: used || ft('tuneDefaultPlain') })}</p>
        )}
      </div>
    );
  };

  return (
    <div className="ai-settings-card fork-tune">
      <div className="ai-card-heading">
        <div>
          <h4>{ft('tuneTitle')}</h4>
          <p>{ft('tuneSub')}</p>
        </div>
      </div>

      {error && <p className="settings-row-sub fork-tune-warn" role="alert">{error}</p>}
      {loading && !data && <p className="settings-row-sub">{ft('tuneLoading')}</p>}

      {data && !data.openrouter && <p className="settings-row-sub">{ft('tuneNotOpenRouter')}</p>}
      {data && data.openrouter && !data.catalogue_ok && <p className="settings-row-sub fork-tune-warn">{ft('tuneListDown')}</p>}
      {data && data.openrouter && data.catalogue_ok && !model && <p className="settings-row-sub">{ft('tuneNoModel')}</p>}
      {data && data.openrouter && data.catalogue_ok && model && !info && !loading && (
        <p className="settings-row-sub fork-tune-warn">{ft('tuneUnknown', { model })}</p>
      )}

      {info && (
        <>
          <div className="fork-tune-facts">
            <Fact ok={info.image_input}>{ft('tuneImages')}</Fact>
            <Fact ok={info.structured_outputs}>{ft('tuneJson')}</Fact>
            {Boolean(info.max_output_tokens) && <span className="fork-tune-fact">{ft('tuneOutput', { n: Number(info.max_output_tokens).toLocaleString() })}</span>}
            {info.price_in != null && info.price_out != null && (
              <span className="fork-tune-fact">{ft('tunePrice', { in: info.price_in.toFixed(2), out: info.price_out.toFixed(2) })}</span>
            )}
          </div>
          {!info.image_input && <p className="settings-row-sub fork-tune-warn">{ft('tuneNoImages')}</p>}
          {!info.structured_outputs && <p className="settings-row-sub fork-tune-warn">{ft('tuneNoJson')}</p>}
        </>
      )}

      {data && (data.openrouter ? info || !model : false) && (
        <>
          <h5 className="fork-tune-heading">{ft('tuneEffortHeading')}</h5>
          <div className="ai-number-grid fork-tune-grid">{FEATURES.map(effortSelect)}</div>
          <div>
            <button className="btn-primary" onClick={save} disabled={saving || !dirty}>{ft('tuneSave')}</button>
            {status && <span className="settings-row-sub" role="status" style={{ marginLeft: 12 }}>{status}</span>}
          </div>
        </>
      )}

      {info && (
        <>
          <h5 className="fork-tune-heading">{ft('tuneTempHeading')}</h5>
          <p className="settings-row-sub">
            {info.temperature
              ? ft('tuneTempUsed', { def: info.default_temperature != null ? ft('tuneTempDefault', { t: info.default_temperature }) : '' })
              : ft('tuneTempIgnored')}
          </p>

          <h5 className="fork-tune-heading">{ft('tuneLimitsHeading')}</h5>
          {Boolean(info.max_output_tokens) && maxTokens > info.max_output_tokens && (
            <p className="settings-row-sub fork-tune-warn">{ft('tuneOverMax', { set: maxTokens, max: info.max_output_tokens })}</p>
          )}
          {Boolean(strongScan) && maxTokens > 0 && maxTokens < 16000 && (
            <p className="settings-row-sub fork-tune-warn">{ft('tuneThinkRoom', { effort: strongScan })}</p>
          )}
          <p className={`settings-row-sub ${strongGuide && timeout > 0 && timeout < 300 ? 'fork-tune-warn' : ''}`}>
            {strongGuide && timeout > 0 && timeout < 300 ? ft('tuneTimeout', { effort: strongGuide }) : ft('tuneTimeoutOk')}
          </p>
          <p className="settings-row-sub">{ft('tunePages')}</p>
        </>
      )}

      {data?.prompts?.length > 0 && (
        <>
          <h5 className="fork-tune-heading">{ft('tunePromptsHeading')}</h5>
          <p className="settings-row-sub">{ft('tunePromptsSub')}</p>
          {data.prompts.map((p) => (
            <details key={p.id} className="fork-tune-prompt">
              <summary>{p.title}</summary>
              <pre>{p.text}</pre>
            </details>
          ))}
        </>
      )}
    </div>
  );
}
