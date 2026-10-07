"""The hosted phone site (SPEC.md, Sections 9.2 and 9.7): its address, and ``check-site``.

``site.json`` at the repo root names the host, the project, and the site's URL. ``rebuild``
bakes that URL into every build as ``VITE_AUDIENCE_URL``, and ``check-site`` fetches the
deployed copy and checks it against the local build. Nothing here deploys anything, and
``check-site`` contacts only the one site named in ``site.json``.
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from email.message import Message
from pathlib import Path

from pipeline.paths import DEMO_DIR, REPO_ROOT, UI_DIR, UI_DIST_DIR

SITE_JSON = REPO_ROOT / "site.json"
WEB_DIST_DIR = UI_DIR / "dist-web"
HEADERS_FILE = UI_DIR / "web" / "public" / "_headers"
PRESENTER_STRINGS_JSON = UI_DIR / "scripts" / "presenter-strings.json"
# The builds whose QR codes must point to the hosted site.
QR_BUILDS = (UI_DIST_DIR / "index.html", DEMO_DIR / "index.html")

HOST = "cloudflare-pages"
PLACEHOLDER_PROJECT = "CHOOSE-A-NAME"
# Cloudflare Pages project names: lowercase letters, digits, and hyphens, at most 58.
_PROJECT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,56}[a-z0-9])?$")
# The host's default address. If the name is taken, Pages adds a suffix to the subdomain,
# so the URL is recorded as Pages reports it rather than derived from the project name.
_URL_RE = re.compile(r"^https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.pages\.dev/$")
_AUDIENCE_META_RE = re.compile(r'<meta name="qrng-audience-url" content="([^"]*)"\s*/?>')
_ASSET_RE = re.compile(r'(?:src|href)="\./([^"#?]+)"')
TIMEOUT_SECONDS = 15


class SiteError(Exception):
    """site.json is missing, malformed, or still holds the placeholder."""


@dataclass(frozen=True)
class Site:
    host: str
    project: str
    url: str

    @property
    def placeholder(self) -> bool:
        return self.project == PLACEHOLDER_PROJECT


def load_site(path: Path = SITE_JSON) -> Site:
    """Read and validate site.json. A placeholder is valid here; callers decide."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SiteError(f"{path.name} is missing") from exc
    except json.JSONDecodeError as exc:
        raise SiteError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) - {"_comment"} != {"host", "project", "url"}:
        raise SiteError(f'{path.name} must hold exactly "host", "project", and "url"')
    host, project, url = raw["host"], raw["project"], raw["url"]
    if host != HOST:
        raise SiteError(f'{path.name}: host must be "{HOST}", not {host!r}')
    if project == PLACEHOLDER_PROJECT:
        return Site(host, project, url)
    if not isinstance(project, str) or not _PROJECT_RE.match(project):
        raise SiteError(
            f"{path.name}: project {project!r} is not a Cloudflare Pages project name "
            "(lowercase letters, digits, and hyphens)"
        )
    if not isinstance(url, str) or not _URL_RE.match(url):
        raise SiteError(
            f"{path.name}: url {url!r} must be the host's default address, "
            "https://<subdomain>.pages.dev/ with the trailing slash"
        )
    return Site(host, project, url)


def short_url(url: str) -> str:
    """The text printed under the QR code: the URL without https:// or the final slash."""
    return re.sub(r"^https?://", "", url).rstrip("/")


def valid_audience_url(url: str) -> bool:
    """An http(s) address with no characters that would need escaping in HTML."""
    return re.match(r"^https?://[^\s\"'<>&]+$", url) is not None


def built_audience_url(index_html: str) -> str | None:
    """The VITE_AUDIENCE_URL a build recorded in its meta tag, or None if it has none."""
    match = _AUDIENCE_META_RE.search(index_html)
    return None if match is None else match.group(1).replace("&amp;", "&")


# --- _headers ----------------------------------------------------------------------------


@dataclass
class HeaderRule:
    """One block of a Cloudflare Pages _headers file: a path pattern and its headers."""

    pattern: str
    set: dict[str, str] = field(default_factory=dict)
    detach: list[str] = field(default_factory=list)

    def matches(self, path: str) -> bool:
        regex = "^" + ".*".join(re.escape(part) for part in self.pattern.split("*")) + "$"
        return re.match(regex, path) is not None


def parse_headers_file(text: str) -> list[HeaderRule]:
    """Parse _headers: a path line, then indented ``Name: value`` or ``! Name`` lines."""
    rules: list[HeaderRule] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            rules.append(HeaderRule(line.strip()))
            continue
        if not rules:
            raise ValueError(f"header line before any path: {line.strip()!r}")
        entry = line.strip()
        if entry.startswith("!"):
            rules[-1].detach.append(entry[1:].strip().lower())
        else:
            name, _, value = entry.partition(":")
            rules[-1].set[name.strip().lower()] = value.strip()
    return rules


def headers_for(rules: Sequence[HeaderRule], path: str) -> tuple[dict[str, str], list[str]]:
    """Headers the host sends for ``path``, and the default headers it removes."""
    out: dict[str, str] = {}
    removed: list[str] = []
    for rule in rules:
        if rule.matches(path):
            out.update(rule.set)
            removed.extend(rule.detach)
    return out, removed


# --- Fetching ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]  # lower-case names; repeated headers joined with ", "
    body: bytes


Fetch = Callable[[str], Response]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def http_fetch(url: str) -> Response:
    """GET ``url`` without following redirects, verifying TLS certificates."""
    opener = urllib.request.build_opener(
        _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context())
    )
    request = urllib.request.Request(url, headers={"User-Agent": "qrng-demo check-site"})
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as reply:
            return Response(reply.status, _header_dict(reply.headers), reply.read())
    except urllib.error.HTTPError as exc:
        return Response(exc.code, _header_dict(exc.headers), exc.read())


