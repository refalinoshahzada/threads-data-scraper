# Ethics, access, and study limitations

## Collection practice

The collector uses a human-signed-in account, randomized 3–7 second delays, bounded search/reply crawling, and stop conditions for login challenges and rate limits. It does not enter credentials or bypass access controls. Technical access to public content does not by itself settle whether redistribution is appropriate; review platform terms and the course's research-ethics requirements before wider sharing.

## Data minimization and publication

Structured permalinks use `/t/<code>` without a username. Structured authors are salted SHA-256 pseudonyms, **not anonymous identities**: the same person can be linked across rows, and post text can itself contain mentions, names, or other personal information. Keep `config_local.py`, logged-in profiles, detailed logs, and text-bearing raw/interim/processed data under controlled team access. Public reports should favor aggregate counts, methods, schema, code, and limited justified excerpts.

Earlier Git commits tracked a six-column full-text dataset and a text-bearing preprocessing handoff. The current cleanup removes those files from the working tree, while private copies of collection exports live under ignored `data/raw/`. This does **not** erase older commits or any remote copies. Before another publication, the team should review repository history and decide which artifacts may remain accessible. Do not rewrite shared history without coordinating that decision with the team.

## Limitations to report

- Keyword and substring-based discovery misses expressions outside the 12 team queries and can include false positives. Search ranking, Top ordering, and crawl caps shape the sample.
- The reply crawl prioritizes root posts with more replies; some nested replies and unavailable/deleted posts are not captured. Parent/root context is incomplete for some collected replies.
- The final checkpoint/log is absent here, so the completeness of the production search job list is not verified from this checkout.
- Threads users and people who post publicly about MBG are not representative of Indonesian citizens. No demographic or geographic population inference is supported.
- Repeated identical text may be legitimate reposting, coordinated messaging, or ordinary formulaic replies. Frequency alone is not bot evidence.
- `include` candidates and Codex-read examples are not final human labels. Their counts should not be presented as sentiment or topic prevalence.
