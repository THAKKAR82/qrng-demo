// Prints what the UI's display-only statistics compute on the exported pool bits, so
// tests/test_ui_stats.py can check them against pipeline.analysis on the same bits.
// Run by Node directly (built-in type stripping): node scripts/stats-check.ts <demo.json>

import { readFileSync } from 'node:fs'
import { decodePool, readPool } from '../src/lib/pool.ts'
import { bitStats, countMatches, countOnes } from '../src/lib/stats.ts'

const demoPath = process.argv[2]
if (demoPath === undefined) {
  console.error('usage: node scripts/stats-check.ts <demo.json>')
  process.exit(2)
}
const demo = JSON.parse(readFileSync(demoPath, 'utf8'))

const report: Record<string, unknown> = {}
for (const source of ['classical', 'quantum']) {
  const pool = decodePool(demo[source].pool)
  const prefixes = [1, 2, 7, 100, 1000, 4097, pool.length].filter((n) => n <= pool.length)
  report[source] = {
    bits: Array.from(pool.bits).join(''),
    predictions: Array.from(pool.predictions).join(''),
    prefixes: prefixes.map((n) => {
      const { bits, predictions } = readPool(pool, 0, n)
      const ones = countOnes(bits)
      const { fractionOnes, entropy } = bitStats(ones, n)
      return { n, ones, fraction_ones: fractionOnes, entropy, matches: countMatches(bits, predictions, n) }
    }),
  }
}
process.stdout.write(JSON.stringify(report))
