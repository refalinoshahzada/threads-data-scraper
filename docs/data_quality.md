# Data quality: collection and relevance snapshot

## Evidence levels

The figures below describe the supplied **27 October 2026 snapshot**, not all Threads content. The offline [collection audit](../metadata/collection_snapshot_2026-10-27.json) was generated from the private frozen 17- and six-column CSVs. It checks structural and internal consistency. The [historical v2 summary](history/preprocessing_v2_summary.md) records a separate provisional screening. Neither establishes final collection completeness or relevance precision.

| Collection check | Result |
|---|---:|
| Rows / distinct `unit_id` | 9,368 / 9,368 |
| Posts / replies / self-threads | 2,196 / 6,835 / 337 |
| First discovered in Recent / Top / reply crawl | 5,232 / 73 / 4,063 |
| Empty source `text` | 81 |
| Reply or self-thread without `root_id` | 1,787 |
| Rows outside 3–30 September WIB | 0 |
| Mismatches with six-column projection | 0 |

All 28 publication dates in the window have at least one row. **2,253 rows (24%) are dated 30 September**; this concentration may reflect discussion volume, query behavior, or collection coverage and must not be interpreted without further evidence. The structural audit reports zero issues under its explicit checks; that is not a claim of semantic relevance, platform completeness, or text accuracy.

## Screening and context quality

The current simplified preprocessing retains **all 9,368 units**, flags 81 missing source texts, 153 same-author duplicate texts, 1,355 units with campaign hashtags, and 818 units from the account flagged for manual verification; **6,962 units** meet the provisional main-subset rules and 5,933 can fit the topic model. The exact-text cross-author duplicate flag marks 394 units. These flags are not independent human judgments. The earlier v2 counts (1,227 provisional candidates, 8,039 review, 102 exclusions) are historical and use different rules; do not compare them as accuracy measures.

Among 7,172 replies/self-threads, 2,831 have a parent ID whose text record is absent; 1,787 lack a root ID; and 1,236 have a root ID whose text record is absent. These categories overlap. A missing parent/root may result from bounded collection or the platform response shape; it is not automatically an extraction bug. The current context rule can still classify many replies through their own words or a collected root. Fifteen source units contain the replacement character `�`.

## Quality gate for future versions

1. **Record:** ID and platform valid; timestamp parseable and inside WIB window; engagement counts nonnegative if present; empty text flagged rather than silently removed.
2. **Dataset:** ID unique; six-column projection consistent; daily, query, mode, and post/reply distributions reviewed; repeated text grouped separately from duplicate IDs.
3. **Research:** relevance to the 2027 budget adjudicated; short replies assessed with available context; unresolved cases counted; target of sentiment identified. Rule-based decisions are not human ground truth.

The collector uses substring matching for query words, and the reply crawl includes conversation members that may not mention the query. The sample also favors discoverable queries, visible ranked posts, and high-reply roots. Deleted content, hidden nested replies, and unknown completion status can reduce coverage. Report these limits in TK2 C5 rather than implying a census or population representativeness.
