# Research scope and data requirements

## Decision in force

The study examines public Threads posts and replies published from **3 September 2026 00:00 WIB** through **30 September 2026 23:59:59 WIB** about the **allocation of the 2027 Makan Bergizi Gratis (MBG) / Badan Gizi Nasional (BGN) budget**. The original TK1 mentioned Reddit; the team subsequently chose Threads only. Do not claim cross-platform coverage.

## Research questions and required fields

| Question | Evidence needed | Collection fields | Downstream step |
|---|---|---|---|
| RQ1: distribution of positive, negative, and neutral sentiment toward the 2027 MBG budget | Relevant unit text and a defensible sentiment label about the *budget target* | `unit_id`, `text`, `created_at_utc`, `unit_type`, parent/root context | Relevance adjudication, sentiment annotation/evaluation, IndoBERT |
| RQ2: dominant discussion themes | Relevant text plus interpretable topic assignments | Same text and IDs; `matched_keywords` helps audit sampling | BERTopic and human topic interpretation |
| RQ3: relationship between themes and sentiment | Both outputs for the same eligible unit | Stable `content_id = threads:<unit_id>` | Join by ID, report shared denominator |

The collector also retains `search_mode`, query matches, engagement counts, `scraped_at_utc`, and pseudonymous author hashes for quality and provenance checks. These are not demographic or geographic measures. No reliable user location is collected, so there is no defensible geographic restriction beyond the Indonesian-language policy context.

## Unit and inclusion policy

One Threads post or reply is one unit, identified by Threads `pk`. Self-thread continuations are `self_thread` in the 17-column export and `reply` in the six-column team export. A post may be found in more than one search but remains one unit after ID deduplication. Equal text from different IDs remains multiple units and is separately grouped for sensitivity analysis.

Collection includes public text units in the WIB window discovered by the 12 queries or the bounded reply crawl. Search inclusion is **not** final research relevance. The current preprocessing uses a broad lexical MBG/BGN filter, with inherited root context for replies; `lex_budget` is retained as a flag rather than a mandatory condition. This is a provisional screen. Human review must decide whether a unit concerns the **2027 budget allocation**, including amount, source, efficiency, transparency, financing priority, or a clear contextual reply. General implementation discussion and unrelated budgets should not be counted as final research evidence without adjudication; unavailable context must be reported, not silently treated as irrelevant.

## Interpretation boundary

The dataset is a keyword- and interface-dependent Threads sample, not all Threads discourse and not a representative sample of Indonesian public opinion. The 2027 budget target must be identified before sentiment is assigned. See [quality findings](data_quality.md), [preprocessing protocol](preprocessing_protocol.md), and the team's TK1 proposal for the original RQs.
