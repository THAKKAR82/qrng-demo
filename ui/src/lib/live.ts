// The optional live run on slide 3 (SPEC.md, Section 6.4). Only the presenter page served
// by `python -m pipeline.tasks live-server` carries a session token. Without one (plain
// preview, file://, the phone site), nothing here sends a request and the control never
// shows. Every number shown for a live run comes from the server's response, computed in
// Python by pipeline.analysis; nothing is computed here.
//
// The state lives outside React so a run carries on while the presenter moves between
// slides. In builds where __QRNG_LIVE__ is false, useLiveRun is a constant and the rest of
// this module is dropped from the bundle.

import { useSyncExternalStore } from 'react'
import { unpackBits } from './pool'

const TOKEN_META = 'qrng-live-token'
const TOKEN_HEADER = 'X-QRNG-Live-Token'
const HEALTH_PATH = '/api/live/health'
const RUNS_PATH = '/api/live/runs'

/** The app gives up on a live run this long after the button is pressed (SPEC.md, 9.5). */
export const LIVE_TIMEOUT_MS = 120_000
const POLL_MS = 1000
const REQUEST_TIMEOUT_MS = 10_000

export interface LiveHealth {
  armed: boolean
  backend: string | null
  runs_remaining: number
  max_runs: number
  shots: number | null
  n_qubits: number | null
}

/** A finished live run as the server reports it, with its bits decoded. */
export interface LiveResult {
  runId: string
  backend: string
  jobId: string
  shots: number
  nQubits: number
  nBits: number
  physicalQubits: number[]
  /** Candidates the qubits were picked from by lowest readout error, or null if not selected. */
  selectedFrom: number | null
  /** Shot-major bits, as a stream the Machines panel can play: one entry per bit. */
  bits: Uint8Array
  submittedUtc: string
  completedUtc: string
  qpuSeconds: number | null
}

export type LiveStage = 'submitting' | 'submitted' | 'queued' | 'running'

export interface LiveView {
  /** Served by an armed live server: the live control is shown. */
  available: boolean
  /** The button can start a run now. */
  canStart: boolean
  health: LiveHealth | null
  phase: 'idle' | 'running' | 'done' | 'fallback'
  stage: LiveStage | null
  jobId: string | null
  elapsedSeconds: number | null
  /** Why the panel fell back to the recorded run. */
  fallback: 'timeout' | 'failed' | null
  /** The server's short reason for refusing to start a run, such as one still in progress. */
  notice: string | null
  result: LiveResult | null
}

const OFF: LiveView = {
  available: false,
  canStart: false,
  health: null,
  phase: 'idle',
  stage: null,
  jobId: null,
  elapsedSeconds: null,
  fallback: null,
  notice: null,
  result: null,
}

let view: LiveView = OFF
let checked = false
/** Bumped whenever an attempt ends, so late replies from it are ignored. */
let attempt = 0
let pollTimer: ReturnType<typeof setTimeout> | undefined
let timeoutTimer: ReturnType<typeof setTimeout> | undefined
const listeners = new Set<() => void>()

function update(next: Partial<LiveView>): void {
  view = { ...view, ...next }
  listeners.forEach((listener) => listener())
}

function token(): string | null {
  const meta = document.querySelector<HTMLMetaElement>(`meta[name="${TOKEN_META}"]`)
  const value = meta?.content.trim() ?? ''
  return value === '' ? null : value
}

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null
const isCount = (v: unknown): v is number => Number.isInteger(v) && (v as number) >= 0
const isText = (v: unknown): v is string => typeof v === 'string' && v !== ''

async function request(path: string, method: 'GET' | 'POST'): Promise<{ status: number; body: unknown }> {
  const secret = token()
  if (secret === null) {
    throw new Error('no live token')
  }
  const response = await fetch(path, {
    method,
    headers: { [TOKEN_HEADER]: secret },
    cache: 'no-store',
    credentials: 'omit',
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  })
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }
  return { status: response.status, body }
}

function parseHealth(body: unknown): LiveHealth | null {
  if (!isObject(body) || typeof body.armed !== 'boolean' || !isCount(body.runs_remaining)) {
    return null
  }
  return {
    armed: body.armed,
    backend: isText(body.backend) ? body.backend : null,
    runs_remaining: body.runs_remaining,
    max_runs: isCount(body.max_runs) ? body.max_runs : 0,
    shots: isCount(body.shots) ? body.shots : null,
    n_qubits: isCount(body.n_qubits) ? body.n_qubits : null,
  }
}

function parseResult(runId: string, raw: unknown): LiveResult | null {
  if (!isObject(raw)) {
    return null
  }
  const { backend, job_id, shots, n_qubits, n_bits, bits, physical_qubits, submitted_utc, completed_utc } = raw
  if (
    !isText(backend) ||
    !isText(job_id) ||
    !isCount(shots) ||
    !isCount(n_qubits) ||
    !isCount(n_bits) ||
    n_bits === 0 ||
    n_bits !== shots * n_qubits ||
    typeof bits !== 'string' ||
    !Array.isArray(physical_qubits) ||
    !physical_qubits.every(isCount) ||
    !isText(submitted_utc) ||
    !isText(completed_utc)
  ) {
    return null
  }
  let decoded: Uint8Array
  try {
    decoded = unpackBits(bits, n_bits)
  } catch {
    return null
  }
  const selection = raw.qubit_selection
  const selectedFrom =
    isObject(selection) && selection.method === 'lowest_readout_error' && isCount(selection.candidates)
      ? selection.candidates
      : null
  return {
    runId,
    backend,
    jobId: job_id,
    shots,
    nQubits: n_qubits,
    nBits: n_bits,
    physicalQubits: physical_qubits,
    selectedFrom,
    bits: decoded,
    submittedUtc: submitted_utc,
    completedUtc: completed_utc,
    qpuSeconds: typeof raw.qpu_seconds === 'number' ? raw.qpu_seconds : null,
  }
}

