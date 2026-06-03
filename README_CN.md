# PremiumNumber (ADDRESS) Miner v2.0
[English Version](./README.md)

BSC 主网 PremiumNumber v9 合约 CREATE2 地址挖矿程序，带 GUI 桌面界面，支持一键编译为 Windows .exe。

## 合约信息 (v9)
| 项目 | 值 |
|------|------|
| PremiumNumber 合约 | `0x3c96052e9229cB332aAc242C842eC911EA2Cf146` |
| AddressManager 合约 | `0x65bd4f1e959f9a6eD51505016f4d03069E386A5f` |
| PremiumNumberQuery | `0xcbC428bD46f66F0890d7cAef2A60d51bB630E33f` |
| 代币 | Address (ADDRESS), 18 位精度 |
| 最大供应量 | 21,000,000 ADDRESS |
| 链 | BSC Mainnet (Chain ID: 56) |

## 挖矿规则 (v9 变更)
| 规则 | 说明 |
|------|------|
| **挖矿方式** | 找 salt 使得 CREATE2 生成的地址末尾有 >= **9** 个连续 hex `8` |
| **地址计算** | `effectiveSalt = keccak256(miner ++ salt)`, `addr = CREATE2(deployer, effectiveSalt, bytecodeHash)` |
| **奖励机制** | **减半制**: 初始 50 ADDRESS, 每 210,000 个减半 |
| **限制** | 每地址每区块只能挖一次 |

## 快速开始
请参考 [英文部署文档](./docs/DEPLOYMENT.md) 获取详细安装步骤。

### 方式 1: Python 直接运行
```bash
pip install -r requirements.txt
python setup.py build_ext --inplace
# 编辑 config.yaml 填写私钥
python premium_miner.py
```

### 方式 2: Windows .exe
双击 `build.bat`，编译完成后运行 `dist\PremiumNumberMiner.exe`。
