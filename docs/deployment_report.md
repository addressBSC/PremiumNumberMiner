# BSC Mainnet Contract Deployment Report

## Deployment Information

| Item | Value |
|------|-------|
| Network | BSC Mainnet (Chain ID: 56) |
| Deployer Account | 0x038C66BDA2e892559295599c32d2C5831a448385 |
| BNB Consumed | 0.000489534276242603 BNB |
| Compiler Version | Solidity 0.8.20 |
| Optimization | Enabled (runs: 200, viaIR: true) |
| EVM Version | paris |

## Contract Addresses

| Contract Name | Address | BscScan |
|---------------|---------|---------|
| PremiumRenderer | 0xa3cCd778AE6a168c12538dea746d0e6931aF8940 | [View](https://bscscan.com/address/0xa3cCd778AE6a168c12538dea746d0e6931aF8940) |
| BlankImpl | 0x6fBDD895164a21E4D3acE64fb87276E038C727Dc | [View](https://bscscan.com/address/0x6fBDD895164a21E4D3acE64fb87276E038C727Dc) |
| AddressManager | 0x78B11198268619728E4b53c642E8d68941004c11 | [View](https://bscscan.com/address/0x78B11198268619728E4b53c642E8d68941004c11) |
| PremiumNumber | 0x1805eE5F34d7434FefCFf0CA2d2383E06823E6d8 | [View](https://bscscan.com/address/0x1805eE5F34d7434FefCFf0CA2d2383E06823E6d8) |
| PremiumNumberQuery | 0x86719c4337b8BF7d54aa73df7e3d460efD076405 | [View](https://bscscan.com/address/0x86719c4337b8BF7d54aa73df7e3d460efD076405) |

## Deployment Sequence & Constructor Arguments

### 1. PremiumRenderer
- No constructor arguments.

### 2. BlankImpl
- No constructor arguments.

### 3. AddressManager
- Constructor arguments:
  - `_renderer`: 0xa3cCd778AE6a168c12538dea746d0e6931aF8940 (PremiumRenderer)

### 4. PremiumNumber
- Constructor arguments:
  - `_addressManager`: 0x78B11198268619728E4b53c642E8d68941004c11 (AddressManager)
  - `_blankImpl`: 0x6fBDD895164a21E4D3acE64fb87276E038C727Dc (BlankImpl)

### 5. Initialization Call
- Called `AddressManager.setPremiumNumber(0x1805eE5F34d7434FefCFf0CA2d2383E06823E6d8)`
- Transaction Hash: 0xd7af5f2e2eb0700ad6fcaad3d2b60bf7ad7c9b52fc27f799a3032d891169c04d

### 6. PremiumNumberQuery
- Constructor arguments:
  - `_premiumNumber`: 0x1805eE5F34d7434FefCFf0CA2d2383E06823E6d8 (PremiumNumber)
  - `_addressManager`: 0x78B11198268619728E4b53c642E8d68941004c11 (AddressManager)

## Contract Dependencies

```
PremiumRenderer (Standalone)
BlankImpl (Standalone)
    └── AddressManager (Depends on PremiumRenderer)
        └── PremiumNumber (Depends on AddressManager + BlankImpl)
            └── PremiumNumberQuery (Depends on PremiumNumber + AddressManager)
```

## Contract Descriptions

| Contract | Function |
|----------|----------|
| IERC20 | ERC20 Standard Interface |
| PerfectAddress | Upgradeable Proxy Contract (EIP-1967 storage slots) |
| BlankImpl | Empty implementation contract used as the initial proxy implementation |
| PremiumRenderer | NFT metadata renderer, generates SVG images and JSON metadata |
| AddressManager | Address Management + ERC721 NFT, manages mined premium addresses |
| PremiumNumber | ERC20 Token (ADD), PoW mining mechanism, total supply 21 million |
| PremiumNumberQuery | Read-only query contract for batch information retrieval |
