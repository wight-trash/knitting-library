// Numbers and ball details for the stash in grams. Fork-only (FORK.md).
import { ft } from '../strings';

const FRACTIONS = { '½': 0.5, '¼': 0.25, '¾': 0.75 };

/** A number typed by a knitter: "50", "4,5", "4.5", "4½". null when empty, NaN when it is not a number. */
export function parseNumber(text) {
  if (text == null) return null;
  if (typeof text === 'number') return Number.isFinite(text) ? text : NaN;
  let s = String(text).trim().replace(/\s+/g, '');
  if (!s) return null;
  let extra = 0;
  const last = s.slice(-1);
  if (FRACTIONS[last] != null) { extra = FRACTIONS[last]; s = s.slice(0, -1); if (!s) return extra; }
  s = s.replace(',', '.');
  if (!/^\d+(\.\d+)?$|^\.\d+$/.test(s)) return NaN;
  return Number(s) + extra;
}

/** 4.5 -> "4.5", 50 -> "50", 4.333 -> "4.33" */
export function formatNumber(n, digits = 2) {
  if (n == null || Number.isNaN(Number(n))) return '';
  return String(Number(Number(n).toFixed(digits)));
}

/** Grams as shown: whole grams from 10 g up, one decimal below. */
export function formatGrams(g) {
  if (g == null) return '';
  const abs = Math.abs(g);
  return abs >= 10 ? String(Math.round(g)) : formatNumber(g, 1);
}

/** "4.3 balls · 215 g" (grams known) or "4 balls" (whole balls only). */
export function amountText(balls, grams) {
  if (grams != null) {
    const b = formatNumber(balls ?? 0, 1);
    return ft(Number(b) === 1 ? 'oneBallAndGrams' : 'ballsAndGrams', { balls: b, grams: formatGrams(grams) });
  }
  const n = Number(balls ?? 0);
  return n === 1 ? ft('oneBall') : ft('ballsOnly', { balls: formatNumber(n, 1) });
}

// Craft Yarn Council categories for plain weight names (the same table as the server's ballband.py).
const WEIGHT_NAMES = [
  [/super\s*(?:bulky|chunky)|roving/, 6], [/jumbo/, 7], [/lace|cobweb|thread/, 0],
  [/fingering|sock|4[\s-]?ply|super\s*fine|baby/, 1], [/sport|5[\s-]?ply/, 2],
  [/light\s*worsted|\bdk\b|double\s*knit|8[\s-]?ply/, 3], [/worsted|aran|afghan|10[\s-]?ply/, 4],
  [/chunky|bulky|12[\s-]?ply|craft|rug/, 5],
];

export function weightCategory(text) {
  const s = (text || '').toLowerCase();
  if (!s || s.includes('drops') || s.includes('group')) return null;
  for (const [rx, cat] of WEIGHT_NAMES) if (rx.test(s)) return cat;
  return null;
}

export const WEIGHT_SUGGESTIONS = [
  'Lace', '4-ply', 'Sport', 'DK', 'Aran', 'Chunky', 'Super chunky',
  'DROPS group A', 'DROPS group B', 'DROPS group C', 'DROPS group D', 'DROPS group E', 'DROPS group F',
];

// The form's text boxes, and the spec fields they come from.
export const EMPTY_BALL_FORM = {
  grams_per_ball: '', metres_per_ball: '', weight: '', fibre: '',
  needle_from: '', needle_to: '', gauge_stitches: '', gauge_rows: '', care: '',
};

const NUMBER_FIELDS = {
  grams_per_ball: 'gramsPerBall', metres_per_ball: 'metresPerBall',
  needle_from: 'needleFrom', needle_to: 'needleTo', gauge_stitches: 'stitches', gauge_rows: 'rows',
};

const show = (n) => (n == null ? '' : formatNumber(n));

export function specToForm(spec) {
  if (!spec) return { ...EMPTY_BALL_FORM };
  const over = spec.gauge_over_cm || 10;
  const per10 = (n) => (n == null ? null : (n * 10) / over);
  return {
    grams_per_ball: show(spec.grams_per_ball),
    metres_per_ball: show(spec.metres_per_ball),
    weight: spec.weight || '',
    fibre: spec.fibre || '',
    needle_from: show(spec.needle_mm_min),
    needle_to: spec.needle_mm_max != null && spec.needle_mm_max !== spec.needle_mm_min ? show(spec.needle_mm_max) : '',
    gauge_stitches: show(per10(spec.gauge_stitches)),
    gauge_rows: show(per10(spec.gauge_rows)),
    care: spec.care || '',
  };
}

/** { spec } ready for PUT .../spec, or { error } with a plain message. Empty boxes clear their field. */
export function formToSpec(form) {
  const nums = {};
  for (const [key, label] of Object.entries(NUMBER_FIELDS)) {
    const n = parseNumber(form[key]);
    if (Number.isNaN(n) || (n != null && n <= 0)) return { error: ft('notANumber', { label: ft(label) }) };
    nums[key] = n;
  }
  const weight = (form.weight || '').trim();
  const from = nums.needle_from ?? nums.needle_to;
  const to = nums.needle_to ?? nums.needle_from;
  const spec = {
    grams_per_ball: nums.grams_per_ball,
    metres_per_ball: nums.metres_per_ball,
    weight: weight || null,
    weight_category: weightCategory(weight),
    fibre: (form.fibre || '').trim() || null,
    needle_mm_min: from == null ? null : Math.min(from, to),
    needle_mm_max: to == null ? null : Math.max(from, to),
    gauge_stitches: nums.gauge_stitches,
    gauge_rows: nums.gauge_rows,
    gauge_over_cm: nums.gauge_stitches != null || nums.gauge_rows != null ? 10 : null,
    care: (form.care || '').trim() || null,
  };
  return { spec };
}

export function formIsEmpty(form) {
  return Object.keys(EMPTY_BALL_FORM).every((k) => !String(form[k] ?? '').trim());
}

export function sameForm(a, b) {
  return Object.keys(EMPTY_BALL_FORM).every((k) => String(a[k] ?? '').trim() === String(b[k] ?? '').trim());
}
