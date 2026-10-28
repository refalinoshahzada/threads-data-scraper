# Historical preprocessing handoff, 27 October 2026

This is an aggregate-only record of the superseded `threads_mbg2027_v2` handoff. Its text-bearing CSV outputs and the original handoff document were removed from the current checkout during repository cleanup. Git history may still contain them. This record is **not** the active preprocessing procedure.

The handoff used a 9,368-unit input whose 17-column CSV SHA-256 was `95c2af37f13bbacbebff1a04c7ac311c6e972e2c5cb67ce64b85e3d882d728df`. It reported 1,227 provisional include candidates, 8,039 unresolved/review, and 102 exclusions (88 empty after cleaning and 14 examples reviewed as out of scope). Among candidates, 1,023 cleaned texts were unique. It also reported 2,831 replies/self-threads whose parent text record was absent, 1,787 without root ID, and 1,236 whose root text record was absent; these categories overlap.

The historical procedure included 142 Codex-reviewed examples, **not** an independent human validation set. The original v2 Python scripts were not in this branch, so exact replay of that handoff was not demonstrated. The team subsequently requested an independent Python pipeline. Its active method, counts, and output checksum are documented in [the preprocessing protocol](../preprocessing_protocol.md). Do not combine v2 and independent-pipeline candidate counts or describe either as final research prevalence.
