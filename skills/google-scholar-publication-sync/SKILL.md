---
name: google-scholar-publication-sync
description: Fetch recent Google Scholar profile publications, compare them with a local static/Jekyll personal website publications page, identify missing papers, and update publication/news HTML with manually supplied metadata such as display publication dates. Use when Codex needs to sync Shuting He/Sigma Lab-style personal website publication records from Google Scholar or audit new Scholar papers against local `publications/index.html`.
---

# Google Scholar Publication Sync

## Workflow

1. Inspect the target repo first.
   - Prefer semantic search for unknown publication storage.
   - Confirm whether the site uses source data (`_bibliography`, `_news`) or generated static HTML.
   - Do not assume generated files can be regenerated unless the repo contains the source config.

2. Run the helper in dry-run mode.

```bash
python skills/google-scholar-publication-sync/scripts/sync_scholar_publications.py --repo <repo-root> --limit 10 --top-new-count 3
```

3. Review the missing papers.
   - Check titles after normalization, not raw string equality.
   - Fetch detail pages for full author names and Scholar publication dates.
   - Capture PDF links when an arXiv PDF is available.
   - Treat `publication_date` as a review field. If the user provides manual display dates, prefer the user dates for the website.
   - If an item has no arXiv PDF, leave its link empty unless the user explicitly provides a direct PDF URL.

4. Apply only after the missing set is correct.

```bash
python skills/google-scholar-publication-sync/scripts/sync_scholar_publications.py --repo <repo-root> --top-new-count 3 --manual-dates "Jun 12, 2026;May 30, 2026;May 30, 2026" --manual-pdf-urls "https://arxiv.org/pdf/2508.09977.pdf;;https://arxiv.org/pdf/2605.19692.pdf" --update-news --apply
```

5. Validate.
   - Re-run dry-run; the just-added titles should no longer appear in `missing_top_new`.
   - Check `git diff -- publications/index.html index.html`.
   - If the repo supports a build command, run it. For static-only repos without source config, run HTML/title checks instead.

## Rules

- Keep updates idempotent: never insert a paper whose normalized title already exists locally.
- Use the local page's existing badge colors and journal URLs when available; TPAMI/PAMI badges use pink (`#e91e63`) in this site.
- Render each known arXiv PDF as a `PDF` button using the existing `btn btn-sm z-depth-0` link style.
- If a venue is unknown, stop and ask for venue metadata instead of guessing.
- If an arXiv PDF URL cannot be verified or inferred, leave the link empty and report the missing PDF instead of inventing one.
- Store exact dates as display notes only when the current publication template has no dedicated date field.
- Google Scholar may block requests or change markup. If fetch fails, use a saved HTML page or manually supplied Scholar rows, then keep the same comparison/update flow.

## Helper

Use `scripts/sync_scholar_publications.py` for fetching Scholar, comparing local titles, rendering entries, and applying updates to Sigma Lab-style static HTML pages.
