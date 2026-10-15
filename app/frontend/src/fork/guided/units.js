// Numbers and units as knitting patterns write them, for showing a guide in centimetres.
// A port of the parts of app/backend/app/guide_builder/units.py the Guided tab needs. Pure functions, no React.
// Guides keep every value as the pattern wrote it; this module only works out what to show beside it.
// The owner's rule: cm by default, so a pattern in inches (or yards, or ounces) shows metric first and the
// pattern's own value in small text. Fork-only (FORK.md).

export const FRACTIONS = {
  '½': 0.5, '¼': 0.25, '¾': 0.75, '⅓': 1 / 3, '⅔': 2 / 3, '⅕': 0.2, '⅖': 0.4, '⅗': 0.6, '⅘': 0.8,
  '⅙': 1 / 6, '⅚': 5 / 6, '⅛': 0.125, '⅜': 0.375, '⅝': 0.625, '⅞': 0.875,
};
const FRAC = Object.keys(FRACTIONS).join('');
const INCH_MARKS = '"”″“\'’';
const DASHES = '\\-–—−';   // for character classes: the hyphen is escaped

const WORDS = {
  zero: 0, one: 1, once: 1, two: 2, twice: 2, three: 3, thrice: 3, four: 4, five: 5, six: 6, seven: 7,
  eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16,
  seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20, thirty: 30, forty: 40, fifty: 50,
};

const NUM_RE = new RegExp(`^(\\d+)?(?:([.,])(\\d+))?(?:\\s*([${FRAC}])|\\s+(\\d+)\\s*/\\s*(\\d+))?$`);
const SLASH_RE = /^(\d+)\s*\/\s*(\d+)$/;
const ORDINAL_RE = /^(\d+)(?:st|nd|rd|th|\.)$/i;

/** A single number as a pattern writes it, or null: "4½" 4.5, "4,5" 4.5, "17 ½" 17.5, "1/2" 0.5, "1 1/2" 1.5,
 *  "three" 3, "1,240" 1240 (three digits after a comma are a thousands separator). A range gives null. */
export function parseNumber(s) {
  if (s == null) return null;
  let t = String(s).trim();
  while (t && INCH_MARKS.includes(t[t.length - 1])) t = t.slice(0, -1);
  t = t.trim();
  if (!t) return null;
  const low = t.toLowerCase();
  if (low in WORDS) return WORDS[low];
  let m = t.match(ORDINAL_RE);
  if (m) return Number(m[1]);
  m = t.match(SLASH_RE);
  if (m) return Number(m[2]) ? Number(m[1]) / Number(m[2]) : null;
  m = t.match(NUM_RE);
  if (!m || !(m[1] || m[4])) return null;
  const [, int, sep, dec, frac, num, den] = m;
  if (dec != null && int == null) return null;
  let value = Number(int || 0);
  if (dec != null) {
    if (sep === ',' && dec.length === 3 && int && int !== '0') value = value * 1000 + Number(dec);
    else value += Number(`0.${dec}`);
  }
  if (frac) value += FRACTIONS[frac];
  else if (num != null) {
    if (!Number(den)) return null;
    value += Number(num) / Number(den);
  }
  return value;
}

const RANGE_RE = new RegExp(`^(.+?)\\s*(?:[${DASHES}]|\\bto\\b)\\s*([^${DASHES}]+)$`, 'i');

/** "65-70" [65, 70], "4 to 5" [4, 5]; a single number x gives [x, x]; anything else null. */
export function parseRange(s) {
  if (s == null) return null;
  const t = String(s).trim();
  const single = parseNumber(t);
  if (single != null) return [single, single];
  const m = t.match(RANGE_RE);
  if (!m) return null;
  const a = parseNumber(m[1]);
  const b = parseNumber(m[2]);
  return a == null || b == null ? null : [a, b];
}

const unitKey = (unit) => String(unit || '').trim().toLowerCase().replace(/\.$/, '');

