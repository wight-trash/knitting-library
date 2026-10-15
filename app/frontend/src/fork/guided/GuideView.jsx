// The read-only guided version: size picker, things to check, materials and the steps for the chosen size.
import React, { useMemo, useState } from 'react';
import { AlertTriangle, Check, ChevronDown, ChevronRight, RefreshCw, Image as ImageIcon, Search } from 'lucide-react';
import { ft, ftParts } from '../strings';
import {
  allSizes, excludedBy, lowerFirst, numbersOnly, resolve, slotText, splitTemplate, tidy, withUnit,
} from './guideValues';
import {
  converts, doubled, gaugeMetric, isDrops, isHalfWidth, metricParts, metricValue, needleSize, stripUnitWord,
} from './units';

// ---------------------------------------------------------------- remembered choices
function readStored(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function writeStored(key, value) {
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* private mode: just do not remember */ }
}
const sizeKey = (recipeId) => `fork_guided_size_${recipeId}`;
const choiceKey = (recipeId) => `fork_guided_choices_${recipeId}`;

function useSelection(recipeId, options) {
  const sizes = options?.sizes || [];
  const choices = options?.choices || [];
  const [sizeId, setSizeIdState] = useState(() => {
    const saved = readStored(sizeKey(recipeId));
    if (saved && sizes.some(s => s.id === saved)) return saved;
    return sizes.length === 1 ? sizes[0].id : null;
  });
  const [chosen, setChosenState] = useState(() => {
    let saved = {};
    try { saved = JSON.parse(readStored(choiceKey(recipeId)) || '{}') || {}; } catch { saved = {}; }
    const clean = {};
    for (const c of choices) {
      if (saved[c.id] && c.values.some(v => v.id === saved[c.id])) clean[c.id] = saved[c.id];
      else if (c.values.length === 1) clean[c.id] = c.values[0].id;
    }
    return clean;
  });
  const setSize = (id) => { setSizeIdState(id); writeStored(sizeKey(recipeId), id); };
  const setChoice = (choiceId, valueId) => {
    setChosenState(prev => {
      const next = { ...prev, [choiceId]: valueId };
      writeStored(choiceKey(recipeId), JSON.stringify(next));
      return next;
    });
  };
  const sizeIdx = sizeId == null ? null : sizes.findIndex(s => s.id === sizeId);
  const sel = { sizeIdx: sizeIdx != null && sizeIdx >= 0 ? sizeIdx : null, chosen, choices };
  return { sel, sizeId, setSize, setChoice };
}

// ---------------------------------------------------------------- small pieces
/** Fill a string's placeholders with elements, e.g. "You should now have {n} stitches" with a number button. */
function T({ k, vars }) {
  return <>{ftParts(k, vars).map((p, i) => <React.Fragment key={i}>{p}</React.Fragment>)}</>;
}

function formatDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}

/** A number for the chosen size. Tapping it opens the list of every size (the list is drawn by the parent). */
function Num({ text, original, perSize, open, onToggle, muted }) {
  const inner = <>{text}{original && <Orig text={original} />}</>;
  if (!perSize || !onToggle) return <span className={`gp-num ${muted ? 'gp-num--muted' : ''}`}>{inner}</span>;
  return (
    <button type="button" className={`gp-num gp-num--btn ${muted ? 'gp-num--muted' : ''} ${open ? 'gp-num--open' : ''}`}
      aria-expanded={open} onClick={onToggle}>
      {inner}
    </button>
  );
}

// ---------------------------------------------------------------- centimetres
// The owner's rule: cm by default. Values in inches, yards or ounces show metric first, the pattern's own after.

/** The pattern's own value, small, after the metric one. */
function Orig({ text }) {
  return <span className="gp-orig"> ({text})</span>;
}

/** Metric with the original: "11 cm (4¼ in)". */
function Metric({ conv }) {
  return <>{conv.main}<Orig text={conv.original} /></>;
}

/** Free text from the pattern with any inches, yards or ounces shown in metric. */
function MetricText({ text, cable }) {
  const parts = metricParts(tidy(text), { cable });
  if (!parts.some(p => p.kind === 'metric')) return <>{tidy(text)}</>;
  return <>{parts.map((p, i) => (p.kind === 'text'
    ? <React.Fragment key={i}>{p.text}</React.Fragment> : <Metric key={i} conv={p} />))}</>;
}

