import type { ViewName } from './lib/view'
import { AudienceView } from './views/AudienceView'
import { PresenterView } from './views/PresenterView'

/** Picks the top-level view; main.tsx reads it from the URL once, at load. */
function App({ view }: { view: ViewName }) {
  return view === 'audience' ? <AudienceView /> : <PresenterView />
}

export default App
