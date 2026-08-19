# DisputeArbiter

A reusable GenLayer Intelligent Contract that lets any two parties stake real value
against a factual dispute, each submit their own position and evidence URL, and get a
consensus-judged, appeal-gated resolution — never a claim judged from one side's
evidence alone, never a verdict that moves value before the losing side has had a real,
bonded chance to contest it. Any app that needs "which of these two parties is right,
with real stakes on the line" decided fairly imports this instead of writing its own
staked-arbitration-with-appeal logic.

## The problem with the naive version

The obvious failure mode is trusting either party's own account: a plaintiff's claim
and a defendant's rebuttal are exactly as self-serving as any unilateral evidence
submission. The usual fixes either fall to a centralized arbitrator (slow, unaccountable,
a single point of bribery, and worse, a single point of *finality* - a bad initial call
has no recourse) or a single LLM call over whatever a backend fetched (unrepeatable, and
the fetch itself is invisible to either party). Even a naive on-chain "consensus decides,
done" design has a real gap: any single judged round can be wrong, and moving real
staked value the instant that round returns leaves the losing party with no path to
contest an actual mistake before it becomes irreversible.

## Why this needs validator consensus, not a backend

Delete GenLayer and staked two-party arbitration either trusts a centralized arbitrator
(unaccountable, slow, and a genuine bribery/conflict-of-interest surface given real
money is on the line) or a backend service that fetches and judges invisibly (no way
for either party to verify the fetch was fair, let alone the judgment). Run the
counterfactual against each alternative:

- **A centralized arbitrator** — unaccountable, and a real target for bribery once
  stakes are large enough to matter.
- **A backend fetch-and-judge service** — the fetch itself is invisible to both
  parties; nothing stops it from quietly favoring one side's URL.
- **Trusting either party's own account with no external evidence** — exactly the
  self-serving-claim problem this primitive exists to avoid.
- **A single, immediately-final consensus round with no appeal** — closer, but still
  leaves a genuine model mistake with no recourse once real value has moved.

GenLayer's validator set independently fetches both parties' evidence and independently
judges which position it supports, reconciling under an equivalence principle - and
because the verdict is provisional until an appeal window closes (or a bonded appeal
spends one more round), a real mistake has one genuine, financially-serious chance to be
caught before any value moves.

## Why it isn't the patterns that don't belong in this category

- **Not an AI app with a blockchain attached.** The output is a state transition and a
  real fund transfer — a dispute reaches `PROVISIONAL`/`REFUNDED`/`FINAL` and value
  moves to a named address — never advice a human reads and acts on manually.
- **Not a format-only validator.** The equivalence principle compares the *verdict*
  itself (`PLAINTIFF`/`DEFENDANT`/`INCONCLUSIVE`), never whether the model's JSON merely
  parses.
- **Not judging party-submitted evidence content.** `resolve_dispute`/`resolve_appeal`
  take no evidence text as an argument at all — both pages are fetched contract-side,
  live, on every judged call. A party controls only which URL and position gets argued,
  never what the contract sees there.
- **Structurally distinct from every other submission this cycle.** ParametricPool pays
  out on a single-source pooled claim with no adversary and no appeal. HandleGuard never
  fetches anything. VisualClaim judges one screenshot. SourceConsensus reconciles a
  cooperative set of sources toward one shared answer. DisputeArbiter is the first
  primitive here with two named, adversarial, *equally staked* parties, a verdict that
  is provisional rather than immediately final, and a bonded appeal round that can
  overturn it — a genuinely different mechanism, not a relabeled copy of any of them.

## The non-deterministic core, and why the deterministic half is just as load-bearing

Exactly **one** non-deterministic operation per judged call, bundled into a single
`gl.eq_principle.prompt_comparative` block: a leader function that fetches both parties'
evidence URLs and asks `gl.nondet.exec_prompt` which position the combined evidence
supports. The model is never asked "who should be paid" or "how much" - only "which
position does the evidence support" - and the deterministic half is where the actual
consequences live: the default-on-timeout forfeit, the refund-on-INCONCLUSIVE rule, the
provisional-then-appeal-gated finality, and every fund transfer. Full rationale in
`DESIGN.md`.

## Safety properties

