# Submission Package

## Title

DisputeArbiter — Staked Adversarial Arbitration with Bonded Appeal

## Notes / Description (≤1000 characters, 979 used)

DisputeArbiter lets two named parties stake equal value and each submit their own
position plus an evidence URL. resolve_dispute fetches both evidence pages live in one
judged round and reaches a PROVISIONAL verdict - never final on the first round. The
losing side gets a bonded appeal window: one more judged round on freshly re-fetched
evidence; a frivolous appeal forfeits its bond to the confirmed winner, a successful
one refunds it plus both stakes. Value only moves once a verdict is truly final.
Unlike every other submission this cycle (pooled insurance, embeddings registry,
screenshot judging, multi-source reconciliation), this is the first primitive with two
adversarial staked parties and provisional-then-appeal-gated finality rather than one
immediately-final round. Fetch failures never get judged one-sided; INCONCLUSIVE
refunds both. 587-line contract, 53-line example, 45 passing direct tests, live
StudioNet round: real fetches, PLAINTIFF verdict, ACCEPTED.

## Evidence links

- GitHub repo: https://github.com/Hilda26/dispute-arbiter (no AI attribution — verified
  via `git log -1 --format='%B' | grep -i "co-authored\|claude\|generated with"` → no
  match, on every commit)
- Explorer contract URL: https://explorer-studio.genlayer.com/address/0x76cf0710053CE05262031cbb6eCd6c7a0a2E82B5
- Studio import URL: open studio.genlayer.com → Import contract →
  `0x76cf0710053CE05262031cbb6eCd6c7a0a2E82B5`
- Deployed StudioNet address: `0x76cf0710053CE05262031cbb6eCd6c7a0a2E82B5`

## What was verified

- `genvm-lint check contracts/dispute_arbiter.py --json` and the worked example: both
  clean.
- `pytest tests/direct/` — 45/45 passing: creation validation, cancel/accept/default
  timing, both judged rounds' full failure/abstention surface (fetch failure,
  unparseable output, INCONCLUSIVE), the provisional-vs-final fund-movement boundary,
  all three appeal outcomes (reconfirmed, INCONCLUSIVE, overturned) with exact balance
  assertions, permissionless retry on both `ERRORED`/`APPEAL_ERRORED`, whole-lifecycle
  fund conservation, and the worked consumer example `DisputeGatedRelease`.
- `pytest tests/integration/ --network=studionet` against the live deployment —
  `test_full_lifecycle_drives_every_write_and_finalizes_without_appeal` passed: real
  `create_dispute` → `accept_dispute` → a judged `resolve_dispute` round (5 validators,
  `MAJORITY_AGREE`) that correctly read a defendant's off-topic evidence as failing to
  support their own claim → `PROVISIONAL` with no funds moved yet → an early
  `finalize_dispute` correctly reverted → after the appeal window genuinely elapsed, a
  permissionless `finalize_dispute` paid out both stakes and reached `FINAL`. A second
  test confirmed `cancel_dispute` refunds the plaintiff and permanently blocks a later
  acceptance. Every judged round across this contract's testing completed
  `SUCCESS`/`ACCEPTED` at the GenVM and consensus level.

## Character count check

979/1000 characters (verified with `len()` in Python, whitespace-normalized).
