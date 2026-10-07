import type { ViewName } from './lib/view'
import { AudienceApp } from './audience/AudienceApp'
import { PresenterView } from './views/PresenterView'

/** Picks the top-level view; main.tsx reads it from the URL once, at load. */
function App({ view }: { view: ViewName }) {
  return view === 'audience' ? <AudienceApp /> : <PresenterView />
}

export default App
