// Visual and offline verification of the UI. Development only: Playwright is a
// devDependency used by this script and nothing else; no run mode or task needs it.
//
//   node scripts/verify.mjs --url http://localhost:4173/   # a running dev or preview server
//   node scripts/verify.mjs --file ../demo/index.html      # the single-file build, offline
//   node scripts/verify.mjs --web http://localhost:4174/   # the phone site (npm run preview:web)
//   add --synthetic yes|no to require (or forbid) the synthetic-data label
//   add --qr yes|no to require (or forbid) the QR code (slide 1, slide 8, the Q overlay)
//   node scripts/verify.mjs --url http://localhost:4173/ --live-mock
//                                                          # the live run on slide 3, mocked
//
// Live run (SPEC.md, Section 6.4). In every ordinary run it checks the live control is
// absent: no "Run on real quantum hardware now" button and no request to /api/live/ in
// plain preview or under file://, and no live code at all in the single-file HTML (--file)
// or in the phone site's files (--web). With --live-mock (and --url pointing at a plain
// preview of ui/dist/) it plays the part of live-server inside the browser: it adds a
// session token to the page and answers /api/live/ itself, so no Python server and no
// IBM account are involved. It then checks slide 3 when the server is unarmed, when it
// can't be reached, and when it is armed: a run that finishes (each stage, the fresh bits
// labelled with the live machine's size and streamed, at both stage sizes; the job ID and
// backend only in the notes, never on screen), the 120-second timeout (with a
// fake clock), a failed job, the server vanishing mid-run, and a refused start. Every API
// request must carry the token. While fresh bits play, both pictures must be 40 × 50 with
// square cells, in the same on-screen square as the 128 × 128 picture, captioned "40 × 50
// bits"; otherwise they must be the normal square picture with no caption.
//
// Presentation, at 1920×1080 and 1280×720: opens with no hash (it must land on slide 1),
// walks every slide and every step to the end, saves a screenshot of each, checks fonts,
// presenter notes, and that nothing spills off the stage. Each slide is also checked as a
// washed-out projector would show it (contrast reduced by 30%): every piece of text must
// keep at least 3:1 contrast with what is behind it, and a screenshot is saved with the
// filter applied. The backend name and job ID must not be on screen; the run is named
// "Run on a N-qubit IBM quantum computer" (SPEC.md, Section 4.8), and slide 3's notes
// carry the backend and job ID. At 1920×1080 it also drives
// every panel with the presenter's keys and mouse: Generate fills the pictures and counts;
// R reveals; 0 and 1 score guesses without moving the deck; M switches machine and Launch
// runs each attack to its result; clicking a chosen qubit on the chip selects that qubit;
// slide 8 shows the QR code and no chip; Q shows and hides the QR overlay, Escape hides it,
// and neither moves the deck.
//
// Primitives page, at both sizes: walks every scene, saves a screenshot of each, and
// checks that
//   - every character on screen renders in IBM Plex, not a fallback font (checked with
//     Chrome's own record of the fonts it used, after a self-test that it catches one);
//   - keys pressed on an interactive element do not move the deck, and the clicker
//     still works after a panel button has been clicked;
//   - N shows and hides the notes overlay, and PageUp goes back.
//
// Phone version (?view=audience in the presenter builds; the site root with --web), on a
// 390×844 touch phone and again on a short 375×560 one: plays both games to completion
// by tapping (five rounds of Spot the quantum machine twice, with no image ever repeated
// in the session, then the "all seen" message; twenty rounds of Beat the attacker on each
// machine), opens the closing screen, and on every screen checks fonts, that nothing
// overflows sideways, that every control is at least 44×44 CSS px, and that a real touch
// drag scrolls the page whenever it is taller than the screen. No presenter content (stage,
// slides, notes, panels, primitives) is on any screen, and N, F, P and Q do nothing. The
// Beat the attacker end screen quotes the chance range from demo.json, and the closing
// screen names the run by the machine's size, never by backend or job ID.
//
// With --web it also checks that the bundle the site loads contains no presenter content,
// live-run code, or source maps; serves every page with the headers from the build's
// _headers file (vite preview doesn't apply them) and fails on any CSP violation or any
// request to another origin; and plays both games under those headers in Firefox and
// WebKit too, so the policy is known to work in every engine phones use.
//
// All: no console or page errors, and no request to any other origin; with --synthetic
// yes|no, the synthetic label is (or is not) on screen. With --file it also blocks the
// network entirely and fails on any request that is not file: or data:, and checks the
// HTML references no external resources.
// Screenshots go to data/scratch/ui-verify/ (gitignored) unless --out is given.

import { mkdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { chromium, firefox, webkit } from 'playwright'

const here = path.dirname(fileURLToPath(import.meta.url))
const args = process.argv.slice(2)
const option = (name) => {
  const i = args.indexOf(name)
  return i >= 0 ? args[i + 1] : undefined
}

const fileArg = option('--file')
const urlArg = option('--url')
const webArg = option('--web')
if ([fileArg, urlArg, webArg].filter((a) => a !== undefined).length !== 1) {
  console.error('Pass exactly one of --url <url>, --file <path>, or --web <url>.')
  process.exit(2)
}
const web = webArg !== undefined
const outDir = path.resolve(option('--out') ?? path.join(here, '..', '..', 'data', 'scratch', 'ui-verify'))
const offline = fileArg !== undefined
const base = offline ? pathToFileURL(path.resolve(fileArg)).href : (urlArg ?? webArg).replace(/#.*$/, '')
const label = offline ? 'file' : web ? 'web' : 'server'

const PRESENTER_SIZES = [
  { width: 1920, height: 1080 },
  { width: 1280, height: 720 },
]
const PHONE = { width: 390, height: 844 }
const SHORT_PHONE = { width: 375, height: 560 }
const expectSynthetic = option('--synthetic') // "yes", "no", or undefined (report only)
const expectQr = option('--qr') // "yes", "no", or undefined (report only)
const liveMock = args.includes('--live-mock')
if (liveMock && urlArg === undefined) {
  console.error('--live-mock needs --url pointing at a plain preview of ui/dist/.')
  process.exit(2)
}
// Strings that exist only in presenter or live-run code, shared with check-site.
const SHARED_STRINGS = JSON.parse(await readFile(path.join(here, 'presenter-strings.json'), 'utf8'))
// Builds without live mode must not hold any live string.
const LIVE_STRINGS = SHARED_STRINGS.live
const LIVE_BUTTON = 'Run on real quantum hardware now'
// The data every build imports. The screen names the run by the machine's size; the backend
// name and job ID belong to the presenter notes only (SPEC.md, Section 4.8).
const demo = JSON.parse(await readFile(path.join(here, '..', 'src', 'data', 'demo.json'), 'utf8'))
const realRun = !demo.metadata.synthetic && demo.metadata.backend !== null
const OFF_SCREEN = [demo.metadata.backend, demo.metadata.job_id].filter((v) => typeof v === 'string' && v !== '')
const machineName = (n) =>
  n === null ? 'an IBM quantum computer' : `${/^8|^1[18](\d{3})*$/.test(String(n)) ? 'an' : 'a'} ${n.toLocaleString('en-US')}-qubit IBM quantum computer`
const RUN_LABEL = `Run on ${machineName(demo.metadata.backend_num_qubits)}`
const BEAT = demo.games.beat
// Longest reveal on any scene is under 2 s.
const SETTLE_MS = 2200

const failures = []
const fail = (message) => {
  failures.push(message)
  console.log(`  FAIL ${message}`)
}

if (offline) {
  const html = await readFile(path.resolve(fileArg), 'utf8')
  // Only real tags and stylesheets count: the inlined JavaScript mentions src= and
  // href= in its own code. The network block below is the runtime guard.
  const markup = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, (tag) => tag.slice(0, tag.indexOf('>') + 1))
  const external = [...markup.matchAll(/<[a-z]+\b[^>]*?\b(?:src|href)\s*=\s*["']?(?!data:|#)([^"'\s>]+)/gi)].map(
    (m) => m[1],
  )
  if (external.length > 0) {
    fail(`HTML references external resources: ${external.slice(0, 5).join(', ')}`)
  }
  const styles = [...html.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/gi)].map((m) => m[1]).join('\n')
  const cssUrls = [...styles.matchAll(/url\(\s*["']?(?!data:|#)([^"')]+)/gi)].map((m) => m[1])
  if (cssUrls.length > 0) {
    fail(`CSS references external resources: ${cssUrls.slice(0, 5).join(', ')}`)
  }
  for (const m of LIVE_STRINGS) if (html.includes(m)) fail(`single file contains live-run code: "${m}"`)
  console.log(`single file: ${(html.length / 1024).toFixed(0)} KiB, no external references or live code checked`)
}

// Which fonts actually rendered the text on screen, from Chrome itself
// (CSS.getPlatformFontsForNode). Any glyph drawn by a font other than the bundled
// IBM Plex faces, such as a system fallback for a character Plex lacks, is reported
// with the element it appeared in.
async function fontReport(cdp) {
  const { root } = await cdp.send('DOM.getDocument', { depth: -1 })
  const { nodeIds } = await cdp.send('DOM.querySelectorAll', { nodeId: root.nodeId, selector: 'body *' })
  const used = new Set()
  const fallbacks = []
  for (const nodeId of nodeIds) {
    const { fonts } = await cdp.send('CSS.getPlatformFontsForNode', { nodeId })
    for (const font of fonts) {
      if (font.glyphCount === 0) continue
      used.add(font.familyName)
      if (!font.isCustomFont || !font.familyName.startsWith('IBM Plex')) {
        const { outerHTML } = await cdp.send('DOM.getOuterHTML', { nodeId })
        fallbacks.push(`${font.familyName} drew ${font.glyphCount} glyph(s) in ${outerHTML.slice(0, 120)}`)
      }
    }
  }
  return { used: [...used], fallbacks }
}

// The phone site's headers, from the _headers file in the build (Cloudflare Pages format:
// a path pattern, then indented "Name: value" lines; "! Name" removes a host default).
let siteHeaders = null
async function loadSiteHeaders() {
  const response = await fetch(new URL('_headers', base))
  if (!response.ok) {
    fail(`web: the build has no _headers file (${response.status})`)
    return {}
  }
  const rules = {}
  let current = null
  for (const line of (await response.text()).split('\n')) {
    if (line.trim() === '' || line.trim().startsWith('#')) continue
    if (!/^\s/.test(line)) {
      current = line.trim()
      rules[current] = {}
    } else if (current !== null && !line.trim().startsWith('!')) {
      const at = line.indexOf(':')
      rules[current][line.slice(0, at).trim().toLowerCase()] = line.slice(at + 1).trim()
    }
  }
  return rules
}

/** Headers for a site path, as the host would send them. */
function headersFor(pathname) {
  const out = {}
  for (const [pattern, headers] of Object.entries(siteHeaders ?? {})) {
    const re = new RegExp(`^${pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace('*', '.*')}$`)
    if (re.test(pathname)) Object.assign(out, headers)
  }
  return out
}

/** In --web mode: send the site's headers with every response and watch for violations. */
async function enforceSiteHeaders(context, page, where) {
  const origin = new URL(base).origin
  await context.route(() => true, async (route) => {
    const url = new URL(route.request().url())
    if (url.origin !== origin) {
      fail(`${where}: request to another origin: ${url.href}`)
      return route.abort()
    }
    const response = await route.fetch()
    return route.fulfill({ response, headers: { ...response.headers(), ...headersFor(url.pathname) } })
  })
  await page.addInitScript(() => {
    window.__cspViolations = []
    document.addEventListener('securitypolicyviolation', (e) =>
      window.__cspViolations.push(`${e.violatedDirective} blocked ${e.blockedURI || 'inline'}`),
    )
  })
}

async function cspViolations(page, where) {
  const seen = await page.evaluate(() => window.__cspViolations ?? null)
  if (seen === null) fail(`${where}: the CSP violation listener did not run`)
  for (const v of seen ?? []) fail(`${where}: CSP violation: ${v}`)
}

await mkdir(outDir, { recursive: true })
async function openPage(size, query, hash, extra = {}) {
  const context = await browser.newContext({ viewport: size, deviceScaleFactor: 1, offline, ...extra })
  const page = await context.newPage()
  if (web) await enforceSiteHeaders(context, page, `web ${size.width}×${size.height}`)
  const errors = []
  page.on('console', (m) => {
    // Enabling the DevTools CSS domain (for the font check) makes Chrome re-read a file:
    // document and log this one warning. It comes from the check, not the app: the same
    // page with no DevTools session logs nothing, offline or not.
    const fromFontCheck = /^Unsafe attempt to load URL file:.* 'file:' URLs are treated as unique security origins\.$/
    if (m.type() === 'error' && !fromFontCheck.test(m.text().trim())) errors.push(m.text())
    // A header the browser can't parse (an unknown Permissions-Policy feature, say) is only a warning.
    if (web && m.type() === 'warning' && /Permissions-Policy|Content.Security.Policy|header/i.test(m.text())) errors.push(m.text())
  })
  page.on('pageerror', (e) => errors.push(e.message))
  // Without live-server there is no token, so the app must never ask for live mode. And
  // the presenter builds load nothing from any other origin: no CDN, fonts, or services.
  page.on('request', (request) => {
    if (request.url().includes('/api/live/')) fail(`request to the live API without live-server: ${request.url()}`)
    const url = new URL(request.url())
    if (!offline && !['data:', 'blob:'].includes(url.protocol) && url.origin !== new URL(base).origin) {
      fail(`request to another origin: ${request.url()}`)
    }
  })
  if (offline) {
    // file: and data: URLs load normally; anything that would reach a network fails.
    await page.route(/^(https?|wss?):/, (route) => {
      fail(`network request attempted: ${route.request().url()}`)
      return route.abort()
    })
  }
  await page.goto(`${base}${query}${hash}`)
  await page.evaluate(() => document.fonts.ready)
  const faces = await page.evaluate(() => [...document.fonts].map((f) => `${f.family} ${f.status}`))
  for (const family of ['IBM Plex Sans', 'IBM Plex Mono']) {
    if (!faces.some((f) => f.includes(family) && f.endsWith('loaded'))) fail(`${family} never loaded`)
  }
  const cdp = await context.newCDPSession(page)
  await cdp.send('DOM.enable')
  await cdp.send('CSS.enable')
  return { context, page, errors, cdp }
}

async function fontSelfTest(page, cdp) {
  // Characters Plex does not have must be reported, or the font check is vacuous.
  await page.evaluate(() => {
    const probe = document.createElement('span')
    probe.id = 'verify-negative'
    probe.style.fontFamily = 'IBM Plex Sans'
    probe.textContent = 'λ★'
    document.body.append(probe)
  })
  // Chrome reports a node's fonts only once it has been laid out.
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  if ((await fontReport(cdp)).fallbacks.length === 0) {
    fail('font check self-test: a character missing from Plex was not detected')
  }
  await page.evaluate(() => document.getElementById('verify-negative')?.remove())
}

async function finish(name, { context, page, errors }) {
  if (web) await cspViolations(page, name)
  const shown = (await page.locator('.synthetic-label').count()) > 0
  console.log(`  synthetic label shown: ${shown ? 'yes' : 'no'}`)
  if (expectSynthetic !== undefined && shown !== (expectSynthetic === 'yes')) {
    fail(`${name}: synthetic label ${shown ? 'shown' : 'missing'}, expected ${expectSynthetic}`)
  }
  for (const e of errors) fail(`${name} console: ${e}`)
  await context.close()
}

async function presenter(size) {
  const tag = `${label}-presenter-${size.width}x${size.height}`
  console.log(`\n${tag}`)
  const session = await openPage(size, '', '#primitives/1')
  const { page, cdp } = session
  await fontSelfTest(page, cdp)
  await washedSelfTest(page, '.stage')

  const count = Number((await page.locator('.progress__count').textContent()).split('/')[1].trim())
  for (let i = 1; i <= count; i += 1) {
    await page.waitForTimeout(SETTLE_MS)
    const name = `${tag}-${String(i).padStart(2, '0')}.png`
    await page.screenshot({ path: path.join(outDir, name) })
    const { used, fallbacks } = await fontReport(cdp)
    for (const f of fallbacks) fail(`scene ${i}: ${f}`)
    console.log(`  scene ${i}: ${name}  [${used.join(', ')}]`)
    if (i < count) await page.keyboard.press('PageDown')
  }

  // Keys aimed at an interactive element stay with that element.
  const before = await page.evaluate(() => window.location.hash)
  await page.evaluate(() => {
    const button = document.createElement('button')
    button.id = 'verify-probe'
    button.textContent = 'probe'
    document.body.append(button)
    button.focus()
  })
  for (const key of ['Space', 'ArrowLeft', 'PageUp', '1', 'n']) await page.keyboard.press(key)
  if ((await page.evaluate(() => window.location.hash)) !== before) {
    fail('a key pressed on a focused button moved the deck')
  }
  if ((await page.locator('.notes').count()) !== 0) fail('N on a focused button opened the notes')
  await page.evaluate(() => document.getElementById('verify-probe')?.remove())

  // Clicking a panel control must not leave the clicker dead.
  const segment = page.locator('.segmented__option').first()
  if ((await segment.count()) > 0) {
    await segment.click()
    if ((await segment.getAttribute('aria-pressed')) !== 'true') fail('clicking a segment did not select it')
    await page.keyboard.press('PageUp')
    if ((await page.evaluate(() => window.location.hash)) !== `#primitives/${count - 1}`) {
      fail('after clicking a panel control, PageUp did not go back a scene')
    }
    await page.keyboard.press('PageDown')
  }

  // Notes open and close; the overlay's text must be Plex too.
  await page.keyboard.press('n')
  await page.waitForTimeout(400)
  if ((await page.locator('.notes').count()) !== 1) fail('N did not open the notes')
  for (const f of (await fontReport(cdp)).fallbacks) fail(`notes: ${f}`)
  await page.screenshot({ path: path.join(outDir, `${tag}-notes.png`) })
  await page.keyboard.press('n')
  if ((await page.locator('.notes').count()) !== 0) fail('N did not close the notes')

  await finish(tag, session)
}


// Everything on a slide must sit inside the 16:9 frame, above the progress rule.
async function offStage(page) {
  return page.evaluate(() => {
    const frame = document.querySelector('.stage__frame')?.getBoundingClientRect()
    const rule = document.querySelector('.progress')?.getBoundingClientRect()
    if (!frame || !rule) return ['no stage']
    // Content only: text-bearing leaves and media, not the full-frame layout boxes.
    const media = new Set(['CANVAS', 'svg', 'BUTTON', 'SELECT', 'IMG'])
    const isContent = (el) =>
      media.has(el.tagName) ||
      (el.closest('svg') === null && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim() !== ''))
    return [...document.querySelectorAll('.deck__scene *')]
      .filter((el) => isContent(el) && el.getClientRects().length > 0 && !el.closest('.sr-only'))
      .map((el) => ({ el, r: el.getBoundingClientRect() }))
      .filter(({ r }) => r.width > 0 && r.height > 0)
      .filter(({ r }) => r.right > frame.right + 1 || r.left < frame.left - 1 || r.bottom > rule.top + 1)
      .map(({ el }) => `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}: ${(el.textContent ?? '').trim().slice(0, 40)}`)
      .slice(0, 5)
  })
}

const hashOf = (page) => page.evaluate(() => window.location.hash)

// The backend name and job ID never appear on screen (SPEC.md, Section 4.8).
async function noRunIdsOnScreen(page, where) {
  const text = await page.evaluate(() => document.body.innerText)
  for (const id of OFF_SCREEN) if (text.includes(id)) fail(`${where}: "${id}" is on screen`)
}

// A washed-out projector, modelled as CSS contrast(0.7): every visible piece of text must
// keep at least 3:1 contrast against the colour behind it. Returns the worst offenders.
async function washedOutText(page, scope) {
  return page.evaluate((scope) => {
    const parse = (c) => {
      const m = c.match(/rgba?\(([^)]+)\)/)
      if (!m) return null
      const [r, g, b, a = 1] = m[1].split(/[ ,/]+/).filter(Boolean).map(Number)
      return { r: r / 255, g: g / 255, b: b / 255, a }
    }
    const over = (top, under) => ({
      r: top.r * top.a + under.r * (1 - top.a),
      g: top.g * top.a + under.g * (1 - top.a),
      b: top.b * top.a + under.b * (1 - top.a),
      a: 1,
    })
    const wash = (c) => ({ r: 0.7 * (c.r - 0.5) + 0.5, g: 0.7 * (c.g - 0.5) + 0.5, b: 0.7 * (c.b - 0.5) + 0.5, a: 1 })
    const lin = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
    const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b)
    const ratio = (a, b) => {
      const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x)
      return (hi + 0.05) / (lo + 0.05)
    }
    const backgroundOf = (el) => {
      const layers = []
      for (let n = el; n !== null; n = n.parentElement) {
        const bg = parse(getComputedStyle(n).backgroundColor)
        if (bg !== null && bg.a > 0) layers.push(bg)
        if (bg !== null && bg.a >= 1) break
      }
      let colour = { r: 1, g: 1, b: 1, a: 1 }
      for (const layer of layers.reverse()) colour = over(layer, colour)
      return colour
    }
    const bad = []
    for (const el of document.querySelectorAll(`${scope} *`)) {
      const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim() !== '')
      if (!own || el.closest('.sr-only') || el.getClientRects().length === 0) continue
      const style = getComputedStyle(el)
      if (style.visibility === 'hidden' || Number(style.opacity) === 0) continue
      const inSvg = el.closest('svg') !== null
      const fg = parse(inSvg && style.fill !== 'none' ? style.fill : style.color)
      if (fg === null) continue
      const bg = backgroundOf(el)
      const r = ratio(wash(over(fg, bg)), wash(bg))
      if (r < 3) bad.push(`${r.toFixed(2)}:1 ${el.tagName.toLowerCase()}.${[...el.classList].join('.')} "${el.textContent.trim().slice(0, 30)}"`)
    }
    return bad.slice(0, 5)
  }, scope)
}

// Faint grey text must be reported, or the washed-out check is vacuous.
async function washedSelfTest(page, scope) {
  await page.evaluate((scope) => {
    const probe = document.createElement('span')
    probe.id = 'verify-faint'
    probe.style.color = '#b4b4b4'
    probe.textContent = 'faint'
    document.querySelector(scope)?.append(probe)
  }, scope)
  if (!(await washedOutText(page, scope)).some((w) => w.includes('"faint"'))) {
    fail('washed-out check self-test: faint text was not detected')
  }
  await page.evaluate(() => document.getElementById('verify-faint')?.remove())
}

async function washedScreenshot(page, file) {
  await page.evaluate(() => (document.documentElement.style.filter = 'contrast(0.7)'))
  await page.screenshot({ path: file })
  await page.evaluate(() => (document.documentElement.style.filter = ''))
}

// Centre of a qubit on the chip map, in viewport pixels, after scrolling it into view.
async function qubitPoint(page, qubit) {
  const circle = page.locator(`.hardware__map [data-qubit="${qubit}"] circle`).first()
  await circle.scrollIntoViewIfNeeded()
  const box = await circle.boundingBox()
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 }
}

