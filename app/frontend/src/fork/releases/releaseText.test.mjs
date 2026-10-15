import test from 'node:test';
import assert from 'node:assert/strict';

import { releaseText } from './releaseText.js';

test('removes image tags from GitHub release notes', () => {
  const body = 'New look for the library.\r\n\r\n<img width="234" height="120" alt="Image" src="https://github.com/user-attachments/assets/abc" />\r\n\r\nFixed a bug.';
  assert.equal(releaseText(body).replace(/\r/g, ''), 'New look for the library.\n\nFixed a bug.');
});

test('keeps text, links and comparisons', () => {
  assert.equal(releaseText('See https://example.com/x and a < b'), 'See https://example.com/x and a < b');
  assert.equal(releaseText('- one<br>- two'), '- one\n- two');
  assert.equal(releaseText('<p>Hello <b>there</b></p><!-- note -->'), 'Hello there');
  assert.equal(releaseText('Before ![shot](https://x/y.png) after'), 'Before  after');
  assert.equal(releaseText(''), '');
  assert.equal(releaseText(null), '');
});
