#!/usr/bin/env python3
"""
update.py — Brain of fastest-growing-finance-repos
────────────────────────────────────────────────────
1. Discovery: searches GitHub for finance/fintech/quant repos (run on first
   run and monthly thereafter) and seeds data/tracked_repos.json
2. Delta: fetches current star counts, calculates Δstars vs last week
3. Ranking: picks the Top 10 by Δstars
4. Publish: writes README.md, appends to archive/, regenerates docs/index.html
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

TOPICS = [
    "finance",
    "fintech",
    "quant",
    "algorithmic-trading",
    "cryptocurrency",
    "trading-bot",
    "quantitative-finance",
    "defi",
    "blockchain-finance",
    "stock-market",
    "options-trading",
    "portfolio-management",
    "backtesting",
    "high-frequency-trading",
    "crypto-trading",
]

MIN_STARS = 100          # minimum stars to track a repo
TOP_N = 10               # number of repos in the weekly list
DISCOVERY_INTERVAL = 28  # days between full discovery scans
REPOS_PER_TOPIC = 30     # how many repos to pull per topic search

DATA_FILE = Path("data/tracked_repos.json")
ARCHIVE_DIR = Path("archive")
README_FILE = Path("README.md")
HTML_FILE = Path("docs/index.html")

GITHUB_API = "https://api.github.com"
LIVE_SITE = "https://davidlifschitz.github.io/fastest-growing-finance-repos/"
REPO_URL = "https://github.com/davidlifschitz/fastest-growing-finance-repos"

# ──────────────────────────────────────────────────────────────
# GitHub session
# ──────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
    s = requests.Session()
    s.headers.update({
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


SESSION = _make_session()


def _get(url: str, params: Optional[dict] = None, retries: int = 3) -> dict | list:
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=20)
            if r.status_code == 403 and "rate limit" in r.text.lower():
                reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(reset - time.time(), 1) + 5
                print(f"  ⏳ Rate-limited — sleeping {int(wait)}s …", flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise
            print(f"  ⚠️  Retry {attempt+1}/{retries} after error: {exc}", flush=True)
            time.sleep(2 ** attempt)
    return {}


# ──────────────────────────────────────────────────────────────
# Data helpers
# ──────────────────────────────────────────────────────────────

def load_data() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"repos": {}, "last_discovery": None, "last_run": None}


def save_data(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2))


# ──────────────────────────────────────────────────────────────
# Discovery
# ──────────────────────────────────────────────────────────────

def should_discover(data: dict) -> bool:
    if not data.get("repos"):
        return True
    if not data.get("last_discovery"):
        return True
    last = datetime.fromisoformat(data["last_discovery"])
    age = (datetime.now(timezone.utc) - last).days
    return age >= DISCOVERY_INTERVAL


def discover_repos(data: dict) -> dict:
    """Search GitHub topics for finance repos and seed the tracker."""
    print("🔍 Discovery scan starting …", flush=True)
    added = 0
    seen: set[str] = set(data["repos"].keys())

    for topic in TOPICS:
        print(f"  topic: {topic}", flush=True)
        page = 1
        collected = 0
        while collected < REPOS_PER_TOPIC:
            params = {
                "q": f"topic:{topic} stars:>{MIN_STARS}",
                "sort": "stars",
                "order": "desc",
                "per_page": 30,
                "page": page,
            }
            try:
                result = _get(f"{GITHUB_API}/search/repositories", params=params)
            except Exception as exc:
                print(f"    ⚠️  Search failed: {exc}", flush=True)
                break

            items = result.get("items", [])
            if not items:
                break

            for repo in items:
                full_name: str = repo["full_name"]
                if full_name not in seen and repo.get("stargazers_count", 0) >= MIN_STARS:
                    data["repos"][full_name] = {
                        "full_name": full_name,
                        "description": (repo.get("description") or "")[:200],
                        "html_url": repo["html_url"],
                        "language": repo.get("language") or "",
                        "stars_last_week": None,
                        "stars_current": repo["stargazers_count"],
                        "last_updated": None,
                    }
                    seen.add(full_name)
                    added += 1
                collected += 1

            page += 1
            time.sleep(0.5)  # be polite

    data["last_discovery"] = datetime.now(timezone.utc).isoformat()
    print(f"✅ Discovery done — added {added} new repos ({len(data['repos'])} total)", flush=True)
    return data


# ──────────────────────────────────────────────────────────────
# Star fetch
# ──────────────────────────────────────────────────────────────

def fetch_star_counts(data: dict) -> dict:
    """Snapshot current stars; promote current→last_week for delta calc."""
    print(f"⭐ Fetching star counts for {len(data['repos'])} repos …", flush=True)
    now_iso = datetime.now(timezone.utc).isoformat()
    errors = 0

    for i, (full_name, meta) in enumerate(data["repos"].items(), 1):
        if i % 50 == 0:
            print(f"  {i}/{len(data['repos'])} …", flush=True)

        # Promote current → last_week before overwriting
        if meta.get("stars_current") is not None:
            meta["stars_last_week"] = meta["stars_current"]

        try:
            repo_data = _get(f"{GITHUB_API}/repos/{full_name}")
            meta["stars_current"] = repo_data.get("stargazers_count", meta.get("stars_current", 0))
            meta["description"] = (repo_data.get("description") or "")[:200]
            meta["language"] = repo_data.get("language") or meta.get("language", "")
            meta["html_url"] = repo_data.get("html_url", meta.get("html_url", ""))
            meta["last_updated"] = now_iso
        except Exception as exc:
            errors += 1
            print(f"  ⚠️  {full_name}: {exc}", flush=True)

        time.sleep(0.1)

    print(f"✅ Star fetch done ({errors} errors)", flush=True)
    data["last_run"] = now_iso
    return data


# ──────────────────────────────────────────────────────────────
# Ranking
# ──────────────────────────────────────────────────────────────

def compute_top(data: dict, n: int = TOP_N) -> list[dict]:
    results = []
    for full_name, meta in data["repos"].items():
        curr = meta.get("stars_current")
        last = meta.get("stars_last_week")
        if curr is None:
            continue
        delta = (curr - last) if last is not None else 0
        results.append({
            "full_name": full_name,
            "html_url": meta.get("html_url", f"https://github.com/{full_name}"),
            "description": meta.get("description", ""),
            "language": meta.get("language", ""),
            "stars_current": curr,
            "stars_last_week": last,
            "delta": delta,
        })

    results.sort(key=lambda r: r["delta"], reverse=True)
    return results[:n]


# ──────────────────────────────────────────────────────────────
# Markdown generation
# ──────────────────────────────────────────────────────────────

BADGE_MAP = {
    "Python": "![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white&style=flat-square)",
    "Rust": "![Rust](https://img.shields.io/badge/Rust-000000?logo=rust&logoColor=white&style=flat-square)",
    "TypeScript": "![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white&style=flat-square)",
    "JavaScript": "![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?logo=javascript&logoColor=black&style=flat-square)",
    "Go": "![Go](https://img.shields.io/badge/Go-00ADD8?logo=go&logoColor=white&style=flat-square)",
    "C++": "![C++](https://img.shields.io/badge/C++-00599C?logo=c%2B%2B&logoColor=white&style=flat-square)",
    "Solidity": "![Solidity](https://img.shields.io/badge/Solidity-363636?logo=solidity&logoColor=white&style=flat-square)",
}


def _lang_badge(lang: str) -> str:
    return BADGE_MAP.get(lang, f"`{lang}`" if lang else "")


def _delta_str(delta: int) -> str:
    if delta > 0:
        return f"+{delta:,} ⭐"
    if delta == 0:
        return "0 ⭐"
    return f"{delta:,} ⭐"


def build_top_table(top: list[dict]) -> str:
    lines = [
        "| # | Repo | Description | Lang | Stars | Δ This Week |",
        "|---|------|-------------|------|-------|-------------|",
    ]
    for rank, r in enumerate(top, 1):
        desc = (r["description"] or "—")[:80].replace("|", "\\|")
        lang = _lang_badge(r.get("language", ""))
        stars = f"{r['stars_current']:,}"
        delta = _delta_str(r["delta"])
        name = r["full_name"].split("/")[1]
        link = f"[{r['full_name']}]({r['html_url']})"
        lines.append(f"| {rank} | {link} | {desc} | {lang} | {stars} | {delta} |")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# README writer
# ──────────────────────────────────────────────────────────────

def load_archive_entries() -> list[str]:
    """Return archive markdown snippets sorted newest-first."""
    entries = []
    for f in sorted(ARCHIVE_DIR.glob("*.md"), reverse=True):
        entries.append(f.read_text().strip())
    return entries


def write_readme(top: list[dict], run_date: str) -> None:
    table = build_top_table(top)
    archive_entries = load_archive_entries()

    if archive_entries:
        archive_section = "\n\n---\n\n".join(archive_entries)
    else:
        archive_section = "_Previous weeks will appear here automatically._"

    topics_line = " · ".join(f"`{t}`" for t in TOPICS)

    readme = f"""<!-- AUTO-GENERATED — DO NOT EDIT MANUALLY -->
