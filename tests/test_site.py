"""site.json, the phone site's _headers, and check-site against a fake deployed site.

Nothing here touches the network: check-site gets a fake fetch that serves a site built
in a temporary folder.
"""

import json
import re
from pathlib import Path

import pytest

from pipeline import site
from pipeline.paths import REPO_ROOT

URL = "https://qrng-talk.pages.dev/"


def _write_site(path: Path, **fields: str) -> Path:
    data = {"host": "cloudflare-pages", "project": "qrng-talk", "url": URL, **fields}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --- site.json -----------------------------------------------------------------------------


def test_load_site_accepts_a_real_project(tmp_path: Path) -> None:
    config = site.load_site(_write_site(tmp_path / "site.json"))
    assert (config.project, config.url, config.placeholder) == ("qrng-talk", URL, False)
    assert site.short_url(config.url) == "qrng-talk.pages.dev"


def test_load_site_accepts_a_suffixed_subdomain(tmp_path: Path) -> None:
    # Pages adds a suffix when the name is taken; the URL is recorded as Pages reports it.
    path = _write_site(tmp_path / "site.json", url="https://qrng-talk-4ab.pages.dev/")
    assert site.load_site(path).url == "https://qrng-talk-4ab.pages.dev/"


def test_committed_site_json_is_valid() -> None:
    config = site.load_site()
    assert config.placeholder or config.url.endswith(".pages.dev/")


@pytest.mark.parametrize(
    "fields",
    [
        {"host": "netlify"},
        {"project": "Qrng Talk"},
        {"project": "-qrng"},
        {"url": "http://qrng-talk.pages.dev/"},
        {"url": "https://qrng-talk.pages.dev"},
        {"url": "https://qrng-talk.example.org/"},
        {"url": "https://qrng-talk.pages.dev/?view=audience"},
    ],
)
def test_load_site_rejects_bad_fields(tmp_path: Path, fields: dict[str, str]) -> None:
    with pytest.raises(site.SiteError):
        site.load_site(_write_site(tmp_path / "site.json", **fields))


def test_load_site_rejects_extra_or_missing_keys(tmp_path: Path) -> None:
    path = tmp_path / "site.json"
    path.write_text(json.dumps({"host": "cloudflare-pages", "project": "x"}), encoding="utf-8")
    with pytest.raises(site.SiteError):
        site.load_site(path)
    path.write_text(
        json.dumps({"host": "cloudflare-pages", "project": "x", "url": URL, "token": "t"}),
        encoding="utf-8",
    )
    with pytest.raises(site.SiteError):
        site.load_site(path)


def test_placeholder_is_recognised(tmp_path: Path) -> None:
    path = _write_site(
        tmp_path / "site.json",
        project=site.PLACEHOLDER_PROJECT,
        url=f"https://{site.PLACEHOLDER_PROJECT}.pages.dev/",
    )
    assert site.load_site(path).placeholder


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        (URL, True),
        ("http://192.168.1.20:4173/?view=audience", True),
        ('https://x.pages.dev/"><script>', False),
        ("javascript:alert(1)", False),
        ("https://x.pages.dev/ a", False),
    ],
)
def test_valid_audience_url(url: str, ok: bool) -> None:
    assert site.valid_audience_url(url) is ok


# --- _headers ------------------------------------------------------------------------------


def test_parse_headers_file_and_match_paths() -> None:
    rules = site.parse_headers_file(
        "/*\n  X-One: a\n  ! Access-Control-Allow-Origin\n\n/assets/*\n  Cache-Control: immutable\n"
    )
    root, removed = site.headers_for(rules, "/")
    assert root == {"x-one": "a"}
    assert removed == ["access-control-allow-origin"]
    asset, _ = site.headers_for(rules, "/assets/index-abc.js")
    assert asset == {"x-one": "a", "cache-control": "immutable"}


def test_repo_headers_file_is_strict() -> None:
    """The committed _headers meets SPEC.md, Section 9.7."""
    rules = site.parse_headers_file(site.HEADERS_FILE.read_text(encoding="utf-8"))
    headers, removed = site.headers_for(rules, "/")
    csp = {
        d.split()[0]: d.split()[1:]
        for d in (part.strip() for part in headers["content-security-policy"].split(";"))
        if d
    }
    assert csp["default-src"] == ["'none'"]
    for directive in ("object-src", "base-uri", "frame-ancestors", "form-action", "connect-src"):
        assert csp[directive] == ["'none'"], directive
    for directive in ("script-src", "style-src", "font-src", "img-src"):
        assert csp[directive] == ["'self'"], directive
    assert "require-trusted-types-for" in csp
    assert not re.search(r"unsafe-|\*|https?:|data:", headers["content-security-policy"])
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cross-origin-opener-policy"] == "same-origin"
    for feature in ("camera", "microphone", "geolocation", "payment", "usb"):
        assert f"{feature}=()" in headers["permissions-policy"]
    assert re.match(r"max-age=\d{8,}", headers["strict-transport-security"])
    assert "access-control-allow-origin" in removed


# --- check-site ----------------------------------------------------------------------------


