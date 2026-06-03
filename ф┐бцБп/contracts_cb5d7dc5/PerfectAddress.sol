// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPerfectAddressAdmin {
    function upgradeToAndCall(address newImplementation, bytes calldata data) external;
    function renounceUpgrade() external;
}

contract PerfectAddress {

    bytes32 private constant _IMPL_SLOT  = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;
    bytes32 private constant _ADMIN_SLOT = 0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103;

    event Upgraded(address indexed implementation);
    event AdminRenounced();

    constructor(address impl_, address admin_) {
        require(impl_ != address(0) && admin_ != address(0), "PA: zero");
        require(impl_.code.length > 0, "PA: impl !contract");
        _store(_IMPL_SLOT, impl_);
        _store(_ADMIN_SLOT, admin_);
        emit Upgraded(impl_);
    }

    function _load(bytes32 slot) private view returns (address a) {
        assembly { a := sload(slot) }
    }

    function _store(bytes32 slot, address v) private {
        assembly { sstore(slot, v) }
    }

    fallback() external payable {
        address admin = _load(_ADMIN_SLOT);

        if (admin != address(0) && msg.sender == admin) {
            bytes4 sig = msg.sig;
            if (sig == IPerfectAddressAdmin.upgradeToAndCall.selector) {
                (address newImpl, bytes memory data) = abi.decode(msg.data[4:], (address, bytes));
                require(newImpl.code.length > 0, "PA: impl !contract");
                _store(_IMPL_SLOT, newImpl);
                if (data.length > 0) {
                    (bool ok, bytes memory ret) = newImpl.delegatecall(data);
                    if (!ok) { assembly { revert(add(ret, 0x20), mload(ret)) } }
                }
                emit Upgraded(newImpl);
            } else if (sig == IPerfectAddressAdmin.renounceUpgrade.selector) {
                _store(_ADMIN_SLOT, address(0));
                emit AdminRenounced();
            } else {
                revert("PA: admin no fallthrough");
            }
        } else {
            _delegate(_load(_IMPL_SLOT));
        }
    }

    receive() external payable {
        _delegate(_load(_IMPL_SLOT));
    }

    function _delegate(address impl) private {
        require(impl != address(0), "PA: no impl");
        assembly {
            calldatacopy(0, 0, calldatasize())
            let result := delegatecall(gas(), impl, 0, calldatasize(), 0, 0)
            returndatacopy(0, 0, returndatasize())
            switch result
            case 0 { revert(0, returndatasize()) }
            default { return(0, returndatasize()) }
        }
    }
}

contract BlankImpl {

}