# 🚀 Top {TOP_N} Fastest-Growing Finance Repos This Week

> Updated **{run_date}** · Tracks {len(top)} repos this week  
> Full list: [GitHub Pages site]({LIVE_SITE})

{table}

---

## 📚 Archive

{archive_section}

---

## ⚙️ How It Works

1. Tracks 300+ finance/fintech/crypto/quant GitHub repos
2. Every Sunday, fetches current star counts and calculates weekly growth
3. Ranks by `Δ stars` (new stars gained in 7 days)
4. Publishes the Top {TOP_N} here + on the [GitHub Pages site]({LIVE_SITE})
5. Monthly discovery scan adds newly trending repos automatically

## 🏷️ Topics Tracked

{topics_line}

## 💡 Suggest a Repo

Open an issue or see [CONTRIBUTING.md](CONTRIBUTING.md)

---

*⭐ Star this repo to stay updated · 🔖 Bookmark the [live site]({LIVE_SITE})*
"""
    README_FILE.write_text(readme)
    print(f"✅ README.md written", flush=True)


# ──────────────────────────────────────────────────────────────
# Archive writer
# ──────────────────────────────────────────────────────────────

def write_archive(top: list[dict], run_date: str) -> None:
    ARCHIVE_DIR.mkdir(exist_ok=True)
    # Use ISO date as filename key (YYYY-MM-DD)
    date_slug = run_date[:10]
    archive_file = ARCHIVE_DIR / f"{date_slug}.md"
    table = build_top_table(top)
    content = f"### Week of {run_date}\n\n{table}\n"
    archive_file.write_text(content)
    print(f"✅ Archive written: {archive_file}", flush=True)


# ──────────────────────────────────────────────────────────────
# HTML writer
# ──────────────────────────────────────────────────────────────

def _html_rows(top: list[dict]) -> str:
    rows = []
    for rank, r in enumerate(top, 1):
        desc = (r["description"] or "No description")[:100]
        lang = r.get("language") or "—"
        stars = f"{r['stars_current']:,}"
        delta = r["delta"]
        delta_cls = "positive" if delta > 0 else ("negative" if delta < 0 else "neutral")
        delta_str = f"+{delta:,}" if delta > 0 else str(delta)
        name = r["full_name"]
        url = r["html_url"]
        rows.append(f"""
    <tr>
      <td class="rank">#{rank}</td>
      <td class="repo"><a href="{url}" target="_blank" rel="noopener">{name}</a></td>
      <td class="desc">{desc}</td>
      <td class="lang">{lang}</td>
      <td class="stars">{stars}</td>
      <td class="delta {delta_cls}">{delta_str} ⭐</td>
    </tr>""")
    return "".join(rows)


def write_html(top: list[dict], run_date: str) -> None:
    HTML_FILE.parent.mkdir(exist_ok=True)
    rows = _html_rows(top)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>🚀 Fastest-Growing Finance Repos</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:       #0d1117;
      --surface:  #161b22;
      --border:   #30363d;
      --text:     #e6edf3;
      --muted:    #8b949e;
      --link:     #58a6ff;
      --green:    #3fb950;
      --red:      #f85149;
      --gold:     #d29922;
    }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh;
      padding: 2rem 1rem 4rem;
    }}

    .container {{ max-width: 1100px; margin: 0 auto; }}

    header {{
      text-align: center;
      padding: 2rem 0 2.5rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 2rem;
    }}
    header h1 {{ font-size: clamp(1.4rem, 4vw, 2.2rem); letter-spacing: -0.5px; }}
    header .meta {{ color: var(--muted); font-size: 0.9rem; margin-top: 0.5rem; }}
    header .meta a {{ color: var(--link); text-decoration: none; }}
    header .meta a:hover {{ text-decoration: underline; }}

    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }}

    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }}
    th {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; background: #1c2128; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: rgba(255,255,255,0.02); }}

    td.rank   {{ font-weight: 700; color: var(--gold); width: 3rem; }}
    td.repo a {{ color: var(--link); text-decoration: none; font-weight: 600; }}
    td.repo a:hover {{ text-decoration: underline; }}
    td.desc   {{ color: var(--muted); font-size: 0.85rem; max-width: 280px; }}
    td.lang   {{ font-size: 0.85rem; white-space: nowrap; }}
    td.stars  {{ white-space: nowrap; }}
    td.delta  {{ font-weight: 700; white-space: nowrap; }}
    td.delta.positive {{ color: var(--green); }}
    td.delta.negative {{ color: var(--red); }}
    td.delta.neutral  {{ color: var(--muted); }}

    @media (max-width: 700px) {{
      td.desc, td.lang {{ display: none; }}
      th:nth-child(3), th:nth-child(4) {{ display: none; }}
    }}

    footer {{
      text-align: center;
      color: var(--muted);
      font-size: 0.8rem;
      margin-top: 2rem;
    }}
    footer a {{ color: var(--link); text-decoration: none; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>🚀 Top {TOP_N} Fastest-Growing Finance Repos</h1>
      <p class="meta">
        Updated <strong>{run_date}</strong> &nbsp;·&nbsp;
        <a href="{REPO_URL}">GitHub</a> &nbsp;·&nbsp;
        Auto-refreshed every Sunday at 00:00 UTC
      </p>
    </header>

    <div class="card">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Repository</th>
            <th>Description</th>
            <th>Language</th>
            <th>⭐ Stars</th>
            <th>Δ This Week</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>

    <footer>
      <p>
        Tracked topics: {" · ".join(TOPICS[:8])} …
        &nbsp;·&nbsp;
        <a href="{REPO_URL}">Star this repo</a> to stay updated
      </p>
    </footer>
  </div>
</body>
</html>
"""
    HTML_FILE.write_text(html)
    print(f"✅ docs/index.html written", flush=True)


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60, flush=True)
    print("🚀 fastest-growing-finance-repos — weekly update", flush=True)
    print("=" * 60, flush=True)

    data = load_data()

    # Step 1: Discovery (first run or monthly)
    if should_discover(data):
        data = discover_repos(data)
        save_data(data)

    # Step 2: Fetch current star counts (promotes current→last_week)
    data = fetch_star_counts(data)
    save_data(data)

    # Step 3: Rank
    top = compute_top(data)
    if not top:
        print("⚠️  No repos ranked — check data.", flush=True)
        sys.exit(1)

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"\n🏆 Top {TOP_N} this week ({run_date}):", flush=True)
    for i, r in enumerate(top, 1):
        print(f"  {i:>2}. {r['full_name']:40s}  Δ{r['delta']:+,}", flush=True)

    # Step 4: Publish
    write_archive(top, run_date)
    write_readme(top, run_date)
    write_html(top, run_date)

    print("\n🎉 All done!", flush=True)


if __name__ == "__main__":
    main()
