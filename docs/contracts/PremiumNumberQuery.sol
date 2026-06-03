// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPremiumNumber {
    function computeAddressByEffectiveSalt(uint256 effectiveSalt) external view returns (address);
    function checkAddress(address addr) external view returns (
        uint256 trailing, uint256 leading, uint256 occurrences, bool valid
    );
    function totalSupply() external view returns (uint256);
    function totalMinted() external view returns (uint256);
    function totalBurned() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function walletBytecodeHash() external view returns (bytes32);
    function MAX_SUPPLY() external view returns (uint256);
    function RUN_MIN() external view returns (uint256);
    function RUN_MAX() external view returns (uint256);
    function totalMined() external view returns (uint256);
    function currentReward() external view returns (uint256);
    function era() external view returns (uint256);
    function windowCount() external view returns (uint256);
    function requiredRun() external view returns (uint256);
    function owner() external view returns (address);
    function addressManager() external view returns (address);
}

interface IAddressManager {
    function walletIdToSalt(uint256 walletId) external view returns (uint256);
    function nextWalletId() external view returns (uint256);
    function getApproved(uint256 tokenId) external view returns (address);
    function isApprovedForAll(address addrOwner, address operator) external view returns (bool);
    function currentPrice(uint256 salt) external view returns (uint256);
    function purchasePrice() external view returns (uint256);
    function PRICE_MIN() external view returns (uint256);
    function PRICE_MAX() external view returns (uint256);
    function PRICE_TICK() external view returns (uint256);
    function owner() external view returns (address);
    function renderer() external view returns (address);
    function getAddressInfo(uint256 salt) external view returns (
        uint256 walletId, address wallet, address currentOwner, uint256 streak, uint256 occurrences
    );
}

interface IRenderer {
    function traitsOf(address wallet) external pure returns (
        string memory pattern, uint8 digit, uint256 streak, uint256 leading,
        uint256 trailing, uint256 occurrences, string memory tier, uint256 rarityScore
    );
}

