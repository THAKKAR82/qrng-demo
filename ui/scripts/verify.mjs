// Visual and offline verification of the UI. Development only: Playwright is a
// devDependency used by this script and nothing else; no run mode or task needs it.
//
//   node scripts/verify.mjs --url http://localhost:4173/   # a running dev or preview server
//   node scripts/verify.mjs --file ../demo/index.html      # the single-file build, offline
//   add --synthetic yes|no to require (or forbid) the synthetic-data label
//
// Presenter view, at 1920×1080 and 1280×720: walks every scene of the primitives page,
// saves a screenshot of each, and checks that
//   - every character on screen renders in IBM Plex, not a fallback font (checked with
//     Chrome's own record of the fonts it used, after a self-test that it catches one);
//   - keys pressed on an interactive element do not move the deck, and the clicker
//     still works after a panel button has been clicked;
//   - N shows and hides the notes overlay, and PageUp goes back.
// Audience view (?view=audience), on a 390×844 touch phone: saves screenshots and checks
// fonts, that nothing overflows sideways, that every control is at least 44×44 CSS px,
// and that tapping a control works.
// Both: no console or page errors; with --synthetic yes|no, the synthetic label is (or
// is not) on screen.
// With --file it also blocks the network entirely and fails on any request that is not
// file: or data:, and checks the HTML references no external resources.
// Screenshots go to data/scratch/ui-verify/ (gitignored) unless --out is given.

import { mkdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { chromium } from 'playwright'

const here = path.dirname(fileURLToPath(import.meta.url))
const args = process.argv.slice(2)
const option = (name) => {
  const i = args.indexOf(name)
  return i >= 0 ? args[i + 1] : undefined
}

const fileArg = option('--file')
const urlArg = option('--url')
if ((fileArg === undefined) === (urlArg === undefined)) {
  console.error('Pass exactly one of --url <url> or --file <path>.')
  process.exit(2)
}
const outDir = path.resolve(option('--out') ?? path.join(here, '..', '..', 'data', 'scratch', 'ui-verify'))
const offline = fileArg !== undefined
const base = offline ? pathToFileURL(path.resolve(fileArg)).href : urlArg.replace(/#.*$/, '')
const label = offline ? 'file' : 'server'

const PRESENTER_SIZES = [
  { width: 1920, height: 1080 },
  { width: 1280, height: 720 },
]
const PHONE = { width: 390, height: 844 }
const expectSynthetic = option('--synthetic') // "yes", "no", or undefined (report only)
// Longest reveal on any scene is under 2 s.
const SETTLE_MS = 2200

const failures = []
const fail = (message) => {
  failures.push(message)
  console.log(`  FAIL ${message}`)
}

if (offline) {
  const html = await readFile(path.resolve(fileArg), 'utf8')
  const external = [...html.matchAll(/\b(?:src|href)\s*=\s*["']?(?!data:|#)([^"'\s>]+)/gi)].map((m) => m[1])
  if (external.length > 0) {
    fail(`HTML references external resources: ${external.slice(0, 5).join(', ')}`)
  }
  const cssUrls = [...html.matchAll(/url\(\s*["']?(?!data:|#)([^"')]+)/gi)].map((m) => m[1])
  if (cssUrls.length > 0) {
    fail(`CSS references external resources: ${cssUrls.slice(0, 5).join(', ')}`)
  }
  console.log(`single file: ${(html.length / 1024).toFixed(0)} KiB, no external references checked`)
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

await mkdir(outDir, { recursive: true })
async function openPage(size, query, hash, extra = {}) {
  const context = await browser.newContext({ viewport: size, deviceScaleFactor: 1, offline, ...extra })
  const page = await context.newPage()
  const errors = []
  page.on('console', (m) => {
    // Enabling the DevTools CSS domain (for the font check) makes Chrome re-read a file:
    // document and log this one warning. It comes from the check, not the app: the same
    // page with no DevTools session logs nothing, offline or not.
    const fromFontCheck = /^Unsafe attempt to load URL file:.* 'file:' URLs are treated as unique security origins\.$/
    if (m.type() === 'error' && !fromFontCheck.test(m.text().trim())) errors.push(m.text())
  })
  page.on('pageerror', (e) => errors.push(e.message))
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
  if ((await fontReport(cdp)).fallbacks.length === 0) {
    fail('font check self-test: a character missing from Plex was not detected')
  }
  await page.evaluate(() => document.getElementById('verify-negative')?.remove())
}

async function finish(name, { context, page, errors }) {
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

async function audience(size) {
  const tag = `${label}-audience-${size.width}x${size.height}`
  console.log(`\n${tag}`)
  const session = await openPage(size, '?view=audience', '', {
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  })
  const { page, cdp } = session
  await fontSelfTest(page, cdp)
  await page.waitForTimeout(SETTLE_MS)

  const { used, fallbacks } = await fontReport(cdp)
  for (const f of fallbacks) fail(`audience: ${f}`)
  console.log(`  fonts: [${used.join(', ')}]`)

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
  if (layout.overflow > 0) fail(`audience: page is ${layout.overflow}px wider than the screen`)
  if (layout.bodyFont < 16) fail(`audience: body text is ${layout.bodyFont}px`)
  for (const t of layout.small) fail(`audience: control "${t.text}" is ${t.w.toFixed(0)}×${t.h.toFixed(0)} px`)

  await page.screenshot({ path: path.join(outDir, `${tag}-top.png`) })
  await page.screenshot({ path: path.join(outDir, `${tag}-full.png`), fullPage: true })

  // Tap every unselected segment once: each tap must select it.
  const options = page.locator('.segmented__option[aria-pressed="false"]')
  const n = await options.count()
  for (let i = n - 1; i >= 0; i -= 1) {
    const option = options.nth(i)
    await option.scrollIntoViewIfNeeded()
    await option.tap()
  }
  if ((await page.locator('.segmented__option[aria-pressed="false"]').count()) !== n) {
    fail('audience: tapping a segment did not move the selection')
  }
  await page.waitForTimeout(SETTLE_MS)
  await page.screenshot({ path: path.join(outDir, `${tag}-full-tapped.png`), fullPage: true })
  console.log(`  ${n} segment(s) tapped; screenshots ${tag}-*.png`)

  await finish(tag, session)
}

const browser = await chromium.launch()
try {
  for (const size of PRESENTER_SIZES) await presenter(size)
  await audience(PHONE)
} finally {
  await browser.close()
}

console.log(`\nscreenshots in ${outDir}`)
if (failures.length > 0) {
  console.log(`${failures.length} check(s) failed`)
  process.exit(1)
}
console.log('all checks passed')
