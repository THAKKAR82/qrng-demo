/**
 * SPEC.md, Sections 4.1 and 9: shown on every screen of both views when the data is
 * synthetic. There is no way to close it. On the presenter's stage it sits at the top
 * right; on the audience's page it is a bar that stays at the top while scrolling.
 */
export function SyntheticLabel({ placement = 'stage' }: { placement?: 'stage' | 'page' }) {
  return (
    <p className={`synthetic-label synthetic-label--${placement}`} role="note">
      SYNTHETIC DATA: not from quantum hardware
    </p>
  )
}
