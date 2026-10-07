// Display formatting only. No analysis happens in TypeScript (SPEC.md, Section 7):
// these functions change how a value from demo.json looks, never what it is.

const MINUS = '−'

/** A number with a fixed number of decimals and a true minus sign: 0.98862 → "0.989". */
export function fixed(value: number, decimals: number): string {
  const text = value.toFixed(decimals)
  return text.startsWith('-') ? MINUS + text.slice(1) : text
}

/** A probability as a percentage: 0.50396 → "50.4%". */
export function percent(value: number, decimals = 1): string {
  return `${fixed(value * 100, decimals)}%`
}

/** A count with thousands separators: 180032 → "180,032". */
export function count(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

/** An interval, low to high, with an en dash: "50.1–50.7%". */
export function percentRange(low: number, high: number, decimals = 1): string {
  return `${fixed(low * 100, decimals)}–${fixed(high * 100, decimals)}%`
}

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

/**
 * A UTC time from demo.json, kept in UTC so it reads the same on any laptop:
 * "2026-10-06T01:35:01Z" → "6 October 2026, 01:35 UTC".
 */
export function utcDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):\d{2}Z$/.exec(value)
  if (match === null) {
    return value
  }
  const [, year, month, day, hour, minute] = match
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}, ${hour}:${minute} UTC`
}

/**
 * How the screen names the machine a run used (SPEC.md, Section 4.8), from the backend's
 * qubit count in the data: 156 → "a 156-qubit IBM quantum computer". Never the backend's
 * name or the job ID, which stay in the presenter notes.
 */
export function ibmQuantumComputer(numQubits: number | null): string {
  if (numQubits === null) {
    return 'an IBM quantum computer'
  }
  // "an" where the number is spoken with a vowel sound: 8, 11, 18, 80–89, 800–899, 11,000 …
  const digits = String(numQubits)
  const vowel = digits.startsWith('8') || (digits.length % 3 === 2 && /^1[18]/.test(digits))
  return `${vowel ? 'an' : 'a'} ${count(numQubits)}-qubit IBM quantum computer`
}
