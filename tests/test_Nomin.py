import unittest
import time

import utils.generalutils
from utils.generalutils import to_seconds
from utils.deployutils import W3, UNIT, MASTER, DUMMY, ETHER, fresh_account
from utils.deployutils import compile_contracts, attempt_deploy, mine_tx
from utils.deployutils import take_snapshot, restore_snapshot, fast_forward
from utils.testutils import assertReverts, block_time, send_value, get_eth_balance
from utils.testutils import generate_topic_event_map, get_event_data_from_log
from utils.testutils import ZERO_ADDRESS

from tests.contract_interfaces.nomin_interface import PublicNominInterface

Nomin_SOURCE = "tests/contracts/PublicNomin.sol"
FAKECOURT_SOURCE = "tests/contracts/FakeCourt.sol"


def setUpModule():
    print("Testing Nomin...")


def tearDownModule():
    print()


class TestNomin(unittest.TestCase):
    def setUp(self):
        self.snapshot = take_snapshot()

    def tearDown(self):
        restore_snapshot(self.snapshot)

    @classmethod
    def setUpClass(cls):
        cls.assertReverts = assertReverts

        compiled = compile_contracts([Nomin_SOURCE, FAKECOURT_SOURCE],
                                     remappings=['""=contracts'])
        cls.nomin_abi = compiled['PublicNomin']['abi']
        cls.nomin_event_dict = generate_topic_event_map(cls.nomin_abi)

        cls.nomin_contract, cls.construction_txr = attempt_deploy(
            compiled, 'PublicNomin', MASTER, [MASTER, MASTER, ZERO_ADDRESS]
        )

        cls.nomin = PublicNominInterface(cls.nomin_contract)

        cls.fake_court, _ = attempt_deploy(compiled, 'FakeCourt', MASTER, [])

        cls.fake_court.setNomin = lambda sender, new_nomin: mine_tx(
            cls.fake_court.functions.setNomin(new_nomin).transact({'from': sender}))
        cls.fake_court.setConfirming = lambda sender, target, status: mine_tx(
            cls.fake_court.functions.setConfirming(target, status).transact({'from': sender}))
        cls.fake_court.setVotePasses = lambda sender, target, status: mine_tx(
            cls.fake_court.functions.setVotePasses(target, status).transact({'from': sender}))
        cls.fake_court.setTargetMotionID = lambda sender, target, motion_id: mine_tx(
            cls.fake_court.functions.setTargetMotionID(target, motion_id).transact({'from': sender}))
        cls.fake_court.confiscateBalance = lambda sender, target: mine_tx(
            cls.fake_court.functions.confiscateBalance(target).transact({'from': sender}))
        cls.fake_court.setNomin(W3.eth.accounts[0], cls.nomin.contract.address)

        cls.nomin.setCourt(MASTER, cls.fake_court.address)

    def test_constructor(self):
        # Nomin-specific members
        self.assertEqual(self.nomin.owner(), MASTER)
        self.assertTrue(self.nomin.frozen(self.nomin.contract.address))

        # ExternStateFeeToken members
        self.assertEqual(self.nomin.name(), "Havven-Backed USD Nomins")
        self.assertEqual(self.nomin.symbol(), "nUSD")
        self.assertEqual(self.nomin.totalSupply(), 0)
        self.assertEqual(self.nomin.balanceOf(MASTER), 0)
        self.assertEqual(self.nomin.transferFeeRate(), 15 * UNIT // 10000)
        self.assertEqual(self.nomin.feeAuthority(), self.nomin.havven())
        self.assertEqual(self.nomin.decimals(), 18)

    def test_getSetOwner(self):
        pre_owner = self.nomin.owner()
        new_owner = DUMMY

        # Only the owner must be able to set the owner.
        self.assertReverts(self.nomin.nominateOwner, new_owner, new_owner)
        self.nomin.nominateOwner(pre_owner, new_owner)
        self.nomin.acceptOwnership(new_owner)
        self.assertEqual(self.nomin.owner(), new_owner)

    def test_getSetCourt(self):
        new_court = DUMMY

        # Only the owner must be able to set the court.
        self.nomin.setCourt(self.nomin.owner(), new_court)
        self.assertEqual(self.nomin.court(), new_court)

    def test_transfer(self):
        target = fresh_account()

        fast_forward(2)

        self.nomin.giveNomins(MASTER, MASTER, 10 * UNIT)
        self.assertEqual(self.nomin.balanceOf(MASTER), 10 * UNIT)
        self.assertEqual(self.nomin.balanceOf(target), 0)

        # Should be impossible to transfer to the nomin contract itself.
        self.assertReverts(self.nomin.transfer, MASTER, self.nomin.contract.address, UNIT)

        self.nomin.transfer(MASTER, target, 5 * UNIT)
        remainder = 10 * UNIT - self.nomin.transferPlusFee(5 * UNIT)
        self.assertEqual(self.nomin.balanceOf(MASTER), remainder)
        self.assertEqual(self.nomin.balanceOf(target), 5 * UNIT)

        self.nomin.debugFreezeAccount(MASTER, target)

        self.assertReverts(self.nomin.transfer, MASTER, target, UNIT)
        # self.assertReverts(self.nomin.transfer, target, MASTER, UNIT)

        self.nomin.unfreezeAccount(MASTER, target)

        qty = (5 * UNIT * UNIT) // self.nomin.transferPlusFee(UNIT) + 1
        self.nomin.transfer(target, MASTER, qty)

        self.assertEqual(self.nomin.balanceOf(MASTER), remainder + qty)
        self.assertEqual(self.nomin.balanceOf(target), 0)

    def test_transferFrom(self):
        target = fresh_account()

        self.nomin.giveNomins(MASTER, MASTER, 10 * UNIT)

        # Unauthorized transfers should not work
        self.assertReverts(self.nomin.transferFrom, DUMMY, MASTER, target, UNIT)

        # Neither should transfers that are too large for the allowance.
        self.nomin.approve(MASTER, DUMMY, UNIT)
        self.assertReverts(self.nomin.transferFrom, DUMMY, MASTER, target, 2 * UNIT)

        self.nomin.approve(MASTER, DUMMY, 10000 * UNIT)

        self.assertEqual(self.nomin.balanceOf(MASTER), 10 * UNIT)
        self.assertEqual(self.nomin.balanceOf(target), 0)

        # Should be impossible to transfer to the nomin contract itself.
        self.assertReverts(self.nomin.transferFrom, DUMMY, MASTER, self.nomin.contract.address, UNIT)

        self.nomin.transferFrom(DUMMY, MASTER, target, 5 * UNIT)
        remainder = 10 * UNIT - self.nomin.transferPlusFee(5 * UNIT)
        self.assertEqual(self.nomin.balanceOf(MASTER), remainder)
        self.assertEqual(self.nomin.balanceOf(target), 5 * UNIT)

        self.nomin.debugFreezeAccount(MASTER, target)

        self.assertReverts(self.nomin.transferFrom, DUMMY, MASTER, target, UNIT)
        self.assertReverts(self.nomin.transferFrom, DUMMY, target, MASTER, UNIT)

        self.nomin.unfreezeAccount(MASTER, target)

        qty = (5 * UNIT * UNIT) // self.nomin.transferPlusFee(UNIT) + 1
        self.nomin.transfer(target, MASTER, qty)

        self.assertEqual(self.nomin.balanceOf(MASTER), remainder + qty)
        self.assertEqual(self.nomin.balanceOf(target), 0)

    def test_confiscateBalance(self):
        target = W3.eth.accounts[2]

        self.assertEqual(self.nomin.court(), self.fake_court.address)

        self.nomin.giveNomins(MASTER, target, 10 * UNIT)

        # The target must have some nomins.
        self.assertEqual(self.nomin.balanceOf(target), 10 * UNIT)

        motion_id = 1
        self.fake_court.setTargetMotionID(MASTER, target, motion_id)

        # Attempt to confiscate even though the conditions are not met.
        self.fake_court.setConfirming(MASTER, motion_id, False)
        self.fake_court.setVotePasses(MASTER, motion_id, False)
        self.assertReverts(self.fake_court.confiscateBalance, MASTER, target)

        self.fake_court.setConfirming(MASTER, motion_id, True)
        self.fake_court.setVotePasses(MASTER, motion_id, False)
        self.assertReverts(self.fake_court.confiscateBalance, MASTER, target)

        self.fake_court.setConfirming(MASTER, motion_id, False)
        self.fake_court.setVotePasses(MASTER, motion_id, True)
        self.assertReverts(self.fake_court.confiscateBalance, MASTER, target)

        # Set up the target balance to be confiscatable.
        self.fake_court.setConfirming(MASTER, motion_id, True)
        self.fake_court.setVotePasses(MASTER, motion_id, True)

        # Only the court should be able to confiscate balances.
        self.assertReverts(self.nomin.confiscateBalance, MASTER, target)

        # Actually confiscate the balance.
        pre_feePool = self.nomin.feePool()
        pre_balance = self.nomin.balanceOf(target)
        self.fake_court.confiscateBalance(MASTER, target)
        self.assertEqual(self.nomin.balanceOf(target), 0)
        self.assertEqual(self.nomin.feePool(), pre_feePool + pre_balance)
        self.assertTrue(self.nomin.frozen(target))

    def test_unfreezeAccount(self):
        target = fresh_account()

        # The nomin contract itself should not be unfreezable.
        tx_receipt = self.nomin.unfreezeAccount(MASTER, self.nomin.contract.address)
        self.assertTrue(self.nomin.frozen(self.nomin.contract.address))
        self.assertEqual(len(tx_receipt.logs), 0)

        # Unfreezing non-frozen accounts should not do anything.
        self.assertFalse(self.nomin.frozen(target))
        tx_receipt = self.nomin.unfreezeAccount(MASTER, target)
        self.assertFalse(self.nomin.frozen(target))
        self.assertEqual(len(tx_receipt.logs), 0)

        self.nomin.debugFreezeAccount(MASTER, target)
        self.assertTrue(self.nomin.frozen(target))

        # Only the owner should be able to unfreeze an account.
        self.assertReverts(self.nomin.unfreezeAccount, target, target)

        tx_receipt = self.nomin.unfreezeAccount(MASTER, target)
        self.assertFalse(self.nomin.frozen(target))

        # Unfreezing should emit the appropriate log.
        log = get_event_data_from_log(self.nomin_event_dict, tx_receipt.logs[0])
        self.assertEqual(log['event'], 'AccountUnfrozen')