// A used qubit other than the one selected now, to tap or click.
async function anotherUsedQubit(page) {
  const current = (await page.locator('.hardware__name').first().textContent())?.match(/\d+/)?.[0]
  const used = await page.$$eval('.hardware__map g[data-qubit]', (gs) =>
    gs.filter((g) => g.querySelector('.hardware__used')).map((g) => g.dataset.qubit),
  )
  return used.filter((q) => q !== current)[Math.floor(used.length / 2)]
}

async function expectSelected(page, qubit, where) {
  const name = (await page.locator('.hardware__name').first().textContent()) ?? ''
  if (!new RegExp(`\\bQubit\\s*${qubit}\\b`).test(name.replace(/\s+/g, ' '))) {
    fail(`${where}: selecting qubit ${qubit} showed "${name.trim()}"`)
  }
}

async function talk(size, drivePanels) {
  const tag = `${label}-talk-${size.width}x${size.height}`
  console.log(`\n${tag}`)
  const session = await openPage(size, '', '')
  const { page, cdp } = session
  await page.waitForTimeout(300)
  if ((await hashOf(page)) !== '#1') fail(`presentation opened on ${await hashOf(page)}, not slide 1`)

  const qr = (await page.locator('.qr-code').count()) > 0
  console.log(`  QR code on slide 1: ${qr ? 'yes' : 'no'}`)
  if (expectQr !== undefined && qr !== (expectQr === 'yes')) fail(`QR code ${qr ? 'shown' : 'missing'}, expected ${expectQr}`)

  const seen = []
  for (;;) {
    await page.waitForTimeout(SETTLE_MS)
    const hash = await hashOf(page)
    seen.push(hash)
    const name = `${tag}-${hash.slice(1).replace('.', '-')}.png`
    await page.screenshot({ path: path.join(outDir, name) })
    const { used, fallbacks } = await fontReport(cdp)
    for (const f of fallbacks) fail(`slide ${hash}: ${f}`)
    for (const o of await offStage(page)) fail(`slide ${hash} at ${size.width}×${size.height}: off the stage: ${o}`)
    await noRunIdsOnScreen(page, `slide ${hash}`)
    for (const w of await washedOutText(page, '.stage')) fail(`slide ${hash} on a washed-out projector: ${w}`)
    if (drivePanels) await washedScreenshot(page, path.join(outDir, `${tag}-${hash.slice(1).replace('.', '-')}-washed.png`))
    if ((await page.locator('.notes').count()) === 0) {
      await page.keyboard.press('n')
      const notes = ((await page.locator('.notes__body').textContent()) ?? '').trim()
      if (notes === '' || /No notes for this scene/.test(notes)) fail(`slide ${hash} has no presenter notes`)
      if (hash === '#3' && realRun && !OFF_SCREEN.every((id) => notes.includes(id))) fail('slide 3 notes lack the backend and job ID')
      await page.keyboard.press('n')
    }
    console.log(`  ${hash}: ${name}  [${used.join(', ')}]`)
    await page.keyboard.press('PageDown')
    await page.waitForTimeout(100)
    if ((await hashOf(page)) === hash) break
    if (seen.length > 60) {
      fail('the deck never reached its end')
      break
    }
  }
  const count = Number((await page.locator('.progress__count').textContent()).split('/')[1].trim())
  if (!seen.at(-1).startsWith(`#${count}`)) fail(`walk ended on ${seen.at(-1)}, not slide ${count}`)
  // Back from the first step of a slide lands on the previous slide's last step.
  const lastOf = (n) => seen.filter((h) => h === `#${n}` || h.startsWith(`#${n}.`)).at(-1)
  await page.goto(`${base}#5`)
  await page.waitForTimeout(300)
  await page.keyboard.press('PageUp')
  if ((await hashOf(page)) !== lastOf(4)) fail(`PageUp from #5 went to ${await hashOf(page)}, not ${lastOf(4)}`)

  if (drivePanels) {
    // Machines: Generate fills the pictures and the counts.
    await page.goto(`${base}#3`)
    await page.waitForTimeout(500)
    // Not served by live-server: no live control and no live status.
    if ((await page.getByRole('button', { name: LIVE_BUTTON }).count()) > 0) fail('live control shown without live-server')
    if ((await page.locator('.live-run').count()) > 0) fail('live-run status shown without live-server')
    await page.getByRole('button', { name: 'Fast', exact: true }).click()
    await page.getByRole('button', { name: 'Generate bits' }).click()
    await page.waitForTimeout(1200)
    const status = (await page.locator('.machines__status').textContent()) ?? ''
    if (/^\s*0 of/.test(status)) fail(`Generate did not stream bits: "${status.trim()}"`)
    if ((await page.locator('.machine__stats dd.num').first().textContent())?.trim() === '–') fail('Generate did not update the counts')
    if (realRun) {
      const facts = ((await page.locator('.machine--quantum .run-facts').textContent()) ?? '').replace(/\s+/g, ' ')
      if (!facts.startsWith(RUN_LABEL)) fail(`slide 3 names the run "${facts.slice(0, 60)}", expected "${RUN_LABEL}"`)
    }
    // A panel button was clicked: the clicker must still move the deck.
    await page.keyboard.press('PageDown')
    if ((await hashOf(page)) !== '#4') fail(`after clicking Generate, PageDown went to ${await hashOf(page)}`)

    // Tell them apart: R reveals and does not move the deck.
    await page.waitForTimeout(400)
    if ((await page.locator('.tell-apart__caption .is-quantum').count()) !== 0) fail('pictures were labelled before the reveal')
    await page.keyboard.press('r')
    await page.waitForTimeout(400)
    if ((await page.locator('.tell-apart__caption .is-quantum').count()) !== 1) fail('R did not reveal the pictures')
    if ((await hashOf(page)) !== '#4') fail('R moved the deck')

    // Guess game: 0 and 1 score rounds and do not move the deck.
    await page.goto(`${base}#5`)
    await page.waitForTimeout(400)
    for (const key of ['0', '1', '1']) await page.keyboard.press(key)
    const score = (await page.locator('.guess__score').first().textContent()) ?? ''
    if (!/of\s*3\b/.test(score)) fail(`three guesses scored as "${score.trim()}"`)
    if ((await hashOf(page)) !== '#5') fail('0 or 1 moved the deck')

    // Attacker row, then the attack itself.
    await page.keyboard.press('PageDown')
    await page.waitForTimeout(400)
    await page.keyboard.press('1')
    if ((await page.locator('.guess__score').count()) !== 2) fail('the attacker row is missing on slide 6')
    await page.keyboard.press('PageDown')
    await page.waitForTimeout(400)
    for (const machine of ['classical', 'quantum']) {
      // The attacker panel starts on classical; M switches to quantum.
      if (machine === 'quantum') await page.keyboard.press('m')
      const picked = await page.locator('.segmented__option[aria-pressed="true"]').first().textContent()
      if (!new RegExp(machine, 'i').test(picked ?? '')) fail(`M did not switch the attacker to ${machine}`)
      await page.getByRole('button', { name: /^Launch/ }).click()
      await page.waitForTimeout(6600)
      if ((await page.locator('.attacker__final').count()) !== 1) fail(`the ${machine} attack did not reach its result`)
      await page.screenshot({ path: path.join(outDir, `${tag}-attack-${machine}.png`) })
    }

    // Slide 8: the QR code for phones, and no chip.
    let playSlide
    for (const hash of seen) {
      await page.goto(`${base}${hash}`)
      const titles = await page.locator('.scene__title').allTextContents()
      if (titles.some((t) => t.includes('play on your phone'))) {
        playSlide = hash
        break
      }
    }
    if (playSlide !== '#8') fail(`"Your turn: play on your phone" is ${playSlide ?? 'missing'}, not slide 8`)
    if (playSlide !== undefined) {
      if ((await page.locator('.hardware').count()) !== 0) fail('slide 8 still shows the chip')
      const code = (await page.locator('.qr-code').count()) > 0
      if (expectQr !== undefined && code !== (expectQr === 'yes')) fail(`slide 8: QR code ${code ? 'shown' : 'missing'}, expected ${expectQr}`)
    }

    // Q shows the QR overlay over any slide; Q again or Escape hides it; the deck stays put.
    await page.goto(`${base}#3`)
    await page.waitForTimeout(400)
    for (const close of ['q', 'Escape']) {
      await page.keyboard.press('q')
      await page.waitForTimeout(300)
      if ((await page.locator('.qr-overlay').count()) !== 1) fail('Q did not show the QR overlay')
      const overlayCode = (await page.locator('.qr-overlay .qr-code').count()) > 0
      if (expectQr !== undefined && overlayCode !== (expectQr === 'yes')) fail(`QR overlay: code ${overlayCode ? 'shown' : 'missing'}, expected ${expectQr}`)
      if (close === 'q') await page.screenshot({ path: path.join(outDir, `${tag}-qr-overlay.png`) })
      await page.keyboard.press(close)
      await page.waitForTimeout(200)
      if ((await page.locator('.qr-overlay').count()) !== 0) fail(`${close} did not hide the QR overlay`)
    }
    if ((await hashOf(page)) !== '#3') fail(`the QR overlay keys moved the deck to ${await hashOf(page)}`)

    // Chip: clicking a chosen qubit selects exactly that qubit.
    // The chip is the last step of the slide that has one.
    let chipSlide
    for (const hash of seen) {
      await page.goto(`${base}${hash}`)
      if ((await page.locator('.hardware').count()) > 0) {
        chipSlide = hash
        break
      }
    }
    if (chipSlide === undefined) {
      fail('no slide shows the chip')
    } else if ((await page.locator('.hardware__map').count()) === 0) {
      console.log('  no device layout in this data; chip click skipped')
    } else {
      await page.waitForTimeout(500)
      const qubit = await anotherUsedQubit(page)
      const { x, y } = await qubitPoint(page, qubit)
      await page.mouse.click(x, y)
      await expectSelected(page, qubit, 'presenter chip')
    }
  }
  await finish(tag, session)
}

