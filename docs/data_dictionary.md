# Dataset dictionary and lineage

## Three collection representations

1. `output/raw_observations.jsonl`: append-only parsed sightings. It may repeat a unit after multiple queries or resumes. It is the earliest **persisted** collection representation in this scraper; it is not a byte-for-byte archive of every GraphQL response.
2. `output/threads_raw.csv` / `.jsonl`: one row per `unit_id`, with 17 fields, unchanged collected text, and merged search evidence. This is the input to downstream preprocessing, despite the word `raw` in its name.
3. `output/threads_dataset.csv`: six-column projection of the same units for the team. It has not been relevance-filtered or linguistically cleaned.

The private frozen copies are `data/raw/threads_units_2026-09_v1.csv` and `data/raw/threads_team_export_2026-09_v1.csv`. Their hashes are recorded in the [collection snapshot](../metadata/collection_snapshot_2026-10-27.json). Do not create another named “final” copy without a version and manifest.

## Seventeen-column unit export

| Column | Meaning and missing-value rule |
|---|---|
| `platform` | Always `threads`. |
| `unit_id` | Threads numeric post ID, stored as a **string**. Primary deduplication key. |
| `unit_type` | `post`, `reply`, or `self_thread`. |
| `parent_id` | Immediate parent where inferred. Empty for root posts; an ID can be present when its text row was not collected. |
| `root_id` | Root post ID if known. Can be empty for search-found nested replies. |
| `text` | Caption text as collected, unchanged. Empty for some media-only or unavailable captions. |
| `created_at_utc` | Publication time in aware ISO 8601 UTC. |
| `created_at_wib` | Same instant in UTC+07:00. Filtering uses WIB boundaries. |
| `like_count`, `reply_count`, `repost_count`, `quote_count` | Counts at collection time. `0` means observed zero; empty would mean unavailable. |
| `permalink` | `https://www.threads.com/t/<code>`; no username in the structured URL. |
| `author_hash` | Salted SHA-256 pseudonym for an author; not an anonymous identity guarantee. Salt is private. |
| `matched_keywords` | Team queries separated by `;;`. May be empty for a unit first found through reply crawl. |
| `search_mode` | **First discovery**: `recent`, `top`, or `reply_crawl`; does not list every later observation. |
| `scraped_at_utc` | Time of the retained first-seen observation, not publication time. |

## Six-column team export

| Column | Derivation |
|---|---|
| `content_id` | `threads:` plus `unit_id`; stable cross-stage join key. |
| `platform` | From raw-unit export. |
| `text` | Unchanged `text`. |
| `created_at` | `created_at_utc`. |
| `content_type` | `post` for `unit_type=post`; `reply` for `reply` and `self_thread`. |
| `permalink` | From raw-unit export. |

The six-column export deliberately loses parent/root, query, mode, and author pseudonym fields. Do not use it as a substitute for the 17-column input when relevance decisions require reply context. The current `preprocess.py` adds `text_raw`, `text_clean`, `text_sent_a`, `text_sent_b`, `text_topic`, and quality flags to the private full Parquet; it never overwrites `text`. The main CSV omits `permalink` and `text_raw`.
