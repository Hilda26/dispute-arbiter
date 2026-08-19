import os
import pytest
from gltest import get_contract_factory, get_accounts, get_default_account

CONTRACT_PATH = "dispute_arbiter.py"


def _address_from_env() -> str | None:
    return os.environ.get("DISPUTEARBITER_ADDRESS")


@pytest.fixture(scope="session")
def deployed_contract():
    """
    Connects to an already-deployed DisputeArbiter instead of deploying a
    fresh one. Set DISPUTEARBITER_ADDRESS to the address printed by:

        genlayer deploy --contract contracts/dispute_arbiter.py

    Tests in this module are skipped (not failed) when the env var is
    absent, so `pytest tests/integration` is safe to run before deploying.
    """
    address = _address_from_env()
    if not address:
        pytest.skip(
            "DISPUTEARBITER_ADDRESS not set - deploy manually first with "
            "`genlayer deploy --contract contracts/dispute_arbiter.py` and "
            "export the printed address."
        )
    factory = get_contract_factory(contract_file_path=CONTRACT_PATH)
    return factory.build_contract(contract_address=address)


@pytest.fixture(scope="session")
def plaintiff_account():
    return get_default_account()


@pytest.fixture(scope="session")
def defendant_account():
    accounts = get_accounts()
    if len(accounts) > 1:
        return accounts[1]
    from gltest import create_account

    return create_account()
