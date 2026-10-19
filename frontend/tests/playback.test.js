import assert from 'node:assert/strict';
import test from 'node:test';
import { activeSegmentId } from '../src/shared/lib/transcriptPlayback.js';

const segments = [
  { id: 10, start: 1, end: 3 },
  { id: 11, start: 3, end: 5 },
  { id: 12, start: 7, end: 9 },
];

test('follows the segment at the audio position, including exact boundaries', () => {
  assert.equal(activeSegmentId(segments, 1), 10);
  assert.equal(activeSegmentId(segments, 2.9), 10);
  assert.equal(activeSegmentId(segments, 3), 11);
  assert.equal(activeSegmentId(segments, 7), 12);
});

test('does not highlight speech during silence or after it ends', () => {
  assert.equal(activeSegmentId(segments, 0), null);
  assert.equal(activeSegmentId(segments, 5), null);
  assert.equal(activeSegmentId(segments, 6), null);
  assert.equal(activeSegmentId(segments, 9), null);
});

test('prefers the most recently started segment when timestamps overlap', () => {
  assert.equal(activeSegmentId([{ id: 1, start: 1, end: 5 }, { id: 2, start: 3, end: 6 }], 4), 2);
});