def _header_dict(message: Message) -> dict[str, str]:
    names = dict.fromkeys(name.lower() for name in message)
    return {name: ", ".join(message.get_all(name) or []) for name in names}


# --- check-site --------------------------------------------------------------------------


@dataclass
class Report:
    lines: list[tuple[bool, str]] = field(default_factory=list)

    def check(self, ok: bool, message: str) -> bool:
        self.lines.append((ok, message))
        print(f"  {'ok  ' if ok else 'FAIL'} {message}")
        return ok

    def note(self, message: str) -> None:
        print(f"  note {message}")

    @property
    def failures(self) -> int:
        return sum(not ok for ok, _ in self.lines)


def _norm(value: str) -> str:
    return " ".join(value.split())


def _presenter_strings(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [*data["presenter"], *data["live"]]


def check_site(
    site: Site,
    fetch: Fetch = http_fetch,
    *,
    dist_web: Path = WEB_DIST_DIR,
    headers_file: Path = HEADERS_FILE,
    qr_builds: Sequence[Path] = QR_BUILDS,
    strings_file: Path = PRESENTER_STRINGS_JSON,
) -> Report:
    """Check the deployed phone site against site.json and the local build."""
    report = Report()
    url = site.url
    rules = parse_headers_file(headers_file.read_text(encoding="utf-8"))
    forbidden = _presenter_strings(strings_file)

    # 1. HTTPS answers with the page itself, not a redirect.
    try:
        root = fetch(url)
    except (urllib.error.URLError, OSError) as exc:
        report.check(False, f"{url} could not be reached over HTTPS: {exc}")
        return report
    content_type = root.headers.get("content-type", "")
    if not report.check(
        root.status == 200 and content_type.startswith("text/html"),
        f"HTTPS: {url} answers {root.status} ({content_type or 'no content type'})",
    ):
        return report

    # 2. Plain HTTP does not serve the page.
    http_url = "http://" + url.removeprefix("https://")
    try:
        plain = fetch(http_url)
        location = plain.headers.get("location", "")
        if plain.status in (301, 302, 307, 308) and location.startswith("https://"):
            report.check(True, f"plain HTTP redirects to HTTPS ({plain.status})")
        elif plain.status == 200:
            # Every .dev name is on browsers' HSTS preload list, so browsers never ask over
            # plain HTTP; a 200 there is reachable only by tools such as curl.
            report.note("plain HTTP answers 200, but browsers never use it: .dev is HSTS-preloaded")
        else:
            report.check(True, f"plain HTTP does not serve the page ({plain.status})")
    except (urllib.error.URLError, OSError):
        report.check(True, "plain HTTP is refused")

    # 3. Every header in _headers, and none of the defaults it removes.
    expected, removed = headers_for(rules, "/")
    for name, value in expected.items():
        sent = root.headers.get(name)
        report.check(
            sent is not None and _norm(sent) == _norm(value),
            f"header {name}"
            + ("" if sent is not None and _norm(sent) == _norm(value) else f": sent {sent!r}"),
        )
    for name in removed:
        report.check(name not in root.headers, f"header {name} is not sent")

    # 4. The deployed page is the local build.
    local_index = dist_web / "index.html"
    if local_index.is_file():
        report.check(
            root.body == local_index.read_bytes(),
            "the deployed index.html matches ui/dist-web/index.html",
        )
    else:
        report.check(False, "ui/dist-web/index.html is missing: run rebuild before check-site")

    # 5. No presenter content, live-run code, or source maps in what the page loads.
    page = root.body.decode("utf-8", errors="replace")
    texts = [page]
    assets = sorted(set(_ASSET_RE.findall(page)))
    for asset in assets:
        reply = fetch(url + asset)
        if not report.check(reply.status == 200, f"{asset} loads ({reply.status})"):
            continue
        if asset.endswith((".js", ".css")):
            texts.append(reply.body.decode("utf-8", errors="replace"))
            asset_headers, _ = headers_for(rules, "/" + asset)
            cache = asset_headers.get("cache-control")
            if cache is not None:
                report.check(
                    _norm(reply.headers.get("cache-control", "")) == _norm(cache),
                    f"{asset} is cached as {cache!r}",
                )
            source_map = fetch(url + asset + ".map")
            report.check(
                source_map.status != 200 or not source_map.body.lstrip().startswith(b"{"),
                f"no source map is served for {asset} ({source_map.status})",
            )
    combined = "\n".join(texts)
    found = [s for s in forbidden if s in combined]
    report.check(
        not found,
        f"no presenter or live-run content ({len(texts)} files checked)"
        + (f": found {found}" if found else ""),
    )
    report.check("sourceMappingURL" not in combined, "no file refers to a source map")

    # 6. Paths outside the build are not served (no single-page fallback to the app). Pages
    # may redirect a missing .html path to its extensionless form first; only 200 serves.
    for path in ("_headers", "demo/index.html", "check-site-probe/"):
        reply = fetch(url + path)
        report.check(reply.status != 200, f"/{path} is not served ({reply.status})")

    # 7. The QR codes in the presenter builds point exactly to this site.
    for build in qr_builds:
        shown = build.relative_to(REPO_ROOT) if build.is_relative_to(REPO_ROOT) else build
        if not build.is_file():
            report.check(False, f"{shown} is missing: run rebuild")
            continue
        recorded = built_audience_url(build.read_text(encoding="utf-8"))
        report.check(
            recorded == url,
            f"{shown} QR code points to {recorded or 'nothing'}"
            + ("" if recorded == url else f", not {url}"),
        )
    print(f"  QR text under the code: {short_url(url)}")
    return report