// Things that belong only to the presenter: none may appear in the phone version.
const PRESENTER_SELECTORS = '.stage, .deck__scene, .scene, .notes, .panel, .progress, .qr-overlay, .primitives__half'
const PRESENTER_STRINGS = SHARED_STRINGS.presenter

// A real touch drag (Chrome's synthesized touch gesture) must scroll any screen taller
// than the viewport. Returns whether the screen was tall.
async function touchScrolls(page, cdp, where) {
  const { tall, width, height } = await page.evaluate(() => ({
    tall: document.documentElement.scrollHeight > window.innerHeight + 1,
    width: window.innerWidth,
    height: window.innerHeight,
  }))
  if (!tall) return false
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.waitForTimeout(100)
  await cdp.send('Input.synthesizeScrollGesture', {
    x: Math.round(width / 2),
    y: Math.round(height * 0.7),
    yDistance: -Math.round(height * 0.4),
    gestureSourceType: 'touch',
    speed: 1200,
  })
  await page.waitForTimeout(300)
  if ((await page.evaluate(() => window.scrollY)) <= 0) fail(`${where}: a touch drag did not scroll the page`)
  await page.evaluate(() => window.scrollTo(0, 0))
  return true
}

async function phone(size, shots) {
  const tag = `${label}-phone-${size.width}x${size.height}`
  console.log(`\n${tag}`)
  const session = await openPage(size, web ? '' : '?view=audience', '', {
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  })
  const { page, cdp } = session
  await fontSelfTest(page, cdp)
  await washedSelfTest(page, 'body')
  await page.waitForTimeout(600)
  let tallScreens = 0
  const screens = []

  async function screen(name) {
    await page.waitForTimeout(250)
    screens.push(name)
    const where = `phone ${size.width}×${size.height} ${name}`
    if (shots) await page.screenshot({ path: path.join(outDir, `${tag}-${name}.png`), fullPage: true })
    if ((await page.locator(PRESENTER_SELECTORS).count()) > 0) fail(`${where}: presenter content on screen`)
    const layout = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      bodyFont: parseFloat(getComputedStyle(document.body).fontSize),
      small: [...document.querySelectorAll('button, a[href], input, select, [role="button"]')]
        .map((el) => {
          const r = el.getBoundingClientRect()
          return { text: el.textContent?.trim() ?? '', w: r.width, h: r.height }
        })
        .filter((t) => t.w < 44 || t.h < 44),
    }))
    if (layout.overflow > 0) fail(`${where}: page is ${layout.overflow}px wider than the screen`)
    if (layout.bodyFont < 16) fail(`${where}: body text is ${layout.bodyFont}px`)
    for (const t of layout.small) fail(`${where}: control "${t.text}" is ${t.w.toFixed(0)}×${t.h.toFixed(0)} px`)
    for (const f of (await fontReport(cdp)).fallbacks) fail(`${where}: ${f}`)
    await noRunIdsOnScreen(page, where)
    for (const w of await washedOutText(page, 'body')) fail(`${where} with contrast reduced 30%: ${w}`)
    if (await touchScrolls(page, cdp, where)) tallScreens += 1
  }
  const tap = async (name) => {
    const button = page.getByRole('button', { name, exact: typeof name === 'string' }).first()
    await button.scrollIntoViewIfNeeded()
    await button.tap()
  }

  // Intro: the title and the two games.
  const title = (await page.locator('h1').first().textContent()) ?? ''
  if (!/beat a quantum computer/i.test(title)) fail(`phone intro title is "${title.trim()}"`)
  await screen('intro')

  // Presenter keys do nothing here.
  const before = await hashOf(page)
  for (const key of ['n', 'f', 'p', 'q']) await page.keyboard.press(key)
  await page.waitForTimeout(300)
  if ((await page.locator(PRESENTER_SELECTORS).count()) > 0) fail('phone: a presenter key showed presenter content')
  if ((await page.evaluate(() => document.fullscreenElement !== null))) fail('phone: F went fullscreen')
  if ((await hashOf(page)) !== before) fail('phone: a presenter key changed the page')

  // Game 1, twice: every image fresh, then the "all seen" message.
  await tap('Spot the quantum machine')
  await screen('spot-start')
  const seenImages = []
  for (let game = 1; game <= 2; game += 1) {
    await tap(game === 1 ? 'Start' : 'Play again with new pictures')
    for (let round = 1; round <= 5; round += 1) {
      await page.waitForTimeout(150)
      const ids = await page.$$eval('[data-spot]', (els) => els.map((el) => el.getAttribute('data-spot')))
      if (ids.length !== 2 || !ids.some((i) => i.startsWith('classical:')) || !ids.some((i) => i.startsWith('quantum:'))) {
        fail(`spot round ${round}: expected one image from each machine, got ${ids.join(', ')}`)
      }
      seenImages.push(...ids)
      if (game === 1 && round === 1) await screen('spot-round')
      if ((await page.locator('.spot-pair__caption .is-quantum').count()) !== 0) fail('spot: labels shown before answering')
      await tap(round % 2 ? 'Picture A' : 'Picture B')
      if ((await page.locator('.spot-pair__caption .is-quantum').count()) !== 1) fail('spot: tapping did not reveal the pictures')
      if (game === 1 && round === 1) await screen('spot-reveal')
      await tap(round < 5 ? 'Next pair' : 'See your score')
    }
    const score = (await page.locator('.phone-score').first().textContent()) ?? ''
    if (!/of\s*5\b/.test(score)) fail(`spot game ${game}: score reads "${score.trim()}"`)
    if (game === 1) await screen('spot-end')
  }
  if (new Set(seenImages).size !== seenImages.length) fail(`spot: an image was shown twice (${seenImages.length} shown, ${new Set(seenImages).size} distinct)`)
  console.log(`  spot: ${seenImages.length} images, all distinct`)
  if ((await page.getByRole('button', { name: 'Play again with new pictures' }).count()) !== 0) {
    fail('spot: offered to play again with no unseen pictures left')
  }

  // Game 2 on each machine: all its rounds, then the two counts side by side.
  await tap(/^Next game/)
  await screen('beat-pick')
  for (const [i, machine] of ['Ordinary formula', 'Quantum computer'].entries()) {
    await tap(i === 0 ? machine : 'Try the quantum computer')
    for (let round = 1; round <= BEAT.rounds; round += 1) {
      const counter = (await page.locator('.phone-step').first().textContent()) ?? ''
      if (!new RegExp(`Round\\s*${round}\\s*of\\s*${BEAT.rounds}`).test(counter)) fail(`beat ${machine}: round counter reads "${counter.trim()}"`)
      await tap(round % 3 ? 'Guess 1' : 'Guess 0')
      if (round === 1) {
        const feedback = (await page.locator('.beat-feedback').textContent()) ?? ''
        if (!/The bit was/.test(feedback) || !/attacker guessed/.test(feedback)) fail(`beat ${machine}: no feedback after a guess`)
        if (i === 0) await screen('beat-round')
      }
    }
    await page.waitForTimeout(150)
    const scores = await page.$$eval('.beat-score', (els) => els.map((el) => el.textContent?.replace(/\s+/g, ' ').trim()))
    if (scores.length !== 2 || !scores.every((t) => new RegExp(`of ${BEAT.rounds}$`).test(t ?? ''))) fail(`beat ${machine}: end scores read ${JSON.stringify(scores)}`)
    const luck = ((await page.locator('[data-chance-range]').textContent()) ?? '').replace(/\s+/g, ' ').trim()
    const { low, high } = BEAT.chance_range
    if (!luck.includes(`With only ${BEAT.rounds} rounds, luck swings scores a lot: most pure-guess games land between ${low} and ${high} out of ${BEAT.rounds}. One game isn't the measurement; the full dataset is.`)) {
      fail(`beat ${machine}: the luck line reads "${luck}"`)
    }
    console.log(`  beat ${machine}: ${scores.join(' | ')}`)
    if (i === 0) await screen('beat-end')
  }

  // Closing screen, with the run's details.
  await tap('What it all means')
  await screen('end')
  const small = (await page.locator('.phone-small').allTextContents()).join(' ')
  if (realRun && !small.replace(/\s+/g, ' ').includes(`The quantum bits: ${RUN_LABEL.replace('Run', 'run')}`)) {
    fail(`closing screen does not say "${RUN_LABEL}": "${small.trim().slice(0, 120)}"`)
  }
  await tap('Back to the games')
  if (!/beat a quantum computer/i.test((await page.locator('h1').first().textContent()) ?? '')) fail('Back to the games did not return to the intro')

  console.log(`  screens: ${screens.length}, taller than the screen (touch-scrolled): ${tallScreens}`)
  await finish(tag, session)
}

