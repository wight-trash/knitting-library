import test from 'node:test';
import assert from 'node:assert/strict';

import {
  cableLengthCm, convertNumbers, displayCm, displayHalf, doubled, gaugeMetric, gaugePer10cm, isDrops, isHalfWidth,
  metricParts, metricValue, needleSize, parseNumber, parseRange, stripUnitWord, toCm, toGrams, toMetres,
  ukNeedleMm, usNeedleMm,
} from './units.js';

const metricOnly = (parts) => parts.filter(p => p.kind === 'metric').map(p => `${p.main} | ${p.original}`);
const joined = (parts) => parts.map(p => (p.kind === 'text' ? p.text : `${p.main} (${p.original})`)).join('');

test('reads numbers as patterns write them', () => {
  assert.equal(parseNumber('4¾'), 4.75);
  assert.equal(parseNumber('17 ½'), 17.5);
  assert.equal(parseNumber('1/2'), 0.5);
  assert.equal(parseNumber('1 1/2'), 1.5);
  assert.equal(parseNumber('4,5'), 4.5);
  assert.equal(parseNumber('1,240'), 1240);
  assert.equal(parseNumber('6.9”'), 6.9);
  assert.equal(parseNumber('three'), 3);
  assert.equal(parseNumber('6th'), 6);
  assert.equal(parseNumber('65-70'), null);
  assert.equal(parseNumber('-'), null);
  assert.equal(parseNumber(''), null);
});

test('reads ranges', () => {
  assert.deepEqual(parseRange('65-70'), [65, 70]);
  assert.deepEqual(parseRange('4–5'), [4, 5]);
  assert.deepEqual(parseRange('4 to 5'), [4, 5]);
  assert.deepEqual(parseRange('4½'), [4.5, 4.5]);
  assert.equal(parseRange('lots'), null);
});

test('converts lengths and weights', () => {
  assert.equal(toCm(1, 'in'), 2.54);
  assert.equal(toCm(2, 'inches'), 5.08);
  assert.equal(toCm(3, 'cm'), 3);
  assert.equal(toCm(3, 'balls'), null);
  assert.ok(Math.abs(toMetres(100, 'yds') - 91.44) < 1e-9);
  assert.ok(Math.abs(toGrams(1, 'oz') - 28.3495) < 1e-9);
});

test('rounds the way a knitter measures', () => {
  assert.equal(displayCm(4.4), '4.5');
  assert.equal(displayCm(4.0), '4');
  assert.equal(displayCm(26.67), '27');
  assert.equal(displayCm(9.9), '10');
  assert.equal(displayCm(12.065), '12');
  assert.equal(displayHalf(31.496), '31.5');
  assert.equal(displayHalf(53.15), '53');
});

test('shows a value in inches as cm with the original', () => {
  assert.deepEqual(metricValue('4¼', 'in'), { main: '11 cm', original: '4¼ in' });
  assert.deepEqual(metricValue('1½', 'in'), { main: '4 cm', original: '1½ in' });
  assert.deepEqual(metricValue('65-70', 'in'), { main: '165-178 cm', original: '65-70 in' });
  assert.deepEqual(metricValue('4¾ (5½, 6¾, 7¼, 8) inches', 'in'),
    { main: '12 (14, 17, 18, 20) cm', original: '4¾ (5½, 6¾, 7¼, 8) inches' });
  assert.deepEqual(metricValue('32"', 'in'), { main: '81 cm', original: '32"' });
  assert.deepEqual(metricValue('16', 'in', { cable: true }), { main: '40 cm', original: '16 in' });
});

test('shows yards as metres and ounces as grams, whole', () => {
  assert.deepEqual(metricValue('1240', 'yd'), { main: '1134 m', original: '1240 yd' });
  assert.deepEqual(metricValue('1,240 yds', 'yd'), { main: '1134 m', original: '1,240 yds' });
  assert.deepEqual(metricValue('3½', 'oz'), { main: '99 g', original: '3½ oz' });
});

test('leaves units that are not lengths or weights alone', () => {
  assert.equal(metricValue('12', 'cm'), null);
  assert.equal(metricValue('12', 'stitches'), null);
  assert.equal(metricValue('2', 'balls'), null);
  assert.equal(metricValue('twice-ish', 'in'), null);
});

test('drops the unit word the step text repeats after a slot', () => {
  assert.equal(stripUnitWord(' inches from cast-on edge', 'in'), ' from cast-on edge');
  assert.equal(stripUnitWord(' in from cast-on edge', 'in'), ' from cast-on edge');
  assert.equal(stripUnitWord('" from the edge', 'in'), ' from the edge');
  assert.equal(stripUnitWord(' into the next st', 'in'), ' into the next st');
  assert.equal(stripUnitWord(' yds of yarn', 'yd'), ' of yarn');
});

