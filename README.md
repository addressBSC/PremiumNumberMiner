# PremiumNumber (ADDRESS) Miner v2.0

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

### v9 与旧版差异

| 项目 | 旧版 (v1.0) | v9 (v2.0) |
|------|-------------|-----------|
| MIN_TRAILING_8S | 10 | **9** |
| 奖励机制 | 固定 10/20 ADDRESS | **初始 50 ADDRESS, 每 210,000 减半** |
| 合约地址 | 0x842B...7100 | **0x3c96...f146** |

## 文件清单

| 文件 | 作用 |
|------|------|
| `premium_miner.py` | 主程序 (GUI + 挖矿引擎) |
| `gpu_miner.py` | GPU OpenCL 内核 (被主程序调用) |
| `config.yaml` | 配置文件 (**填私钥后使用**) |
| `create2_pow.c` + `setup.py` | C 加速扩展源码 |
| `requirements.txt` | Python 依赖清单 |
| `build.bat` | **一键编译 .exe** |
| `icon.ico` / `icon_circle.png` | 图标 |

## 快速开始

### 方式 1: Python 直接运行

```bash
pip install -r requirements.txt

# (可选) 编译 C 加速扩展
python setup.py build_ext --inplace

# 编辑 config.yaml 填写私钥
# 运行
python premium_miner.py
```

### 方式 2: Windows .exe

双击 `build.bat`，编译完成后运行 `dist\PremiumNumberMiner.exe`。

### GPU 模式

在 `config.yaml` 中设置 `solver: gpu`，需要安装 `pyopencl`：
```bash
pip install pyopencl
```

## 配置说明

编辑 `config.yaml`：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `private_key` | 钱包私钥 | 必填 |
| `contract_address` | PremiumNumber 合约 | 0x3c96...f146 |
| `address_manager` | AddressManager 合约 | 0x65bd...A5f |
| `solver` | `cpu` 或 `gpu` | `cpu` |
| `gpu_batch_size` | GPU 每批 nonce 数 | 16000000 |
| `gpu_target_util` | GPU 占用率 (1-100) | 100 |
| `gas_limit` | Gas 上限 | 500000 |
| `min_trailing_8s` | 最少尾部 8 的数量 | **9** |
| `dry_run` | 试运行不花 gas | false |