// The phone site's own files must not carry presenter content.
async function webBundle() {
  console.log('\nweb bundle')
  const context = await browser.newContext()
  const page = await context.newPage()
  await enforceSiteHeaders(context, page, 'web bundle')
  const bodies = []
  const scripts = []
  page.on('response', async (response) => {
    if (/\.(js|css|html)(\?|$)|\/$/.test(response.url())) bodies.push(response.text().catch(() => ''))
    if (/\.js(\?|$)/.test(response.url())) scripts.push(response.url())
    if (/\.map(\?|$)/.test(response.url())) fail(`web: a source map was loaded: ${response.url()}`)
  })
  await page.goto(base)
  await page.waitForLoadState('networkidle')
  const text = (await Promise.all(bodies)).join('\n')
  if (text.length < 1000) fail('web bundle: could not read the site\'s files')
  for (const s of PRESENTER_STRINGS) if (text.includes(s)) fail(`web bundle contains presenter content: "${s}"`)
  for (const m of LIVE_STRINGS) if (text.includes(m)) fail(`web bundle contains live-run code: "${m}"`)
  if (/sourceMappingURL/.test(text)) fail('web bundle refers to a source map')
  for (const url of scripts) {
    const map = await fetch(`${url}.map`)
    if (map.ok && (await map.text()).trimStart().startsWith('{')) fail(`web: ${url}.map is served`)
  }
  // The headers every page must carry (SPEC.md, Section 9.7).
  const rootHeaders = headersFor('/')
  const csp = rootHeaders['content-security-policy'] ?? ''
  for (const directive of ["default-src 'none'", "object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'", "form-action 'none'", "connect-src 'none'"]) {
    if (!csp.includes(directive)) fail(`_headers: the CSP lacks ${directive}`)
  }
  if (/unsafe-(eval|inline)|\*|https?:/.test(csp)) fail(`_headers: the CSP allows more than the site's own files: ${csp}`)
  const expected = {
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'no-referrer',
    'cross-origin-opener-policy': 'same-origin',
  }
  for (const [name, value] of Object.entries(expected)) if (rootHeaders[name] !== value) fail(`_headers: ${name} is "${rootHeaders[name]}"`)
  for (const feature of ['camera=()', 'microphone=()', 'geolocation=()']) {
    if (!(rootHeaders['permissions-policy'] ?? '').includes(feature)) fail(`_headers: Permissions-Policy lacks ${feature}`)
  }
  if (!/max-age=\d{7,}/.test(rootHeaders['strict-transport-security'] ?? '')) fail('_headers: no Strict-Transport-Security')
  // The primitives page and the deck's routes don't exist here.
  for (const route of ['?primitives', '#primitives', '?view=presenter#3']) {
    await page.goto(`${base}${route}`)
    await page.waitForTimeout(300)
    if ((await page.locator(PRESENTER_SELECTORS).count()) > 0) fail(`web: ${route} shows presenter content`)
  }
  console.log(`  ${(text.length / 1024).toFixed(0)} KiB checked`)
  await cspViolations(page, 'web bundle')
  await context.close()
}