| Property | Enforced by | Verified by |
|---|---|---|
| A dispute's parties, positions, evidence, stake, and bond can never be edited after they're set | no setter exists at all | `test_create_dispute_succeeds_and_stores_declared_fields` and the absence of any editing method |
| A verdict never moves funds before both fetches succeed and the model output parses | `FETCH_ERROR`/unparseable output route to `ERRORED`/`APPEAL_ERRORED`, never a paid verdict | `test_resolve_dispute_on_fetch_failure_sets_errored_and_moves_no_funds`, `test_resolve_dispute_on_unparseable_output_errors_not_a_verdict` |
| A `PROVISIONAL` verdict moves no funds until the appeal window closes or an appeal resolves | `resolve_dispute` only sets state/`provisional_winner`; only `finalize_dispute`/`resolve_appeal` ever call `emit_transfer` | `test_resolve_dispute_plaintiff_verdict_is_provisional_not_paid_yet` |
| Only the losing party may appeal, only within the window, only by posting the exact bond | `appeal_dispute` checks caller against the losing side, the deadline, and the exact value sent | `test_appeal_dispute_rejects_the_winning_party`, `test_appeal_dispute_rejects_after_appeal_window_passed`, `test_appeal_dispute_rejects_wrong_bond_value` |
| A frivolous appeal (reconfirmed or INCONCLUSIVE) forfeits the appellant's bond to the original winner | `resolve_appeal`'s `overturned` branch | `test_resolve_appeal_reconfirmed_verdict_forfeits_appellants_bond_to_original_winner`, `test_resolve_appeal_inconclusive_does_not_overturn_provisional_winner` |
| A successful appeal pays the appellant both stakes and refunds their own bond, never a penalty on a winning challenge | same `overturned` branch | `test_resolve_appeal_overturned_verdict_pays_the_appellant_including_their_own_bond_back` |
| An `INCONCLUSIVE` first-round verdict refunds exactly what both parties put in - no winner, no loser | `resolve_dispute`'s inconclusive branch | `test_resolve_dispute_inconclusive_verdict_refunds_both_sides`, `test_full_lifecycle_conserves_total_value_with_no_appeal` |
| A defendant who never accepts costs them nothing beyond the plaintiff reclaiming only their own stake | `default_dispute` refunds the plaintiff their own stake, never more | `test_default_dispute_is_permissionless_and_refunds_only_the_plaintiff` |
| Anyone can push a stuck `ERRORED`/`APPEAL_ERRORED` dispute forward, not just a party to it | no caller restriction on `resolve_dispute`/`resolve_appeal`/`default_dispute`/`finalize_dispute` | `test_resolve_dispute_after_errored_can_be_retried_permissionlessly`, `test_resolve_appeal_after_appeal_errored_can_be_retried` |

## Why it's reusable

The consumer integration is genuinely small — this is the whole thing, from
`examples/dispute_gated_release.py`:

```python
@gl.contract_interface
class IDisputeArbiter:
    class View:
        def get_dispute(self, dispute_id: u256) -> dict: ...
    class Write:
        pass

dispute = IDisputeArbiter(self.dispute_arbiter_address).view().get_dispute(dispute_id)
if dispute["state"] == "FINAL":
    winner = dispute["plaintiff"] if dispute["final_winner"] == "PLAINTIFF" else dispute["defendant"]
    ...  # release whatever this contract controls to winner
```

Any escrow, access-grant, or reputation contract that needs to act on "which party won
a staked, appeal-gated dispute" can gate on that instead of writing its own
adversarial-evidence-and-appeal machinery.

## Testing

- **Direct-mode** (`tests/direct/`, `pytest tests/direct/`): 45 tests, no network, no
  live consensus — fast feedback on every deterministic branch (creation validation,
  cancel/accept/default timing), every failure/abstention path on both judged rounds,
  fund-conservation across the full lifecycle, and the worked consumer example, using
  gltest's built-in `mock_web`/`mock_llm` plus a real-balance-moving `EthSend` hook.
- **Integration** (`tests/integration/`): requires `DISPUTEARBITER_ADDRESS` set to a
  real StudioNet deployment; drives a full staked dispute lifecycle against real,
  opposed evidence pages.

## Deployment

- Deployed StudioNet address: _pending manual deployment_
- Studio import: open [studio.genlayer.com](https://studio.genlayer.com) → "Import
  contract" → paste the deployed address once available.
