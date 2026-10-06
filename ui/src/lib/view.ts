/** The two top-level views (SPEC.md, Section 9.1). */
export type ViewName = 'presenter' | 'audience'

/** `?view=audience` selects the audience view; anything else is the presenter view. */
export function currentView(search: string = window.location.search): ViewName {
  return new URLSearchParams(search).get('view') === 'audience' ? 'audience' : 'presenter'
}
