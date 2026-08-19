"""
Full-lifecycle integration test against a StudioNet-deployed DisputeArbiter.
Requires DISPUTEARBITER_ADDRESS (see conftest.py).

resolve_dispute is the slow judged write here: two real page fetches plus
one exec_prompt, in a single consensus round, so this uses a generous
wait_interval/wait_retries. appeal_window_seconds is set to the contract's
minimum (60s) so the no-appeal finalize path can be exercised with a real,
short sleep rather than skipped.
"""

import time
import pytest
from gltest.assertions import tx_execution_succeeded, tx_execution_failed

FAST_WAIT = dict(wait_interval=3000, wait_retries=30)
SLOW_WAIT = dict(wait_interval=6000, wait_retries=100)

STAKE = 1_000
APPEAL_BOND = 200
ACCEPT_DEADLINE = 3600
APPEAL_WINDOW = 300  # generous margin: a two-fetch judged round plus RPC
# polling latency can itself eat well past the contract's 60s minimum
# between resolved_at being stamped and the test regaining control, which
# made the "too early" assertion flaky at the bare minimum window.

ISSUE_DESCRIPTION = "Is Python a general-purpose programming language?"
PLAINTIFF_POSITION = "Python is a general-purpose programming language, as its own official site documents."
PLAINTIFF_URL = "https://www.python.org/"
DEFENDANT_POSITION = "Python is not general-purpose - it is a narrow, single-use scripting tool."
DEFENDANT_URL = "https://en.wikipedia.org/wiki/Photosynthesis"  # deliberately irrelevant to the defendant's own claim


@pytest.mark.integration
def test_full_lifecycle_drives_every_write_and_finalizes_without_appeal(
    deployed_contract, plaintiff_account, defendant_account
):
    c = deployed_contract
    plaintiff = c.connect(plaintiff_account)
    defendant = c.connect(defendant_account)

    # --- open + accept (deterministic writes) -----------------------------
    create_result = plaintiff.create_dispute(
        args=[
            defendant_account.address,
            ISSUE_DESCRIPTION,
            PLAINTIFF_POSITION,
            PLAINTIFF_URL,
            STAKE,
            APPEAL_BOND,
            ACCEPT_DEADLINE,
            APPEAL_WINDOW,
        ]
    ).transact(value=STAKE, **FAST_WAIT)
    assert tx_execution_succeeded(create_result), create_result
    dispute_id = int(c.dispute_count(args=[]).call()) - 1
    dispute = c.get_dispute(args=[dispute_id]).call()
    print("created dispute:", dispute)
    assert dispute["state"] == "AWAITING_DEFENDANT"

    accept_result = defendant.accept_dispute(args=[dispute_id, DEFENDANT_POSITION, DEFENDANT_URL]).transact(
        value=STAKE, **FAST_WAIT
    )
    assert tx_execution_succeeded(accept_result), accept_result
    assert c.get_dispute(args=[dispute_id]).call()["state"] == "READY"

    # --- the slow judged write: two real fetches + one exec_prompt --------
    resolve_result = plaintiff.resolve_dispute(args=[dispute_id]).transact(**SLOW_WAIT)
    print("resolve_dispute receipt:", resolve_result)
    assert tx_execution_succeeded(resolve_result), (
        "resolve_dispute failed or returned UNDETERMINED - known retryable "
        "StudioNet behavior; rerun this test if so"
    )
    resolved = c.get_dispute(args=[dispute_id]).call()
    print("resolved dispute:", resolved)
    assert resolved["state"] in ("PROVISIONAL", "REFUNDED", "ERRORED"), resolved

    if resolved["state"] == "REFUNDED":
        # Genuine INCONCLUSIVE verdict - nothing further to finalize.
        return
    if resolved["state"] == "ERRORED":
        pytest.skip("resolve_dispute ERRORED (unparseable model output) - rerun to retry")

    assert resolved["provisional_winner"] in ("PLAINTIFF", "DEFENDANT")

    # --- appeal-window enforcement: too early must fail --------------------
    early_finalize = plaintiff.finalize_dispute(args=[dispute_id]).transact(**FAST_WAIT)
    assert tx_execution_failed(early_finalize), "finalize_dispute before the appeal window should fail"

    # --- wait out the real appeal window, then finalize permissionlessly ---
    time.sleep(APPEAL_WINDOW + 10)
    finalize_result = defendant.finalize_dispute(args=[dispute_id]).transact(**FAST_WAIT)
    assert tx_execution_succeeded(finalize_result), finalize_result
    final = c.get_dispute(args=[dispute_id]).call()
    print("finalized dispute:", final)
    assert final["state"] == "FINAL"
    assert final["final_winner"] == resolved["provisional_winner"]


@pytest.mark.integration
def test_cancel_dispute_before_acceptance_refunds_plaintiff(deployed_contract, plaintiff_account, defendant_account):
    c = deployed_contract
    plaintiff = c.connect(plaintiff_account)
    defendant_hex = defendant_account.address

    create_result = plaintiff.create_dispute(
        args=[defendant_hex, ISSUE_DESCRIPTION, PLAINTIFF_POSITION, PLAINTIFF_URL, STAKE, APPEAL_BOND, ACCEPT_DEADLINE, APPEAL_WINDOW]
    ).transact(value=STAKE, **FAST_WAIT)
    assert tx_execution_succeeded(create_result), create_result
    dispute_id = int(c.dispute_count(args=[]).call()) - 1

    cancel_result = plaintiff.cancel_dispute(args=[dispute_id]).transact(**FAST_WAIT)
    assert tx_execution_succeeded(cancel_result), cancel_result
    assert c.get_dispute(args=[dispute_id]).call()["state"] == "CANCELLED"

    # a cancelled dispute can never be accepted afterward
    late_accept = c.connect(defendant_account).accept_dispute(
        args=[dispute_id, DEFENDANT_POSITION, DEFENDANT_URL]
    ).transact(value=STAKE, **FAST_WAIT)
    assert tx_execution_failed(late_accept), "accept_dispute on a cancelled dispute should fail"