// Both games under the site's headers in another engine: Firefox (Gecko) or WebKit (Safari).
async function webEngine(engine) {
  const where = `web ${engine.name()}`
  console.log(`\n${where}`)
  const other = await engine.launch()
  try {
    const context = await other.newContext({ viewport: PHONE, hasTouch: true })
    const page = await context.newPage()
    const errors = []
    page.on('console', (m) => {
      if (m.type() === 'error') errors.push(m.text())
    })
    page.on('pageerror', (e) => errors.push(e.message))
    await enforceSiteHeaders(context, page, where)
    await page.goto(base)
    await page.evaluate(() => document.fonts.ready)
    const faces = await page.evaluate(() => [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family))
    if (!faces.some((f) => f.includes('IBM Plex Sans'))) fail(`${where}: IBM Plex Sans did not load`)
    const click = (name) => page.getByRole('button', { name, exact: typeof name === 'string' }).first().click()
    await click('Spot the quantum machine')
    await click('Start')
    for (let round = 1; round <= 5; round += 1) {
      await click(round % 2 ? 'Picture A' : 'Picture B')
      await click(round < 5 ? 'Next pair' : 'See your score')
    }
    await click(/^Next game/)
    await click('Quantum computer')
    for (let round = 1; round <= BEAT.rounds; round += 1) await click(round % 2 ? 'Guess 1' : 'Guess 0')
    if ((await page.locator('[data-chance-range]').count()) !== 1) fail(`${where}: Beat the attacker did not reach its end`)
    await click('What it all means')
    // Before the screenshot: Playwright's WebKit screenshot injects a <style> of its own
    // (to hide the caret), which the CSP rightly blocks; it is not the app's.
    await cspViolations(page, where)
    for (const e of errors) fail(`${where} console: ${e}`)
    await page.screenshot({ path: path.join(outDir, `web-${engine.name()}-end.png`), fullPage: true, caret: 'initial' })
    console.log('  both games played under the site headers')
    await context.close()
  } finally {
    await other.close()
  }
}

// ---- Live run, mocked (--live-mock) -------------------------------------------------
// The browser plays the part of live-server: a token in the page and /api/live/ answered
// here. Nothing reaches a Python server or IBM.

const MOCK_BACKEND = 'mock_backend'
// Not the recorded run's size, so the fresh label must come from the live response.
const MOCK_BACKEND_QUBITS = 133
const MOCK_JOB = 'd3mockjob00000000000'
const MOCK_RUN = '0123456789abcdef'

function mockResult() {
  const bytes = Buffer.alloc(2000 / 8)
  let x = 20261007
  for (let i = 0; i < bytes.length; i += 1) {
    x = (x * 1103515245 + 12345) & 0x7fffffff
    bytes[i] = (x >> 16) & 0xff
  }
  return {
    backend: MOCK_BACKEND,
    backend_num_qubits: MOCK_BACKEND_QUBITS,
    job_id: MOCK_JOB,
    shots: 200,
    n_qubits: 10,
    n_bits: 2000,
    physical_qubits: [3, 7, 12, 19, 24, 31, 40, 55, 61, 77],
    qubit_selection: { method: 'lowest_readout_error', candidates: 156 },
    bits: bytes.toString('base64'),
    p_one: Array(10).fill(0.5),
    fraction_ones: 0.5,
    shannon_entropy: { pooled: 1, per_qubit_mean: 1 },
    submitted_utc: '2026-10-07T14:30:00Z',
    completed_utc: '2026-10-07T14:31:05Z',
    qpu_seconds: 2.1,
  }
}

const ARMED = (remaining) => ({
  armed: true,
  backend: MOCK_BACKEND,
  backend_num_qubits: MOCK_BACKEND_QUBITS,
  runs_remaining: remaining,
  max_runs: 3,
  shots: 200,
  n_qubits: 10,
})
const UNARMED = { armed: false, backend: null, backend_num_qubits: null, runs_remaining: 0, max_runs: 0, shots: null, n_qubits: null }
const MOCK_MACHINE = `a ${MOCK_BACKEND_QUBITS}-qubit IBM quantum computer`
const json = (route, status, body) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

