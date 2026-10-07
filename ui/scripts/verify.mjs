// Visual and offline verification of the UI. Development only: Playwright is a
// devDependency used by this script and nothing else; no run mode or task needs it.
//
//   node scripts/verify.mjs --url http://localhost:4173/   # a running dev or preview server
//   node scripts/verify.mjs --file ../demo/index.html      # the single-file build, offline
//   node scripts/verify.mjs --web http://localhost:4174/   # the phone site (npm run preview:web)
//   add --synthetic yes|no to require (or forbid) the synthetic-data label
//   add --qr yes|no to require (or forbid) the QR code (slide 1, slide 8, the Q overlay)
//
// Presentation, at 1920×1080 and 1280×720: opens with no hash (it must land on slide 1),
// walks every slide and every step to the end, saves a screenshot of each, checks fonts,
// presenter notes, and that nothing spills off the stage. At 1920×1080 it also drives
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
// slides, notes, panels, primitives) is on any screen, and N, F, P and Q do nothing. With
// --web it also checks that the bundle the site loads contains no presenter content at all.
//
// All: no console or page errors; with --synthetic yes|no, the synthetic label is (or is
// not) on screen. With --file it also blocks the network entirely and fails on any request
// that is not file: or data:, and checks the HTML references no external resources.
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
  // Chrome reports a node's fonts only once it has been laid out.
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))))
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
const PRESENTER_STRINGS = [
  'Presenter notes',
  'stage__frame',
  'deck__scene',
  'notes__',
  'qr-overlay',
  'hardware__',
  'primitives',
  'Design tokens',
  'Why randomness matters',
  'Measuring unpredictability',
  'Launch the attacker',
  'Inside the quantum computer',
  'play on your phone',
]

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

  // Game 2 on each machine: twenty rounds, then the two counts side by side.
  await tap(/^Next game/)
  await screen('beat-pick')
  for (const [i, machine] of ['Ordinary formula', 'Quantum computer'].entries()) {
    await tap(i === 0 ? machine : 'Try the quantum computer')
    for (let round = 1; round <= 20; round += 1) {
      const counter = (await page.locator('.phone-step').first().textContent()) ?? ''
      if (!new RegExp(`Round\\s*${round}\\s*of\\s*20`).test(counter)) fail(`beat ${machine}: round counter reads "${counter.trim()}"`)
      await tap(round % 3 ? 'Guess 1' : 'Guess 0')
      if (round === 1) {
        const feedback = (await page.locator('.beat-feedback').textContent()) ?? ''
        if (!/The bit was/.test(feedback) || !/attacker guessed/.test(feedback)) fail(`beat ${machine}: no feedback after a guess`)
        if (i === 0) await screen('beat-round')
      }
    }
    await page.waitForTimeout(150)
    const scores = await page.$$eval('.beat-score', (els) => els.map((el) => el.textContent?.replace(/\s+/g, ' ').trim()))
    if (scores.length !== 2 || !scores.every((t) => /of 20$/.test(t ?? ''))) fail(`beat ${machine}: end scores read ${JSON.stringify(scores)}`)
    console.log(`  beat ${machine}: ${scores.join(' | ')}`)
    if (i === 0) await screen('beat-end')
  }

  // Closing screen, with the run's details.
  await tap('What it all means')
  await screen('end')
  const small = (await page.locator('.phone-small').allTextContents()).join(' ')
  if (expectSynthetic === 'no' && !/job\s/.test(small)) fail('closing screen does not show the job ID')
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
  const bodies = []
  page.on('response', async (response) => {
    if (/\.(js|css|html)(\?|$)|\/$/.test(response.url())) bodies.push(response.text().catch(() => ''))
  })
  await page.goto(base)
  await page.waitForLoadState('networkidle')
  const text = (await Promise.all(bodies)).join('\n')
  if (text.length < 1000) fail('web bundle: could not read the site\'s files')
  for (const s of PRESENTER_STRINGS) if (text.includes(s)) fail(`web bundle contains presenter content: "${s}"`)
  // The primitives page and the deck's routes don't exist here.
  for (const route of ['?primitives', '#primitives', '?view=presenter#3']) {
    await page.goto(`${base}${route}`)
    await page.waitForTimeout(300)
    if ((await page.locator(PRESENTER_SELECTORS).count()) > 0) fail(`web: ${route} shows presenter content`)
  }
  console.log(`  ${(text.length / 1024).toFixed(0)} KiB checked`)
  await context.close()
}

const browser = await chromium.launch()
try {
  if (web) {
    await webBundle()
  } else {
    for (const [i, size] of PRESENTER_SIZES.entries()) await talk(size, i === 0)
    for (const size of PRESENTER_SIZES) await presenter(size)
  }
  await phone(PHONE, true)
  await phone(SHORT_PHONE, false)
} finally {
  await browser.close()
}

console.log(`\nscreenshots in ${outDir}`)
if (failures.length > 0) {
  console.log(`${failures.length} check(s) failed`)
  process.exit(1)
}
console.log('all checks passed')
