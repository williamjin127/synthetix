from tests.contract_interfaces.safe_decimal_math_interface import SafeDecimalMathInterface
from tests.contract_interfaces.self_destructible_interface import SelfDestructibleInterface
from utils.deployutils import mine_tx


class DestructibleExternStateTokenInterface(SafeDecimalMathInterface, SelfDestructibleInterface):
    def __init__(self, contract, name):
        SafeDecimalMathInterface.__init__(self, contract, name)
        SelfDestructibleInterface.__init__(self, contract, name)
        self.contract = contract
        self.name = name

        self.owner = lambda: self.contract.functions.owner().call()
        self.totalSupply = lambda: self.contract.functions.totalSupply().call()
        self.state = lambda: self.contract.functions.state().call()
        self.name = lambda: self.contract.functions.name().call()
        self.symbol = lambda: self.contract.functions.symbol().call()
        self.balanceOf = lambda account: self.contract.functions.balanceOf(account).call()
        self.allowance = lambda account, spender: self.contract.functions.allowance(account, spender).call()

        self.setState = lambda sender, new_state: mine_tx(
            self.contract.functions.setState(new_state).transact({'from': sender}), "setState", self.name)
        self.transfer = lambda sender, to, value: mine_tx(
            self.contract.functions.transfer(to, value).transact({'from': sender}), "transfer", self.name)
        self.approve = lambda sender, spender, value: mine_tx(
            self.contract.functions.approve(spender, value).transact({'from': sender}), "approve", self.name)
        self.transferFrom = lambda sender, frm, to, value: mine_tx(
            self.contract.functions.transferFrom(frm, to, value).transact({'from': sender}), "transferFrom", self.name)