@pytest.fixture
def deployed(tmp_path: Path) -> dict[str, object]:
    """A built phone site in tmp_path, a fake host serving it, and matching QR builds."""
    web = tmp_path / "dist-web"
    (web / "assets").mkdir(parents=True)
    index = (
        '<!doctype html><html><head><link rel="icon" href="./favicon.svg" />'
        '<script type="module" crossorigin src="./assets/index-abc.js"></script>'
        '<link rel="stylesheet" crossorigin href="./assets/index-abc.css"></head>'
        '<body><div id="root"></div></body></html>'
    )
    (web / "index.html").write_text(index, encoding="utf-8")
    (web / "assets" / "index-abc.js").write_text("console.log('games')", encoding="utf-8")
    (web / "assets" / "index-abc.css").write_text("body{}", encoding="utf-8")
    (web / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    headers_text = site.HEADERS_FILE.read_text(encoding="utf-8")
    rules = site.parse_headers_file(headers_text)

    builds = []
    for name in ("dist-index.html", "demo-index.html"):
        build = tmp_path / name
        build.write_text(f'<head><meta name="qrng-audience-url" content="{URL}" /></head>')
        builds.append(build)

    files = {
        "": (web / "index.html").read_bytes(),
        "assets/index-abc.js": (web / "assets" / "index-abc.js").read_bytes(),
        "assets/index-abc.css": (web / "assets" / "index-abc.css").read_bytes(),
        "favicon.svg": b"<svg/>",
    }
    state: dict[str, object] = {
        "files": files,
        "extra_headers": {},
        "drop_headers": set(),
        "http_status": 308,
        "spa_fallback": False,
        "requests": [],
    }

    def fetch(url: str) -> site.Response:
        state["requests"].append(url)  # type: ignore[attr-defined]
        if url.startswith("http://"):
            status = int(state["http_status"])  # type: ignore[call-overload]
            location = {"location": "https://" + url.removeprefix("http://")}
            return site.Response(status, location if status != 200 else {}, b"")
        assert url.startswith(URL), url
        path = url.removeprefix(URL)
        headers, _ = site.headers_for(rules, "/" + path)
        headers = {**headers, **state["extra_headers"]}  # type: ignore[dict-item]
        for name in state["drop_headers"]:  # type: ignore[attr-defined]
            headers.pop(name, None)
        body = files.get(path)
        if body is None and state["spa_fallback"]:
            body = files[""]
        if body is None:
            return site.Response(404, {"content-type": "text/html"}, b"<h1>Not found</h1>")
        kind = "text/html" if path == "" else "application/javascript"
        return site.Response(200, {"content-type": kind, **headers}, body)

    state["run"] = lambda: site.check_site(
        site.Site("cloudflare-pages", "qrng-talk", URL),
        fetch,
        dist_web=web,
        qr_builds=builds,
    )
    state["builds"] = builds
    state["web"] = web
    return state


def _run(state: dict[str, object]) -> site.Report:
    return state["run"]()  # type: ignore[operator, no-any-return]


def _failed(report: site.Report) -> list[str]:
    return [message for ok, message in report.lines if not ok]


def test_check_site_passes_a_good_deployment(deployed: dict[str, object]) -> None:
    report = _run(deployed)
    assert _failed(report) == []
    requested = deployed["requests"]
    assert all(u.startswith((URL, "http://qrng-talk.pages.dev/")) for u in requested)  # type: ignore[attr-defined]


def test_check_site_reports_a_missing_header(deployed: dict[str, object]) -> None:
    deployed["drop_headers"] = {"content-security-policy"}
    assert any("content-security-policy" in m for m in _failed(_run(deployed)))


def test_check_site_reports_a_host_default_that_should_be_removed(
    deployed: dict[str, object],
) -> None:
    deployed["extra_headers"] = {"access-control-allow-origin": "*"}
    assert any("access-control-allow-origin" in m for m in _failed(_run(deployed)))


def test_check_site_notes_plain_http_serving_the_page(
    deployed: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    # .dev is HSTS-preloaded, so browsers never use plain HTTP: a note, not a failure.
    deployed["http_status"] = 200
    assert _failed(_run(deployed)) == []
    assert "note plain HTTP answers 200" in capsys.readouterr().out


def test_check_site_reports_presenter_content(deployed: dict[str, object]) -> None:
    files = deployed["files"]
    files["assets/index-abc.js"] = b"const notes = 'Presenter notes'"  # type: ignore[index]
    assert any("presenter" in m for m in _failed(_run(deployed)))


def test_check_site_reports_a_source_map(deployed: dict[str, object]) -> None:
    files = deployed["files"]
    files["assets/index-abc.js.map"] = b'{"version":3}'  # type: ignore[index]
    assert any("source map" in m for m in _failed(_run(deployed)))


def test_check_site_reports_a_single_page_fallback(deployed: dict[str, object]) -> None:
    deployed["spa_fallback"] = True
    assert any("is not served" in m for m in _failed(_run(deployed)))


def test_check_site_reports_a_stale_deployment(deployed: dict[str, object]) -> None:
    web = deployed["web"]
    (web / "index.html").write_text("<!doctype html><p>newer build</p>", encoding="utf-8")  # type: ignore[operator]
    assert any("matches ui/dist-web" in m for m in _failed(_run(deployed)))


def test_check_site_reports_a_qr_code_pointing_elsewhere(deployed: dict[str, object]) -> None:
    builds = deployed["builds"]
    builds[0].write_text('<meta name="qrng-audience-url" content="https://other.pages.dev/" />')  # type: ignore[index]
    failed = _failed(_run(deployed))
    assert any("QR code points to https://other.pages.dev/" in m for m in failed)


def test_built_audience_url_reads_the_meta_tag() -> None:
    assert site.built_audience_url(f'<meta name="qrng-audience-url" content="{URL}" />') == URL
    assert site.built_audience_url('<meta name="qrng-audience-url" content="" />') == ""
    assert site.built_audience_url("<head></head>") is None


def test_presenter_strings_file_is_shared() -> None:
    data = json.loads(site.PRESENTER_STRINGS_JSON.read_text(encoding="utf-8"))
    assert "Presenter notes" in data["presenter"]
    assert "Run on real quantum hardware now" in data["live"]
    verifier = (REPO_ROOT / "ui" / "scripts" / "verify.mjs").read_text(encoding="utf-8")
    assert "presenter-strings.json" in verifier
