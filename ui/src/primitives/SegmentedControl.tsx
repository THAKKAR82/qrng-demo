import type { MouseEvent } from 'react'
import type { Source } from '../data/types'
import './SegmentedControl.css'

export interface Segment<T extends string> {
  value: T
  label: string
  /** Colours the selected segment with this source's colour. */
  source?: Source
}

interface SegmentedControlProps<T extends string> {
  /** Accessible name for the group, such as "Stream". */
  label: string
  segments: readonly Segment<T>[]
  value: T
  onChange: (value: T) => void
}

/**
 * A row of buttons choosing one value. Each button is at least 44 CSS px square and
 * shows its state with a filled background, not on hover.
 *
 * After a tap or click, the button gives up focus. The deck ignores keys aimed at a
 * focused button, so otherwise the presenter's clicker would stop working after
 * someone clicked a panel. Keyboard users keep focus, so Tab and Space work as usual.
 */
export function SegmentedControl<T extends string>({
  label,
  segments,
  value,
  onChange,
}: SegmentedControlProps<T>) {
  const choose = (event: MouseEvent<HTMLButtonElement>, next: T) => {
    onChange(next)
    // detail is 0 when a button is activated from the keyboard.
    if (event.detail > 0) {
      event.currentTarget.blur()
    }
  }
  return (
    <div className="segmented" role="group" aria-label={label}>
      {segments.map((s) => {
        const selected = s.value === value
        const source = s.source === undefined ? '' : ` segmented__option--${s.source}`
        return (
          <button
            key={s.value}
            type="button"
            className={`segmented__option${source}`}
            aria-pressed={selected}
            onClick={(event) => choose(event, s.value)}
          >
            {s.label}
          </button>
        )
      })}
    </div>
  )
}