const CM = {
  cm: 1, cms: 1, centimetre: 1, centimetres: 1, centimeter: 1, centimeters: 1,
  mm: 0.1, millimetre: 0.1, millimetres: 0.1, millimeter: 0.1, millimeters: 0.1,
  m: 100, metre: 100, metres: 100, meter: 100, meters: 100,
  in: 2.54, ins: 2.54, inch: 2.54, inches: 2.54, '"': 2.54, '”': 2.54, '″': 2.54, '“': 2.54,
  yd: 91.44, yds: 91.44, yard: 91.44, yards: 91.44,
};
const METRES = {
  m: 1, metre: 1, metres: 1, meter: 1, meters: 1, mtr: 1, mtrs: 1,
  yd: 0.9144, yds: 0.9144, yard: 0.9144, yards: 0.9144, cm: 0.01, km: 1000,
};
const GRAMS = {
  g: 1, gr: 1, gram: 1, grams: 1, gramme: 1, grammes: 1, kg: 1000,
  oz: 28.3495, ozs: 28.3495, ounce: 28.3495, ounces: 28.3495,
};

const factor = (table) => (value, unit) => {
  const f = table[unitKey(unit)];
  return f == null || value == null ? null : value * f;
};
/** A length in cm (inches, cm, mm, m, yards); null for an unknown unit. */
export const toCm = factor(CM);
/** A yarn length in metres (yards or metres); null for an unknown unit. */
export const toMetres = factor(METRES);
/** A weight in grams (ounces or grams); null for an unknown unit. */
export const toGrams = factor(GRAMS);

const roundHalfUp = (x) => Math.floor(x + 0.5);
const plain = (x) => (Number.isInteger(x) ? String(x) : String(Number(x.toFixed(2))));

/** Knitter-friendly cm: under 10 cm to the nearest 0.5, otherwise whole. 4.4 "4.5", 4.0 "4", 26.67 "27". */
export function displayCm(cm) {
  if (cm < 10) {
    const v = roundHalfUp(cm * 2 + 1e-9) / 2;
    return v >= 10 ? '10' : plain(v);
  }
  return plain(roundHalfUp(cm + 1e-9));
}

/** To the whole number (metres, grams). */
export function displayWhole(x) {
  return plain(roundHalfUp(x + 1e-9));
}

/** To the nearest 0.5 (stitches per 10 cm). */
export function displayHalf(x) {
  return plain(roundHalfUp(x * 2 + 1e-9) / 2);
}

// ---------------------------------------------------------------- needles
// US sizes: the Craft Yarn Council chart (where makers disagree, the CYC value). UK sizes run the other way.
export const US_NEEDLE_MM = {
  '0000': 1.25, '000': 1.5, '00': 1.75, 0: 2.0, 1: 2.25, 1.5: 2.5, 2: 2.75, 2.5: 3.0, 3: 3.25,
  4: 3.5, 5: 3.75, 6: 4.0, 7: 4.5, 8: 5.0, 9: 5.5, 10: 6.0, 10.5: 6.5, 10.75: 7.0,
  11: 8.0, 13: 9.0, 15: 10.0, 17: 12.75, 19: 15.0, 35: 19.0, 50: 25.0,
};
export const UK_NEEDLE_MM = {
  14: 2.0, 13: 2.25, 12: 2.75, 11: 3.0, 10: 3.25, 9: 3.75, 8: 4.0, 7: 4.5, 6: 5.0,
  5: 5.5, 4: 6.0, 3: 6.5, 2: 7.0, 1: 7.5, 0: 8.0, '00': 9.0, '000': 10.0,
};

function sizeToken(text) {
  const m = String(text ?? '').match(new RegExp(`(\\d+(?:[.,]\\d+)?(?:\\s?[${FRAC}])?)`));
  return m ? m[1] : null;
}

/** mm for a US size as written ("7", "US 7", "10½", "000"); null when unknown. */
export function usNeedleMm(size) {
  const token = sizeToken(size);
  if (!token) return null;
  if (/^0+$/.test(token)) return US_NEEDLE_MM[token] ?? null;
  const v = parseNumber(token);
  return v == null ? null : US_NEEDLE_MM[String(v)] ?? null;
}

/** mm for an old UK/Canadian size as written ("9", "UK 9", "00"); null when unknown. */
export function ukNeedleMm(size) {
  const token = sizeToken(size);
  if (!token) return null;
  return UK_NEEDLE_MM[/^0+$/.test(token) ? token : String(Number(token))] ?? null;
}

const mmText = (mm) => plain(Number(mm));

