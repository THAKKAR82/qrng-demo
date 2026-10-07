// Display-only counting statistics (SPEC.md, Section 7): the fraction of ones, its Shannon
// entropy, and match counts, over bits the UI is showing live. Nothing here is written
// back or used to choose wording; every other number comes precomputed from demo.json.
//
// This file is also run directly by Node (tests/test_ui_stats.py checks it against
// pipeline.analysis), so it imports nothing and uses only erasable TypeScript syntax.

/** Ones among the first `n` bits. */
export function countOnes(bits: ArrayLike<number>, n: number = bits.length): number {
  let ones = 0
  for (let i = 0; i < n; i += 1) {
    ones += bits[i]
  }
  return ones
}

/** Positions among the first `n` where `a` and `b` agree: a guessing score. */
export function countMatches(a: ArrayLike<number>, b: ArrayLike<number>, n: number): number {
  let matches = 0
  for (let i = 0; i < n; i += 1) {
    if (a[i] === b[i]) {
      matches += 1
    }
  }
  return matches
}

/** `h(p) = −p·log2 p − (1−p)·log2(1−p)`, with h(0) = h(1) = 0, as `analysis.binary_entropy`. */
export function binaryEntropy(p: number): number {
  if (p <= 0 || p >= 1) {
    return 0
  }
  return -p * Math.log2(p) - (1 - p) * Math.log2(1 - p)
}

/** Fraction of ones and per-bit Shannon entropy h(p̂), as `analysis.shannon_entropy_per_bit`. */
export function bitStats(ones: number, n: number): { fractionOnes: number; entropy: number } {
  if (n <= 0) {
    return { fractionOnes: Number.NaN, entropy: Number.NaN }
  }
  const fractionOnes = ones / n
  return { fractionOnes, entropy: binaryEntropy(fractionOnes) }
}