const METRIC_UNIT = { in: 'cm', yd: 'm', oz: 'g' };

/** The metric form of a value for the selection, or null when it is not converted. r = resolve(value, sel).
 *  When the pattern also gives the value in metric (alt), its own number is used. */
function metricFor(value, r, sel, opts) {
  if (!converts(value?.unit)) return null;
  if (r.state === 'value') {
    const alt = value.alt;
    if (alt && alt.unit === METRIC_UNIT[value.unit] && !opts?.cable) {
      const ra = resolve(alt, sel);
      if (ra.state === 'value') return { main: `${ra.text} ${alt.unit}`, original: metricValue(r.text, value.unit).original };
    }
    return metricValue(r.text, value.unit, opts);
  }
  if (r.state === 'unchosen') return metricValue(numbersOnly(r.text), value.unit, opts);
  return null;
}

/** One size's value in the "all sizes" list, in metric when the pattern is not. */
function SizeValue({ text, value, cable }) {
  const conv = converts(value.unit) ? metricValue(text, value.unit, { cable }) : null;
  return conv ? <Metric conv={conv} /> : text;
}

function AllSizesList({ value, sizes, sel, onClose, cable }) {
  const rows = allSizes(value, sizes, sel);
  if (!rows.length) return null;
  const groups = [...new Set(rows.map(r => r.group))];
  return (
    <div className="gp-allsizes">
      <div className="gp-allsizes-head">
        <span>{ft('allSizes')}</span>
        <button type="button" className="gp-link-btn" onClick={onClose}>{ft('close')}</button>
      </div>
      {groups.map(g => (
        <div key={g || 'all'} className="gp-allsizes-group">
          {g && <div className="gp-allsizes-glabel">{g}</div>}
          <ul>
            {rows.filter(r => r.group === g).map(r => (
              <li key={r.key} className={r.chosen ? 'gp-allsizes-chosen' : ''}>
                <span className="gp-allsizes-size">{r.size}</span>
                <span className="gp-allsizes-value">
                  {r.value === '-' ? ft('notThisSize') : r.value == null || r.value === '' ? ft('notGiven')
                    : <SizeValue text={tidy(r.value)} value={value} cable={cable} />}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <p className="gp-allsizes-source">{tidy(value.text)}</p>{/* the pattern's own words, unconverted */}
    </div>
  );
}

/** A value with its unit for a fact line (target, repeat, checkpoint). Returns null when it does not apply. */
function factValue(value, sel, fallbackUnit, key, openKey, setOpenKey) {
  if (!value) return null;
  const r = resolve(value, sel);
  if (r.state === 'na' || r.state === 'na-choice' || r.state === 'missing') return null;
  const conv = metricFor(value, r, sel);
  const text = conv ? conv.main
    : r.state === 'value' ? withUnit(r.text, value, fallbackUnit) : withUnitRaw(r.text, value, fallbackUnit);
  return (
    <Num key={key} text={text} original={conv?.original} perSize={r.perSize} muted={r.state === 'unchosen'} open={openKey === key}
      onToggle={() => setOpenKey(openKey === key ? null : key)} />
  );
}

function withUnitRaw(raw, value, fallbackUnit) {
  // The pattern's own text with every size, e.g. "52 (56) sts": keep it, adding a unit only if it has none.
  const nums = numbersOnly(raw);
  return nums === raw && fallbackUnit ? `${raw} ${fallbackUnit}` : raw;
}

// ---------------------------------------------------------------- a step
/** Whether a step is for the chosen size and choices, and each slot's value for them. */
function stepState(step, sel, sizes) {
  let excluded = excludedBy(step.applies_to, sel, sizes);
  const resolved = {};
  for (const s of step.slots || []) {
    const r = resolve(s.value, sel);
    resolved[s.name] = r;
    if (!excluded && r.state === 'na') excluded = { reason: 'size' };
    if (!excluded && r.state === 'na-choice') excluded = { reason: 'choice', label: r.label };
  }
  return { excluded, resolved };
}

function Step({ step, index, sizes, sel }) {
  const [openKey, setOpenKey] = useState(null);
  const slots = Object.fromEntries((step.slots || []).map(s => [s.name, s.value]));

  // Does it apply to the chosen size and choices?
  const { excluded, resolved } = stepState(step, sel, sizes);
  const na = Boolean(excluded);

  const parts = splitTemplate(step.text);
  let unitToDrop = null;   // a slot shown in cm: the template's own "inches" after it goes
  const textNodes = parts.map((p, i) => {
    if (p.kind === 'text') {
      const text = unitToDrop ? stripUnitWord(p.text, unitToDrop) : p.text;
      unitToDrop = null;
      return <MetricText key={i} text={text} />;
    }
    unitToDrop = null;
    const value = slots[p.name];
    if (!value) return <React.Fragment key={i}>{`{${p.name}}`}</React.Fragment>;
    const r = resolved[p.name];
    const key = `slot:${p.name}`;
    const conv = metricFor(value, r.state === 'value' ? r : { ...r, state: 'unchosen', text: value.text }, sel);
    if (conv) unitToDrop = value.unit;
    const shown = conv ? conv.main
      : r.state === 'value' ? slotText(r, value, p.after) : (numbersOnly(value.text) || '?');
    return (
      <Num key={i} text={shown} original={conv?.original} perSize={r.perSize} muted={r.state !== 'value'}
        open={openKey === key} onToggle={() => setOpenKey(openKey === key ? null : key)} />
    );
  });

  // Fact lines: what to work, the repeat, and what you should have afterwards.
  const facts = [];
  const t = step.target;
  if (t && t.kind !== 'none') {
    let node = null;
    if ((t.kind === 'rows' || t.kind === 'rounds') && t.count) {
      node = factValue(t.count, sel, t.kind, 'target', openKey, setOpenKey);
    } else if (t.kind === 'repeats' && t.count && !step.repeat?.times) {
      node = factValue(t.count, sel, 'times', 'target', openKey, setOpenKey);
    } else if (t.kind === 'length' && t.length) {
      const v = factValue(t.length, sel, '', 'target', openKey, setOpenKey);
      if (v) {
        node = (
          <>
            <T k="untilLength" vars={{ length: v }} />
            {t.measured_from ? <> <MetricText text={t.measured_from} /></> : ''}
            {t.ending ? <>, <MetricText text={lowerFirst(t.ending)} /></> : ''}
          </>
        );
      }
    } else if (t.kind === 'row_number' && t.until_row) {
      const v = factValue(t.until_row, sel, '', 'target', openKey, setOpenKey);
      if (v) node = <T k="untilRow" vars={{ row: v }} />;
    } else if (t.kind === 'match' && t.match?.text) {
      node = <MetricText text={t.match.text} />;
    }
    if (node && t.kind !== 'length' && t.ending) node = <>{node}, <MetricText text={lowerFirst(t.ending)} /></>;
    if (node) facts.push({ key: 'target', label: ft('targetLabel'), node, value: t.count || t.length || t.until_row });
  }

  const rep = step.repeat;
  if (rep) {
    const bits = [];
    const rows = factValue(rep.rows_in_repeat, sel, 'rows', 'rep-rows', openKey, setOpenKey);
    if (rows) bits.push(<React.Fragment key="rows">{rows}</React.Fragment>);
    const times = factValue(rep.times, sel, 'times', 'rep-times', openKey, setOpenKey);
    if (times) bits.push(<React.Fragment key="times">{times}</React.Fragment>);
    const until = factValue(rep.until_row, sel, '', 'rep-until', openKey, setOpenKey);
    if (until) bits.push(<T key="until" k="untilRow" vars={{ row: until }} />);
    if (rep.until_text) bits.push(<MetricText key="text" text={rep.until_text} />);
    if (rep.includes_earlier_text) bits.push(<MetricText key="earlier" text={rep.includes_earlier_text} />);
    if (bits.length) {
      const joined = bits.flatMap((b, i) => (i ? [<React.Fragment key={`sep${i}`}>, </React.Fragment>, b] : [b]));
      facts.push({ key: 'repeat', label: ft('repeatLabel'), node: <>{joined}</> });
    }
  }

  const cp = step.checkpoint;
  if (cp) {
    let node = null;
    const r = cp.total ? resolve(cp.total, sel) : null;
    if (r && (r.state === 'value' || r.state === 'unchosen')) {
      const shown = r.state === 'value' ? r.text : numbersOnly(r.text);
      const num = (
        <Num text={shown} perSize={r.perSize} muted={r.state !== 'value'} open={openKey === 'checkpoint'}
          onToggle={() => setOpenKey(openKey === 'checkpoint' ? null : 'checkpoint')} />
      );
      if (cp.kind === 'stitches') node = <T k="checkStitches" vars={{ n: num }} />;
      else if (cp.kind === 'rows_worked') node = <T k="checkRows" vars={{ n: num }} />;
      else node = <>{num}{cp.text ? ` (${tidy(cp.text)})` : ''}</>;
      const parts2 = (cp.parts || []).map((p) => {
        const pr = resolve(p.value, sel);
        if (pr.state !== 'value') return null;
        return `${tidy(p.label)} ${pr.text}`;
      }).filter(Boolean);
      if (parts2.length) node = <>{node}: {parts2.join(', ')}</>;
    } else if (!cp.total && cp.text) {
      node = <MetricText text={cp.text} />;
    }
    if (node) facts.push({ key: 'checkpoint', label: ft('checkLabel'), node });
  }

  // Which value's "all sizes" list is open.
  let openValue = null;
  if (openKey?.startsWith('slot:')) openValue = slots[openKey.slice(5)];
  else if (openKey === 'target') openValue = t?.count || t?.length || t?.until_row;
  else if (openKey === 'rep-rows') openValue = rep?.rows_in_repeat;
  else if (openKey === 'rep-times') openValue = rep?.times;
  else if (openKey === 'rep-until') openValue = rep?.until_row;
  else if (openKey === 'checkpoint') openValue = cp?.total;

  const lowConfidence = step.confidence === 'low';
  const page = step.source?.page;

  return (
    <li className={`gp-step ${na ? 'gp-step--na' : ''}`}>
      <span className="gp-step-no" aria-hidden="true">{index + 1}</span>
      <div className="gp-step-body">
        {(na || step.optional) && (
          <div className="gp-step-badges">
            {na && (
              <span className="gp-badge">
                {excluded.reason === 'choice' ? ft('notForChoice', { choice: excluded.label }) : ft('notForSize')}
              </span>
            )}
            {step.optional && <span className="gp-badge">{ft('optional')}</span>}
          </div>
        )}
        <p className="gp-step-text">{textNodes}</p>
        {facts.length > 0 && (
          <dl className="gp-facts">
            {facts.map(f => (
              <div key={f.key} className="gp-fact">
                <dt>{f.label}</dt>
                <dd>{f.node}</dd>
              </div>
            ))}
          </dl>
        )}
        {(step.schedules || []).map((sc, i) => (
          <Schedule key={i} schedule={sc} sel={sel} />
        ))}
        {openValue && <AllSizesList value={openValue} sizes={sizes} sel={sel} onClose={() => setOpenKey(null)} />}
        {lowConfidence && (
          <p className="gp-step-note">
            <Search size={16} aria-hidden="true" />
            <span>{page ? ft('checkPage', { page }) : ft('checkPattern')}</span>
          </p>
        )}
        {step.source?.from_picture && (
          <p className="gp-step-note">
            <ImageIcon size={16} aria-hidden="true" />
            <span>{page ? ft('fromPicturePage', { page }) : ft('fromPicture')}</span>
          </p>
        )}
      </div>
    </li>
  );
}

function Schedule({ schedule, sel }) {
  const slots = Object.fromEntries((schedule.slots || []).map(s => [s.name, s.value]));
  const parts = splitTemplate(schedule.action || '');
  const dropAfter = new Set();   // text parts straight after a slot shown in cm lose the template's "inches"
  const text = parts.map((p, i) => {
    if (p.kind === 'text') {
      const prev = parts[i - 1];
      const unit = dropAfter.has(i) && prev ? slots[prev.name]?.unit : null;
      return <MetricText key={i} text={unit ? stripUnitWord(p.text, unit) : p.text} />;
    }
    const v = slots[p.name];
    if (!v) return <React.Fragment key={i}>{`{${p.name}}`}</React.Fragment>;
    const r = resolve(v, sel);
    const conv = metricFor(v, r.state === 'value' ? r : { ...r, state: 'unchosen', text: v.text }, sel);
    if (conv) dropAfter.add(i + 1);
    return (
      <span key={i} className={`gp-num ${r.state !== 'value' ? 'gp-num--muted' : ''}`}>
        {conv ? <Metric conv={conv} /> : r.state === 'value' ? slotText(r, v, p.after) : tidy(v.text)}
      </span>
    );
  });
  const extra = [];
  const every = schedule.every ? resolve(schedule.every, sel) : null;
  if (every && (every.state === 'value' || every.state === 'unchosen')) {
    const unit = schedule.every_unit && schedule.every_unit !== 'other' ? ` ${schedule.every_unit}` : '';
    const conv = every.state === 'value' ? metricValue(every.text, schedule.every_unit) : null;
    extra.push(ft('everyN', { n: conv ? `${conv.main} (${conv.original})` : `${every.text}${every.state === 'value' ? unit : ''}` }));
  }
  const times = schedule.times ? resolve(schedule.times, sel) : null;
  if (times && (times.state === 'value' || times.state === 'unchosen')) extra.push(ft('timesN', { n: numbersOnly(times.text) }));
  return (
    <div className="gp-schedule">
      <span className="gp-schedule-label">{ft('atSameTime')}</span>
      <p>{text}{extra.length ? ` (${extra.join(', ')})` : ''}</p>
    </div>
  );
}

// ---------------------------------------------------------------- sections
function Section({ section, sizes, sel, open, onToggle }) {
  const [showOther, setShowOther] = useState(false);
  const steps = section.steps || [];
  const instances = section.instances || [];
  const id = `gp-sec-${section.id}`;
  // Steps written for another choice (another yarn weight, the other foot) are tucked away, not just greyed.
  const forOther = steps.map(step => stepState(step, sel, sizes).excluded?.reason === 'choice');
  const hiddenCount = showOther ? 0 : forOther.filter(Boolean).length;
  const otherLabel = forOther.some(Boolean)
    ? stepState(steps[forOther.indexOf(true)], sel, sizes).excluded.label : '';
  const shown = steps.length - forOther.filter(Boolean).length;
  return (
    <section className={`gp-section ${open ? 'gp-section--open' : ''}`}>
      <h3 className="gp-section-h">
        <button type="button" className="gp-section-toggle" aria-expanded={open} aria-controls={id} onClick={onToggle}>
          {open ? <ChevronDown size={22} aria-hidden="true" /> : <ChevronRight size={22} aria-hidden="true" />}
          <span className="gp-section-title">
            <span className="gp-section-name">{tidy(section.name)}</span>
            <span className="gp-section-meta">
              {shown === 1 ? ft('oneStep') : ft('stepsCount', { n: shown })}
              {instances.length > 1 && ` · ${ft('workedTimes', { n: instances.length, labels: instances.map(tidy).join(', ') })}`}
            </span>
          </span>
        </button>
      </h3>
      {open && (
        <div id={id} className="gp-section-body">
          {section.mirrored && instances.length > 1 && <p className="gp-section-note">{ft('mirrored')}</p>}
          <ol className="gp-steps">
            {steps.map((step, i) => (forOther[i] && !showOther ? null
              : <Step key={step.id || i} step={step} index={i} sizes={sizes} sel={sel} />))}
          </ol>
          {forOther.some(Boolean) && (
            <div className="gp-section-other">
              <span>{showOther ? ft('otherShown', { choice: otherLabel })
                : ft(hiddenCount === 1 ? 'otherHiddenOne' : 'otherHidden', { n: hiddenCount, choice: otherLabel })}</span>
              <button type="button" className="gp-btn gp-btn--ghost" onClick={() => setShowOther(v => !v)}>
                {showOther ? ft('hideOther') : ft('showOther')}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- materials
/** "31.5 stitches and 53 rounds = 10 cm" from a gauge given over inches. */
function gaugeText(per10) {
  const rowsWord = ft(per10.rowsUnit === 'rounds' ? 'gaugeRounds' : 'gaugeRows');
  if (per10.stitches && per10.rows) return ft('gaugePer10', { stitches: per10.stitches, rows: per10.rows, rowsWord });
  if (per10.stitches) return ft('gaugePer10St', { stitches: per10.stitches });
  return ft('gaugePer10Rows', { rows: per10.rows, rowsWord });
}

function Materials({ guide, sel, sizes }) {
  const yarns = (guide.yarns || []).filter(y => excludedBy(y.applies_to, sel, sizes)?.reason !== 'choice');
  const needles = (guide.needles || []).filter(n => excludedBy(n.applies_to, sel, sizes)?.reason !== 'choice');
  const gauges = (guide.gauge || []).filter(g => excludedBy(g.applies_to, sel, sizes)?.reason !== 'choice');
  const notions = (guide.notions || []).filter(n => excludedBy(n.applies_to, sel, sizes)?.reason !== 'choice');
  if (!yarns.length && !needles.length && !gauges.length && !notions.length) return null;

  const amount = (value) => {
    if (!value) return null;
    const r = resolve(value, sel);
    if (r.state === 'value') {
      const conv = metricFor(value, r, sel);
      return <span className="gp-num">{conv ? <Metric conv={conv} /> : withUnit(r.text, value)}</span>;
    }
    if (r.state === 'unchosen') return <span><MetricText text={value.text} /></span>;
    if (r.state === 'na') return <span>{ft('notThisSize')}</span>;
    return value.text ? <span><MetricText text={value.text} /></span> : null;
  };

  return (
    <section className="gp-card gp-materials" aria-labelledby="gp-materials-title">
      <h2 id="gp-materials-title" className="gp-h2">{ft('materials')}</h2>
      <div className="gp-materials-grid">
        {yarns.length > 0 && (
          <div className="gp-mat">
            <h3 className="gp-h3">{ft('yarn')}</h3>
            <ul className="gp-mat-list">
              {yarns.map(y => (
                <li key={y.id}>
                  <strong>{tidy(y.name)}</strong>
                  {[y.weight, y.fibre, y.colour, y.ball].filter(Boolean).length > 0 && (
                    <span className="gp-mat-sub"><MetricText text={[y.weight, y.fibre, y.colour, y.ball].filter(Boolean).map(tidy).join(' · ')} /></span>
                  )}
                  {y.amount && <span className="gp-mat-amount">{amount(y.amount)}</span>}
                  {y.alternatives_text && <span className="gp-mat-sub"><MetricText text={y.alternatives_text} /></span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {needles.length > 0 && (
          <div className="gp-mat">
            <h3 className="gp-h3">{ft('needles')}</h3>
            <ul className="gp-mat-list">
              {needles.map(n => {
                const len = n.length && (n.length.by_size || n.length.by_choice) ? resolve(n.length, sel) : null;
                const lenConv = len?.state === 'value' ? metricFor(n.length, len, sel, { cable: true }) : null;
                const size = needleSize(n);
                const sizeInText = size && !size.original && new RegExp(`^${size.main.replace('.', '[.,]').replace(' mm', '\\s*mm')}`, 'i').test(tidy(n.text));
                return (
                  <li key={n.id}>
                    {size && !sizeInText && <strong>{size.main}{size.original && <Orig text={size.original} />}</strong>}
                    <span className={size && !sizeInText ? 'gp-mat-sub' : undefined}><MetricText text={n.text} cable /></span>
                    {n.use && <span className="gp-mat-sub"><MetricText text={n.use} /></span>}
                    {len?.state === 'value' && (
                      <span className="gp-mat-amount">
                        <T k="length" vars={{ length: lenConv ? <Metric conv={lenConv} /> : withUnit(len.text, n.length) }} />
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        {gauges.length > 0 && (
          <div className="gp-mat">
            <h3 className="gp-h3">{ft('gauge')}</h3>
            <ul className="gp-mat-list">
              {gauges.map((g, i) => {
                const per10 = gaugeMetric(g);
                return (
                  <li key={i}>
                    {per10 && <strong>{gaugeText(per10)}</strong>}
                    <span className={per10 ? 'gp-mat-sub' : undefined}>{per10 ? `(${tidy(g.text)})` : <MetricText text={g.text} />}</span>
                    {g.condition && <span className="gp-mat-sub"><MetricText text={g.condition} /></span>}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        {notions.length > 0 && (
          <div className="gp-mat">
            <h3 className="gp-h3">{ft('otherThings')}</h3>
            <ul className="gp-mat-list">
              {notions.map((n, i) => (
                <li key={i}>
                  <span><MetricText text={n.text} /></span>
                  {n.amount && (n.amount.by_size || n.amount.by_choice) && <span className="gp-mat-amount">{amount(n.amount)}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- things to check
function Doubts({ doubts }) {
  const [showAll, setShowAll] = useState(false);
  if (!doubts?.length) return null;
  const shown = showAll ? doubts : doubts.slice(0, 3);
  return (
    <section className="gp-card gp-doubts" aria-labelledby="gp-doubts-title">
      <h2 id="gp-doubts-title" className="gp-h2 gp-h2--icon">
        <AlertTriangle size={22} aria-hidden="true" />
        {ft('thingsToCheck')}
      </h2>
      <p className="gp-muted">{ft('thingsToCheckHint')}</p>
      <ul className="gp-doubt-list">
        {shown.map((d, i) => <li key={i}>{tidy(d.message)}</li>)}
      </ul>
      {doubts.length > 3 && (
        <button type="button" className="gp-btn gp-btn--ghost" aria-expanded={showAll} onClick={() => setShowAll(v => !v)}>
          {showAll ? ft('showFewer') : ft('showAll', { n: doubts.length })}
        </button>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- size and choices
function SizePicker({ options, sel, sizeId, setSize, setChoice, measurements, pattern }) {
  const sizes = options?.sizes || [];
  const choices = options?.choices || [];
  const chosenSize = sel.sizeIdx != null ? sizes[sel.sizeIdx] : null;
  const missingChoice = choices.find(c => !sel.chosen[c.id]);
  const drops = isDrops(pattern);
  const metricPattern = /^cm/.test(pattern?.units_in_source || '');   // sizes with no unit are in cm
  const imperial = /^in/.test(pattern?.units_in_source || '');
  let explained = false;   // the DROPS note goes under the first half width only
  return (
    <section className="gp-card gp-picker" aria-labelledby="gp-size-title">
      <h2 id="gp-size-title" className="gp-h2">{ft('yourSize')}</h2>
      <div className="gp-chips" role="radiogroup" aria-labelledby="gp-size-title">
        {sizes.map(s => (
          <button key={s.id} type="button" role="radio" aria-checked={sizeId === s.id}
            className={`gp-chip ${sizeId === s.id ? 'gp-chip--on' : ''}`} onClick={() => setSize(s.id)}>
            {sizeId === s.id && <Check size={18} strokeWidth={3} aria-hidden="true" />}
            <span>{tidy(s.label)}</span>
          </button>
        ))}
      </div>
      {choices.map(c => (
        <div key={c.id} className="gp-choice">
          <h3 className="gp-h3" id={`gp-choice-${c.id}`}>{tidy(c.name).replace(/^./, ch => ch.toUpperCase())}</h3>
          <div className="gp-chips" role="radiogroup" aria-labelledby={`gp-choice-${c.id}`}>
            {c.values.map(v => {
              const on = sel.chosen[c.id] === v.id;
              return (
                <button key={v.id} type="button" role="radio" aria-checked={on}
                  className={`gp-chip ${on ? 'gp-chip--on' : ''}`} onClick={() => setChoice(c.id, v.id)}>
                  {on && <Check size={18} strokeWidth={3} aria-hidden="true" />}
                  <span>{tidy(v.label)}</span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
      {!chosenSize && <p className="gp-prompt">{ft('chooseSize')}</p>}
      {chosenSize && missingChoice && <p className="gp-prompt">{ft('chooseChoice', { name: tidy(missingChoice.name) })}</p>}
      {chosenSize && !missingChoice && (
        <p className="gp-muted">{ft('sizeChosen', { size: tidy(chosenSize.label) })} {ft('tapNumber')}</p>
      )}
      {chosenSize && measurements.length > 0 && (
        <dl className="gp-measure">
          {measurements.map((m, i) => {
            const r = resolve(m.value, sel);
            if (r.state !== 'value') return null;
            const conv = metricFor(m.value, r, sel);
            const shown = conv ? <Metric conv={conv} /> : withUnit(r.text, m.value, metricPattern ? 'cm' : '');
            const half = drops && !conv && isHalfWidth(m.name) && (!m.value.unit || m.value.unit === 'cm')
              ? doubled(r.text) : null;
            const explain = half && !explained;
            if (half) explained = true;
            return (
              <div key={i} className={half ? 'gp-measure-half' : undefined}>
                <dt>{tidy(m.name)}</dt>
                <dd>
                  {shown}
                  {half && <span className="gp-measure-round">{ft('dropsRound', { n: half })}</span>}
                </dd>
                {explain && <p className="gp-measure-note">{ft('dropsHalfNote')}</p>}
              </div>
            );
          })}
        </dl>
      )}
      {chosenSize && imperial && <p className="gp-muted gp-metric-note">{ft('shownInCm')}</p>}
    </section>
  );
}

// ---------------------------------------------------------------- the whole view
export default function GuideView({ recipeId, recipe, guideRow, canRemake, building, onRemake, remakeError }) {
  const guide = guideRow.guide || {};
  const options = guide.options || { sizes: [], choices: [] };
  const sizes = options.sizes || [];
  const { sel, sizeId, setSize, setChoice } = useSelection(recipeId, options);
  const sections = guide.sections || [];
  const [openSections, setOpenSections] = useState(() => new Set(sections.slice(0, 1).map(s => s.id)));
  const [confirmRemake, setConfirmRemake] = useState(false);
  const [remaking, setRemaking] = useState(false);
  const measurements = useMemo(() => guide.size_guide?.measurements || [], [guide]);

  const title = tidy(guide.pattern?.title) || recipe?.title || '';
  const designer = tidy(guide.pattern?.designer);
  const allOpen = sections.length > 0 && sections.every(s => openSections.has(s.id));

  const toggle = (id) => setOpenSections(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const remake = async () => {
    setRemaking(true);
    try {
      if (await onRemake()) setConfirmRemake(false);
    } finally {
      setRemaking(false);
    }
  };

  return (
    <div className="gp-guide">
      <header className="gp-card gp-header">
        <div className="gp-header-text">
          <h2 className="gp-title">{title}</h2>
          {designer && <p className="gp-muted">{ft('byDesigner', { designer })}</p>}
          <p className="gp-version">{ft('versionMade', { version: guideRow.version, date: formatDate(guideRow.built_at) })}</p>
          {guideRow.review_state !== 'checked' && <p className="gp-muted">{ft('notCheckedYet')}</p>}
        </div>
        {canRemake && !building && !confirmRemake && (
          <button type="button" className="gp-btn gp-btn--secondary gp-header-btn" onClick={() => setConfirmRemake(true)}>
            <RefreshCw size={18} aria-hidden="true" />
            {ft('makeAgain')}
          </button>
        )}
        {canRemake && !building && confirmRemake && (
          <div className="gp-confirm gp-header-confirm" role="group" aria-label={ft('makeAgain')}>
            <p>{ft('makeAgainConfirm')}</p>
            <div className="gp-actions">
              <button type="button" className="gp-btn gp-btn--primary" onClick={remake} disabled={remaking}>
                {remaking ? ft('starting') : ft('makeAgainYes')}
              </button>
              <button type="button" className="gp-btn gp-btn--secondary" onClick={() => setConfirmRemake(false)}>{ft('cancel')}</button>
            </div>
            {remakeError && <p className="gp-note gp-note--warn" role="alert">{remakeError}</p>}
          </div>
        )}
      </header>

      <div className="gp-layout">
        <div className="gp-aside">
          <SizePicker options={options} sel={sel} sizeId={sizeId} setSize={setSize} setChoice={setChoice}
            measurements={measurements} pattern={guide.pattern} />
          <Doubts doubts={guide.doubts} />
          <Materials guide={guide} sel={sel} sizes={sizes} />
        </div>
        <div className="gp-main">
          {sections.length > 1 && (
            <div className="gp-sections-tools">
              <button type="button" className="gp-btn gp-btn--ghost"
                onClick={() => setOpenSections(allOpen ? new Set() : new Set(sections.map(s => s.id)))}>
                {allOpen ? ft('closeAll') : ft('openAll')}
              </button>
            </div>
          )}
          {sections.map(section => (
            <Section key={section.id} section={section} sizes={sizes} sel={sel}
              open={openSections.has(section.id)} onToggle={() => toggle(section.id)} />
          ))}
        </div>
      </div>
    </div>
  );
}
