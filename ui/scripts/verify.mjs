// Visual and offline verification of the UI. Development only: Playwright is a
// devDependency used by this script and nothing else; no run mode or task needs it.
//
//   node scripts/verify.mjs --url http://localhost:4173/   # a running dev or preview server
//   node scripts/verify.mjs --file ../demo/index.html      # the single-file build, offline
//   add --synthetic yes|no to require (or forbid) the synthetic-data label
//   add --qr yes|no to require (or forbid) the QR code on the opening slide
//
// Presentation, at 1920×1080 and 1280×720: opens with no hash (it must land on slide 1),
// walks every slide and every step to the end, saves a screenshot of each, checks fonts
// and that nothing spills off the stage. At 1920×1080 it also drives every panel with the
// presenter's keys and mouse: Generate fills the pictures and counts; R reveals; 0 and 1
// score guesses without moving the deck; Launch runs the attack to its result; clicking a
// chosen qubit on the chip selects that qubit; and the clicker still works afterwards.
//
// Primitives page, at both sizes: walks every scene, saves a screenshot of each, and
// checks that
//   - every character on screen renders in IBM Plex, not a fallback font (checked with
//     Chrome's own record of the fonts it used, after a self-test that it catches one);
//   - keys pressed on an interactive element do not move the deck, and the clicker
//     still works after a panel button has been clicked;
//   - N shows and hides the notes overlay, and PageUp goes back.
// Audience view (?view=audience), on a 390×844 touch phone: walks the guided tour from
// step 1 to the end with its Next button; taps a chosen qubit at 1× and 2× zoom and checks
// that qubit is selected; then in explore mode checks fonts, that nothing overflows
// sideways, that every control is at least 44×44 CSS px, that Generate and the guess
// buttons work, and that tapping a segment selects it.
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
const expectQr = option('--qr') // "yes", "no", or undefined (report only)
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
    if ((await page.locator('.notes').count()) === 0) {
      await page.keyboard.press('n')
      const notes = ((await page.locator('.notes__body').textContent()) ?? '').trim()
      if (notes === '' || /No notes for this scene/.test(notes)) fail(`slide ${hash} has no presenter notes`)
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
    await page.getByRole('button', { name: 'Fast', exact: true }).click()
    await page.getByRole('button', { name: 'Generate bits' }).click()
    await page.waitForTimeout(1200)
    const status = (await page.locator('.machines__status').textContent()) ?? ''
    if (/^\s*0 of/.test(status)) fail(`Generate did not stream bits: "${status.trim()}"`)
    if ((await page.locator('.machine__stats dd.num').first().textContent())?.trim() === '–') fail('Generate did not update the counts')
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
      await page.keyboard.press(machine[0])
      await page.getByRole('button', { name: /^Launch/ }).click()
      await page.waitForTimeout(6600)
      if ((await page.locator('.attacker__final').count()) !== 1) fail(`the ${machine} attack did not reach its result`)
      await page.screenshot({ path: path.join(outDir, `${tag}-attack-${machine}.png`) })
    }

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

  // Guided tour: Next goes through every stop in order.
  if ((await hashOf(page)) !== '#tour/1') fail(`audience view opened on ${await hashOf(page)}, not #tour/1`)
  const stops = Number((await page.locator('.audience__step .num').last().textContent()) ?? 0)
  for (let i = 1; i < stops; i += 1) {
    await page.screenshot({ path: path.join(outDir, `${tag}-tour-${i}.png`), fullPage: true })
    await page.getByRole('button', { name: /^Next/ }).tap()
    await page.waitForTimeout(400)
    if ((await hashOf(page)) !== `#tour/${i + 1}`) fail(`tour Next from stop ${i} went to ${await hashOf(page)}`)
  }
  await page.screenshot({ path: path.join(outDir, `${tag}-tour-${stops}.png`), fullPage: true })
  console.log(`  tour: ${stops} stops`)

  // The chip, on the last stop: a tap selects the qubit under the finger, at 1× and 2×.
  if ((await page.locator('.hardware__map').count()) > 0) {
    for (const zoom of ['1×', '2×']) {
      await page.getByRole('button', { name: zoom, exact: true }).tap()
      await page.waitForTimeout(200)
      const qubit = await anotherUsedQubit(page)
      const { x, y } = await qubitPoint(page, qubit)
      await page.touchscreen.tap(x, y)
      await page.waitForTimeout(100)
      await expectSelected(page, qubit, `phone chip at ${zoom}`)
    }
  } else {
    console.log('  no device layout in this data; chip tap skipped')
  }

  await page.getByRole('button', { name: 'Explore all' }).tap()
  await page.waitForTimeout(SETTLE_MS)
  if ((await hashOf(page)) !== '#explore') fail(`Explore all went to ${await hashOf(page)}`)

  // Generate and guess by tapping.
  await page.getByRole('button', { name: 'Fast', exact: true }).tap()
  await page.getByRole('button', { name: 'Generate bits' }).tap()
  await page.waitForTimeout(1000)
  if (/^\s*0 of/.test((await page.locator('.machines__status').textContent()) ?? '')) fail('audience: Generate did not stream bits')
  const guess0 = page.getByRole('button', { name: 'Guess 0' }).first()
  await guess0.scrollIntoViewIfNeeded()
  await guess0.tap()
  if (!/of\s*1\b/.test((await page.locator('.guess__score').first().textContent()) ?? '')) fail('audience: tapping 0 did not play a round')

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

  // Tap every unselected segment in the panels once: each tap must select it.
  const options = page.locator('.audience__panels .segmented__option[aria-pressed="false"]')
  const n = await options.count()
  for (let i = n - 1; i >= 0; i -= 1) {
    const option = options.nth(i)
    await option.scrollIntoViewIfNeeded()
    await option.tap()
  }
  if ((await page.locator('.audience__panels .segmented__option[aria-pressed="false"]').count()) !== n) {
    fail('audience: tapping a segment did not move the selection')
  }
  await page.waitForTimeout(SETTLE_MS)
  await page.screenshot({ path: path.join(outDir, `${tag}-full-tapped.png`), fullPage: true })
  console.log(`  ${n} segment(s) tapped; screenshots ${tag}-*.png`)

  await finish(tag, session)
}

const browser = await chromium.launch()
try {
  for (const [i, size] of PRESENTER_SIZES.entries()) await talk(size, i === 0)
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
