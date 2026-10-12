#!/usr/bin/env python3
"""16H Family G — inspect a Vite production bundle for same-origin static assets.

Fails if dist/index.html, CSS url(...), or script/module references require a
runtime CDN / external host for presentation assets (fonts, CSS, JS, images).

Operator-configurable backend model endpoint strings inside JS are ignored.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

EXTERNAL_HOST_RE = re.compile(
    r"""(?xi)
    (?:
      https?://
      | //(?![/\s])
    )
    (?P<host>[^/"'\s)]+)
    """
)

ALLOWED_SCHEME_PREFIXES = (
    "data:",
    "blob:",
)

# Host fragments that are never presentation CDNs we accept at runtime.
BLOCKED_HOST_FRAGMENTS = (
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "cdn.jsdelivr.net",
    "unpkg.com",
    "cdnjs.cloudflare.com",
    "ajax.googleapis.com",
    "use.typekit.net",
    "kit.fontawesome.com",
)


def _is_local_ref(ref: str) -> bool:
    ref = ref.strip().strip("\"'")
    if not ref or ref.startswith("#"):
        return True
    if ref.startswith(ALLOWED_SCHEME_PREFIXES):
        return True
    if ref.startswith(("/", "./", "../")):
        return True
    parsed = urlparse(ref)
    if parsed.scheme in {"http", "https"}:
        return False
    if ref.startswith("//"):
        return False
    # Bare relative path without scheme.
    return "://" not in ref


def _collect_html_refs(html: str) -> list[str]:
    refs: list[str] = []
    for match in re.finditer(
        r"""(?xi)
        <(?:script|link|img|source|video|audio|use)
        [^>]+?
        (?:src|href)=["']([^"']+)["']
        """,
        html,
    ):
        refs.append(match.group(1))
    return refs


def _collect_css_urls(css: str) -> list[str]:
    return [m.group(1).strip().strip("\"'") for m in re.finditer(r"url\(([^)]+)\)", css)]


def validate_dist(dist_dir: Path) -> dict:
    index = dist_dir / "index.html"
    if not index.is_file():
        raise FileNotFoundError(f"missing {index}")

    findings: list[dict] = []
    html = index.read_text(encoding="utf-8")
    for ref in _collect_html_refs(html):
        if not _is_local_ref(ref):
            findings.append({"kind": "html", "ref": ref})

    assets_dir = dist_dir / "assets"
    css_files = sorted(assets_dir.glob("*.css")) if assets_dir.is_dir() else []
    js_files = sorted(assets_dir.glob("*.js")) if assets_dir.is_dir() else []

    for css_path in css_files:
        css = css_path.read_text(encoding="utf-8")
        for ref in _collect_css_urls(css):
            if not _is_local_ref(ref):
                findings.append({"kind": "css", "file": css_path.name, "ref": ref})

    # JS may contain configurable generator URLs; only fail blocked presentation CDNs.
    for js_path in js_files:
        text = js_path.read_text(encoding="utf-8", errors="replace")
        for match in EXTERNAL_HOST_RE.finditer(text):
            host = match.group("host").lower()
            if any(frag in host for frag in BLOCKED_HOST_FRAGMENTS):
                findings.append(
                    {
                        "kind": "js_blocked_cdn",
                        "file": js_path.name,
                        "host": host,
                    }
                )

    # Required local presentation assets exist.
    required_local = [
        dist_dir / "favicon.svg",
    ]
    for path in required_local:
        if not path.is_file():
            findings.append({"kind": "missing_asset", "path": str(path)})

    font_files = list(assets_dir.glob("*.woff*")) if assets_dir.is_dir() else []
    if not font_files:
        findings.append({"kind": "missing_fonts", "detail": "no bundled woff/woff2 fonts"})

    ok = len(findings) == 0
    return {
        "ok": ok,
        "dist_dir": str(dist_dir.resolve()),
        "html_refs": _collect_html_refs(html),
        "css_file_count": len(css_files),
        "js_file_count": len(js_files),
        "font_file_count": len(font_files),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "ui" / "dist",
        help="Path to Vite production dist/",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write JSON report",
    )
    args = parser.parse_args(argv)
    report = validate_dist(args.dist)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
