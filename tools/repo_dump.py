#!/usr/bin/env python3
"""Dump GitHub issues, pull requests, releases and referenced attachments.

Uses only Python's standard library. Authentication is read from GITHUB_TOKEN.
Output is deterministic JSON/Markdown plus downloaded media under dump/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

API = "https://api.github.com"
URL_RE = re.compile(r"https://(?:github\.com/user-attachments/(?:assets|files)/[^\s)\]>\"']+|user-images\.githubusercontent\.com/[^\s)\]>\"']+|objects\.githubusercontent\.com/[^\s)\]>\"']+)")


def request_json(url: str, token: str):
    req = Request(url, headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "repo-dump-tool"})
    with urlopen(req, timeout=60) as r:
        return json.load(r), r.headers


def paginate(url: str, token: str):
    out = []
    while url:
        page, headers = request_json(url, token)
        out.extend(page)
        link = headers.get("Link", "")
        nxt = None
        for part in link.split(","):
            if 'rel="next"' in part:
                nxt = part[part.find("<") + 1:part.find(">")]
        url = nxt
    return out


def safe_name(url: str) -> str:
    p = urlparse(url)
    base = Path(p.path).name or "attachment"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:120]
    return hashlib.sha256(url.encode()).hexdigest()[:12] + "_" + base


def collect_urls(value, found: set[str]):
    if isinstance(value, str):
        found.update(URL_RE.findall(value))
    elif isinstance(value, dict):
        for v in value.values(): collect_urls(v, found)
    elif isinstance(value, list):
        for v in value: collect_urls(v, found)


def download(url: str, dest: Path, token: str):
    headers = {"User-Agent": "repo-dump-tool"}
    if url.startswith("https://github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=120) as r:
        dest.write_bytes(r.read())


def md_item(item: dict, comments: list[dict], kind: str) -> str:
    lines = [f"# {kind} #{item.get('number', '')}: {item.get('title', '')}", "", item.get("body") or "", "", "## Comments", ""]
    for c in comments:
        who = (c.get("user") or {}).get("login", "unknown")
        lines += [f"### {who} — {c.get('created_at', '')}", "", c.get("body") or "", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Archive GitHub issues, PRs, releases and attachments into a repository directory")
    ap.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"), help="owner/repo")
    ap.add_argument("--output", default="dump/latest")
    args = ap.parse_args()
    token = os.getenv("GITHUB_TOKEN", "")
    if not args.repo or not token:
        sys.exit("--repo/GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    root = Path(args.output)
    for d in ("issues", "pulls", "releases", "media", "raw"):
        (root / d).mkdir(parents=True, exist_ok=True)
    base = f"{API}/repos/{args.repo}"
    issues_all = paginate(f"{base}/issues?state=all&per_page=100", token)
    issues = [x for x in issues_all if "pull_request" not in x]
    pulls = paginate(f"{base}/pulls?state=all&per_page=100", token)
    releases = paginate(f"{base}/releases?per_page=100", token)
    media: set[str] = set()
    manifest = {"repository": args.repo, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "issues": len(issues), "pulls": len(pulls), "releases": len(releases), "attachments": []}

    for item in issues:
        comments = paginate(item["comments_url"] + "?per_page=100", token)
        record = {"issue": item, "comments": comments}
        collect_urls(record, media)
        n = item["number"]
        (root / "raw" / f"issue-{n}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        (root / "issues" / f"{n}.md").write_text(md_item(item, comments, "Issue"), encoding="utf-8")

    for pr in pulls:
        n = pr["number"]
        issue_comments = paginate(f"{base}/issues/{n}/comments?per_page=100", token)
        reviews = paginate(f"{base}/pulls/{n}/reviews?per_page=100", token)
        review_comments = paginate(f"{base}/pulls/{n}/comments?per_page=100", token)
        record = {"pull": pr, "comments": issue_comments, "reviews": reviews, "review_comments": review_comments}
        collect_urls(record, media)
        (root / "raw" / f"pull-{n}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        (root / "pulls" / f"{n}.md").write_text(md_item(pr, issue_comments + review_comments, "Pull Request"), encoding="utf-8")

    for rel in releases:
        tag = re.sub(r"[^A-Za-z0-9._-]", "_", rel.get("tag_name") or str(rel.get("id")))
        collect_urls(rel, media)
        (root / "releases" / f"{tag}.json").write_text(json.dumps(rel, indent=2, ensure_ascii=False), encoding="utf-8")
        for asset in rel.get("assets", []):
            media.add(asset.get("browser_download_url", ""))

    for url in sorted(media):
        if not url: continue
        name = safe_name(url)
        try:
            download(url, root / "media" / name, token)
            manifest["attachments"].append({"url": url, "file": f"media/{name}", "status": "ok"})
        except Exception as exc:
            manifest["attachments"].append({"url": url, "file": None, "status": f"error: {exc}"})

    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("repository", "issues", "pulls", "releases")}, indent=2))

if __name__ == "__main__":
    main()