/** The needle size to show, mm first: { main: "4.5 mm", original: "US 7" }, or null when nothing is given.
 *  original is null when the pattern only gives mm. */
export function needleSize(needle) {
  if (!needle) return null;
  const us = needle.size_us ? String(needle.size_us).trim() : '';
  const uk = needle.size_uk ? String(needle.size_uk).trim() : '';
  const others = [us && `US ${us.replace(/^US\s*/i, '')}`, uk && `UK ${uk.replace(/^UK\s*/i, '')}`].filter(Boolean);
  let mm = needle.size_mm ? parseNumber(String(needle.size_mm).replace(/\s*mm$/i, '')) : null;
  if (mm == null && needle.size_mm) {
    return { main: `${String(needle.size_mm).trim()}${/mm$/i.test(needle.size_mm) ? '' : ' mm'}`, original: others.join(', ') || null };
  }
  if (mm == null && us) mm = usNeedleMm(us);
  if (mm == null && uk) mm = ukNeedleMm(uk);
  if (mm == null) return others.length ? { main: others.join(', '), original: null } : null;
  return { main: `${mmText(mm)} mm`, original: others.join(', ') || null };
}

// ---------------------------------------------------------------- gauge and cables
/** Stitches (or rows) per 10 cm, to the nearest 0.5: 32 sts over 4 in gives 31.5. null when it cannot. */
export function gaugePer10cm(count, overValue, overUnit) {
  const overCm = toCm(overValue, overUnit);
  if (!overCm || count == null) return null;
  return roundHalfUp((count * 10) / overCm * 2 + 1e-9) / 2;
}

export const STANDARD_CABLE_LENGTHS_CM = [20, 25, 30, 40, 50, 60, 80, 100, 120, 150];

/** The nearest standard circular needle length: 16 in 40, 24 in 60, 32 in 80; on a tie the shorter. */
export function cableLengthCm(inches) {
  const cm = inches * 2.54;
  let best = STANDARD_CABLE_LENGTHS_CM[0];
  for (const len of STANDARD_CABLE_LENGTHS_CM) {
    if (Math.abs(len - cm) < Math.abs(best - cm)) best = len;
  }
  return best;
}

// ---------------------------------------------------------------- showing values in metric
// A number inside a value as written: "1 1/2", "1/2", "4,5", "1,240", "17 ½", "4¾", or a lone "½".
const TOKEN_RE = new RegExp(`\\d+\\s+\\d+\\s*/\\s*\\d+|\\d+\\s*/\\s*\\d+|\\d+(?:[.,]\\d+)?(?:\\s?[${FRAC}])?|[${FRAC}]`, 'g');

/** Every number in the text through fn (number -> string); text between numbers is kept. changed is false
 *  when no number could be read. */
export function convertNumbers(text, fn) {
  let changed = false;
  const out = String(text ?? '').replace(TOKEN_RE, (tok) => {
    const v = parseNumber(tok.replace(/\s+(?=\d+\s*\/)/, ' '));
    if (v == null) return tok;
    changed = true;
    return fn(v);
  });
  return { text: out, changed };
}

