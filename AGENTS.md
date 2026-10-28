# Instructions for coding agents

Read [README.md](README.md) first. Use [docs/tk2_evidence.md](docs/tk2_evidence.md) for TK2 status, [docs/collection_pipeline.md](docs/collection_pipeline.md) for the collector, and [docs/preprocessing_protocol.md](docs/preprocessing_protocol.md) for the current preprocessing. Dated notes are under `docs/history/`; `keywords.txt` is the authoritative query list.

## Project scope and current status

- Platform: Threads only. Topic: MBG/BGN 2027 budget. Publication window: 3–30 September 2026 WIB.
- Frozen collection export: 9,368 unique units in private `data/raw/threads_units_2026-09_v1.csv` (17 columns) and `data/raw/threads_team_export_2026-09_v1.csv` (six columns).
- Active preprocessing is the single script `python preprocess.py`, following the team's simplified 27 October specification. It preserves all rows in a private full Parquet and writes a main CSV, a label sample, and two small audit reports. The old rebuild and v2 handoff are historical only.
- The repo owner's `account_a` laptop is the collection source. The older two-machine plan and 1,218-row desktop snapshot are obsolete.
- Deadline for TK2: 28 October 2026, 23:59 WIB. Preserve the `python scraper.py ...` resume command and collection behavior.

## Hard rules

- Never request, store, or type passwords. The human logs in manually in Chrome.
- Never bypass login walls, CAPTCHA, challenges, or rate limits. Keep delays and stop checks. Exit code 2 means stop and wait hours before a deliberate resume; do not retry in a loop.
- Never commit `profiles/`, `config_local.py`, `output/`, `state/`, `logs/`, `recon/`, `runs/`, or `data/`. Check `git status` before every commit. Do not add text-bearing dataset snapshots to Git.
- Do not push without the human's explicit OK. Do not force-push or rewrite shared branch history by default.
- Do not put raw usernames in structured author fields. `author_hash` is a salted pseudonym, not guaranteed anonymity; raw post text may contain usernames and must remain private.
- Do not edit, move, or commit `TK1_beno.pdf` if present. Preserve collection `text` unchanged; `text_raw` must equal `text`.
- Rule-based relevance, campaign, and bot flags are provisional. Never present them as human ground truth; retain full data for sensitivity analysis.

## Code boundaries

- Root `scraper.py` is a compatibility entry point. `collection/` contains the browser collector, parser, and settings; dated reconnaissance notes are under `docs/history/`.
- `scripts/audit_collection.py`: read-only CSV validation and aggregate report.
- `preprocess.py`: eight straightforward functions with constants at the top; `resources/` contains only slang and stopword lists plus the stopword license.
- `docs/`: maintained methods and data documentation. Keep dated handoffs and reconnaissance distinct from current status.

The collector's default profile in `collection/config.py` is `account_a`. For the ongoing Account A run, pass `--profile account_a --keywords keywords.txt --resume` explicitly and verify the salt fingerprint.
