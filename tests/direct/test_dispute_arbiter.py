"""
Direct-mode tests for DisputeArbiter.

Naming convention: each test name states the property being verified, not
the mechanics used to verify it.
"""

from .conftest import warp_to, _addr_bytes

CONTRACT = "contracts/dispute_arbiter.py"

STAKE = 10_000
APPEAL_BOND = 2_000
ACCEPT_DEADLINE = 3600
APPEAL_WINDOW = 3600

ISSUE_DESC = "Did the contractor deliver the agreed work by the stated deadline?"
PLAINTIFF_POSITION = "The contractor never delivered the agreed work."
PLAINTIFF_URL = "https://evidence-plaintiff.example.com/proof"
DEFENDANT_POSITION = "The work was delivered on time, as agreed."
DEFENDANT_URL = "https://evidence-defendant.example.com/proof"

PLAINTIFF_PATTERN = r"evidence-plaintiff\.example\.com"
DEFENDANT_PATTERN = r"evidence-defendant\.example\.com"


def _deploy(direct_deploy, direct_vm, sender):
    direct_vm.sender = sender
    return direct_deploy(CONTRACT)


def _defendant_hex(addr) -> str:
    return "0x" + _addr_bytes(addr).hex()


def _create(contract, direct_vm, plaintiff, defendant, **overrides):
    direct_vm.sender = plaintiff
    direct_vm.value = overrides.get("value", STAKE)
    dispute_id = contract.create_dispute(
        overrides.get("defendant", _defendant_hex(defendant)),
        overrides.get("issue_description", ISSUE_DESC),
        overrides.get("plaintiff_position", PLAINTIFF_POSITION),
        overrides.get("plaintiff_evidence_url", PLAINTIFF_URL),
        overrides.get("stake_amount", STAKE),
        overrides.get("appeal_bond", APPEAL_BOND),
        overrides.get("accept_deadline_seconds", ACCEPT_DEADLINE),
        overrides.get("appeal_window_seconds", APPEAL_WINDOW),
    )
    direct_vm.value = 0
    return dispute_id


def _accept(contract, direct_vm, defendant, dispute_id, **overrides):
    direct_vm.sender = defendant
    direct_vm.value = overrides.get("value", STAKE)
    contract.accept_dispute(
        dispute_id,
        overrides.get("defendant_position", DEFENDANT_POSITION),
        overrides.get("defendant_evidence_url", DEFENDANT_URL),
    )
    direct_vm.value = 0


def _open_ready_dispute(contract, direct_vm, plaintiff, defendant, **overrides):
    dispute_id = _create(contract, direct_vm, plaintiff, defendant, **overrides)
    _accept(contract, direct_vm, defendant, dispute_id, **overrides)
    return dispute_id


def _mock_evidence(direct_vm, plaintiff_body=None, defendant_body=None):
    if plaintiff_body is not None:
        direct_vm.mock_web(PLAINTIFF_PATTERN, {"status": 200, "body": plaintiff_body})
    if defendant_body is not None:
        direct_vm.mock_web(DEFENDANT_PATTERN, {"status": 200, "body": defendant_body})


def _mock_verdict(direct_vm, raw: str) -> None:
    direct_vm.mock_llm(r"arbitrating a two-party dispute", raw)


# ---------------------------------------------------------------------
# Deploy / initial state
# ---------------------------------------------------------------------