// The metric unit and rounding for each unit a guide can give. Units not here are shown as written.
const CONVERT = {
  in: { unit: 'cm', fn: (v) => displayCm(v * 2.54), cable: (v) => String(cableLengthCm(v)) },
  yd: { unit: 'm', fn: (v) => displayWhole(v * 0.9144) },
  oz: { unit: 'g', fn: (v) => displayWhole(v * 28.3495) },
};
const SHORT = { in: 'in', yd: 'yd', oz: 'oz' };
const WORD_RE = {
  in: /\s*-?\s*(?:inches|inch|ins|in|["”″“])\.?\s*$/i,
  yd: /\s*(?:yards|yard|yds|yd)\.?\s*$/i,
  oz: /\s*(?:ounces|ounce|ozs|oz)\.?\s*$/i,
};

/** Whether values in this unit are shown converted. */
export function converts(unit) {
  return Boolean(CONVERT[unit]);
}

/**
 * A value in a guide unit (the numbers for one size, or the pattern's text for every size) to show in metric:
 * { main: "12 cm", original: "4¾ in" }, or null when the unit is not converted or no number is found.
 * opts.cable: lengths of circular needles go to the nearest standard metric length.
 */
export function metricValue(text, unit, opts = {}) {
  const conv = CONVERT[unit];
  if (!conv) return null;
  const written = String(text ?? '').replace(/\s*\n\s*/g, ' ').trim();
  const bare = written.replace(WORD_RE[unit], '').trim();
  const { text: out, changed } = convertNumbers(bare, opts.cable && conv.cable ? conv.cable : conv.fn);
  if (!changed) return null;
  const original = bare === written ? `${written}${unit === 'in' && /^["”″]$/.test(written.slice(-1)) ? '' : ` ${SHORT[unit]}`}` : written;
  return { main: `${out} ${conv.unit}`, original };
}

/** The text after a slot without the unit word the template repeats ("{s1} inches from" becomes " from"). */
export function stripUnitWord(text, unit) {
  const re = {
    in: /^\s*-?\s*(?:inches|inch|ins|in(?![A-Za-z])|["”″])\.?(?![A-Za-z])/i,
    yd: /^\s*(?:yards|yard|yds|yd)\.?(?![A-Za-z])/i,
    oz: /^\s*(?:ounces|ounce|ozs|oz)\.?(?![A-Za-z])/i,
  }[unit];
  return re ? String(text ?? '').replace(re, '') : text;
}

// Unit words in free text. "in" counts only where it cannot be the word "in" ("4 in pattern" is left alone).
const FREE_UNIT_RE = new RegExp(
  '(?<![A-Za-z])(inches|inch|ins\\.?(?![A-Za-z])|in\\.?(?=\\s*(?:$|[.,;:)/x×]|\\s(?:x|×|\\(|/|from|long|wide|high|deep|across|around|or|and|to|of|=)(?![A-Za-z])))'
  + '|["”″](?![A-Za-z0-9])|yards|yard|yds\\.?|yd\\.?|ounces|ounce|ozs|oz\\.?)(?![A-Za-z])',
  'gi',
);
const RUN_CHARS = new RegExp(`[\\d${FRAC}\\s.,/()${DASHES}]`);

function unitOf(word) {
  const w = word.toLowerCase();
  if (w.startsWith('y')) return 'yd';
  if (w.startsWith('o')) return 'oz';
  return 'in';
}

/** The numbers written just before position end ("4¾ (5½, 6¾, 7¼, 8) "), or null. */
function runBefore(text, end, quoteMark) {
  let start = end;
  while (start > 0 && RUN_CHARS.test(text[start - 1])) start -= 1;
  let run = text.slice(start, end);
  // Only the last sentence ("Round 1. 3 inches") and nothing before an unmatched ")" ("(Round 2) 4 in").
  const dot = run.search(/\.\s+(?=[^.]*$)/);
  if (dot >= 0) { start += dot + 1; run = text.slice(start, end); }
  let open = 0;
  let cut = 0;
  for (let i = 0; i < run.length; i += 1) {
    if (run[i] === '(') open += 1;
    else if (run[i] === ')') { if (open) open -= 1; else cut = i + 1; }
  }
  if (cut) { start += cut; run = text.slice(start, end); }
  const lead = run.search(new RegExp(`[\\d${FRAC}]`));
  if (lead < 0) return null;
  start += lead;
  run = text.slice(start, end);
  // "US 7, 32-inch": a needle size is not part of the length.
  if (/\b(?:US|UK|size|no\.?)\s*#?\s*$|#\s*$/i.test(text.slice(0, start))) {
    const next = run.match(/^[^,(]*,\s*/);
    if (!next) return null;
    start += next[0].length;
    run = text.slice(start, end);
  }
  const trimmed = run.replace(new RegExp(`[\\s${DASHES}]+$`), '');
  if (!trimmed || !new RegExp(`[\\d${FRAC})]$`).test(trimmed)) return null;
  if (quoteMark && trimmed.length !== run.length) return null;   // 4" only straight after the number
  if (start > 0 && /[A-Za-z]/.test(text[start - 1])) return null;  // "US7 in"
  return { start, end: start + trimmed.length };
}

/**
 * Free text from a pattern (a ball band, a needle line, a notion, plain step text) as parts:
 * { kind: 'text', text } and { kind: 'metric', main, original } for each length in inches or yards and each
 * weight in ounces, e.g. "142 yards/ 50 grams" gives "130 m" (142 yards) then "/ 50 grams".
 * opts.cable: inch lengths are circular needle lengths (nearest standard metric length).
 */
export function metricParts(text, opts = {}) {
  const src = String(text ?? '');
  const parts = [];
  let last = 0;
  FREE_UNIT_RE.lastIndex = 0;
  let m;
  while ((m = FREE_UNIT_RE.exec(src))) {
    const word = m[1].replace(/\.$/, '');   // "2 in." at the end of a sentence keeps its full stop
    const quote = /^["”″]$/.test(word);
    const run = runBefore(src, m.index, quote);
    if (!run || run.start < last) continue;
    let from = run.start;
    // "12- or 16-inch": take the first number too.
    const before = src.slice(last, from).match(new RegExp(`(\\d[\\d${FRAC}.,]*)[${DASHES}]?\\s+(?:or|to|and)\\s+$`));
    if (before) from -= before[0].length;
    const unit = unitOf(quote ? 'in' : word);
    const conv = CONVERT[unit];
    const numbers = src.slice(from, run.end);
    const { text: converted, changed } = convertNumbers(numbers, opts.cable && conv.cable ? conv.cable : conv.fn);
    if (!changed) continue;
    const out = converted.replace(new RegExp(`[${DASHES}](\\s+(?:or|to|and)\\s)`), '$1');   // "30 or 40 cm"
    const wordEnd = m.index + word.length;
    if (from > last) parts.push({ kind: 'text', text: src.slice(last, from) });
    parts.push({ kind: 'metric', main: `${out} ${conv.unit}`, original: src.slice(from, wordEnd) });
    last = wordEnd;
  }
  if (last < src.length) parts.push({ kind: 'text', text: src.slice(last) });
  return parts;
}

/** Whether metricParts would change anything. */
export function hasImperial(text) {
  return metricParts(text).some(p => p.kind === 'metric');
}

const OVER_RE = new RegExp(`(\\d+(?:[.,]\\d+)?(?:\\s?[${FRAC}])?)\\s*(?:x\\s*\\d+(?:[.,]\\d+)?\\s*)?-?\\s*(inches|inch|ins|in|cm|["”″])`, 'i');

/**
 * A gauge given over inches, per 10 cm: { stitches: "31.5", rows: "53", rowsUnit: "rounds" } (strings, either
 * may be null), or null when the gauge is already metric or cannot be read. Round pairs count as two rounds.
 */
export function gaugeMetric(gauge) {
  if (!gauge?.over) return null;
  const m = String(gauge.over).match(OVER_RE);
  if (!m) return null;
  const unit = /^c/i.test(m[2]) ? 'cm' : 'in';
  if (unit !== 'in') return null;
  const over = parseNumber(m[1]);
  if (!over) return null;
  const st = parseNumber(gauge.stitches);
  let rows = parseNumber(gauge.rows);
  let rowsUnit = gauge.rows_unit || 'rows';
  if (rows != null && rowsUnit === 'round_pairs') { rows *= 2; rowsUnit = 'rounds'; }
  const sPer = st == null ? null : gaugePer10cm(st, over, 'in');
  const rPer = rows == null ? null : gaugePer10cm(rows, over, 'in');
  if (sPer == null && rPer == null) return null;
  return { stitches: sPer == null ? null : plain(sPer), rows: rPer == null ? null : plain(rPer), rowsUnit };
}

// ---------------------------------------------------------------- DROPS widths
/** DROPS size charts give widths across the front (half the round measurement). */
export function isDrops(pattern) {
  return /drops/i.test(`${pattern?.publisher || ''} ${pattern?.pattern_number || ''}`);
}

/** A measurement name that DROPS gives as half the round measurement ("chest width", "Bust (width ...)"). */
export function isHalfWidth(name) {
  const n = String(name || '').toLowerCase();
  return /width|chest/.test(n) && !/neck|shoulder/.test(n);
}

/** The numbers in a value doubled: "48" "96", "48-52" "96-104". null when none can be read. */
export function doubled(text) {
  const { text: out, changed } = convertNumbers(text, (v) => plain(Math.round(v * 2 * 10) / 10));
  return changed ? out : null;
}
