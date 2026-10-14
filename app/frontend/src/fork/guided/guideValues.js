// Helpers that pick the right number from a guide (format 0.2) for the chosen size and choices.
// Values are shown exactly as the pattern writes them; nothing is converted or worked out here.

const UNIT_WORDS = {
  stitches: 'stitches', rows: 'rows', rounds: 'rounds', row_pairs: 'pairs of rows', repeats: 'times', times: 'times',
  cm: 'cm', mm: 'mm', in: 'in', m: 'm', yd: 'yd', g: 'g', oz: 'oz', balls: 'balls', skeins: 'skeins', pieces: 'pieces',
};

/** Tidy the line breaks copied from the PDF into ordinary spaces. */
export function tidy(text) {
  return String(text ?? '').replace(/\s*\n\s*/g, ' ').replace(/\s{2,}/g, ' ').trim();
}

/** The word written after the numbers in the pattern, e.g. "sts" in "96 (104) sts", or '' when there is none. */
export function trailingUnit(text) {
  const t = tidy(text);
  const m = t.match(/[\d½¼¾⅓⅔)\]]\s*([A-Za-z"”'’.]+(?:\s[A-Za-z.]+)?)\s*$/);
  if (!m) return '';
  const word = m[1].replace(/\.$/, '');
  return word.length <= 12 ? word : '';
}

/** The numbers part of a value as written, without the unit word at the end. */
export function numbersOnly(text) {
  const t = tidy(text);
  const unit = trailingUnit(t);
  return unit ? t.slice(0, t.lastIndexOf(unit)).trim() : t;
}

function hasDigit(text) {
  return /[\d½¼¾]/.test(String(text ?? ''));
}

const MEASURES = new Set(['cm', 'mm', 'in', 'm', 'yd', 'g', 'oz']);
const SAME_UNIT = { in: ['in', 'inch', '"', '”', "''"], cm: ['cm'], mm: ['mm'], m: ['m ', 'm.', 'm,', 'metre', 'meter'],
  yd: ['yd', 'yard'], g: ['g ', 'g.', 'g,', 'gram'], oz: ['oz', 'ounce'] };

/** The unit to write after a single value: the guide's own unit for measurements (the pattern text may give two
 *  units), otherwise as the pattern writes it, else from the unit field, else the fallback. */
export function unitFor(value, fallback = '') {
  if (!value) return fallback;
  if (MEASURES.has(value.unit)) return UNIT_WORDS[value.unit];
  return trailingUnit(value.text) || UNIT_WORDS[value.unit] || fallback;
}

/** A value for the chosen size with its unit, e.g. "28 rounds" or "30 cm". Words like "twice" are left alone. */
export function withUnit(text, value, fallback = '') {
  if (!hasDigit(text)) return text;
  const unit = unitFor(value, fallback);
  if (!unit) return text;
  if (/^["”'’]$/.test(unit)) return `${text}${unit}`;
  return `${text} ${String(text).trim() === '1' ? (SINGULAR[unit] || unit) : unit}`;
}

const SINGULAR = { rows: 'row', rounds: 'round', stitches: 'stitch', times: 'time', repeats: 'repeat', balls: 'ball',
  skeins: 'skein', pieces: 'piece', 'pairs of rows': 'pair of rows' };

/** "Ending with a WS row" reads better as "ending with a WS row" after a comma. */
export function lowerFirst(text) {
  const t = tidy(text);
  return /^[A-Z][a-z]/.test(t) ? t[0].toLowerCase() + t.slice(1) : t;
}

function choiceGroupOf(choiceValueId, choices) {
  return (choices || []).find(c => (c.values || []).some(v => v.id === choiceValueId)) || null;
}

function choiceLabel(choiceValueId, choices) {
  for (const c of choices || []) {
    const v = (c.values || []).find(x => x.id === choiceValueId);
    if (v) return v.label;
  }
  return choiceValueId;
}

/**
 * Resolve a sized value for the selection.
 * sel = { sizeIdx: number|null, chosen: {choiceId: valueId}, choices: options.choices }
 * Returns { state, text, perSize } where state is:
 *   'value'     the value to show (text);
 *   'unchosen'  no size (or choice) chosen yet: text is the pattern's text with every size;
 *   'na'        "-": does not apply to this size;
 *   'na-choice' only given for another choice; label names the chosen one;
 *   'missing'   the pattern gives none.
 */
export function resolve(value, sel) {
  if (!value) return { state: 'missing', text: '', perSize: false };
  const raw = tidy(value.text);
  if (value.all != null && value.all !== '') return { state: 'value', text: tidy(value.all), perSize: false };
  let list = null;
  if (Array.isArray(value.by_size)) {
    list = value.by_size;
  } else if (Array.isArray(value.by_choice) && value.by_choice.length) {
    const chosenIds = Object.values(sel.chosen || {});
    const entry = value.by_choice.find(e => chosenIds.includes(e.choice));
    if (!entry) {
      const group = choiceGroupOf(value.by_choice[0].choice, sel.choices);
      const picked = group ? sel.chosen?.[group.id] : null;
      if (picked) return { state: 'na-choice', text: raw, perSize: true, label: choiceLabel(picked, sel.choices) };
      return { state: 'unchosen', text: raw, perSize: true };
    }
    list = entry.by_size;
  }
  if (!list) return { state: 'missing', text: raw, perSize: false };
  if (sel.sizeIdx == null) return { state: 'unchosen', text: raw, perSize: true };
  const v = list[sel.sizeIdx];
  if (v === '-') return { state: 'na', text: raw, perSize: true };
  if (v == null || v === '') return { state: 'missing', text: raw, perSize: true };
  return { state: 'value', text: tidy(v), perSize: true };
}

/** Every size's value, for the "all sizes" list. Rows: [{label, value, chosen, choiceLabel}] */
export function allSizes(value, sizes, sel) {
  if (!value) return [];
  const rows = [];
  const add = (list, groupLabel) => {
    (sizes || []).forEach((s, i) => {
      rows.push({ key: `${groupLabel || ''}-${s.id}`, size: s.label, group: groupLabel, value: list?.[i] ?? null,
        chosen: sel.sizeIdx === i });
    });
  };
  if (Array.isArray(value.by_size)) {
    add(value.by_size, null);
  } else if (Array.isArray(value.by_choice)) {
    const chosenIds = Object.values(sel.chosen || {});
    const entries = value.by_choice.filter(e => chosenIds.includes(e.choice));
    (entries.length ? entries : value.by_choice).forEach(e => add(e.by_size, choiceLabel(e.choice, sel.choices)));
  }
  return rows;
}

/** Whether something marked with applies_to is for the selection: null (it is) or {reason, label}. */
export function excludedBy(appliesTo, sel, sizes) {
  if (!appliesTo) return null;
  const sizeId = sel.sizeIdx != null ? sizes?.[sel.sizeIdx]?.id : null;
  const chosenIds = Object.values(sel.chosen || {});
  if (sizeId && Array.isArray(appliesTo.sizes) && !appliesTo.sizes.includes(sizeId)) return { reason: 'size' };
  if (Array.isArray(appliesTo.choices) && appliesTo.choices.length) {
    const group = choiceGroupOf(appliesTo.choices[0], sel.choices);
    const picked = group ? sel.chosen?.[group.id] : null;
    if (picked && !appliesTo.choices.includes(picked)) return { reason: 'choice', label: choiceLabel(picked, sel.choices) };
  }
  for (const ex of appliesTo.except || []) {
    if (ex.size == null && ex.choice == null) continue;
    const sizeMatch = ex.size == null || (sizeId != null && ex.size === sizeId);
    const choiceMatch = ex.choice == null || chosenIds.includes(ex.choice);
    if (sizeMatch && choiceMatch) {
      return ex.choice ? { reason: 'choice', label: choiceLabel(ex.choice, sel.choices) } : { reason: 'size' };
    }
  }
  return null;
}

/** Split step text into plain parts and {slot} parts. */
export function splitTemplate(text) {
  const parts = [];
  const re = /\{([A-Za-z0-9_-]+)\}/g;
  const src = tidy(text);
  let last = 0;
  let m;
  while ((m = re.exec(src))) {
    if (m.index > last) parts.push({ kind: 'text', text: src.slice(last, m.index) });
    parts.push({ kind: 'slot', name: m[1], after: src.slice(m.index + m[0].length) });
    last = m.index + m[0].length;
  }
  if (last < src.length) parts.push({ kind: 'text', text: src.slice(last) });
  return parts;
}

/**
 * The text for a slot inside a sentence. Adds the unit only when the sentence does not already say it
 * (e.g. "measures {length}." becomes "measures 5 cm." but "Cast on {n} sts" stays as it is).
 */
export function slotText(resolved, value, after) {
  const text = resolved.text;
  if (resolved.state !== 'value' || !hasDigit(text)) return text;
  const next = `${String(after || '').trimStart().toLowerCase()} `;
  if (MEASURES.has(value?.unit)) {
    const unit = UNIT_WORDS[value.unit];
    const already = (SAME_UNIT[value.unit] || [unit]).some(u => next.startsWith(u));
    return already ? text : `${text} ${unit}`;
  }
  const unit = trailingUnit(value?.text) || '';
  if (!unit) return text;
  const u = unit.toLowerCase();
  const stitchy = /^(sts?|stitch(es)?)$/.test(u) && /^st/.test(next);
  if (next.startsWith(u) || stitchy) return text;
  return /^["”'’]$/.test(unit) ? `${text}${unit}` : `${text} ${unit}`;
}
