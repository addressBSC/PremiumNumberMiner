// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./IERC20.sol";
import "./PerfectAddress.sol";

contract PremiumNumber is IERC20 {

    string  public constant name     = "Address";
    string  public constant symbol   = "ADD";
    uint8   public constant decimals = 18;
    uint256 public constant MAX_SUPPLY = 21_000_000 * 1e18;

    uint256 public constant RUN_MIN = 9;
    uint256 public constant RUN_MAX = 20;
    uint256 public requiredRun;
    address public owner;

    uint256 public constant WINDOW = 10;
    uint256 public constant BASE_REWARD = 50;
    uint256 public constant REWARD_STEP = 5;

    uint256 private _totalMinted;
    uint256 private _totalBurned;

    uint256 public era;
    uint256 private _nextHalving;
    uint256 private _halvingIncrement;

    uint256[WINDOW] private _slotCount;
    uint256[WINDOW] private _slotBlock;

    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    bytes32 public immutable walletBytecodeHash;
    address public immutable blankImpl;

    address public immutable addressManager;

    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;
    uint256 private _status = _NOT_ENTERED;

    bytes32 private constant _PERMIT_TYPEHASH =
        keccak256("Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)");
    bytes32 private constant _EIP712_DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 private immutable _HASHED_NAME;
    bytes32 private immutable _HASHED_VERSION;
    uint256 private immutable _CACHED_CHAIN_ID;
    bytes32 private immutable _CACHED_DOMAIN_SEPARATOR;
    mapping(address => uint256) public nonces;

    modifier nonReentrant() {
        require(_status != _ENTERED, "PN: reentrant call");
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }

    event Minted(
        address indexed miner,
        uint256 indexed tokenId,
        uint256 salt,
        uint256 streak,
        uint256 occurrences,
        address walletAddr,
        uint256 reward
    );

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event RequiredRunSet(uint256 oldN, uint256 newN);

    modifier onlyOwner() {
        require(msg.sender == owner, "PN: not owner");
        _;
    }

    constructor(address _addressManager, address _blankImpl) {
        require(_addressManager != address(0), "PN: zero manager");
        require(_blankImpl != address(0), "PN: zero blankImpl");
        addressManager = _addressManager;
        blankImpl = _blankImpl;
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);

        requiredRun = RUN_MIN;
        emit RequiredRunSet(0, RUN_MIN);

        walletBytecodeHash = keccak256(abi.encodePacked(
            type(PerfectAddress).creationCode,
            abi.encode(_blankImpl, _addressManager)
        ));

        _nextHalving = MAX_SUPPLY / 2;
        _halvingIncrement = MAX_SUPPLY / 4;

        _HASHED_NAME = keccak256(bytes(name));
        _HASHED_VERSION = keccak256(bytes("1"));
        _CACHED_CHAIN_ID = block.chainid;
        _CACHED_DOMAIN_SEPARATOR = _buildDomainSeparator();
    }

    function setRequiredRun(uint256 n) external onlyOwner {
        require(n >= RUN_MIN && n <= RUN_MAX, "PN: N out of range");
        uint256 old = requiredRun;
        requiredRun = n;
        emit RequiredRunSet(old, n);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function _buildDomainSeparator() private view returns (bytes32) {
        return keccak256(abi.encode(
            _EIP712_DOMAIN_TYPEHASH, _HASHED_NAME, _HASHED_VERSION, block.chainid, address(this)
        ));
    }

    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        if (block.chainid == _CACHED_CHAIN_ID) return _CACHED_DOMAIN_SEPARATOR;
        return _buildDomainSeparator();
    }

    function permit(
        address owner_,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external {
        require(block.timestamp <= deadline, "PN: permit expired");

        require(uint256(s) <= 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0, "PN: bad s");
        require(v == 27 || v == 28, "PN: bad v");

        bytes32 structHash = keccak256(abi.encode(
            _PERMIT_TYPEHASH, owner_, spender, value, nonces[owner_]++, deadline
        ));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), structHash));
        address signer = ecrecover(digest, v, r, s);
        require(signer != address(0) && signer == owner_, "PN: invalid signature");
        _approve(owner_, spender, value);
    }

    function mine(uint256 salt) external nonReentrant {
        _mine(salt, msg.sender);
    }

    function mineBatch(uint256[] calldata saltList) external nonReentrant {
        for (uint256 i = 0; i < saltList.length; i++) {
            _mine(saltList[i], msg.sender);
        }
    }

    function _mine(uint256 salt, address miner) internal {
        uint256 effectiveSalt = _effectiveSalt(miner, salt);
        address predicted = _computeAddress(effectiveSalt);

        (, uint256 streak, uint256 total, , , bool valid) = _evaluate(predicted, requiredRun);
        require(valid, "PN: pattern not met");

        uint256 tokenId = IAddressManager(addressManager).onMined(effectiveSalt, predicted, miner, streak, total);

        _deploy(effectiveSalt);

        _updateEra();
        uint256 reward = _baseReward() >> era;
        uint256 remaining = MAX_SUPPLY - _totalMinted;
        if (reward > remaining) reward = remaining;

        if (reward > 0) {
            unchecked {
                _totalMinted += reward;
                _balances[miner] += reward;
            }
            emit Transfer(address(0), miner, reward);
            _updateEra();
        }

        _recordSubmission();

        emit Minted(miner, tokenId, effectiveSalt, streak, total, predicted, reward);
    }

    function windowCount() public view returns (uint256 total) {
        uint256 lo = block.number >= WINDOW ? block.number - (WINDOW - 1) : 0;
        for (uint256 i = 0; i < WINDOW; i++) {
            uint256 b = _slotBlock[i];
            if (b >= lo && b <= block.number) {
                total += _slotCount[i];
            }
        }
    }

    function _recordSubmission() internal {
        uint256 slot = block.number % WINDOW;
        if (_slotBlock[slot] != block.number) {
            _slotBlock[slot] = block.number;
            _slotCount[slot] = 1;
        } else {
            _slotCount[slot] += 1;
        }
    }

    function _baseReward() internal view returns (uint256) {
        uint256 n = windowCount();
        uint256 baseWhole;
        if (n >= 10) {
            baseWhole = 1;
        } else {
            baseWhole = BASE_REWARD - REWARD_STEP * n;
        }
        return baseWhole * 1e18;
    }

    function _updateEra() internal {
        while (_halvingIncrement > 0 && _totalMinted >= _nextHalving) {
            era += 1;
            _nextHalving += _halvingIncrement;
            _halvingIncrement /= 2;
        }
    }

    function currentReward() external view returns (uint256) {
        uint256 reward = _baseReward() >> era;
        uint256 remaining = MAX_SUPPLY - _totalMinted;
        return reward > remaining ? remaining : reward;
    }

    function checkAddress(address addr) external view returns (
        uint256 trailing,
        uint256 leading,
        uint256 occurrences,
        bool valid
    ) {
        (, , uint256 occ, uint256 tr, uint256 ld, bool v) = _evaluate(addr, requiredRun);
        trailing    = tr;
        leading     = ld;
        occurrences = occ;
        valid       = v;
    }

    function _evaluate(address addr, uint256 n) internal pure returns (
        uint8 digit,
        uint256 streak,
        uint256 total,
        uint256 trailing,
        uint256 leading,
        bool valid
    ) {
        uint8 tDigit;
        uint8 lDigit;
        (tDigit, trailing) = _trailingRun(addr);
        (lDigit, leading)  = _leadingRun(addr);

        bool tOk = tDigit <= 9 && trailing >= n;
        bool lOk = lDigit <= 9 && leading >= n;
        valid = tOk || lOk;

        if (tOk && (!lOk || trailing >= leading)) {
            digit = tDigit;
            streak = trailing;
        } else if (lOk) {
            digit = lDigit;
            streak = leading;
        }
        if (valid) total = _countDigit(addr, digit);
    }

    function computeAddress(address miner, uint256 salt) external view returns (address) {
        return _computeAddress(_effectiveSalt(miner, salt));
    }

    function computeAddressByEffectiveSalt(uint256 effectiveSalt) external view returns (address) {
        return _computeAddress(effectiveSalt);
    }

    function totalMined() external view returns (uint256) {
        return IAddressManager(addressManager).nextWalletId() - 1;
    }

    function totalMinted() external view returns (uint256) {
        return _totalMinted;
    }

    function totalSupply() external view override returns (uint256) {
        return _totalMinted - _totalBurned;
    }

    function totalBurned() external view returns (uint256) {
        return _totalBurned;
    }

    function balanceOf(address account) external view override returns (uint256) {
        return _balances[account];
    }

    function transfer(address to, uint256 amount) external override returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function allowance(address _owner, address spender) external view override returns (uint256) {
        return _allowances[_owner][spender];
    }

    function approve(address spender, uint256 amount) external override returns (bool) {
        _approve(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external override returns (bool) {
        uint256 currentAllowance = _allowances[from][msg.sender];
        require(currentAllowance >= amount, "PN: allowance exceeded");
        _approve(from, msg.sender, currentAllowance - amount);
        _transfer(from, to, amount);
        return true;
    }

    function increaseAllowance(address spender, uint256 addedValue) external returns (bool) {
        _approve(msg.sender, spender, _allowances[msg.sender][spender] + addedValue);
        return true;
    }

    function decreaseAllowance(address spender, uint256 subtractedValue) external returns (bool) {
        uint256 currentAllowance = _allowances[msg.sender][spender];
        require(currentAllowance >= subtractedValue, "PN: decreased below zero");
        _approve(msg.sender, spender, currentAllowance - subtractedValue);
        return true;
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(from != address(0), "PN: from zero");
        require(to != address(0), "PN: to zero");
        require(_balances[from] >= amount, "PN: insufficient balance");
        _balances[from] -= amount;
        _balances[to] += amount;
        emit Transfer(from, to, amount);
    }

    function _approve(address _owner, address spender, uint256 amount) internal {
        require(_owner != address(0), "PN: approve from zero");
        require(spender != address(0), "PN: approve to zero");
        _allowances[_owner][spender] = amount;
        emit Approval(_owner, spender, amount);
    }

    function burn(uint256 amount) external {
        require(_balances[msg.sender] >= amount, "PN: insufficient balance");
        _balances[msg.sender] -= amount;
        _totalBurned += amount;
        emit Transfer(msg.sender, address(0), amount);
    }

    function burnFrom(address account, uint256 amount) external {
        uint256 allowed = _allowances[account][msg.sender];
        require(allowed >= amount, "PN: burn allowance exceeded");
        _approve(account, msg.sender, allowed - amount);
        require(_balances[account] >= amount, "PN: insufficient balance");
        _balances[account] -= amount;
        _totalBurned += amount;
        emit Transfer(account, address(0), amount);
    }

    function _effectiveSalt(address miner, uint256 salt) internal pure returns (uint256) {
        return uint256(keccak256(abi.encodePacked(miner, salt)));
    }

    function walletBytecode() public view returns (bytes memory) {
        return abi.encodePacked(
            type(PerfectAddress).creationCode,
            abi.encode(blankImpl, addressManager)
        );
    }

    function deployWallet(uint256 effectiveSalt) public returns (address addr) {
        (, address w, , , ) = IAddressManager(addressManager).getAddressInfo(effectiveSalt);
        require(w != address(0), "PN: salt not mined");
        addr = _deploy(effectiveSalt);
    }

    function _deploy(uint256 effectiveSalt) internal returns (address addr) {
        addr = _computeAddress(effectiveSalt);
        if (addr.code.length > 0) return addr;
        bytes memory bytecode = walletBytecode();
        assembly {
            addr := create2(0, add(bytecode, 0x20), mload(bytecode), effectiveSalt)
            if iszero(extcodesize(addr)) { revert(0, 0) }
        }
    }

    function _computeAddress(uint256 effectiveSalt) internal view returns (address) {
        bytes32 hash = keccak256(
            abi.encodePacked(bytes1(0xff), address(this), effectiveSalt, walletBytecodeHash)
        );
        return address(uint160(uint256(hash)));
    }

    function _trailingRun(address addr) internal pure returns (uint8 digit, uint256 count) {
        uint160 val = uint160(addr);
        digit = uint8(val & 0xf);
        unchecked {
            for (uint256 i = 0; i < 40; i++) {
                if (uint8(val & 0xf) == digit) {
                    count++;
                    val >>= 4;
                } else {
                    break;
                }
            }
        }
    }

    function _leadingRun(address addr) internal pure returns (uint8 digit, uint256 count) {
        uint160 val = uint160(addr);
        digit = uint8((val >> 156) & 0xf);
        unchecked {
            for (uint256 i = 0; i < 40; i++) {
                uint256 shift = (39 - i) * 4;
                if (uint8((val >> shift) & 0xf) == digit) {
                    count++;
                } else {
                    break;
                }
            }
        }
    }

    function _countDigit(address addr, uint8 digit) internal pure returns (uint256 count) {
        uint160 val = uint160(addr);
        unchecked {
            for (uint256 i = 0; i < 40; i++) {
                if (uint8(val & 0xf) == digit) {
                    count++;
                }
                val >>= 4;
            }
        }
    }

}

interface IAddressManager {
    function onMined(uint256 salt, address wallet, address miner, uint256 streak, uint256 occurrences) external returns (uint256 walletId);
    function nextWalletId() external view returns (uint256);
    function getAddressInfo(uint256 salt) external view returns (
        uint256 walletId, address wallet, address currentOwner, uint256 streak, uint256 occurrences
    );
}
