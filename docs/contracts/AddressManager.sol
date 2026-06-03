// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./PerfectAddress.sol";

interface IPremiumNumberToken {
    function deployWallet(uint256 effectiveSalt) external returns (address);
}

interface IPremiumRenderer {
    function tokenURI(uint256 tokenId, address wallet) external view returns (string memory);
}

interface IERC721Receiver {
    function onERC721Received(address operator, address from, uint256 tokenId, bytes calldata data) external returns (bytes4);
}

contract AddressManager {

    string public constant name = "Premium Address";
    string public constant symbol = "PADD";

    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;
    uint256 private _status = _NOT_ENTERED;

    modifier nonReentrant() {
        require(_status != _ENTERED, "AM: reentrant call");
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }

    address public immutable deployer;
    address public premiumNumber;
    address public immutable renderer;

    uint256 public constant PRICE_MIN  = 0.001 ether;
    uint256 public constant PRICE_MAX  = 1 ether;
    uint256 public constant PRICE_TICK = 0.001 ether;

    uint256 public purchasePrice = PRICE_MIN;

    address public owner;

    address public payoutAddress;

    struct AddressInfo {
        address wallet;
        uint64  walletId;
        uint16  streak;
        uint16  occurrences;
        address currentOwner;
    }

    uint256 public nextWalletId = 1;

    mapping(uint256 => AddressInfo) public addressInfos;
    mapping(uint256 => uint256) public walletIdToSalt;

    mapping(uint256 => bool) public upgradeRenounced;

    mapping(uint256 => address) private _approvals;
    mapping(address => mapping(address => bool)) private _operatorApprovals;
    mapping(address => uint256) private _balances;

    event AddressRegistered(
        uint256 indexed walletId,
        uint256 indexed salt,
        address indexed wallet,
        address miner,
        uint256 streak,
        uint256 occurrences
    );
    event AddressOwnerChanged(
        uint256 indexed walletId,
        uint256 indexed salt,
        address indexed wallet,
        address newOwner,
        address previousOwner
    );
    event PremiumNumberSet(address indexed premiumNumber);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event PurchasePriceChanged(uint256 oldPrice, uint256 newPrice);
    event PayoutAddressSet(address indexed previous, address indexed next);
    event Swept(address indexed to, uint256 amount);

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);
    event Claimed(uint256 indexed walletId, uint256 indexed salt, address indexed buyer, uint256 pricePaid);

    event WalletUpgraded(uint256 indexed walletId, address indexed wallet, address indexed newImplementation);
    event WalletUpgradeRenounced(uint256 indexed walletId, address indexed wallet);

    modifier onlyPremiumNumber() {
        require(msg.sender == premiumNumber, "AM: not PremiumNumber");
        _;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "AM: not owner");
        _;
    }

    constructor(address _renderer) {
        require(_renderer != address(0), "AM: zero renderer");
        deployer = msg.sender;
        owner = msg.sender;
        renderer = _renderer;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function onMined(uint256 salt, address wallet, address miner, uint256 streak, uint256 occurrences)
        external onlyPremiumNumber returns (uint256 wid)
    {
        require(addressInfos[salt].wallet == address(0), "AM: salt already registered");

        wid = nextWalletId++;

        addressInfos[salt] = AddressInfo({
            walletId: uint64(wid),
            wallet: wallet,
            currentOwner: address(0),
            streak: uint16(streak),
            occurrences: uint16(occurrences)
        });
        walletIdToSalt[wid] = salt;

        emit AddressRegistered(wid, salt, wallet, miner, streak, occurrences);
    }

    function currentPrice(uint256 salt) public view returns (uint256) {
        require(addressInfos[salt].wallet != address(0), "AM: not registered");
        return purchasePrice;
    }

    function _claim(uint256 salt, address buyer, uint256 paid) internal {
        AddressInfo storage info = addressInfos[salt];
        require(info.wallet != address(0), "AM: not registered");
        require(info.currentOwner == address(0), "AM: not available");

        uint256 price = purchasePrice;
        require(paid >= price, "AM: insufficient payment");

        info.currentOwner = buyer;
        _balances[buyer] += 1;

        if (paid > price) {
            (bool ok, ) = payable(buyer).call{value: paid - price}("");
            require(ok, "AM: refund failed");
        }

        emit Transfer(address(0), buyer, info.walletId);
        emit Claimed(info.walletId, salt, buyer, price);
        emit AddressOwnerChanged(info.walletId, salt, info.wallet, buyer, address(0));
    }

    function claim(uint256 salt) external payable nonReentrant {
        _claim(salt, msg.sender, msg.value);
    }

    function claimById(uint256 walletId) external payable nonReentrant {
        require(walletId >= 1 && walletId < nextWalletId, "AM: invalid walletId");
        _claim(walletIdToSalt[walletId], msg.sender, msg.value);
    }

    function setPurchasePrice(uint256 newPrice) external onlyOwner {
        require(newPrice >= PRICE_MIN && newPrice <= PRICE_MAX, "AM: price out of range");
        require(newPrice % PRICE_TICK == 0, "AM: price not on tick");
        uint256 old = purchasePrice;
        purchasePrice = newPrice;
        emit PurchasePriceChanged(old, newPrice);
    }

    function setPayoutAddress(address newPayout) external onlyOwner {
        require(newPayout != address(0), "AM: zero payout");
        emit PayoutAddressSet(payoutAddress, newPayout);
        payoutAddress = newPayout;
    }

    function sweep() external nonReentrant onlyOwner {
        address to = payoutAddress;
        require(to != address(0), "AM: payout not set");
        uint256 amount = address(this).balance;
        require(amount > 0, "AM: nothing to sweep");
        (bool ok, ) = payable(to).call{value: amount}("");
        require(ok, "AM: sweep failed");
        emit Swept(to, amount);
    }

    function balanceOf(address account) external view returns (uint256) {
        require(account != address(0), "AM: zero address");
        return _balances[account];
    }

    function ownerOf(uint256 tokenId) public view returns (address) {
        address o = addressInfos[walletIdToSalt[tokenId]].currentOwner;
        require(o != address(0), "AM: nonexistent token");
        return o;
    }

    function _saltOf(uint256 tokenId) internal view returns (uint256 salt) {
        require(tokenId >= 1 && tokenId < nextWalletId, "AM: invalid tokenId");
        salt = walletIdToSalt[tokenId];
    }

    function _isApprovedOrOwner(address spender, uint256 salt) internal view returns (bool) {
        address addrOwner = addressInfos[salt].currentOwner;
        return (addrOwner != address(0) &&
                (spender == addrOwner ||
                 _approvals[salt] == spender ||
                 _operatorApprovals[addrOwner][spender]));
    }

    function approve(address to, uint256 tokenId) external {
        uint256 salt = _saltOf(tokenId);
        address addrOwner = addressInfos[salt].currentOwner;
        require(addrOwner != address(0), "AM: not owned yet");
        require(
            msg.sender == addrOwner || _operatorApprovals[addrOwner][msg.sender],
            "AM: not owner or operator"
        );
        require(to != addrOwner, "AM: approve to owner");
        _approvals[salt] = to;
        emit Approval(addrOwner, to, tokenId);
    }

    function setApprovalForAll(address operator, bool approved) external {
        require(operator != msg.sender, "AM: approve to self");
        _operatorApprovals[msg.sender][operator] = approved;
        emit ApprovalForAll(msg.sender, operator, approved);
    }

    function getApproved(uint256 tokenId) external view returns (address) {
        return _approvals[_saltOf(tokenId)];
    }

    function isApprovedForAll(address addrOwner, address operator) external view returns (bool) {
        return _operatorApprovals[addrOwner][operator];
    }

    function _transferOwnership(uint256 salt, address from, address to) internal {
        AddressInfo storage info = addressInfos[salt];
        require(info.wallet != address(0), "AM: not registered");
        require(info.currentOwner == from && from != address(0), "AM: not address owner");
        require(to != address(0), "AM: zero address");

        delete _approvals[salt];
        _balances[from] -= 1;
        _balances[to] += 1;
        info.currentOwner = to;

        emit Transfer(from, to, info.walletId);
        emit AddressOwnerChanged(info.walletId, salt, info.wallet, to, from);
    }

    function transferFrom(address from, address to, uint256 tokenId) public {
        uint256 salt = _saltOf(tokenId);
        require(_isApprovedOrOwner(msg.sender, salt), "AM: not owner or approved");
        _transferOwnership(salt, from, to);
    }

    function safeTransferFrom(address from, address to, uint256 tokenId) external {
        safeTransferFrom(from, to, tokenId, "");
    }

    function safeTransferFrom(address from, address to, uint256 tokenId, bytes memory data) public {
        transferFrom(from, to, tokenId);
        if (to.code.length > 0) {
            require(
                IERC721Receiver(to).onERC721Received(msg.sender, from, tokenId, data)
                    == IERC721Receiver.onERC721Received.selector,
                "AM: non ERC721Receiver"
            );
        }
    }

    function tokenURI(uint256 tokenId) external view returns (string memory) {
        uint256 salt = _saltOf(tokenId);
        require(addressInfos[salt].currentOwner != address(0), "AM: nonexistent token");
        return IPremiumRenderer(renderer).tokenURI(tokenId, addressInfos[salt].wallet);
    }

    function supportsInterface(bytes4 id) external pure returns (bool) {
        return id == 0x01ffc9a7 ||
               id == 0x80ac58cd ||
               id == 0x5b5e139f;
    }

    function transferAddressOwnership(uint256 salt, address newOwner) external {
        require(addressInfos[salt].currentOwner == msg.sender, "AM: not address owner");
        _transferOwnership(salt, msg.sender, newOwner);
    }

    function upgradeWalletToToken(uint256 tokenId, address newImpl, bytes calldata initData)
        external nonReentrant
    {
        uint256 salt = _saltOf(tokenId);
        AddressInfo storage info = addressInfos[salt];
        require(info.currentOwner == msg.sender, "AM: not address owner");
        require(!upgradeRenounced[salt], "AM: upgrade renounced");
        address wallet = info.wallet;

        IPerfectAddressAdmin(payable(wallet)).upgradeToAndCall(newImpl, initData);
        emit WalletUpgraded(info.walletId, wallet, newImpl);
    }

    function renounceWalletUpgrade(uint256 tokenId) external nonReentrant {
        uint256 salt = _saltOf(tokenId);
        AddressInfo storage info = addressInfos[salt];
        require(info.currentOwner == msg.sender, "AM: not address owner");
        require(!upgradeRenounced[salt], "AM: already renounced");
        upgradeRenounced[salt] = true;
        address wallet = info.wallet;
        IPerfectAddressAdmin(payable(wallet)).renounceUpgrade();
        emit WalletUpgradeRenounced(info.walletId, wallet);
    }

    function setPremiumNumber(address _premiumNumber) external {
        require(msg.sender == deployer, "AM: not deployer");
        require(_premiumNumber != address(0), "AM: zero address");
        require(premiumNumber == address(0), "AM: premiumNumber already set");
        premiumNumber = _premiumNumber;
        emit PremiumNumberSet(_premiumNumber);
    }

    function isAvailable(uint256 salt) external view returns (bool) {
        AddressInfo memory info = addressInfos[salt];
        return info.wallet != address(0) && info.currentOwner == address(0);
    }

    function lookupByWallet(address wallet, uint256 salt) external view
        returns (bool ok, uint256 tokenId, address currentOwner)
    {
        AddressInfo memory info = addressInfos[salt];
        if (info.wallet == wallet && wallet != address(0)) {
            return (true, info.walletId, info.currentOwner);
        }
        return (false, 0, address(0));
    }

    function getAddressInfo(uint256 salt) external view returns (
        uint256 walletId,
        address wallet,
        address currentOwner_,
        uint256 streak,
        uint256 occurrences
    ) {
        AddressInfo memory info = addressInfos[salt];
        return (info.walletId, info.wallet, info.currentOwner, info.streak, info.occurrences);
    }

    function getAddressInfoById(uint256 walletId) external view returns (
        uint256 salt,
        address wallet,
        address currentOwner_,
        uint256 streak,
        uint256 occurrences
    ) {
        require(walletId >= 1 && walletId < nextWalletId, "AM: invalid walletId");
        salt = walletIdToSalt[walletId];
        AddressInfo memory info = addressInfos[salt];
        require(info.wallet != address(0), "AM: not registered");
        return (salt, info.wallet, info.currentOwner, info.streak, info.occurrences);
    }

}
