// Ball details on the yarn page, in the page's own spec-row style, with an Edit button. Shows nothing while the
// stash in grams is switched off. Fork-only (FORK.md).
import { useEffect, useState } from 'react';
import { Pencil, Plus } from 'lucide-react';
import { ft } from '../strings';
import { getYarnSpec } from '../forkApi';
import { useStashStatus, onSpecSaved } from './stashStore';
import { formatNumber } from './stashNumbers';
import { BallDetailsDialog } from './StashDialogs';
import './Stash.css';

export default function BallDetailsSection({ yarnId, yarnName }) {
  const status = useStashStatus();
  if (!status?.enabled || !yarnId) return null;
  return <Section yarnId={yarnId} yarnName={yarnName} />;
}

function rows(spec) {
  if (!spec) return [];
  const out = [];
  const n = (v) => formatNumber(v);
  if (spec.grams_per_ball != null) out.push(['⚖️', ft('gramsPerBall'), ft('gramsValue', { n: n(spec.grams_per_ball) })]);
  if (spec.metres_per_ball != null) out.push(['📏', ft('metresPerBall'), ft('metresValue', { n: n(spec.metres_per_ball) })]);
  if (spec.weight) out.push(['🧶', ft('yarnWeight'), spec.weight]);
  if (spec.fibre) out.push(['🐑', ft('fibre'), spec.fibre]);
  if (spec.needle_mm_min != null) {
    const one = spec.needle_mm_max == null || spec.needle_mm_max === spec.needle_mm_min;
    out.push(['🪡', ft('needleSize'), one ? ft('needleOne', { mm: n(spec.needle_mm_min) })
      : ft('needleRange', { from: n(spec.needle_mm_min), to: n(spec.needle_mm_max) })]);
  }
  if (spec.gauge_stitches != null || spec.gauge_rows != null) {
    const over = spec.gauge_over_cm || 10;
    const st = spec.gauge_stitches != null ? n((spec.gauge_stitches * 10) / over) : null;
    const rw = spec.gauge_rows != null ? n((spec.gauge_rows * 10) / over) : null;
    const text = st && rw ? ft('tensionText', { stitches: st, rows: rw })
      : st ? ft('tensionStitches', { stitches: st }) : ft('tensionRows', { rows: rw });
    out.push(['📐', ft('tensionLabel'), text]);
  }
  if (spec.care) out.push(['🧺', ft('care'), spec.care]);
  return out;
}

function Section({ yarnId, yarnName }) {
  const [spec, setSpec] = useState(undefined);   // undefined while loading, null when there is none
  const [editing, setEditing] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => onSpecSaved((id) => { if (id === yarnId) setVersion((v) => v + 1); }), [yarnId]);

  useEffect(() => {
    let alive = true;
    getYarnSpec(yarnId).then((res) => { if (alive) setSpec(res.spec || null); }).catch(() => { if (alive) setSpec(null); });
    return () => { alive = false; };
  }, [yarnId, version]);

  if (spec === undefined) return null;
  const list = rows(spec);
  return (
    <div className="st-yv-section">
      <div className="st-yv-head">
        <h3 className="yv-section-title">{ft('ballDetails')}</h3>
        <button type="button" className="st-btn st-btn--small st-btn--secondary" onClick={() => setEditing(true)}>
          {list.length ? <Pencil size={16} aria-hidden="true" /> : <Plus size={16} aria-hidden="true" />}
          {list.length ? ft('editBallDetails') : ft('addBallDetails')}
        </button>
      </div>
      {list.length ? (
        <div className="yv-specs">
          {list.map(([icon, label, value]) => (
            <div className="yv-spec-row" key={label}>
              <span className="yv-spec-icon">{icon}</span>
              <span className="yv-spec-label">{label}</span>
              <span className="yv-spec-value">{value}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="st-hint">{ft('noBallDetails')} {ft('ballDetailsHint')}</p>
      )}
      {editing && (
        <BallDetailsDialog yarnId={yarnId} yarnName={yarnName} onClose={() => setEditing(false)} onSaved={(s) => setSpec(s || null)} />
      )}
    </div>
  );
}
