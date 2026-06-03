# BSC 主网合约部署报告

## 部署信息

| 项目 | 值 |
|------|-----|
| 网络 | BSC 主网 (Chain ID: 56) |
| 部署账户 | 0x038C66BDA2e892559295599c32d2C5831a448385 |
| 消耗 BNB | 0.000489534276242603 BNB |
| 编译器版本 | Solidity 0.8.20 |
| 优化 | 开启 (runs: 200, viaIR: true) |
| EVM 版本 | paris |

## 合约地址

| 合约名称 | 地址 | BscScan |
|----------|------|---------|
| PremiumRenderer | 0xa3cCd778AE6a168c12538dea746d0e6931aF8940 | [查看](https://bscscan.com/address/0xa3cCd778AE6a168c12538dea746d0e6931aF8940) |
| BlankImpl | 0x6fBDD895164a21E4D3acE64fb87276E038C727Dc | [查看](https://bscscan.com/address/0x6fBDD895164a21E4D3acE64fb87276E038C727Dc) |
| AddressManager | 0x78B11198268619728E4b53c642E8d68941004c11 | [查看](https://bscscan.com/address/0x78B11198268619728E4b53c642E8d68941004c11) |
| PremiumNumber | 0x1805eE5F34d7434FefCFf0CA2d2383E06823E6d8 | [查看](https://bscscan.com/address/0x1805eE5F34d7434FefCFf0CA2d2383E06823E6d8) |
| PremiumNumberQuery | 0x86719c4337b8BF7d54aa73df7e3d460efD076405 | [查看](https://bscscan.com/address/0x86719c4337b8BF7d54aa73df7e3d460efD076405) |

## 部署顺序与构造函数参数

### 1. PremiumRenderer
- 无构造函数参数

### 2. BlankImpl
- 无构造函数参数

### 3. AddressManager
- 构造函数参数:
  - `_renderer`: 0xa3cCd778AE6a168c12538dea746d0e6931aF8940 (PremiumRenderer)

### 4. PremiumNumber
- 构造函数参数:
  - `_addressManager`: 0x78B11198268619728E4b53c642E8d68941004c11 (AddressManager)
  - `_blankImpl`: 0x6fBDD895164a21E4D3acE64fb87276E038C727Dc (BlankImpl)

### 5. 初始化调用
- 调用 `AddressManager.setPremiumNumber(0x1805eE5F34d7434FefCFf0CA2d2383E06823E6d8)`
- 交易哈希: 0xd7af5f2e2eb0700ad6fcaad3d2b60bf7ad7c9b52fc27f799a3032d891169c04d

### 6. PremiumNumberQuery
- 构造函数参数:
  - `_premiumNumber`: 0x1805eE5F34d7434FefCFf0CA2d2383E06823E6d8 (PremiumNumber)
  - `_addressManager`: 0x78B11198268619728E4b53c642E8d68941004c11 (AddressManager)

## 合约依赖关系

```
PremiumRenderer (独立)
BlankImpl (独立)
    └── AddressManager (依赖 PremiumRenderer)
        └── PremiumNumber (依赖 AddressManager + BlankImpl)
            └── PremiumNumberQuery (依赖 PremiumNumber + AddressManager)
```

## 合约功能说明

| 合约 | 功能 |
|------|------|
| IERC20 | ERC20 标准接口 |
| PerfectAddress | 可升级代理合约 (EIP-1967 存储槽) |
| BlankImpl | 空实现合约，用作代理的初始实现 |
| PremiumRenderer | NFT 元数据渲染器，生成 SVG 图片和 JSON 元数据 |
| AddressManager | 地址管理 + ERC721 NFT，管理挖掘到的靓号地址 |
| PremiumNumber | ERC20 代币 (ADD)，PoW 挖矿机制，总量 2100 万 |
| PremiumNumberQuery | 只读查询合约，批量查询全局信息和钱包详情 |