test('finds inches, yards and ounces in free text', () => {
  assert.deepEqual(metricOnly(metricParts('142 yards/ 50 grams')), ['130 m | 142 yards']);
  assert.equal(joined(metricParts('142 yards/ 50 grams')), '130 m (142 yards)/ 50 grams');
  assert.deepEqual(metricOnly(metricParts('until piece measures 4¾ (5½, 6¾, 7¼, 8) inches from cast-on edge')),
    ['12 (14, 17, 18, 20) cm | 4¾ (5½, 6¾, 7¼, 8) inches']);
  assert.deepEqual(metricOnly(metricParts('Work even for 2 in.')), ['5 cm | 2 in']);
  assert.deepEqual(metricOnly(metricParts('a 6" length')), ['15 cm | 6"']);
  assert.deepEqual(metricOnly(metricParts('4 oz skein')), ['113 g | 4 oz']);
});

test('does not take the word "in" for inches', () => {
  assert.deepEqual(metricOnly(metricParts('Work 4 in pattern')), []);
  assert.deepEqual(metricOnly(metricParts('k2tog 3 in each repeat')), []);
  assert.deepEqual(metricOnly(metricParts('Rounds 1 and 2 in stocking stitch')), []);
  assert.deepEqual(metricOnly(metricParts('Size US7 in the round')), []);
  assert.deepEqual(metricOnly(metricParts('ending with Round 1. 3 inches more')), ['7.5 cm | 3 inches']);
  assert.deepEqual(metricOnly(metricParts('(Round 2) 4 inches')), ['10 cm | 4 inches']);
});

test('needle lengths go to the nearest standard metric cable', () => {
  assert.equal(cableLengthCm(16), 40);
  assert.equal(cableLengthCm(24), 60);
  assert.equal(cableLengthCm(32), 80);
  assert.equal(cableLengthCm(40), 100);
  assert.equal(cableLengthCm(47), 120);
  assert.equal(cableLengthCm(12), 30);
  assert.equal(joined(metricParts('US 7, 12- or 16-inch circular needles', { cable: true })),
    'US 7, 30 or 40 cm (12- or 16-inch) circular needles');
  assert.equal(joined(metricParts('US 7 double pointed needles OR US 7, 32-inch circular needles', { cable: true })),
    'US 7 double pointed needles OR US 7, 80 cm (32-inch) circular needles');
  assert.deepEqual(metricOnly(metricParts('size 8 in the round')), []);
});

test('needle sizes show mm first', () => {
  assert.equal(usNeedleMm('7'), 4.5);
  assert.equal(usNeedleMm('US 10½'), 6.5);
  assert.equal(usNeedleMm('10.75'), 7);
  assert.equal(usNeedleMm('000'), 1.5);
  assert.equal(usNeedleMm('12'), null);
  assert.equal(ukNeedleMm('9'), 3.75);
  assert.equal(ukNeedleMm('00'), 9);
  assert.deepEqual(needleSize({ size_mm: '4.5', size_us: '7', size_uk: null }), { main: '4.5 mm', original: 'US 7' });
  assert.deepEqual(needleSize({ size_mm: null, size_us: '7', size_uk: null }), { main: '4.5 mm', original: 'US 7' });
  assert.deepEqual(needleSize({ size_mm: '5', size_us: null, size_uk: null }), { main: '5 mm', original: null });
  assert.deepEqual(needleSize({ size_mm: '4,5', size_us: null, size_uk: '7' }), { main: '4.5 mm', original: 'UK 7' });
  assert.equal(needleSize({ size_mm: null, size_us: null, size_uk: null }), null);
});

test('gauge over 4 inches is shown per 10 cm', () => {
  assert.equal(gaugePer10cm(32, 4, 'in'), 31.5);
  assert.equal(gaugePer10cm(22, 4, 'in'), 21.5);
  assert.deepEqual(gaugeMetric({ stitches: '32', rows: '27', rows_unit: 'round_pairs', over: '4 inches' }),
    { stitches: '31.5', rows: '53', rowsUnit: 'rounds' });
  assert.deepEqual(gaugeMetric({ stitches: '20', rows: null, rows_unit: null, over: '4"' }),
    { stitches: '19.5', rows: null, rowsUnit: 'rows' });
  assert.equal(gaugeMetric({ stitches: '17', rows: '22', rows_unit: 'rows', over: '10 x 10 cm' }), null);
  assert.equal(gaugeMetric({ stitches: '17', rows: '22', rows_unit: 'rows', over: null }), null);
});

test('DROPS half widths', () => {
  assert.equal(isDrops({ publisher: 'DROPS Design', pattern_number: null }), true);
  assert.equal(isDrops({ publisher: null, pattern_number: 'drops 224-21' }), true);
  assert.equal(isDrops({ publisher: 'Purl Soho', pattern_number: null }), false);
  assert.equal(isHalfWidth('chest width'), true);
  assert.equal(isHalfWidth('Bust (width at underarm, flat)'), true);
  assert.equal(isHalfWidth('Neck width'), false);
  assert.equal(isHalfWidth('Shoulder width'), false);
  assert.equal(isHalfWidth('total length'), false);
  assert.equal(doubled('48'), '96');
  assert.equal(doubled('48-52'), '96-104');
  assert.equal(doubled('45½'), '91');
  assert.equal(doubled('n/a'), null);
});

test('convertNumbers keeps the text around the numbers', () => {
  assert.deepEqual(convertNumbers('13 (15, 17)', v => String(v * 2)), { text: '26 (30, 34)', changed: true });
  assert.deepEqual(convertNumbers('none', v => String(v)), { text: 'none', changed: false });
});
