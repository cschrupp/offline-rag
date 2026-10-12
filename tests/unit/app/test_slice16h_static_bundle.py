"""16H — unit coverage for Seneca static-bundle validator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = REPO_ROOT / "scripts" / "validate_seneca_static_bundle.py"
_SPEC = importlib.util.spec_from_file_location(
    "validate_seneca_static_bundle", _MODULE_PATH
)
assert _SPEC and _SPEC.loader
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
validate_dist = _MOD.validate_dist


def _write_good_dist(root: Path) -> Path:
    dist = root / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        """<!doctype html>
<html lang="en">
<head>
  <link rel="icon" href="/favicon.svg" />
  <script type="module" src="/assets/index-abc.js"></script>
  <link rel="stylesheet" href="/assets/index-abc.css" />
</head>
<body><div id="root"></div></body>
</html>
""",
        encoding="utf-8",
    )
    (dist / "favicon.svg").write_text("<svg></svg>\n", encoding="utf-8")
    (assets / "index-abc.css").write_text(
        "@font-face{font-family:Inter;src:url(/assets/inter-latin.woff2)}\n",
        encoding="utf-8",
    )
    (assets / "index-abc.js").write_text(
        'window.__SENECA__=1;const cfg={base_url:"http://127.0.0.1:11434/v1"};\n',
        encoding="utf-8",
    )
    (assets / "inter-latin.woff2").write_bytes(b"woff2")
    return dist


def test_validate_dist_accepts_local_bundle(tmp_path: Path) -> None:
    dist = _write_good_dist(tmp_path)
    report = validate_dist(dist)
    assert report["ok"] is True
    assert report["font_file_count"] >= 1
    assert report["findings"] == []


def test_validate_dist_rejects_external_css_font(tmp_path: Path) -> None:
    dist = _write_good_dist(tmp_path)
    (dist / "assets" / "index-abc.css").write_text(
        "@font-face{src:url(https://fonts.gstatic.com/s/inter.woff2)}\n",
        encoding="utf-8",
    )
    report = validate_dist(dist)
    assert report["ok"] is False
    assert any(f.get("kind") == "css" for f in report["findings"])


def test_validate_dist_rejects_blocked_js_cdn(tmp_path: Path) -> None:
    dist = _write_good_dist(tmp_path)
    (dist / "assets" / "index-abc.js").write_text(
        'import "https://cdn.jsdelivr.net/npm/react@19/index.js";\n',
        encoding="utf-8",
    )
    report = validate_dist(dist)
    assert report["ok"] is False
    assert any(f.get("kind") == "js_blocked_cdn" for f in report["findings"])


def test_repo_ui_dist_is_local_when_present() -> None:
    dist = Path(__file__).resolve().parents[3] / "ui" / "dist"
    if not (dist / "index.html").is_file():
        pytest.skip("ui/dist not built in this environment")
    report = validate_dist(dist)
    assert report["ok"] is True, report["findings"]