contract PremiumNumberQuery {

    IPremiumNumber public immutable pn;
    IAddressManager public immutable am;

    constructor(address _premiumNumber, address _addressManager) {
        pn = IPremiumNumber(_premiumNumber);
        am = IAddressManager(_addressManager);
    }

    struct GlobalInfo {
        uint256 totalSupply;
        uint256 totalMinted;
        uint256 totalBurned;
        uint256 maxSupply;
        uint256 totalMined;
        uint256 totalRegistered;
        uint256 nextWalletId;
        uint256 runMin;
        uint256 runMax;
        uint256 currentReward;
        uint256 era;
        uint256 windowCount;
        uint256 requiredRun;
        address pnOwner;
        uint256 purchasePrice;
        uint256 priceMin;
        uint256 priceMax;
        uint256 priceTick;
        address amOwner;
        bytes32 walletBytecodeHash;
        address addressManager;
    }

    function getGlobalInfo() external view returns (GlobalInfo memory info) {
        info.totalSupply = pn.totalSupply();
        info.totalMinted = pn.totalMinted();
        info.totalBurned = pn.totalBurned();
        info.maxSupply = pn.MAX_SUPPLY();
        info.totalMined = pn.totalMined();
        info.totalRegistered = am.nextWalletId() - 1;
        info.nextWalletId = am.nextWalletId();
        info.runMin = pn.RUN_MIN();
        info.runMax = pn.RUN_MAX();
        info.currentReward = pn.currentReward();
        info.era = pn.era();
        info.windowCount = pn.windowCount();
        info.requiredRun = pn.requiredRun();
        info.pnOwner = pn.owner();
        info.purchasePrice = am.purchasePrice();
        info.priceMin = am.PRICE_MIN();
        info.priceMax = am.PRICE_MAX();
        info.priceTick = am.PRICE_TICK();
        info.amOwner = am.owner();
        info.walletBytecodeHash = pn.walletBytecodeHash();
        info.addressManager = pn.addressManager();
    }

    struct WalletDetail {
        uint256 walletId;
        uint256 tokenId;
        uint256 salt;
        address currentOwner;
        uint256 streak;
        uint256 occurrences;
        address walletAddr;
        address approved;
        bool    purchasable;
        uint256 price;
    }

    function getByWalletId(uint256 walletId) external view returns (WalletDetail memory d) {
        return _getByWalletId(walletId);
    }

    function getByWalletIdRange(uint256 fromId, uint256 toId)
        external view returns (WalletDetail[] memory details)
    {
        uint256 maxId = am.nextWalletId() - 1;
        if (fromId == 0) fromId = 1;
        if (toId > maxId) toId = maxId;
        if (fromId > toId) return new WalletDetail[](0);

        uint256 count = toId - fromId + 1;
        details = new WalletDetail[](count);
        for (uint256 i = 0; i < count; i++) {
            details[i] = _getByWalletId(fromId + i);
        }
    }

    function getByTokenIdRange(uint256 fromId, uint256 toId)
        external view returns (WalletDetail[] memory details)
    {
        uint256 total = pn.totalMined();
        if (fromId == 0) fromId = 1;
        if (toId > total) toId = total;
        if (fromId > toId) return new WalletDetail[](0);

        uint256 count = toId - fromId + 1;
        details = new WalletDetail[](count);
        for (uint256 i = 0; i < count; i++) {
            details[i] = _getByWalletId(fromId + i);
        }
    }

    function isApprovedForAll(address addrOwner, address operator)
        external view returns (bool)
    {
        return am.isApprovedForAll(addrOwner, operator);
    }

    function getUserDashboard(address user)
        external view returns (uint256 tokenBalance, uint256 bnbBalance)
    {
        tokenBalance = pn.balanceOf(user);
        bnbBalance = user.balance;
    }

    function batchBalanceOf(address[] calldata users)
        external view returns (uint256[] memory balances)
    {
        balances = new uint256[](users.length);
        for (uint256 i = 0; i < users.length; i++) {
            balances[i] = pn.balanceOf(users[i]);
        }
    }

    function _getByWalletId(uint256 wid) internal view returns (WalletDetail memory d) {
        uint256 salt = am.walletIdToSalt(wid);
        (uint256 walletId, address wallet, address curOwner, uint256 streak, uint256 occ)
            = am.getAddressInfo(salt);
        require(wallet != address(0), "Q: not registered");

        d = WalletDetail({
            walletId: walletId,
            tokenId: walletId,
            salt: salt,
            currentOwner: curOwner,
            streak: streak,
            occurrences: occ,
            walletAddr: wallet,
            approved: am.getApproved(walletId),
            purchasable: curOwner == address(0),
            price: curOwner == address(0) ? am.currentPrice(salt) : 0
        });
    }

    struct SaltPreview {
        uint256 effectiveSalt;
        address predictedAddr;
        uint256 trailing;
        uint256 leading;
        uint256 occurrences;
        bool    valid;
        uint256 reward;
    }

    function batchPreview(uint256[] calldata effectiveSalts)
        external view returns (SaltPreview[] memory previews)
    {
        previews = new SaltPreview[](effectiveSalts.length);
        uint256 curReward = pn.currentReward();

        for (uint256 i = 0; i < effectiveSalts.length; i++) {
            address predicted = pn.computeAddressByEffectiveSalt(effectiveSalts[i]);
            (uint256 tr, uint256 ld, uint256 occ, bool valid) = pn.checkAddress(predicted);

            previews[i] = SaltPreview({
                effectiveSalt: effectiveSalts[i],
                predictedAddr: predicted,
                trailing: tr,
                leading: ld,
                occurrences: occ,
                valid: valid,
                reward: valid ? curReward : 0
            });
        }
    }

    struct TokenTraits {
        uint256 tokenId;
        address wallet;
        address currentOwner;
        string  pattern;
        uint8   digit;
        uint256 streak;
        uint256 leading;
        uint256 trailing;
        uint256 occurrences;
        string  tier;
        uint256 rarityScore;
    }

    function traitsOf(uint256 tokenId) public view returns (TokenTraits memory t) {
        uint256 salt = am.walletIdToSalt(tokenId);
        (, address wallet, address curOwner, , ) = am.getAddressInfo(salt);
        require(wallet != address(0), "Q: not registered");
        t.tokenId = tokenId;
        t.wallet = wallet;
        t.currentOwner = curOwner;
        (t.pattern, t.digit, t.streak, t.leading, t.trailing, t.occurrences, t.tier, t.rarityScore)
            = IRenderer(am.renderer()).traitsOf(wallet);
    }

    function traitsRange(uint256 fromId, uint256 toId) external view returns (TokenTraits[] memory arr) {
        uint256 maxId = am.nextWalletId() - 1;
        if (fromId == 0) fromId = 1;
        if (toId > maxId) toId = maxId;
        if (fromId > toId) return new TokenTraits[](0);
        uint256 count = toId - fromId + 1;
        arr = new TokenTraits[](count);
        for (uint256 i = 0; i < count; i++) {
            arr[i] = traitsOf(fromId + i);
        }
    }
}