/** A mocked live server: health, start, and a scripted list of status replies. */
function armedServer({ statuses = [], start = { status: 202, body: { id: MOCK_RUN, stage: 'submitting' } }, vanish = false } = {}) {
  let polls = 0
  let remaining = 3
  return async (route, request, pathname) => {
    if (pathname === '/api/live/health' && request.method() === 'GET') return json(route, 200, ARMED(remaining))
    if (pathname === '/api/live/runs' && request.method() === 'POST') {
      if (start.status === 202) remaining -= 1
      return json(route, start.status, start.body)
    }
    if (pathname === `/api/live/runs/${MOCK_RUN}` && request.method() === 'GET') {
      if (vanish) return route.abort('connectionrefused')
      const reply = statuses[Math.min(polls, statuses.length - 1)]
      polls += 1
      return json(route, 200, { id: MOCK_RUN, job_id: null, elapsed_seconds: null, error: null, result: null, ...reply })
    }
    fail(`unexpected live API call ${request.method()} ${pathname}`)
    return json(route, 404, { error: 'Not found.' })
  }
}

async function waitText(locator, pattern, what, timeout = 8000) {
  const deadline = Date.now() + timeout
  let text = ''
  while (Date.now() < deadline) {
    text = ((await locator.count()) > 0 ? await locator.first().textContent() : '') ?? ''
    if (pattern.test(text)) return text
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  fail(`${what}: expected ${pattern}, saw "${text.trim()}"`)
  return text
}

async function notesText(page) {
  await page.keyboard.press('n')
  const text = ((await page.locator('.notes__body').textContent()) ?? '').trim()
  await page.keyboard.press('n')
  return text
}

async function liveScenario(name, { size = PRESENTER_SIZES[0], server, fakeClock = false }, check) {
  const tag = `live-${name}-${size.width}x${size.height}`
  console.log(`\n${tag}`)
  const token = `verify-${name}-token`
  const context = await browser.newContext({ viewport: size, deviceScaleFactor: 1 })
  const page = await context.newPage()
  const errors = []
  // A refused connection is logged by Chrome itself; anything else is an app error.
  page.on('console', (m) => {
    if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text())
  })
  page.on('pageerror', (e) => errors.push(e.message))
  const calls = []
  await page.route(
    (url) => url.pathname.endsWith('/') || url.pathname.endsWith('/index.html'),
    async (route) => {
      if (route.request().resourceType() !== 'document') return route.continue()
      const response = await route.fetch()
      const html = (await response.text()).replace('</head>', `<meta name="qrng-live-token" content="${token}" /></head>`)
      return route.fulfill({ response, body: html })
    },
  )
  await page.route(/\/api\/live\//, async (route) => {
    const request = route.request()
    const { pathname } = new URL(request.url())
    const sent = request.headers()['x-qrng-live-token']
    calls.push({ method: request.method(), pathname })
    if (sent !== token) fail(`${tag}: ${request.method()} ${pathname} without the session token`)
    return server(route, request, pathname)
  })
  if (fakeClock) await page.clock.install()
  await page.goto(`${base}#3`)
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(800)
  const cdp = await context.newCDPSession(page)
  await cdp.send('DOM.enable')
  await cdp.send('CSS.enable')
  await check({ page, calls, tag })
  const screen = await page.evaluate(() => document.body.innerText)
  for (const id of [MOCK_BACKEND, MOCK_JOB, ...OFF_SCREEN]) if (screen.includes(id)) fail(`${tag}: "${id}" is on screen`)
  const { fallbacks } = await fontReport(cdp)
  for (const f of fallbacks) fail(`${tag}: ${f}`)
  for (const o of await offStage(page)) fail(`${tag}: off the stage: ${o}`)
  await page.screenshot({ path: path.join(outDir, `${tag}.png`) })
  for (const e of errors) fail(`${tag} console: ${e}`)
  await context.close()
}

/** Each machine's picture: its box on screen, its frame's box, its canvas pixels, and its caption. */
async function pictures(page) {
  return page.$$eval('.machine', (machines) =>
    machines.map((m) => {
      const canvas = m.querySelector('canvas.bitmap')
      const frame = m.querySelector('.machine__frame')
      const box = (el) => {
        const r = el.getBoundingClientRect()
        return { x: r.x, y: r.y, width: r.width, height: r.height }
      }
      return {
        source: m.classList.contains('machine--quantum') ? 'quantum' : 'classical',
        canvas: box(canvas),
        frame: box(frame),
        pixels: { width: canvas.width, height: canvas.height },
        caption: m.querySelector('.machine__caption')?.textContent?.trim() ?? null,
      }
    }),
  )
}

/** The recorded-run picture: 128 × 128, square, filling its frame, with no caption. */
async function expectNormalPictures(page, tag) {
  const shown = await pictures(page)
  if (shown.length !== 2) fail(`${tag}: expected two machine pictures, saw ${shown.length}`)
  for (const p of shown) {
    if (Math.abs(p.canvas.width - p.canvas.height) > 1) fail(`${tag}: ${p.source} picture is not square (${p.canvas.width}×${p.canvas.height})`)
    if (Math.abs(p.canvas.width - p.frame.width) > 1 || Math.abs(p.canvas.height - p.frame.height) > 1) fail(`${tag}: ${p.source} picture does not fill its square`)
    if (p.caption !== null) fail(`${tag}: ${p.source} picture has a caption: "${p.caption}"`)
  }
  return shown
}

const RECORDED = /showing (the run from \d{1,2} [A-Z][a-z]+ \d{4}, \d{2}:\d{2} UTC|the recorded sample data)\./

