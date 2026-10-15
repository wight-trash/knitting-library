// The stash in grams inside the upstream Add / edit yarn form: ball details, reading a ball band photo, and the
// shop picture fetched by our own server. Everything here is off while the switch is off. Fork-only (FORK.md).
// Nothing is saved until the knitter taps the form's own Save button.
import { useEffect, useRef, useState } from 'react';
import { ft } from '../strings';
import { getYarnSpec, saveYarnSpec, readBallBand, fetchStashImage, addYarnColourName } from '../forkApi';
import { useStashStatus, specSaved } from './stashStore';
import { EMPTY_BALL_FORM, formToSpec, formIsEmpty, sameForm, specToForm } from './stashNumbers';

// Which ball-band fields each box of the form comes from, to mark the ones that were hard to read.
const YARN_SOURCES = {
  name: ['name', 'brand'], wool_type: ['fibre'], yardage: ['metres_per_ball', 'grams_per_ball'],
  needles: ['needle'], tension: ['gauge'],
};
const BALL_SOURCES = {
  grams_per_ball: ['grams_per_ball'], metres_per_ball: ['metres_per_ball'], weight: ['weight', 'weight_category'],
  fibre: ['fibre'], needle_from: ['needle'], needle_to: ['needle'], gauge_stitches: ['gauge'], gauge_rows: ['gauge'],
  care: ['care'],
};
const YARN_KEYS = Object.keys(YARN_SOURCES);

/** A phone photo made smaller (at most 1600 px) as a JPEG, the right way up. null if this browser cannot read it. */
async function shrinkPhoto(file) {
  let url = '';
  try {
    url = URL.createObjectURL(file);
    const img = await new Promise((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = reject;
      i.src = url;
    });
    const w = img.naturalWidth;
    const h = img.naturalHeight;
    if (!w || !h) return null;
    const scale = Math.min(1, 1600 / Math.max(w, h));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.86));
    return blob ? new File([blob], 'ball-band.jpg', { type: 'image/jpeg' }) : null;
  } catch {
    return null;
  } finally {
    if (url) URL.revokeObjectURL(url);
  }
}

function specToBallForm(spec) {
  if (!spec) return {};
  const f = specToForm({ ...spec, gauge_over_cm: spec.gauge_over_cm || 10 });
  return Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ''));
}

