#!/usr/bin/env python3
"""Build private, self-contained HTML artifacts for map use and calibration."""

from __future__ import annotations

from pathlib import Path
import base64
import re
from html import escape


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
GENERATED_DIR = ROOT / "data" / "generated"
DIST_DIR = ROOT / "dist"


def inline_script(html: str, src: str, path: Path) -> str:
    tag = f'<script src="{src}"></script>'
    if tag not in html:
        raise ValueError(f"Missing script tag: {tag}")
    content = path.read_text(encoding="utf-8").replace("</script", "<\\/script")
    return html.replace(tag, f"<script>\n{content.rstrip()}\n</script>", 1)


def build_map() -> Path:
    html = (WEB_DIR / "map.html").read_text(encoding="utf-8")
    html = inline_script(
        html,
        "../data/generated/places-data.js",
        GENERATED_DIR / "places-data.js",
    )
    for name in ('vendor/maplibre-gl.css', 'atlas-base.css', 'atlas.css', 'atlas-v2.css'):
        css = (WEB_DIR / 'assets' / name).read_text(encoding='utf-8')
        if name == 'atlas-base.css':
            def embed_font(match):
                data = (WEB_DIR / 'assets' / match[1]).read_bytes()
                return 'url("data:font/woff2;base64,' + base64.b64encode(data).decode() + '")'
            css = re.sub(r'url\("\./(fonts/[^"\)]+)"\)', embed_font, css)
        tag = f'<link rel="stylesheet" href="./assets/{name}" />'
        if tag not in html:
            raise ValueError(f'Missing stylesheet tag: {tag}')
        html = html.replace(tag, '<style>\n' + css + '\n</style>', 1)
    for name in ('vendor/maplibre-gl.js', 'vendor/positron-style.js', 'vendor/gcoord.js', 'atlas.js'):
        html = inline_script(html, './assets/' + name, WEB_DIR / 'assets' / name)
    licenses = [WEB_DIR / 'assets' / 'vendor' / 'gcoord.LICENSE', *sorted((WEB_DIR / 'assets' / 'licenses').glob('*.txt'))]
    license_text = '\n\n'.join(path.name + '\n' + path.read_text(encoding='utf-8') for path in licenses)
    html = html.replace('</body>', '<template id="third-party-licenses"><pre>' + escape(license_text) + '</pre></template>\n</body>', 1)
    output = DIST_DIR / "Review-Map.html"
    output.write_text(html, encoding="utf-8")
    return output


def build_review() -> Path:
    html = (WEB_DIR / "review.html").read_text(encoding="utf-8")
    dependencies = (
        ("../data/generated/review-data.js", GENERATED_DIR / "review-data.js"),
        ("../data/generated/review-progress-seed.js", GENERATED_DIR / "review-progress-seed.js"),
        ("../data/generated/places-data.js", GENERATED_DIR / "places-data.js"),
    )
    for src, path in dependencies:
        html = inline_script(html, src, path)
    output = DIST_DIR / "Calibration-Desk.html"
    output.write_text(html, encoding="utf-8")
    return output


def main() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    for path in (build_map(), build_review()):
        print(f"created={path.relative_to(ROOT)} bytes={path.stat().st_size}")


if __name__ == "__main__":
    main()
