import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/fonts.css'
import './styles/tokens.css'
import './styles/base.css'
import App from './App.tsx'
import { currentView } from './lib/view'

// Set before the first render: tokens.css switches the type and space scales on it.
const view = currentView()
document.documentElement.dataset.view = view

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App view={view} />
  </StrictMode>,
)