export default function useStashYarnForm({
  isEdit, editYarn, fields, setFields, setError, imageFile, setImageFile, setImagePreview, hasExistingImage,
}) {
  const status = useStashStatus();
  const enabled = Boolean(status?.enabled);

  const [ball, setBall] = useState(EMPTY_BALL_FORM);
  const [loadedBall, setLoadedBall] = useState(null);       // edit: the ball details as saved
  const [band, setBand] = useState({ state: 'idle' });       // idle | reading | done | error
  const [filled, setFilled] = useState({ yarn: {}, ball: {} });   // what the band put in each box
  const [low, setLow] = useState([]);                        // ball-band fields read with low confidence
  const [addColour, setAddColour] = useState(true);
  const [usePicture, setUsePicture] = useState(false);
  const photoUrl = useRef('');
  const fieldsRef = useRef(fields);
  fieldsRef.current = fields;
  const ballRef = useRef(ball);
  ballRef.current = ball;
  const filledRef = useRef(filled);
  filledRef.current = filled;

  // Edit: load the yarn's saved ball details.
  useEffect(() => {
    if (!enabled || !isEdit || !editYarn?.id) return undefined;
    let alive = true;
    getYarnSpec(editYarn.id)
      .then((res) => { if (!alive) return; const f = specToForm(res.spec); setBall(f); setLoadedBall(f); })
      .catch(() => {});
    return () => { alive = false; };
  }, [enabled, isEdit, editYarn?.id]);

  useEffect(() => () => { if (photoUrl.current) URL.revokeObjectURL(photoUrl.current); }, []);

  const lowSet = new Set(low);
  const isLow = (sources) => sources.some((s) => lowSet.has(s));

  /** For the upstream boxes: true when the band filled this box, it was hard to read, and it is unchanged. */
  const check = (key) => enabled && YARN_SOURCES[key] && isLow(YARN_SOURCES[key])
    && filled.yarn[key] != null && fields[key] === filled.yarn[key];

  const ballChecks = {};
  if (enabled) {
    for (const [key, sources] of Object.entries(BALL_SOURCES)) {
      if (isLow(sources) && filled.ball[key] != null && ball[key] === filled.ball[key]) ballChecks[key] = true;
    }
    if (ballChecks.needle_from || ballChecks.needle_to) ballChecks.needle = true;
    if (ballChecks.gauge_stitches || ballChecks.gauge_rows) ballChecks.gauge = true;
  }

  const readPhoto = async (file) => {
    if (!file) return;
    const small = await shrinkPhoto(file);
    if (photoUrl.current) URL.revokeObjectURL(photoUrl.current);
    photoUrl.current = URL.createObjectURL(small || file);
    setBand({ state: 'reading', photo: photoUrl.current, small });
    try {
      const result = await readBallBand(small || file);
      applyResult(result, small);
    } catch (e) {
      setBand({ state: 'error', photo: photoUrl.current, small,
        message: e?.fromServer ? e.message : ft('bandFailed') });
    }
  };

  const applyResult = (result, small) => {
    const prevFilled = filledRef.current;
    const yarnForm = result.yarn_form || {};
    const yarnFilled = {};
    const nextFields = { ...fieldsRef.current };
    for (const key of YARN_KEYS) {
      const value = yarnForm[key];
      const current = nextFields[key] ?? '';
      if (value && (!String(current).trim() || current === prevFilled.yarn[key])) {
        nextFields[key] = value;
        yarnFilled[key] = value;
      }
    }
    const fromBand = specToBallForm(result.spec);
    const ballFilled = {};
    const nextBall = { ...ballRef.current };
    for (const [key, value] of Object.entries(fromBand)) {
      const current = nextBall[key] ?? '';
      if (!String(current).trim() || current === prevFilled.ball[key]) {
        nextBall[key] = value;
        ballFilled[key] = value;
      }
    }
    setFields(nextFields);
    setBall(nextBall);
    setFilled({ yarn: yarnFilled, ball: ballFilled });
    setLow(result.low_confidence || []);

    const f = result.fields || {};
    const colour = [f.colour_name?.text, f.colour_number?.text].filter(Boolean).join(' ');
    const pictureFree = !imageFile && !hasExistingImage && Boolean(small);
    setUsePicture(pictureFree);
    if (pictureFree) { setImageFile(small); setImagePreview(small.name); }
    const anything = Object.keys(yarnFilled).length + Object.keys(ballFilled).length > 0
      || Object.values(yarnForm).some(Boolean) || Object.values(fromBand).some(Boolean);
    setBand({
      state: anything ? 'done' : 'empty',
      photo: photoUrl.current,
      small,
      colour: isEdit ? '' : colour,
      dyeLot: f.dye_lot?.text || '',
      bandText: {
        grams_per_ball: f.grams_per_ball?.text || '',
        metres_per_ball: f.metres_per_ball?.text || '',
        needle: f.needle?.text || '',
        gauge: f.gauge?.text || '',
      },
      hasChecks: (result.low_confidence || []).length > 0,
    });
  };

  const choosePicture = (on) => {
    setUsePicture(on);
    if (!band.small) return;
    if (on) { setImageFile(band.small); setImagePreview(band.small.name); }
    else if (imageFile === band.small) { setImageFile(null); setImagePreview(null); }
  };

  const validate = () => {
    if (!enabled) return true;
    const { error } = formToSpec(ball);
    if (error) { setError(error); return false; }
    return true;
  };

  const afterSave = async (yarn) => {
    if (!enabled || !yarn?.id) return;
    const problems = [];
    const changed = isEdit ? loadedBall != null && !sameForm(ball, loadedBall) : !formIsEmpty(ball);
    if (changed) {
      const { spec } = formToSpec(ball);
      const fromBand = Object.entries(filled.ball).some(([k, v]) => ball[k] === v);
      try {
        await saveYarnSpec(yarn.id, { ...spec, ...(fromBand ? { source: 'ball_band' } : {}) });
        specSaved(yarn.id);
      } catch (e) {
        problems.push(ft('specNotSaved', { message: e?.fromServer ? e.message : ft('couldNotSave') }));
      }
    }
    if (!isEdit && band.colour && addColour && band.state === 'done') {
      try {
        await addYarnColourName(yarn.id, band.colour);
      } catch {
        problems.push(ft('colourNotSaved'));
      }
    }
    if (problems.length) window.alert(problems.join('\n\n'));
  };

  /** The shop's picture, through our own server (the page may not fetch other sites). */
  const fetchImage = (url) => (enabled ? fetchStashImage(url) : window.fetch(url));

  return {
    enabled,
    check,
    validate,
    afterSave,
    fetchImage,
    bandProps: {
      available: Boolean(status?.ballband_available),
      band, readPhoto, addColour, setAddColour, usePicture, choosePicture,
    },
    ballProps: {
      value: ball,
      onChange: (k, v) => setBall((b) => ({ ...b, [k]: v })),
      checks: ballChecks,
      bandText: band.bandText || {},
    },
  };
}

