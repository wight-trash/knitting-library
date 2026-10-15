// The "Ball details" boxes: grams and metres per ball, weight, fibre, needle, tension and care. Fork-only (FORK.md).
// value: the form's text (see EMPTY_BALL_FORM); onChange(key, text); checks: keys to mark "Please check";
// bandText: what the ball band said, shown under a box ({ key: "120 yds" }).
import { useId } from 'react';
import { ft } from '../strings';
import { WEIGHT_SUGGESTIONS } from './stashNumbers';
import './Stash.css';

export default function BallDetailsFields({ value, onChange, checks = {}, bandText = {}, heading = true }) {
  const id = useId();
  const box = (key, label, props = {}, badge = true) => (
    <BallField id={`${id}-${key}`} label={label} check={badge && checks[key]} band={bandText[key]}>
      <input
        id={`${id}-${key}`}
        className={`st-input ${checks[key] ? 'st-input--check' : ''}`}
        value={value[key] ?? ''}
        onChange={(e) => onChange(key, e.target.value)}
        autoComplete="off"
        {...props}
      />
    </BallField>
  );
  const num = { inputMode: 'decimal', enterKeyHint: 'next' };

  return (
    <section className="st-ball-fields" aria-labelledby={heading ? `${id}-h` : undefined}>
      {heading && (
        <div className="st-ball-head">
          <h3 id={`${id}-h`} className="st-h3">{ft('ballDetails')}</h3>
          <p className="st-hint">{ft('ballDetailsHint')}</p>
        </div>
      )}
      <div className="st-grid">
        {box('grams_per_ball', ft('gramsPerBall'), { ...num, placeholder: '50' })}
        {box('metres_per_ball', ft('metresPerBall'), { ...num, placeholder: '110' })}
        {box('weight', ft('yarnWeight'), { list: `${id}-weights`, placeholder: ft('yarnWeightPlaceholder'), autoCapitalize: 'sentences' })}
        {box('fibre', ft('fibre'), { placeholder: ft('fibrePlaceholder'), autoCapitalize: 'sentences' })}
      </div>
      <datalist id={`${id}-weights`}>
        {WEIGHT_SUGGESTIONS.map((w) => <option key={w} value={w} />)}
      </datalist>

      <fieldset className={`st-fieldset ${checks.needle ? 'st-fieldset--check' : ''}`}>
        <legend className="st-label">
          {ft('needleSize')}
          {checks.needle && <CheckBadge />}
        </legend>
        <div className="st-pair">
          {box('needle_from', ft('needleFrom'), { ...num, placeholder: '4' }, false)}
          {box('needle_to', ft('needleTo'), { ...num, placeholder: '4,5' }, false)}
        </div>
        {bandText.needle && <p className="st-band-text">{ft('onTheBand', { text: bandText.needle })}</p>}
      </fieldset>

      <fieldset className={`st-fieldset ${checks.gauge ? 'st-fieldset--check' : ''}`}>
        <legend className="st-label">
          {ft('tension')}
          {checks.gauge && <CheckBadge />}
        </legend>
        <div className="st-pair">
          {box('gauge_stitches', ft('stitches'), { ...num, placeholder: '22' }, false)}
          {box('gauge_rows', ft('rows'), { ...num, placeholder: '28' }, false)}
        </div>
        {bandText.gauge && <p className="st-band-text">{ft('onTheBand', { text: bandText.gauge })}</p>}
      </fieldset>

      <BallField id={`${id}-care`} label={ft('care')} check={checks.care} band={bandText.care}>
        <textarea
          id={`${id}-care`}
          className={`st-input st-textarea ${checks.care ? 'st-input--check' : ''}`}
          value={value.care ?? ''}
          onChange={(e) => onChange('care', e.target.value)}
          placeholder={ft('carePlaceholder')}
          rows={2}
        />
      </BallField>
    </section>
  );
}

function BallField({ id, label, check, band, children }) {
  return (
    <div className="st-field">
      <label className="st-label" htmlFor={id}>
        {label}
        {check && <CheckBadge />}
      </label>
      {children}
      {band && <p className="st-band-text">{ft('onTheBand', { text: band })}</p>}
    </div>
  );
}

export function CheckBadge() {
  return <span className="st-check-badge">{ft('pleaseCheck')}</span>;
}
