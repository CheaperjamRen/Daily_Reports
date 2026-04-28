#!/usr/bin/env python3
"""
Daily GitHub AI Projects Report Generator
每日 GitHub AI 高Stars项目日报生成器

Environment variables
---------------------
GITHUB_TOKEN – GitHub token (auto-set by GitHub Actions).
               Used for both the GitHub REST API and the GitHub Models inference
               API (https://models.inference.ai.azure.com) that powers AI analysis.
               No additional secrets are required when the repository owner has
               GitHub Copilot Free or higher.
"""

import base64
import csv
import datetime
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# ── Configuration ──────────────────────────────────────────────────────────────

GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")

# Minimum stars threshold for inclusion
MIN_STARS = 1000

# How many new repos to show in the report (sorted by stars desc)
MAX_NEW_REPOS = 20

# How many new repos / major-update repos to send to GitHub Copilot for deep analysis
MAX_DEEP_ANALYSIS = 10

# Seconds to sleep between consecutive GitHub API calls
API_DELAY = 1.5

# A repo is considered a "major update" if it gained this many stars in one day …
MAJOR_UPDATE_STARS_ABS = 200
# … OR grew by this percentage
MAJOR_UPDATE_STARS_PCT = 15.0

# GitHub repository search queries (topics that indicate AI / interesting tools)
SEARCH_QUERIES: List[str] = [
    f"topic:llm stars:>{MIN_STARS}",
    f"topic:ai stars:>{MIN_STARS}",
    f"topic:artificial-intelligence stars:>{MIN_STARS}",
    f"topic:machine-learning stars:>{MIN_STARS}",
    f"topic:deep-learning stars:>{MIN_STARS}",
    f"topic:generative-ai stars:>{MIN_STARS}",
    f"topic:chatgpt stars:>{MIN_STARS}",
    f"topic:stable-diffusion stars:>{MIN_STARS}",
    f"topic:openai stars:>{MIN_STARS}",
    f"topic:neural-network stars:>{MIN_STARS}",
    f"topic:rag stars:>{MIN_STARS}",
    f"topic:agent stars:>{MIN_STARS}",
]

RESULTS_PER_QUERY = 30  # GitHub search API max per page

# CSV column order
TRACKING_FIELDS = [
    "full_name",
    "stars",
    "last_updated",
    "tracked_since",
    "description",
    "url",
    "last_release",
]


# ── GitHub API helpers ─────────────────────────────────────────────────────────

def _headers() -> Dict[str, str]:
    h: Dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


def _get(url: str, params: Optional[Dict] = None, retries: int = 3) -> Optional[Dict]:
    """GET a GitHub API endpoint, handling rate-limiting with automatic retry."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=30)
            if r.status_code == 403:
                retry_after = int(r.headers.get("Retry-After", 60))
                print(f"  Rate-limited. Sleeping {retry_after}s …")
                time.sleep(retry_after)
                continue
            if r.status_code == 200:
                return r.json()
            print(f"  HTTP {r.status_code} for {url}")
            return None
        except Exception as exc:
            print(f"  Request error (attempt {attempt + 1}): {exc}")
            time.sleep(5)
    return None


def search_repos(query: str, per_page: int = 30) -> List[Dict]:
    """Return up to *per_page* repositories matching *query*, sorted by stars."""
    data = _get(
        "https://api.github.com/search/repositories",
        {"q": query, "sort": "stars", "order": "desc", "per_page": per_page},
    )
    return data.get("items", []) if data else []


def get_readme(owner: str, repo: str) -> str:
    """Return the decoded README text, or an empty string on failure."""
    data = _get(f"https://api.github.com/repos/{owner}/{repo}/readme")
    if data and data.get("content"):
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            pass
    return ""


# ── GitHub Models (Copilot) analysis ──────────────────────────────────────────

# GitHub Models inference endpoint – OpenAI-compatible, authenticated with GITHUB_TOKEN.
# Available to all accounts that have GitHub Copilot Free or higher.
_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
_ANALYSIS_MODEL = "gpt-4o-mini"

# Rate-limit guard: GitHub Models free tier allows up to 15 req/min.
_MODELS_CALL_DELAY = 5  # seconds between consecutive Copilot API calls


def analyze_repo(readme: str, extra_prompt: str = "") -> Optional[str]:
    """
    Send README text to GitHub Models (Copilot) and return a Chinese analysis.
    Returns None when GITHUB_TOKEN is not set or on any error.
    """
    if not GITHUB_TOKEN:
        print("  GITHUB_TOKEN not set; skipping AI analysis.")
        return None
    try:
        system_msg = (
            "你是一位专注于 AI 和软件项目的技术分析师。"
            "请用中文简洁地分析以下 GitHub 项目，内容不超过 300 字。"
        )
        user_msg = (
            f"{extra_prompt}\n\nREADME 内容（摘录）：\n{readme[:4000]}"
            if extra_prompt
            else f"README 内容（摘录）：\n{readme[:4000]}"
        )
        resp = requests.post(
            f"{_MODELS_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "model": _ANALYSIS_MODEL,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 600,
            },
            timeout=60,
        )
        time.sleep(_MODELS_CALL_DELAY)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        print(f"  GitHub Models error: {resp.status_code} - {resp.text}")
        return None
    except Exception as exc:
        print(f"  GitHub Models error: {exc}")
    return None


# ── Tracking CSV helpers ───────────────────────────────────────────────────────

def load_tracking(path: Path) -> Dict[str, Dict]:
    """Load the previous-day tracking CSV into a dict keyed by full_name."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {row["full_name"]: dict(row) for row in csv.DictReader(f)}