/** Asks the server once whether live mode is available; called on first use. */
async function checkHealth(): Promise<void> {
  if (token() === null) {
    return
  }
  try {
    const { status, body } = await request(HEALTH_PATH, 'GET')
    const health = status === 200 ? parseHealth(body) : null
    if (health !== null && health.armed && health.runs_remaining > 0) {
      update({ available: true, canStart: true, health })
    }
  } catch {
    // Unreachable: stay off and keep the recorded run.
  }
}

/** After a run ends: may another one start? The server's answer decides. */
async function refreshHealth(): Promise<void> {
  try {
    const { status, body } = await request(HEALTH_PATH, 'GET')
    const health = status === 200 ? parseHealth(body) : null
    update({
      health: health ?? view.health,
      canStart: health !== null && health.armed && health.runs_remaining > 0 && view.phase !== 'running',
    })
  } catch {
    update({ canStart: false })
  }
}

function endAttempt(): void {
  attempt += 1
  clearTimeout(pollTimer)
  clearTimeout(timeoutTimer)
}

function fallBack(reason: 'timeout' | 'failed'): void {
  endAttempt()
  update({ phase: 'fallback', fallback: reason, stage: null, elapsedSeconds: null, canStart: false })
  void refreshHealth()
}

async function poll(mine: number, runId: string): Promise<void> {
  let reply: { status: number; body: unknown }
  try {
    reply = await request(`${RUNS_PATH}/${runId}`, 'GET')
  } catch {
    if (mine === attempt) {
      fallBack('failed')
    }
    return
  }
  if (mine !== attempt) {
    return
  }
  const { status, body } = reply
  if (status !== 200 || !isObject(body) || typeof body.stage !== 'string') {
    fallBack('failed')
    return
  }
  const jobId = isText(body.job_id) ? body.job_id : view.jobId
  if (body.stage === 'done') {
    const result = parseResult(runId, body.result)
    if (result === null) {
      update({ jobId })
      fallBack('failed')
      return
    }
    endAttempt()
    update({ phase: 'done', stage: null, jobId, elapsedSeconds: null, result, canStart: false })
    void refreshHealth()
    return
  }
  if (body.stage === 'failed') {
    update({ jobId })
    fallBack('failed')
    return
  }
  const stage = (['submitting', 'submitted', 'queued', 'running'] as const).find((s) => s === body.stage)
  update({
    stage: stage ?? view.stage,
    jobId,
    elapsedSeconds: isCount(body.elapsed_seconds) ? body.elapsed_seconds : null,
  })
  pollTimer = setTimeout(() => void poll(mine, runId), POLL_MS)
}

/** The button: start one live run. The server decides whether it may. */
export async function startLiveRun(): Promise<void> {
  if (!view.available || view.phase === 'running') {
    return
  }
  endAttempt()
  const mine = attempt
  update({
    phase: 'running',
    stage: 'submitting',
    jobId: null,
    elapsedSeconds: null,
    fallback: null,
    notice: null,
    canStart: false,
  })
  timeoutTimer = setTimeout(() => {
    if (mine === attempt) {
      fallBack('timeout')
    }
  }, LIVE_TIMEOUT_MS)
  let reply: { status: number; body: unknown }
  try {
    reply = await request(RUNS_PATH, 'POST')
  } catch {
    if (mine === attempt) {
      fallBack('failed')
    }
    return
  }
  if (mine !== attempt) {
    return
  }
  const { status, body } = reply
  if (status === 202 && isObject(body) && typeof body.id === 'string' && /^[0-9a-f]{16}$/.test(body.id)) {
    const runId = body.id
    pollTimer = setTimeout(() => void poll(mine, runId), POLL_MS)
    return
  }
  // Refused before anything was submitted (a run still in progress, no runs left): say so,
  // keep whatever the panel was showing, and ask the server what is possible now.
  endAttempt()
  const notice = isObject(body) && isText(body.error) && body.error.length <= 120 ? body.error : null
  update({
    phase: view.result !== null ? 'done' : 'idle',
    stage: null,
    notice: notice ?? 'The live server did not start a run.',
  })
  void refreshHealth()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  if (!checked) {
    checked = true
    void checkHealth()
  }
  return () => listeners.delete(listener)
}

function useLiveStore(): LiveView {
  return useSyncExternalStore(subscribe, () => view)
}

function useNoLive(): LiveView {
  return OFF
}

/** The live run's state, or a constant "off" in builds without live mode. */
export const useLiveRun: () => LiveView = __QRNG_LIVE__ ? useLiveStore : useNoLive
