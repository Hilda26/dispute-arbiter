# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

# ---------------------------------------------------------------------------
# DisputeGatedRelease - a worked consumer of the DisputeArbiter primitive.
#
# Any contract that holds something contingent on who wins a two-party
# dispute - an escrow release, an access grant, a reputation mark - can gate
# on a DisputeArbiter dispute reaching FINAL, instead of writing its own
# staked-arbitration-with-appeal machinery. This example contains none of
# DisputeArbiter's evidence-fetching, judgment, or fund-escrow logic, it
# only reads the FINAL verdict DisputeArbiter already reached and settled.
# ---------------------------------------------------------------------------


@gl.contract_interface
class IDisputeArbiter:
    class View:
        def get_dispute(self, dispute_id: u256) -> dict: ...

    class Write:
        pass


class DisputeGatedRelease(gl.Contract):
    dispute_arbiter_address: Address
    released_to: TreeMap[u256, str]

    def __init__(self, dispute_arbiter_address: str):
        addr = (
            dispute_arbiter_address
            if isinstance(dispute_arbiter_address, Address)
            else Address(dispute_arbiter_address)
        )
        self.dispute_arbiter_address = addr

    @gl.public.write
    def release(self, dispute_id: u256) -> None:
        if dispute_id in self.released_to:
            raise gl.vm.UserError("already released for this dispute")

        dispute = IDisputeArbiter(self.dispute_arbiter_address).view().get_dispute(dispute_id)

        if dispute["state"] != "FINAL":
            raise gl.vm.UserError("dispute has not reached a FINAL verdict")

        winner_address = dispute["plaintiff"] if dispute["final_winner"] == "PLAINTIFF" else dispute["defendant"]
        self.released_to[dispute_id] = winner_address

    @gl.public.view
    def released_winner(self, dispute_id: u256) -> str:
        return self.released_to.get(dispute_id, "")