def save_tracking(path: Path, data: Dict[str, Dict]) -> None:
    """Persist the tracking dict to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKING_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data.values())


# ── README plain-text summary (fallback when no AI key) ───────────────────────

def summarize_readme(text: str, max_chars: int = 400) -> str:
    """Extract the first few meaningful lines of a README as plain text."""
    paragraphs: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "!", "[", "|", "```", "<!--", "---", "===")):
            paragraphs.append(line)
        if sum(len(p) for p in paragraphs) >= max_chars:
            break
    summary = " ".join(paragraphs)
    return summary[:max_chars] + ("…" if len(summary) > max_chars else "")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pct(growth: int, base: int) -> str:
    if base == 0:
        return "N/A"
    return f"{growth / base * 100:+.1f}%"


def is_major_update(old_stars: int, new_stars: int) -> bool:
    growth = new_stars - old_stars
    pct = growth / old_stars * 100 if old_stars > 0 else 0
    return growth >= MAJOR_UPDATE_STARS_ABS or pct >= MAJOR_UPDATE_STARS_PCT


# ── Report builder ─────────────────────────────────────────────────────────────

def build_report(
    date_str: str,
    major_updates: List[Tuple[str, Dict]],
    minor_updates: List[Tuple[str, Dict]],
    new_repos: List[Dict],
) -> str:
    lines: List[str] = [
        f"# 每日 AI 项目日报 · {date_str}",
        "",
        f"> 报告生成时间：{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        "---",
        "",
    ]

    # ── Part 1: Tracked project updates ───────────────────────────────────────
    lines += ["## 一、已追踪项目动态", ""]

    if major_updates:
        lines += ["### 🔥 重大更新项目", ""]
        for name, d in major_updates:
            growth = d["new_stars"] - d["old_stars"]
            lines += [
                f"#### [{name}]({d['url']})",
                "",
                (
                    f"- ⭐ Stars：{d['old_stars']:,} → {d['new_stars']:,}"
                    f"（{growth:+,}，{_pct(growth, d['old_stars'])}）"
                ),
                f"- 📝 简介：{d['description'] or '无'}",
                "",
            ]
            if d.get("analysis"):
                lines += ["**更新分析：**", "", d["analysis"], ""]
            lines += ["---", ""]

    if minor_updates:
        lines += [
            "### 📈 Stars 增长追踪（小幅更新）",
            "",
            "| 项目 | 前日 Stars | 今日 Stars | 增长 | 增长率 |",
            "|------|-----------|-----------|------|--------|",
        ]
        for name, d in minor_updates:
            growth = d["new_stars"] - d["old_stars"]
            lines.append(
                f"| [{name}]({d['url']}) | {d['old_stars']:,} | {d['new_stars']:,}"
                f" | {growth:+,} | {_pct(growth, d['old_stars'])} |"
            )
        lines += ["", "---", ""]

    if not major_updates and not minor_updates:
        lines += ["暂无已追踪项目更新。", "", "---", ""]

    # ── Part 2: New high-stars repos (deep analysis) ───────────────────────────
    lines += ["## 二、新发现高 Stars 项目深度解析", ""]

    if new_repos:
        for repo in new_repos:
            name = repo["full_name"]
            stars = repo["stargazers_count"]
            desc = repo.get("description") or "无描述"
            url = repo["html_url"]
            lang = repo.get("language") or "未知"
            topics = "、".join(repo.get("topics", [])) or "无"
            created = (repo.get("created_at") or "")[:10]

            lines += [
                f"### 🆕 [{name}]({url})",
                "",
                f"- ⭐ Stars：{stars:,}",
                f"- 💻 主要语言：{lang}",
                f"- 🏷️ 话题标签：{topics}",
                f"- 📅 创建时间：{created}",
                f"- 📝 官方描述：{desc}",
                "",
            ]
            if repo.get("analysis"):
                lines += ["**深度分析：**", "", repo["analysis"], ""]
            elif repo.get("readme_summary"):
                lines += ["**README 摘要：**", "", repo["readme_summary"], ""]
            lines += ["---", ""]
    else:
        lines += ["今日未发现新的高 Stars 项目。", ""]

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    today = datetime.datetime.now(datetime.timezone.utc).date()
    date_str = today.strftime("%Y-%m-%d")

    base = Path(__file__).resolve().parent.parent
    tracking_path = base / "data" / "tracked_repos.csv"
    report_path = base / "reports" / f"{date_str}.md"

    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "reports").mkdir(parents=True, exist_ok=True)

    print(f"[{date_str}] Daily AI Report Generator starting …")

    # ── Step 1: Load previous tracking data ───────────────────────────────────
    previous: Dict[str, Dict] = load_tracking(tracking_path)
    print(f"  Loaded {len(previous)} previously tracked repos.")

    # ── Step 2: Fetch repos from GitHub ───────────────────────────────────────
    fetched: Dict[str, Dict] = {}
    for query in SEARCH_QUERIES:
        print(f"  Searching: {query}")
        for item in search_repos(query, per_page=RESULTS_PER_QUERY):
            fetched[item["full_name"]] = item
        time.sleep(API_DELAY)
    print(f"  Fetched {len(fetched)} unique repos.")

    # ── Step 3: Categorise repos ──────────────────────────────────────────────
    major_updates: List[Tuple[str, Dict]] = []
    minor_updates: List[Tuple[str, Dict]] = []
    new_repo_list: List[Dict] = []

    for name, repo in fetched.items():
        new_stars = repo["stargazers_count"]
        if name in previous:
            old_stars = int(previous[name]["stars"])
            entry: Dict = {
                "old_stars": old_stars,
                "new_stars": new_stars,
                "url": repo["html_url"],
                "description": repo.get("description") or "",
            }
            if is_major_update(old_stars, new_stars):
                major_updates.append((name, entry))
            else:
                minor_updates.append((name, entry))
        else:
            new_repo_list.append(repo)

    # Sort lists for nicer output
    major_updates.sort(
        key=lambda x: x[1]["new_stars"] - x[1]["old_stars"], reverse=True
    )
    minor_updates.sort(key=lambda x: x[1]["new_stars"], reverse=True)
    new_repo_list.sort(key=lambda x: x["stargazers_count"], reverse=True)
    new_repo_list = new_repo_list[:MAX_NEW_REPOS]

    print(
        f"  Categorised → major updates: {len(major_updates)}, "
        f"minor: {len(minor_updates)}, new: {len(new_repo_list)}"
    )

    # ── Step 4: Enrich new repos (README + optional AI analysis) ──────────────
    for i, repo in enumerate(new_repo_list):
        owner, repo_name = repo["full_name"].split("/", 1)
        print(f"  Enriching new repo [{i + 1}/{len(new_repo_list)}]: {repo['full_name']}")
        readme = get_readme(owner, repo_name)
        time.sleep(API_DELAY)

        if readme:
            if i < MAX_DEEP_ANALYSIS:
                analysis = analyze_repo(
                    readme,
                    "请分析此 GitHub 项目：1. 这是什么项目？2. 用了哪些技术/方法？3. 有何价值/意义？",
                )
                if analysis:
                    repo["analysis"] = analysis
                else:
                    repo["readme_summary"] = summarize_readme(readme)
            else:
                repo["readme_summary"] = summarize_readme(readme)

    # ── Step 5: Enrich major updates (README + optional AI analysis) ──────────
    for name, entry in major_updates[:5]:
        owner, repo_name = name.split("/", 1)
        print(f"  Enriching major update: {name}")
        readme = get_readme(owner, repo_name)
        time.sleep(API_DELAY)
        if readme:
            growth = entry["new_stars"] - entry["old_stars"]
            analysis = analyze_repo(
                readme,
                (
                    f"该项目近期 stars 激增（+{growth:,}）。"
                    "请简要说明项目的主要功能与价值，以及此次增长可能的原因。"
                ),
            )
            if analysis:
                entry["analysis"] = analysis

    # ── Step 6: Write report ──────────────────────────────────────────────────
    report_content = build_report(date_str, major_updates, minor_updates, new_repo_list)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"  Report written → {report_path}")

    # ── Step 7: Update tracking CSV ───────────────────────────────────────────
    new_tracking: Dict[str, Dict] = {}

    # Keep existing entries, refreshing star count and last_updated
    for name, old in previous.items():
        if name in fetched:
            repo = fetched[name]
            new_tracking[name] = {
                "full_name": name,
                "stars": repo["stargazers_count"],
                "last_updated": repo.get("updated_at", ""),
                "tracked_since": old.get("tracked_since", date_str),
                "description": (repo.get("description") or "")[:200],
                "url": repo["html_url"],
                "last_release": old.get("last_release", ""),
            }
        else:
            # Repo fell out of search results; keep old data as-is
            new_tracking[name] = old

    # Add newly discovered repos
    for repo in fetched.values():
        name = repo["full_name"]
        if name not in new_tracking:
            new_tracking[name] = {
                "full_name": name,
                "stars": repo["stargazers_count"],
                "last_updated": repo.get("updated_at", ""),
                "tracked_since": date_str,
                "description": (repo.get("description") or "")[:200],
                "url": repo["html_url"],
                "last_release": "",
            }

    save_tracking(tracking_path, new_tracking)
    print(f"  Tracking CSV updated → {tracking_path} ({len(new_tracking)} repos)")
    print("Done ✓")


if __name__ == "__main__":
    main()
