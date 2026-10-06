interface ProgressProps {
  index: number
  count: number
}

/** Where we are in the deck: a thin rule that fills as the talk goes on, and "3 / 6". */
export function Progress({ index, count }: ProgressProps) {
  const done = count > 0 ? ((index + 1) / count) * 100 : 0
  return (
    <div className="progress" aria-label={`Scene ${index + 1} of ${count}`}>
      <div className="progress__track">
        <div className="progress__fill" style={{ width: `${done}%` }} />
      </div>
      <span className="progress__count num" aria-hidden="true">
        {index + 1} / {count}
      </span>
    </div>
  )
}
