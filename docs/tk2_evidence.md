# TK2 evidence map and remaining work

The assignment's report uses the provided template and is submitted as **PDF** by **28 October 2026, 23:59 WIB**. It asks for a public code repository, a collection-pipeline diagram, technical justification, quality/ethics discussion, and a reproducible working implementation. This file maps existing evidence to the report; it is **not** the report itself. Do not modify the provided template or the original TK1 PDF.

| TK2 section | Evidence available now | Still needed before final wording |
|---|---|---|
| A1–A6 Introduction | TK1 RQs about sentiment, themes, and their relationship; [scope](research_scope.md) | Remove Reddit and any cross-platform contribution claim consistently. |
| B Literature | TK1 literature review | Retain only claims that support the revised Threads-only study; check reference formatting. |
| C1 Data requirements | [scope](research_scope.md), [dictionary](data_dictionary.md), 12 queries, WIB window | State expected volume as a target or observed 9,368-unit snapshot, not a completeness guarantee; map each RQ to fields. |
| C2 Pipeline | [diagram and flow](collection_pipeline.md) | Insert a legible diagram in the template; distinguish collection export from later relevance screening. |
| C3 Method | Root `scraper.py`, `collection/`, [collection protocol](collection_pipeline.md), [dated reconnaissance](history/threads_recon_2026-10-26.md) | Briefly justify Selenium/network capture, login, pagination, delays, stop/resume, deduplication, formats, and link the public code repo. |
| C4 Real implementation | [collection audit](../metadata/collection_snapshot_2026-10-27.json), six-column export, current preprocessing [protocol](preprocessing_protocol.md) | Add actual production run/checkpoint/log evidence if available; never say all 20 searches finished without it. Separate collection results from downstream preprocessing. |
| C5 Quality and limitations | [quality findings](data_quality.md), private `reports/funnel.csv` and `reports/relevance_check.csv`, [historical comparison](history/preprocessing_v2_summary.md) | Use current flag/subset counts, explain reply context, text repetition, search/reply bias, and effect on each RQ. Label old v2 figures as historical. |
| C6 Ethics | [ethics and limitations](ethics_and_limitations.md) | Record the team's artifact access/publication decision; explain public content, pseudonyms, and controlled raw-data sharing. |
| C7 Closing | The collection-to-analysis chain | Summarize what the dataset permits and what requires validation; avoid sentiment/topic conclusions not yet computed. |

## Priority order

1. Obtain the actual production checkpoint and final log, or explicitly report that job completion is unverified.
2. The current tree no longer includes text-bearing handoff CSVs or the duplicate tracked team export. Review historical publication with the team; Git history may retain the old files.
3. Complete the TK2 report from the current evidence and verify its PDF, diagram, repository link, and references.
4. Use the current [single-file preprocessing pipeline](preprocessing_protocol.md), its local `reports/funnel.csv`, and the `unittest` checks. The original v2 code remains absent, so do not describe the current run as an exact v2 reproduction.
5. Run two-person annotation and adjudication before freezing a research corpus or making sentiment/topic claims.