def test_fresh_deploy_has_zero_disputes(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    assert int(c.dispute_count()) == 0


# ---------------------------------------------------------------------
# create_dispute - input validation
# ---------------------------------------------------------------------


def test_create_dispute_succeeds_and_stores_declared_fields(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    dispute_id = _create(c, direct_vm, direct_alice, direct_bob)
    d = c.get_dispute(dispute_id)
    assert d["plaintiff"].lower() == _defendant_hex(direct_alice).lower()
    assert d["defendant"].lower() == _defendant_hex(direct_bob).lower()
    assert d["issue_description"] == ISSUE_DESC
    assert d["stake_amount"] == STAKE
    assert d["appeal_bond"] == APPEAL_BOND
    assert d["state"] == "AWAITING_DEFENDANT"
    assert d["appellant"] is None


def test_create_dispute_rejects_plaintiff_as_own_defendant(direct_deploy, direct_vm, direct_alice):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("must be different"):
        _create(c, direct_vm, direct_alice, direct_alice)


def test_create_dispute_rejects_empty_issue_description(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("issue_description must be"):
        _create(c, direct_vm, direct_alice, direct_bob, issue_description="")


def test_create_dispute_rejects_non_https_evidence_url(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("https://"):
        _create(c, direct_vm, direct_alice, direct_bob, plaintiff_evidence_url="http://insecure.example.com")


def test_create_dispute_rejects_zero_stake(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("stake_amount must be positive"):
        _create(c, direct_vm, direct_alice, direct_bob, stake_amount=0, value=0)


def test_create_dispute_rejects_value_not_matching_stake(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("sent value must exactly equal stake_amount"):
        _create(c, direct_vm, direct_alice, direct_bob, value=STAKE - 1)


def test_create_dispute_rejects_out_of_range_accept_deadline(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("accept_deadline_seconds"):
        _create(c, direct_vm, direct_alice, direct_bob, accept_deadline_seconds=0)


def test_create_dispute_rejects_out_of_range_appeal_window(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    with direct_vm.expect_revert("appeal_window_seconds"):
        _create(c, direct_vm, direct_alice, direct_bob, appeal_window_seconds=0)


# ---------------------------------------------------------------------
# cancel_dispute
# ---------------------------------------------------------------------


def test_cancel_dispute_rejects_non_plaintiff(direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _create(c, vm, direct_alice, direct_bob)
    vm.sender = direct_bob
    with vm.expect_revert("only the plaintiff"):
        c.cancel_dispute(dispute_id)


def test_cancel_dispute_refunds_plaintiff_and_moves_real_balance(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob
):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _create(c, vm, direct_alice, direct_bob)
    vm.sender = direct_alice
    c.cancel_dispute(dispute_id)
    assert c.get_dispute(dispute_id)["state"] == "CANCELLED"
    assert vm._balances.get(_addr_bytes(direct_alice), 0) == STAKE


def test_cancel_dispute_rejects_once_defendant_has_accepted(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob
):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    vm.sender = direct_alice
    with vm.expect_revert("not awaiting the defendant"):
        c.cancel_dispute(dispute_id)


# ---------------------------------------------------------------------
# accept_dispute
# ---------------------------------------------------------------------


def test_accept_dispute_rejects_non_defendant_caller(direct_deploy, direct_vm, direct_alice, direct_bob, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    dispute_id = _create(c, direct_vm, direct_alice, direct_bob)
    with direct_vm.expect_revert("only the named defendant"):
        _accept(c, direct_vm, direct_owner, dispute_id)


def test_accept_dispute_rejects_value_not_matching_stake(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    dispute_id = _create(c, direct_vm, direct_alice, direct_bob)
    with direct_vm.expect_revert("sent value must exactly equal stake_amount"):
        _accept(c, direct_vm, direct_bob, dispute_id, value=STAKE - 1)


def test_accept_dispute_succeeds_and_moves_to_ready(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    dispute_id = _open_ready_dispute(c, direct_vm, direct_alice, direct_bob)
    d = c.get_dispute(dispute_id)
    assert d["state"] == "READY"
    assert d["defendant_position"] == DEFENDANT_POSITION
    assert d["defendant_evidence_url"] == DEFENDANT_URL


def test_accept_dispute_rejects_after_deadline_passed(direct_deploy, direct_vm, direct_alice, direct_bob):
    from datetime import datetime, timedelta

    c = _deploy(direct_deploy, direct_vm, direct_alice)
    dispute_id = _create(c, direct_vm, direct_alice, direct_bob, accept_deadline_seconds=60)
    created_at = c.get_dispute(dispute_id)["created_at"]
    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    warp_to(direct_vm, (created_dt + timedelta(seconds=61)).isoformat())
    with direct_vm.expect_revert("deadline has passed"):
        _accept(c, direct_vm, direct_bob, dispute_id)


# ---------------------------------------------------------------------
# default_dispute
# ---------------------------------------------------------------------


def test_default_dispute_rejects_before_deadline(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    dispute_id = _create(c, direct_vm, direct_alice, direct_bob)
    with direct_vm.expect_revert("has not passed yet"):
        c.default_dispute(dispute_id)


def test_default_dispute_is_permissionless_and_refunds_only_the_plaintiff(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob, direct_owner
):
    from datetime import datetime, timedelta

    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _create(c, vm, direct_alice, direct_bob, accept_deadline_seconds=60)
    created_at = c.get_dispute(dispute_id)["created_at"]
    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    warp_to(vm, (created_dt + timedelta(seconds=61)).isoformat())

    vm.sender = direct_owner  # anyone, not the plaintiff, may trigger this
    c.default_dispute(dispute_id)
    d = c.get_dispute(dispute_id)
    assert d["state"] == "DEFAULTED"
    assert d["final_winner"] == "PLAINTIFF"
    assert vm._balances.get(_addr_bytes(direct_alice), 0) == STAKE
    assert vm._balances.get(_addr_bytes(direct_bob), 0) == 0


# ---------------------------------------------------------------------
# resolve_dispute - the first judged round
# ---------------------------------------------------------------------


def test_resolve_dispute_rejects_when_not_ready_or_errored(direct_deploy, direct_vm, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_vm, direct_alice)
    dispute_id = _create(c, direct_vm, direct_alice, direct_bob)
    with direct_vm.expect_revert("not resolvable"):
        c.resolve_dispute(dispute_id)  # still AWAITING_DEFENDANT


def test_resolve_dispute_on_fetch_failure_sets_errored_and_moves_no_funds(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob
):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    # no web mocks at all -> both fetches raise inside leader()
    c.resolve_dispute(dispute_id)
    d = c.get_dispute(dispute_id)
    assert d["state"] == "ERRORED"
    assert vm._balances.get(_addr_bytes(direct_alice), 0) == 0
    assert vm._balances.get(_addr_bytes(direct_bob), 0) == 0


def test_resolve_dispute_on_unparseable_output_errors_not_a_verdict(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob
):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _mock_evidence(vm, "plaintiff evidence text", "defendant evidence text")
    vm.mock_llm(r"arbitrating a two-party dispute", "not json at all, sorry")
    c.resolve_dispute(dispute_id)
    assert c.get_dispute(dispute_id)["state"] == "ERRORED"


def test_resolve_dispute_inconclusive_verdict_refunds_both_sides(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob
):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _mock_evidence(vm, "ambiguous", "ambiguous")
    _mock_verdict(vm, '{"verdict": "INCONCLUSIVE"}')
    c.resolve_dispute(dispute_id)
    d = c.get_dispute(dispute_id)
    assert d["state"] == "REFUNDED"
    assert vm._balances.get(_addr_bytes(direct_alice), 0) == STAKE
    assert vm._balances.get(_addr_bytes(direct_bob), 0) == STAKE


def test_resolve_dispute_plaintiff_verdict_is_provisional_not_paid_yet(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob
):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _mock_evidence(vm, "supports plaintiff", "does not support defendant")
    _mock_verdict(vm, '{"verdict": "PLAINTIFF"}')
    c.resolve_dispute(dispute_id)
    d = c.get_dispute(dispute_id)
    assert d["state"] == "PROVISIONAL"
    assert d["provisional_winner"] == "PLAINTIFF"
    assert d["resolved_at"] != ""
    # no payout yet - this is provisional, not final
    assert vm._balances.get(_addr_bytes(direct_alice), 0) == 0
    assert vm._balances.get(_addr_bytes(direct_bob), 0) == 0


def test_resolve_dispute_after_errored_can_be_retried_permissionlessly(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob, direct_owner
):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    c.resolve_dispute(dispute_id)  # no mocks -> ERRORED
    assert c.get_dispute(dispute_id)["state"] == "ERRORED"

    _mock_evidence(vm, "supports defendant", "supports defendant")
    _mock_verdict(vm, '{"verdict": "DEFENDANT"}')
    vm.sender = direct_owner
    c.resolve_dispute(dispute_id)
    d = c.get_dispute(dispute_id)
    assert d["state"] == "PROVISIONAL"
    assert d["provisional_winner"] == "DEFENDANT"


# ---------------------------------------------------------------------
# appeal_dispute
# ---------------------------------------------------------------------


def _resolve_to_provisional(c, vm, dispute_id, winner: str):
    _mock_evidence(vm, "evidence a", "evidence b")
    _mock_verdict(vm, '{"verdict": "%s"}' % winner)
    c.resolve_dispute(dispute_id)
    vm.clear_mocks()


def test_appeal_dispute_rejects_when_not_provisional(direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    vm.sender = direct_bob
    vm.value = APPEAL_BOND
    with vm.expect_revert("no provisional verdict"):
        c.appeal_dispute(dispute_id)
    vm.value = 0


def test_appeal_dispute_rejects_the_winning_party(direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _resolve_to_provisional(c, vm, dispute_id, "PLAINTIFF")
    vm.sender = direct_alice  # alice won, alice may not appeal
    vm.value = APPEAL_BOND
    with vm.expect_revert("only the losing party"):
        c.appeal_dispute(dispute_id)
    vm.value = 0


def test_appeal_dispute_rejects_wrong_bond_value(direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _resolve_to_provisional(c, vm, dispute_id, "PLAINTIFF")
    vm.sender = direct_bob
    vm.value = APPEAL_BOND - 1
    with vm.expect_revert("sent value must exactly equal appeal_bond"):
        c.appeal_dispute(dispute_id)
    vm.value = 0


def test_appeal_dispute_rejects_after_appeal_window_passed(direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob):
    from datetime import datetime, timedelta

    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob, appeal_window_seconds=60)
    _resolve_to_provisional(c, vm, dispute_id, "PLAINTIFF")
    resolved_at = c.get_dispute(dispute_id)["resolved_at"]
    resolved_dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
    warp_to(vm, (resolved_dt + timedelta(seconds=61)).isoformat())

    vm.sender = direct_bob
    vm.value = APPEAL_BOND
    with vm.expect_revert("appeal window has passed"):
        c.appeal_dispute(dispute_id)
    vm.value = 0


def test_appeal_dispute_succeeds_and_moves_to_appeal_pending(direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _resolve_to_provisional(c, vm, dispute_id, "PLAINTIFF")

    vm.sender = direct_bob
    vm.value = APPEAL_BOND
    c.appeal_dispute(dispute_id)
    vm.value = 0
    d = c.get_dispute(dispute_id)
    assert d["state"] == "APPEAL_PENDING"
    assert d["appellant"].lower() == _defendant_hex(direct_bob).lower()


# ---------------------------------------------------------------------
# resolve_appeal
# ---------------------------------------------------------------------


def _appeal(c, vm, appellant, dispute_id):
    vm.sender = appellant
    vm.value = APPEAL_BOND
    c.appeal_dispute(dispute_id)
    vm.value = 0


def test_resolve_appeal_rejects_when_not_pending(direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    with vm.expect_revert("no pending appeal"):
        c.resolve_appeal(dispute_id)


def test_resolve_appeal_on_fetch_failure_sets_appeal_errored(direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _resolve_to_provisional(c, vm, dispute_id, "PLAINTIFF")
    _appeal(c, vm, direct_bob, dispute_id)
    # no mocks registered for the appeal round
    c.resolve_appeal(dispute_id)
    assert c.get_dispute(dispute_id)["state"] == "APPEAL_ERRORED"


def test_resolve_appeal_reconfirmed_verdict_forfeits_appellants_bond_to_original_winner(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob
):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _resolve_to_provisional(c, vm, dispute_id, "PLAINTIFF")  # alice provisionally wins
    _appeal(c, vm, direct_bob, dispute_id)  # bob (loser) appeals

    _mock_evidence(vm, "still supports plaintiff", "still does not support defendant")
    _mock_verdict(vm, '{"verdict": "PLAINTIFF"}')  # reconfirmed
    c.resolve_appeal(dispute_id)

    d = c.get_dispute(dispute_id)
    assert d["state"] == "FINAL"
    assert d["final_winner"] == "PLAINTIFF"
    # alice gets both stakes AND bob's forfeited appeal bond
    assert vm._balances.get(_addr_bytes(direct_alice), 0) == 2 * STAKE + APPEAL_BOND
    assert vm._balances.get(_addr_bytes(direct_bob), 0) == 0


def test_resolve_appeal_inconclusive_does_not_overturn_provisional_winner(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob
):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _resolve_to_provisional(c, vm, dispute_id, "DEFENDANT")  # bob provisionally wins
    _appeal(c, vm, direct_alice, dispute_id)  # alice (loser) appeals

    _mock_evidence(vm, "murky", "murky")
    _mock_verdict(vm, '{"verdict": "INCONCLUSIVE"}')
    c.resolve_appeal(dispute_id)

    d = c.get_dispute(dispute_id)
    assert d["final_winner"] == "DEFENDANT"
    # bob (original winner) gets both stakes plus alice's forfeited bond
    assert vm._balances.get(_addr_bytes(direct_bob), 0) == 2 * STAKE + APPEAL_BOND
    assert vm._balances.get(_addr_bytes(direct_alice), 0) == 0


def test_resolve_appeal_overturned_verdict_pays_the_appellant_including_their_own_bond_back(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob
):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _resolve_to_provisional(c, vm, dispute_id, "PLAINTIFF")  # alice provisionally wins
    _appeal(c, vm, direct_bob, dispute_id)  # bob (loser) appeals and this time wins

    _mock_evidence(vm, "reveals plaintiff was wrong", "actually supports defendant")
    _mock_verdict(vm, '{"verdict": "DEFENDANT"}')
    c.resolve_appeal(dispute_id)

    d = c.get_dispute(dispute_id)
    assert d["state"] == "FINAL"
    assert d["final_winner"] == "DEFENDANT"
    # bob wins both stakes AND gets his own appeal bond back (not forfeited)
    assert vm._balances.get(_addr_bytes(direct_bob), 0) == 2 * STAKE + APPEAL_BOND
    assert vm._balances.get(_addr_bytes(direct_alice), 0) == 0


def test_resolve_appeal_after_appeal_errored_can_be_retried(direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _resolve_to_provisional(c, vm, dispute_id, "PLAINTIFF")
    _appeal(c, vm, direct_bob, dispute_id)
    c.resolve_appeal(dispute_id)  # no mocks -> APPEAL_ERRORED
    assert c.get_dispute(dispute_id)["state"] == "APPEAL_ERRORED"

    _mock_evidence(vm, "a", "b")
    _mock_verdict(vm, '{"verdict": "PLAINTIFF"}')
    c.resolve_appeal(dispute_id)
    assert c.get_dispute(dispute_id)["state"] == "FINAL"


# ---------------------------------------------------------------------
# finalize_dispute
# ---------------------------------------------------------------------


def test_finalize_dispute_rejects_when_not_provisional(direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    with vm.expect_revert("no unappealed provisional verdict"):
        c.finalize_dispute(dispute_id)


def test_finalize_dispute_rejects_before_appeal_window_passes(direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob):
    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob)
    _resolve_to_provisional(c, vm, dispute_id, "PLAINTIFF")
    with vm.expect_revert("has not passed yet"):
        c.finalize_dispute(dispute_id)


def test_finalize_dispute_pays_provisional_winner_after_window_with_no_appeal(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob, direct_owner
):
    from datetime import datetime, timedelta

    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob, appeal_window_seconds=60)
    _resolve_to_provisional(c, vm, dispute_id, "DEFENDANT")

    resolved_at = c.get_dispute(dispute_id)["resolved_at"]
    resolved_dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
    warp_to(vm, (resolved_dt + timedelta(seconds=61)).isoformat())

    vm.sender = direct_owner  # permissionless
    c.finalize_dispute(dispute_id)
    d = c.get_dispute(dispute_id)
    assert d["state"] == "FINAL"
    assert d["final_winner"] == "DEFENDANT"
    assert vm._balances.get(_addr_bytes(direct_bob), 0) == 2 * STAKE
    assert vm._balances.get(_addr_bytes(direct_alice), 0) == 0


def test_finalize_dispute_rejects_a_dispute_that_was_already_appealed(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob
):
    from datetime import datetime, timedelta

    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob, appeal_window_seconds=60)
    _resolve_to_provisional(c, vm, dispute_id, "PLAINTIFF")
    _appeal(c, vm, direct_bob, dispute_id)

    resolved_at = c.get_dispute(dispute_id)["resolved_at"]
    resolved_dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
    warp_to(vm, (resolved_dt + timedelta(seconds=61)).isoformat())

    with vm.expect_revert("no unappealed provisional verdict"):
        c.finalize_dispute(dispute_id)  # now APPEAL_PENDING, not PROVISIONAL


# ---------------------------------------------------------------------
# Fund conservation / unknown ids
# ---------------------------------------------------------------------


def test_full_lifecycle_conserves_total_value_with_no_appeal(
    direct_deploy, direct_vm_with_transfers, direct_alice, direct_bob
):
    from datetime import datetime, timedelta

    vm = direct_vm_with_transfers
    c = _deploy(direct_deploy, vm, direct_alice)
    dispute_id = _open_ready_dispute(c, vm, direct_alice, direct_bob, appeal_window_seconds=60)
    _resolve_to_provisional(c, vm, dispute_id, "PLAINTIFF")

    resolved_at = c.get_dispute(dispute_id)["resolved_at"]
    resolved_dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
    warp_to(vm, (resolved_dt + timedelta(seconds=61)).isoformat())
    c.finalize_dispute(dispute_id)

    total_out = vm._balances.get(_addr_bytes(direct_alice), 0) + vm._balances.get(_addr_bytes(direct_bob), 0)
    assert total_out == 2 * STAKE  # exactly what both parties put in, no more, no less


def test_operations_on_unknown_dispute_id_revert(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    with direct_vm.expect_revert("unknown dispute_id"):
        c.get_dispute(999)
