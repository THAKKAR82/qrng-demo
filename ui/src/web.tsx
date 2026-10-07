// Entry point of the phone site (`npm run build:web`, SPEC.md, Section 9.2). It imports
// only the phone version, so the bundle carries no deck, slides, notes, presenter keys,
// talk panels, or primitives page.

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/fonts.css'
import './styles/tokens.css'
import './styles/base.css'
import { AudienceApp } from './audience/AudienceApp'

// Set before the first render: tokens.css switches the type and space scales on it.
document.documentElement.dataset.view = 'audience'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AudienceApp />
  </StrictMode>,
)
