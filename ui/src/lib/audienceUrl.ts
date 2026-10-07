/**
 * The address phones should open, from the build-time setting VITE_AUDIENCE_URL (SPEC.md,
 * Section 9.2), or null when it is unset, empty, or not an http(s) URL.
 */
export function audienceUrl(raw: unknown = import.meta.env.VITE_AUDIENCE_URL): { href: string; short: string } | null {
  if (typeof raw !== 'string' || raw.trim() === '') {
    return null
  }
  let url: URL
  try {
    url = new URL(raw.trim())
  } catch {
    return null
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    return null
  }
  const short = url.href.replace(/^https?:\/\//, '').replace(/\/$/, '')
  return { href: url.href, short }
}
