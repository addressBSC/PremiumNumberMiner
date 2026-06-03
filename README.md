# PremiumNumber (ADDRESS) Miner v2.0
[中文版本](./README_CN.md)

PremiumNumber v9 contract CREATE2 address mining program for BSC Mainnet. Features a GUI desktop interface and supports one-click compilation to Windows .exe.

## Contract Information (v9)
| Item | Value |
|------|-------|
| PremiumNumber | `0x3c96052e9229cB332aAc242C842eC911EA2Cf146` |
| AddressManager | `0x65bd4f1e959f9a6eD51505016f4d03069E386A5f` |
| PremiumNumberQuery | `0xcbC428bD46f66F0890d7cAef2A60d51bB630E33f` |
| Token | Address (ADDRESS), 18 Decimals |
| Max Supply | 21,000,000 ADDRESS |
| Network | BSC Mainnet (Chain ID: 56) |

## Mining Rules (v9 Changes)
| Rule | Description |
|------|-------------|
| **Mining Method** | Find a salt such that the CREATE2 generated address ends with >= **9** consecutive hex `8`s. |
| **Address Calculation** | `effectiveSalt = keccak256(miner ++ salt)`, `addr = CREATE2(deployer, effectiveSalt, bytecodeHash)` |
| **Reward Mechanism** | **Halving**: Starts at 50 ADDRESS, halves every 210,000 blocks. |
| **Restriction** | One mine per address per block. |

## Quick Start
Detailed instructions can be found in the [Deployment Guide](./docs/DEPLOYMENT.md).

### Method 1: Run with Python
```bash
pip install -r requirements.txt
python setup.py build_ext --inplace
# Edit config.yaml to fill in your private key
python premium_miner.py
```

### Method 2: Windows .exe
Double-click `build.bat`. After compilation, run `dist\PremiumNumberMiner.exe`.
