// Axis tick positions for charts. Layout only: no data is changed.

/** Round tick values (1, 2 or 5 times a power of ten) covering [min, max]. */
export function niceTicks(min: number, max: number, target = 5): number[] {
  const span = max - min
  if (!(span > 0)) {
    return [min]
  }
  const raw = span / target
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = ([1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? 10 * power) as number
  const ticks: number[] = []
  for (let t = Math.ceil(min / step) * step; t <= max + step * 1e-9; t += step) {
    ticks.push(Number(t.toPrecision(12)))
  }
  return ticks
}