async function liveChecks() {
  await liveScenario('unarmed', { server: (route, request, pathname) => {
    if (pathname === '/api/live/health') return json(route, 200, UNARMED)
    fail(`unarmed: unexpected ${request.method()} ${pathname}`)
    return json(route, 503, { error: 'Live mode is not available.' })
  } }, async ({ page, calls, tag }) => {
    if ((await page.getByRole('button', { name: LIVE_BUTTON }).count()) > 0) fail(`${tag}: live control shown`)
    if ((await page.locator('.live-run').count()) > 0) fail(`${tag}: live status shown`)
    if (/Live run/.test(await notesText(page))) fail(`${tag}: notes mention the live run`)
    await expectNormalPictures(page, tag)
    const asked = calls.map((c) => `${c.method} ${c.pathname}`)
    if (asked.join() !== 'GET /api/live/health') fail(`${tag}: expected one health check, saw ${asked.join(', ')}`)
  })

  await liveScenario('unreachable', { server: (route) => route.abort('connectionrefused') }, async ({ page, tag }) => {
    if ((await page.getByRole('button', { name: LIVE_BUTTON }).count()) > 0) fail(`${tag}: live control shown`)
    if ((await page.locator('.live-run').count()) > 0) fail(`${tag}: live status shown`)
    await page.getByRole('button', { name: 'Fast', exact: true }).click()
    await page.getByRole('button', { name: 'Generate bits' }).click()
    await page.waitForTimeout(800)
    await waitText(page.locator('.machines__status'), /recorded bits from each machine/, `${tag}: recorded bits still stream`)
    if ((await page.locator('.run-facts', { hasText: realRun ? RUN_LABEL : 'Sample data' }).count()) === 0) {
      fail(`${tag}: the recorded run's facts are missing`)
    }
  })

  for (const size of PRESENTER_SIZES) {
    await liveScenario('done', { size, server: armedServer({ statuses: [
      { stage: 'submitted', job_id: MOCK_JOB },
      { stage: 'queued', job_id: MOCK_JOB, elapsed_seconds: 5 },
      { stage: 'running', job_id: MOCK_JOB, elapsed_seconds: 9 },
      { stage: 'done', job_id: MOCK_JOB, result: mockResult() },
    ] }) }, async ({ page, calls, tag }) => {
      const button = page.getByRole('button', { name: LIVE_BUTTON, exact: true })
      if ((await button.count()) !== 1) {
        fail(`${tag}: live control missing`)
        return
      }
      const box = await button.boundingBox()
      const scale = size.width / 1920
      if (box === null || box.width < 44 * scale || box.height < 44 * scale) fail(`${tag}: live button under 44 px`)
      if (!/Live run/.test(await notesText(page))) fail(`${tag}: notes don't explain the live run`)
      const before = await expectNormalPictures(page, `${tag} before the run`)
      await page.getByRole('button', { name: 'Fast', exact: true }).click()
      await button.click()
      // The button gives up focus, so the clicker still drives the deck.
      if ((await page.evaluate(() => document.activeElement?.tagName)) === 'BUTTON') fail(`${tag}: live button kept focus`)
      const status = page.locator('.live-run')
      await waitText(status, new RegExp(`^Sending a job to ${MOCK_MACHINE}\\.$`), `${tag}: submitting`)
      await waitText(status, /^Sent\. Waiting for IBM's queue\.$/, `${tag}: submitted`)
      await waitText(status, /^Waiting in IBM's queue: 0:05\.$/, `${tag}: queued with time`)
      await waitText(status, /^Running on the quantum computer now\.$/, `${tag}: running`)
      // The live job's ID and backend are in the notes as soon as they exist, never on screen.
      if (!(await notesText(page)).includes(`job ${MOCK_JOB} on ${MOCK_BACKEND}`)) fail(`${tag}: notes lack the live job ID and backend`)
      await waitText(status, new RegExp(`^Fresh bits from ${MOCK_MACHINE} are playing on the quantum machine\\..*\\(2,000 bits\\), so its numbers are noisy; the headline numbers come from the full run\\.$`), `${tag}: done`)
      await waitText(page.locator('.machine--quantum .run-facts'), new RegExp(`^Fresh from ${MOCK_MACHINE}, 7 October 2026, 14:31 UTC: 10 qubits × 200 shots \\(qubits picked for lowest readout error from 156\\)\\.$`), `${tag}: fresh label`)
      await waitText(page.locator('.machines__status'), /^End of the fresh bits\.$/, `${tag}: fresh bits streamed to the end`)
      if ((await page.locator('.machine--quantum .machine__stats dd.num').first().textContent())?.trim() === '–') fail(`${tag}: no counts for the fresh bits`)
      // Both pictures are sized to the 2,000 bits (40 × 50), with square cells, inside the
      // same on-screen square as the 128 × 128 picture, and captioned with the dimensions.
      const after = await pictures(page)
      for (const p of after) {
        const normal = before.find((b) => b.source === p.source)
        if (p.caption !== '40 × 50 bits') fail(`${tag}: ${p.source} caption is "${p.caption}", expected "40 × 50 bits"`)
        if (normal !== undefined) {
          const same = (a, b) => Math.abs(a - b) <= 1
          if (!same(p.frame.width, normal.frame.width) || !same(p.frame.height, normal.frame.height)) fail(`${tag}: ${p.source} picture's square changed size`)
          if (!same(p.canvas.height, normal.canvas.height)) fail(`${tag}: ${p.source} live picture is ${p.canvas.height}px tall, not ${normal.canvas.height}px like the normal one`)
          if (!same(p.canvas.width, (normal.canvas.height * 40) / 50)) fail(`${tag}: ${p.source} live picture is ${p.canvas.width}px wide, expected 40/50 of its height`)
          if (!same(p.canvas.x + p.canvas.width / 2, p.frame.x + p.frame.width / 2)) fail(`${tag}: ${p.source} live picture is not centred in its square`)
        }
        if (Math.abs(p.pixels.width / p.pixels.height - 40 / 50) > 0.02) fail(`${tag}: ${p.source} canvas is drawn ${p.pixels.width}×${p.pixels.height}, not 40:50`)
      }
      const posts = calls.filter((c) => c.method === 'POST')
      if (posts.length !== 1) fail(`${tag}: expected one POST, saw ${posts.length}`)
      if (size === PRESENTER_SIZES[0]) {
        await page.keyboard.press('PageDown')
        if ((await hashOf(page)) !== '#4') fail(`${tag}: after the live run, PageDown went to ${await hashOf(page)}`)
        await page.keyboard.press('PageUp')
        await page.waitForTimeout(400)
        // Back on the slide, the fresh run is still shown.
        await waitText(page.locator('.machine--quantum .run-facts'), new RegExp(`^Fresh from ${MOCK_MACHINE}`), `${tag}: fresh run kept across slides`)
      }
    })
  }

  await liveScenario('timeout', { fakeClock: true, server: armedServer({ statuses: [{ stage: 'queued', job_id: MOCK_JOB, elapsed_seconds: 30 }] }) }, async ({ page, calls, tag }) => {
    await page.getByRole('button', { name: LIVE_BUTTON }).click()
    await waitText(page.locator('.live-run'), /Waiting in IBM's queue/, `${tag}: queued`)
    if ((await page.locator('.live-run', { hasText: 'busy' }).count()) > 0) fail(`${tag}: fell back before the timeout`)
    await page.clock.fastForward('01:50')
    await page.waitForTimeout(300)
    if ((await page.locator('.live-run', { hasText: 'busy' }).count()) > 0) fail(`${tag}: fell back before 120 s`)
    await page.clock.fastForward('00:11')
    const text = await waitText(page.locator('.live-run'), /^IBM's queue is busy; showing /, `${tag}: timeout label`)
    if (!RECORDED.test(text)) fail(`${tag}: label does not name the recorded run: "${text}"`)
    if (!/The job may still finish on IBM\.$/.test(text)) fail(`${tag}: no note that the job may still finish`)
    if ((await page.locator('.machine--quantum .run-facts', { hasText: 'Fresh from' }).count()) > 0) fail(`${tag}: fresh label after a timeout`)
    await expectNormalPictures(page, tag)
    const polls = () => calls.filter((c) => c.pathname.startsWith('/api/live/runs/')).length
    const before = polls()
    await page.clock.fastForward('00:05')
    await page.waitForTimeout(300)
    if (polls() > before) fail(`${tag}: kept polling after giving up`)
    const notes = await notesText(page)
    if (!/may still finish on IBM/.test(notes)) fail(`${tag}: notes don't say the job may still finish`)
    if (!notes.includes(`job ${MOCK_JOB} on ${MOCK_BACKEND}`)) fail(`${tag}: notes lack the job ID to look up later`)
  })

  await liveScenario('failed', { server: armedServer({ statuses: [{ stage: 'queued', job_id: MOCK_JOB, elapsed_seconds: 2 }, { stage: 'failed', job_id: MOCK_JOB, error: 'The job ended as ERROR.' }] }) }, async ({ page, tag }) => {
    await page.getByRole('button', { name: LIVE_BUTTON }).click()
    const text = await waitText(page.locator('.live-run'), /^The live run didn't finish; showing /, `${tag}: failure label`)
    if (!RECORDED.test(text)) fail(`${tag}: label does not name the recorded run: "${text}"`)
    if ((await page.locator('.machine--quantum .run-facts', { hasText: 'Fresh from' }).count()) > 0) fail(`${tag}: fresh label after a failure`)
    await expectNormalPictures(page, tag)
  })

  await liveScenario('vanished', { server: armedServer({ vanish: true }) }, async ({ page, tag }) => {
    await page.getByRole('button', { name: LIVE_BUTTON }).click()
    await waitText(page.locator('.live-run'), /^The live run didn't finish; showing /, `${tag}: failure label when the server is gone`)
  })

  await liveScenario('refused', { server: armedServer({ start: { status: 409, body: { error: 'A live run is still in progress.' } } }) }, async ({ page, tag }) => {
    await page.getByRole('button', { name: LIVE_BUTTON }).click()
    await waitText(page.locator('.live-run'), /^A live run is still in progress\.$/, `${tag}: refusal shown`)
    if ((await page.locator('.machine--quantum .run-facts', { hasText: 'Fresh from' }).count()) > 0) fail(`${tag}: fresh label after a refusal`)
  })
}

const browser = await chromium.launch()
try {
  if (liveMock) {
    await liveChecks()
  } else if (web) {
    siteHeaders = await loadSiteHeaders()
    await webBundle()
    for (const engine of [firefox, webkit]) await webEngine(engine)
  } else {
    for (const [i, size] of PRESENTER_SIZES.entries()) await talk(size, i === 0)
    for (const size of PRESENTER_SIZES) await presenter(size)
  }
  if (!liveMock) {
    await phone(PHONE, true)
    await phone(SHORT_PHONE, false)
  }
} finally {
  await browser.close()
}

console.log(`\nscreenshots in ${outDir}`)
if (failures.length > 0) {
  console.log(`${failures.length} check(s) failed`)
  process.exit(1)
}
console.log('all checks passed')
