"""
Tests for the worked consumer example (examples/dispute_gated_release.py).
Proves the example genuinely reads DisputeArbiter's settled FINAL verdict
rather than re-implementing any arbitration of its own.
"""

from gltest.direct.loader import create_address

from .conftest import install_call_contract_hook

CONTRACT = "examples/dispute_gated_release.py"
ARBITER_ADDRESS_SEED = "some_dispute_arbiter"


def _arbiter_addr_hex(seed=ARBITER_ADDRESS_SEED):
    addr = create_address(seed)
    return "0x" + (addr if isinstance(addr, bytes) else bytes(addr.as_bytes)).hex()


def _dispute_payload(state: str, final_winner: str) -> dict:
    return {
        "id": 1,
        "plaintiff": "0x" + "11" * 20,
        "defendant": "0x" + "22" * 20,
        "issue_description": "Did the work get delivered?",
        "stake_amount": 10000,
        "appeal_bond": 2000,
        "accept_deadline_seconds": 3600,
        "appeal_window_seconds": 3600,
        "created_at": "2026-01-01T00:00:00+00:00",
        "plaintiff_position": "It was not delivered.",
        "plaintiff_evidence_url": "https://a.example.com",
        "defendant_position": "It was delivered.",
        "defendant_evidence_url": "https://b.example.com",
        "accepted_at": "2026-01-01T01:00:00+00:00",
        "state": state,
        "provisional_winner": final_winner,
        "resolved_at": "2026-01-01T02:00:00+00:00",
        "appellant": None,
        "appealed_at": "",
        "final_winner": final_winner,
    }


def test_release_succeeds_when_dispute_is_final(direct_deploy, direct_vm, direct_alice):
    from .conftest import install_call_contract_hook

    direct_vm.sender = direct_alice
    c = direct_deploy(CONTRACT, _arbiter_addr_hex())
    install_call_contract_hook(direct_vm, {"get_dispute": _dispute_payload("FINAL", "PLAINTIFF")})

    c.release(1)
    assert c.released_winner(1) == "0x" + "11" * 20


def test_release_rejects_when_dispute_has_not_reached_final(direct_deploy, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c = direct_deploy(CONTRACT, _arbiter_addr_hex())
    install_call_contract_hook(direct_vm, {"get_dispute": _dispute_payload("PROVISIONAL", "PLAINTIFF")})

    with direct_vm.expect_revert("has not reached a FINAL verdict"):
        c.release(1)
    assert c.released_winner(1) == ""


def test_release_records_the_defendant_when_defendant_wins(direct_deploy, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c = direct_deploy(CONTRACT, _arbiter_addr_hex())
    install_call_contract_hook(direct_vm, {"get_dispute": _dispute_payload("FINAL", "DEFENDANT")})

    c.release(1)
    assert c.released_winner(1) == "0x" + "22" * 20


def test_release_cannot_be_triggered_twice_for_the_same_dispute(direct_deploy, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c = direct_deploy(CONTRACT, _arbiter_addr_hex())
    install_call_contract_hook(direct_vm, {"get_dispute": _dispute_payload("FINAL", "PLAINTIFF")})

    c.release(1)
    with direct_vm.expect_revert("already released"):
        c.release(1)
