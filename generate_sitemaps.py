#!/usr/bin/env python3
"""Generate sitemap.xml + ai-sitemap.xml with correct base URL.

Why this exists
- Google rejects sitemaps when the sitemap is hosted on one domain (e.g., https://sub.example.com/sitemap.xml)
  but the <loc> URLs inside point to a different domain (e.g., https://owner.github.io/repo/...).

What this script does
- Uses your repo root CNAME (if present) as the canonical base URL.
- Falls back to the default GitHub Pages URL if no CNAME exists.
- Generates:
    - sitemap.xml      (human-facing pages: *.html at repo root)
    - ai-sitemap.xml   (machine-readable files in folders you choose)

Safe to re-run
- Overwrites sitemap.xml and ai-sitemap.xml (no -1/-2 duplicates).
"""

from __future__ import annotations

import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

# ----------------------------
# Base URL discovery
# ----------------------------

def _read_cname(repo_root: Path) -> str:
    cname_path = repo_root / "CNAME"
    if not cname_path.exists():
        return ""
    txt = cname_path.read_text(encoding="utf-8").strip()
    # CNAME can include comments/extra lines; take first non-empty token
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # drop protocol if someone pasted it
        line = line.replace("https://", "").replace("http://", "")
        return line.strip().strip("/")
    return ""


def discover_base_url(repo_root: Path) -> str:
    cname = _read_cname(repo_root)
    if cname:
        return f"https://{cname}/"

    repo_slug = os.getenv("GITHUB_REPOSITORY", "")  # owner/repo
    if repo_slug and "/" in repo_slug:
        owner, repo = repo_slug.split("/", 1)
        return f"https://{owner}.github.io/{repo}/"

    # last-resort fallback (still valid for local generation)
    return "https://example.com/"


# ----------------------------
# File collection helpers
# ----------------------------

def _is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def collect_html_pages(repo_root: Path) -> list[str]:
    """Return relative paths for root-level HTML pages."""
    pages: list[str] = []
    for p in repo_root.glob("*.html"):
        if p.is_file() and not _is_hidden(p):
            pages.append(p.name)
    # Stable order
    pages.sort()
    return pages


def collect_machine_files(repo_root: Path, folders: list[str], exts: list[str]) -> list[str]:
    """Return relative paths for machine-readable files under given folders."""
    rels: list[str] = []
    for folder in folders:
        base = repo_root / folder
        if not base.exists() or not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or _is_hidden(p):
                continue
            if p.suffix.lower() in exts:
                rels.append(str(p.relative_to(repo_root)).replace("\\", "/"))
    rels = sorted(set(rels))
    return rels


# ----------------------------
# XML writers
# ----------------------------

def write_sitemap(repo_root: Path, out_name: str, base_url: str, rel_paths: list[str]):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out_path = repo_root / out_name

    # Always overwrite (no duplicates)
    with out_path.open("w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for rel in rel_paths:
            loc = urljoin(base_url, rel)
            f.write("  <url>\n")
            f.write(f"    <loc>{loc}</loc>\n")
            f.write(f"    <lastmod>{now}</lastmod>\n")
            f.write("  </url>\n")
        f.write("</urlset>\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".", help="Repo root (default: .)")
    ap.add_argument(
        "--machine-folders",
        default="schemas,llm-data,faq-schemas,locations,organization",
        help="Comma-separated folders to include in ai-sitemap.xml",
    )
    ap.add_argument(
        "--machine-exts",
        default=".json,.yaml,.yml,.jsonl,.md,.llm,.txt",
        help="Comma-separated extensions to include in ai-sitemap.xml",
    )
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    os.chdir(repo_root)

    base_url = discover_base_url(repo_root)
    html_pages = collect_html_pages(repo_root)

    folders = [s.strip() for s in str(args.machine_folders).split(",") if s.strip()]
    exts = [s.strip().lower() for s in str(args.machine_exts).split(",") if s.strip()]
    machine_files = collect_machine_files(repo_root, folders, exts)

    # Write output files
    write_sitemap(repo_root, "sitemap.xml", base_url, html_pages)
    write_sitemap(repo_root, "ai-sitemap.xml", base_url, machine_files)

    print("✅ Generated sitemap.xml with", len(html_pages), "page URL(s)")
    print("✅ Generated ai-sitemap.xml with", len(machine_files), "file URL(s)")
    print("🌐 Base URL:", base_url)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("❌ sitemap generation failed:", e)
        sys.exit(2)
