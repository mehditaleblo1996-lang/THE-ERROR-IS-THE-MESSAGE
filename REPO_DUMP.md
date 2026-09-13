# Repository Dump Tool

A dependency-free repository archiver for bounty #60.

## What it preserves

- All open and closed issues, bodies and complete issue comments.
- All open and closed pull requests, conversation comments, reviews and inline review comments.
- Releases, release notes, tags and release assets.
- GitHub user attachments referenced from archived content, downloaded into `dump/latest/media/`.
- Machine-readable raw JSON plus human-readable Markdown.
- A manifest containing counts and attachment download status.

## Mobile / non-technical use

Open **Actions → Repository dump → Run workflow** in the GitHub mobile app or website. Leave `target_repo` empty to archive this repository, or provide another `owner/repo` accessible to the workflow token.

The workflow runs the exporter and commits `dump/latest/` back into the repository automatically.

## Local use

```bash
export GITHUB_TOKEN=github_token_with_read_access
python tools/repo_dump.py --repo owner/repository --output dump/latest
```

No third-party Python packages are required.

## Design notes

The exporter follows GitHub pagination, so it is not limited to the first 30/100 records. Pull request review threads are captured separately from ordinary PR conversation comments. Attachment failures do not abort the archive; they are recorded in `manifest.json`, making incomplete media preservation visible rather than silently losing files.
