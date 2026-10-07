// Pool reads never repeat or wrap, and guessing-game offsets leave room for 200 rounds.
// Run by Node's test runner (from tests/test_ui_stats.py): node --test scripts/pool.test.ts

import assert from 'node:assert/strict'
import { test } from 'node:test'
import { GUESS_ROUNDS, advanceBy, decodePool, randomStart, readPool, unpackBits } from '../src/lib/pool.ts'

const pool = decodePool({ start_bit: 100, n_bits: 10, bits: btoa('\xA5\x80'), predictions: btoa('\xFF\xC0') })

test('unpacks most significant bit first and checks the length', () => {
  assert.deepEqual([...unpackBits(btoa('\x81\x80'), 9)], [1, 0, 0, 0, 0, 0, 0, 1, 1])
  assert.throws(() => unpackBits(btoa('\x81'), 9))
})

test('decodes bits and predictions', () => {
  assert.deepEqual([...pool.bits], [1, 0, 1, 0, 0, 1, 0, 1, 1, 0])
  assert.deepEqual([...pool.predictions], [1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
  assert.equal(pool.startBit, 100)
})

test('reads are bounded and never wrap', () => {
  assert.deepEqual([...readPool(pool, 8, 2).bits], [1, 0])
  assert.equal(readPool(pool, 10, 0).bits.length, 0)
  assert.throws(() => readPool(pool, 9, 2), RangeError)
  assert.throws(() => readPool(pool, -1, 1), RangeError)
  assert.throws(() => readPool(pool, 0.5, 1), RangeError)
})

test('a stream stops at the end of the pool instead of looping', () => {
  let position = 0
  const steps: number[] = []
  for (;;) {
    const step = advanceBy(position, 4, pool.length)
    if (step === 0) break
    readPool(pool, position, step)
    position += step
    steps.push(step)
  }
  assert.deepEqual(steps, [4, 4, 2])
  assert.equal(position, pool.length)
  assert.equal(advanceBy(position, 4, pool.length), 0)
  assert.equal(advanceBy(position + 3, 4, pool.length), 0)
})

test('random starts leave room for every round', () => {
  assert.equal(GUESS_ROUNDS, 200)
  assert.equal(randomStart(20_000, 200, () => 0), 0)
  assert.equal(randomStart(20_000, 200, () => 0.999999999), 19_800)
  assert.equal(randomStart(200, 200, () => 0.7), 0)
  assert.throws(() => randomStart(199, 200), RangeError)
  for (let i = 0; i < 2000; i += 1) {
    const start = randomStart(20_000)
    assert.ok(Number.isInteger(start) && start >= 0 && start + GUESS_ROUNDS <= 20_000)
  }
})
