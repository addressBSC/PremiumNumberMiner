#!/usr/bin/env python3
"""
PremiumNumber (ADD) Miner v3.1 — CREATE2 地址挖矿 + GUI
适配 PremiumNumber v3.1 合约 (BSC Mainnet)

合约地址:
  PremiumNumber: 0x1805eE5F34d7434FefCFf0CA2d2383E06823E6d8
  AddressManager: 0x78B11198268619728E4b53c642E8d68941004c11

挖矿规则:
  - 找 salt 使得 CREATE2 生成的地址满足:
    尾部 digit (0-9) 连续重复 >= requiredRun 次
    **或**
    开头 digit (0-9) 连续重复 >= requiredRun 次
    (取 streak 更大者)
  - requiredRun 由合约 owner 设置 (范围: RUN_MIN=9 ~ RUN_MAX=20)
  - effectiveSalt = keccak256(miner ++ salt)
  - addr = CREATE2(deployer, effectiveSalt, bytecodeHash)
  - 奖励: 动态, 基于窗口频率, 随供应量减半
  - 最大供应量 21,000,000 ADD (18位精度)
  - 支持 CPU 多进程 / GPU OpenCL
"""

import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import multiprocessing
import time
import json
import os
import sys
import random
import base64
import signal
from datetime import datetime

# Third-party imports
try:
    from web3 import Web3
    from eth_account import Account
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "web3", "eth-account"])
    from web3 import Web3
    from eth_account import Account

try:
    from web3.middleware import ExtraDataToPOAMiddleware as _POA
except Exception:
    from web3.middleware import geth_poa_middleware as _POA

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from Crypto.Hash import keccak as _pycryptodome_keccak
    def _fast_keccak256(data):
        return _pycryptodome_keccak.new(digest_bits=256, data=data).digest()
    KECCAK_ENGINE = "pycryptodome"
except ImportError:
    def _fast_keccak256(data):
        return bytes(Web3.keccak(data))
    KECCAK_ENGINE = "web3 (slow)"

# ─── Constants (适配 v3 合约) ─────────────────────────────────────────────────

CONTRACT_ADDRESS = "0x1805eE5F34d7434FefCFf0CA2d2383E06823E6d8"
ADDRESS_MANAGER  = "0x78B11198268619728E4b53c642E8d68941004c11"
DEFAULT_RPC = "https://bsc-dataseed.bnbchain.org"
CONFIG_FILE = "miner_config.json"
HISTORY_FILE = "mining_history.json"
YAML_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

IS_WINDOWS = (os.name == "nt")

# 新合约挖矿参数
RUN_MIN = 9
RUN_MAX = 20
INITIAL_REWARD = 50
MAX_SUPPLY = 21_000_000

CONTRACT_ABI = json.loads('''[
    {"inputs": [{"name": "salt", "type": "uint256"}], "name": "mine", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "saltList", "type": "uint256[]"}], "name": "mineBatch", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "miner", "type": "address"}, {"name": "salt", "type": "uint256"}], "name": "computeAddress", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "addr", "type": "address"}], "name": "checkAddress", "outputs": [{"type": "uint256"}, {"type": "uint256"}, {"type": "uint256"}, {"type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "walletBytecodeHash", "outputs": [{"type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalSupply", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "currentReward", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "era", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "requiredRun", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "RUN_MIN", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "RUN_MAX", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "MAX_SUPPLY", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalMined", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalMinted", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "windowCount", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "effectiveSalt", "type": "uint256"}], "name": "computeAddressByEffectiveSalt", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "addressManager", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"}
]''')

DEFAULT_RPC_LIST = [
    "https://bsc.rpc.blxrbdn.com",
    "https://1rpc.io/bnb",
    "https://binance.nodereal.io",
    "https://bsc-mainnet.public.blastapi.io",
    "https://bsc-dataseed.bnbchain.org",
]


def calc_mining_reward(token_id):
    return 0  # 使用合约 currentReward() 查询


# ─── YAML 配置加载 ────────────────────────────────────────────────────────────

def load_yaml_config():
    defaults = {
        "private_key": "",
        "contract_address": CONTRACT_ADDRESS,
        "address_manager": ADDRESS_MANAGER,
        "chain_id": 56,
        "use_network_gas": True,
        "network_gas_multiplier": 1.0,
        "min_gas_price_gwei": 0.01,
        "max_gas_price_gwei": 5,
        "gas_price_gwei": 0.05,
        "gas_limit": 2200000,
        "solver": "cpu",
        "gpu_device": "",
        "gpu_target_util": 100,
        "gpu_batch_size": 16000000,
        "relay_urls": [],
        "dry_run": False,
        "verbose_logs": False,
        "min_trailing_8s": RUN_MIN,
    }
    if HAS_YAML and os.path.exists(YAML_CONFIG_FILE):
        try:
            with open(YAML_CONFIG_FILE, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            defaults.update(cfg)
        except Exception:
            pass
    return defaults


# ─── RPC / Gas 工具 ──────────────────────────────────────────────────────────

def select_best_rpc(rpc_urls, on_log=None):
    best, best_lat = None, None
    for url in rpc_urls:
        try:
            t0 = time.time()
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 6}))
            if not w3.is_connected():
                if on_log: on_log(f"  {url}  连接失败")
                continue
            _ = w3.eth.block_number
            lat = (time.time() - t0) * 1000
            if on_log: on_log(f"  {url}  {lat:.0f}ms")
            if best_lat is None or lat < best_lat:
                best, best_lat = url, lat
        except Exception as e:
            if on_log: on_log(f"  {url}  失败: {str(e)[:40]}")
    return best, best_lat


def gas_price_wei(w3, cfg):
    try:
        net = w3.eth.gas_price
    except Exception:
        net = Web3.to_wei(float(cfg.get("gas_price_gwei", 0.05)), "gwei")
    if cfg.get("use_network_gas", True):
        g = int(net * float(cfg.get("network_gas_multiplier", 1.0)))
        lo = Web3.to_wei(float(cfg.get("min_gas_price_gwei", 0.01)), "gwei")
        hi = Web3.to_wei(float(cfg.get("max_gas_price_gwei", 5)), "gwei")
        return max(lo, min(g, hi))
    return Web3.to_wei(float(cfg.get("gas_price_gwei", 0.05)), "gwei")


# ─── CREATE2 地址计算工具 ────────────────────────────────────────────────────

def compute_effective_salt(miner_bytes, salt):
    """effectiveSalt = keccak256(miner(20) ++ salt(uint256, 32 bytes BE))"""
    salt_be = salt.to_bytes(32, "big")
    return _fast_keccak256(miner_bytes + salt_be)


def compute_create2_address(deployer_bytes, effective_salt, bytecode_hash):
    """addr = keccak256(0xff ++ deployer(20) ++ effectiveSalt(32) ++ bytecodeHash(32))[12:]"""
    data = b'\xff' + deployer_bytes + effective_salt + bytecode_hash
    h = _fast_keccak256(data)
    return h[12:]  # 20 bytes


def count_trailing_digit(addr_bytes):
    val = int.from_bytes(addr_bytes, "big")
    digit = val & 0xf
    count = 0
    for _ in range(40):
        if (val & 0xf) == digit:
            count += 1
            val >>= 4
        else:
            break
    return digit, count

def count_leading_digit(addr_bytes):
    val = int.from_bytes(addr_bytes, "big")
    digit = (val >> 156) & 0xf
    count = 0
    for i in range(40):
        shift = (39 - i) * 4
        if ((val >> shift) & 0xf) == digit:
            count += 1
        else:
            break
    return digit, count

def count_total_digit(addr_bytes, digit):
    val = int.from_bytes(addr_bytes, "big")
    count = 0
    for _ in range(40):
        if (val & 0xf) == digit:
            count += 1
        val >>= 4
    return count

def check_address_valid(addr_bytes, required_run=9):
    tDigit, trailing = count_trailing_digit(addr_bytes)
    lDigit, leading = count_leading_digit(addr_bytes)
    tOk = tDigit <= 9 and trailing >= required_run
    lOk = lDigit <= 9 and leading >= required_run
    valid = tOk or lOk
    if not valid:
        return False, trailing, leading, 0, tDigit, 0
    if tOk and (not lOk or trailing >= leading):
        digit = tDigit
        streak = trailing
    else:
        digit = lDigit
        streak = leading
    total = count_total_digit(addr_bytes, digit)
    return True, trailing, leading, total, digit, streak


def fmt_hashrate(rate):
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:.2f} MH/s"
    if rate >= 1_000:
        return f"{rate / 1_000:.2f} KH/s"
    return f"{rate:.0f} H/s"


# ─── CPU 多进程求解 ─────────────────────────────────────────────────────────

def cpu_worker(wid, num_workers, miner_bytes_raw, deployer_bytes_raw, bytecode_hash_raw,
               stop_event, result_q):
    """CPU 工作进程: 扫描 salt 找合格地址."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    from Crypto.Hash import keccak as _kc
    miner_b = bytes(miner_bytes_raw)
    deployer_b = bytes(deployer_bytes_raw)
    bch = bytes(bytecode_hash_raw)
    BATCH = 4096

    base_salt = random.getrandbits(64)
    salt = (base_salt + wid) & ((1 << 64) - 1)
    step = num_workers

    while not stop_event.is_set():
        for _ in range(BATCH):
            salt_be = salt.to_bytes(32, "big")
            k1 = _kc.new(digest_bits=256)
            k1.update(miner_b + salt_be)
            esalt = k1.digest()

            k2 = _kc.new(digest_bits=256)
            k2.update(b'\xff' + deployer_b + esalt + bch)
            addr_hash = k2.digest()
            addr_b = addr_hash[12:]

            val = int.from_bytes(addr_b, "big")

            # trailing run
            tDigit = val & 0xf
            tc = 0
            if tDigit <= 9:
                tv = val
                for _ in range(40):
                    if (tv & 0xf) == tDigit:
                        tc += 1
                        tv >>= 4
                    else:
                        break

            # leading run
            lDigit = (val >> 156) & 0xf
            lc = 0
            if lDigit <= 9:
                for i in range(40):
                    shift = (39 - i) * 4
                    if ((val >> shift) & 0xf) == lDigit:
                        lc += 1
                    else:
                        break

            if (tc >= 9) or (lc >= 9):
                result_q.put((salt, max(tc, lc), esalt, addr_b))
                while not stop_event.is_set():
                    time.sleep(0.1)
                    if result_q.empty():
                        break
                break

            salt = (salt + step) & ((1 << 64) - 1)


def resolve_workers(cfg):
    cores = os.cpu_count() or 4
    try:
        pct = float(cfg.get("cpu_percent", 0) or 0)
    except (TypeError, ValueError):
        pct = 0
    if pct > 0:
        return max(1, round(cores * pct / 100))
    w = cfg.get("workers", "auto")
    if isinstance(w, int):
        return max(1, w)
    if isinstance(w, str) and w.isdigit():
        return max(1, int(w))
    return max(1, cores // 2)


# ─── 挖矿引擎 ───────────────────────────────────────────────────────────────

class MiningEngine:
    """PremiumNumber v3 挖矿引擎: CPU 或 GPU."""
    def __init__(self, cfg, on_log=None, on_win=None, on_lose=None, on_stats=None):
        self.cfg = cfg
        self.on_log = on_log or (lambda msg, lv="INFO": None)
        self.on_win = on_win or (lambda salt, count, addr, reward_str: None)
        self.on_lose = on_lose or (lambda: None)
        self.on_stats = on_stats or (lambda s: None)
        self.running = False
        self.dry = bool(os.environ.get("DRY_RUN")) or bool(cfg.get("dry_run", False))
        self.verbose = bool(cfg.get("verbose_logs", False))

        # Web3
        setup_rpc = (cfg.get("rpc_urls") or DEFAULT_RPC_LIST)[0]
        self.w3 = Web3(Web3.HTTPProvider(setup_rpc, request_kwargs={"timeout": 8}))
        try:
            self.w3.middleware_onion.inject(_POA, layer=0)
        except Exception:
            try:
                self.w3.middleware_onion.inject(_POA(self.w3), layer=0)
            except Exception:
                pass

        pk = cfg.get("_pk") or cfg.get("private_key", "")
        if not pk.startswith("0x"):
            pk = "0x" + pk
        self.acct = self.w3.eth.account.from_key(pk)
        self.me = self.acct.address
        self.miner_bytes = bytes.fromhex(self.me[2:])

        self.contract_addr = Web3.to_checksum_address(
            cfg.get("contract_address", CONTRACT_ADDRESS))
        self.chain_id = int(cfg.get("chain_id", 56))
        self.gas_limit = int(cfg.get("gas_limit", 500000))
        self.c = self.w3.eth.contract(address=self.contract_addr, abi=CONTRACT_ABI)

        # 获取合约参数
        self.bytecode_hash = self.c.functions.walletBytecodeHash().call()
        self.deployer_bytes = bytes.fromhex(self.contract_addr[2:])
        try:
            self.required_run = self.c.functions.requiredRun().call()
        except Exception:
            self.required_run = RUN_MIN

        # 获取当前奖励信息
        try:
            self.current_reward_wei = self.c.functions.currentReward().call()
            self.current_era = self.c.functions.era().call()
            total_mined = self.c.functions.totalMined().call()
            self.on_log(f"当前纪元: {self.current_era}  "
                        f"当前奖励: {Web3.from_wei(self.current_reward_wei, 'ether')} ADD  "
                        f"已挖: {total_mined} 个"
                        f"  requiredRun: {self.required_run}")
        except Exception as e:
            self.on_log(f"读取奖励信息失败: {str(e)[:60]}")
            self.current_reward_wei = 0
            self.current_era = 0

        self.gas_wei = gas_price_wei(self.w3, cfg)
        self.nonce = self.w3.eth.get_transaction_count(self.me, "pending")
        self.nlock = threading.Lock()

        # 统计
        self.sent = 0
        self.won = 0
        self.lost = 0
        self.total_scanned = 0
        self.start_time = time.time()

        # 求解器模式
        self.mode = str(cfg.get("solver", "cpu")).lower()
        if self.mode not in ("cpu", "gpu"):
            self.mode = "cpu"
        self.gpu = None

        if self.mode == "gpu":
            try:
                from gpu_miner import GpuMiner
                self.gpu = GpuMiner(cfg)
                self.on_log(f"求解器: GPU {self.gpu.device_name}  batch={self.gpu.batch_size}")
            except Exception as e:
                self.on_log(f"GPU 不可用, 退回 CPU: {str(e)[:70]}")
                self.mode = "cpu"

        if self.mode == "cpu":
            n_workers = resolve_workers(cfg)
            self.on_log(f"求解器: CPU ({n_workers} 进程)")
            self.n_workers = n_workers

        self.on_log(f"合约: {self.contract_addr}")
        self.on_log(f"bytecodeHash: 0x{self.bytecode_hash.hex()[:16]}...")
        self.on_log(f"requiredRun: {self.required_run} (范围 {RUN_MIN}-{RUN_MAX})  Keccak 引擎: {KECCAK_ENGINE}")
        self.on_log(f"钱包: {self.me}")

    def start(self):
        self.running = True
        threading.Thread(target=self._mine_thread, daemon=True).start()
        threading.Thread(target=self._stats_loop, daemon=True).start()

    def stop(self):
        self.running = False

    def _mine_thread(self):
        while self.running:
            try:
                if self.mode == "gpu":
                    self._gpu_mine_round()
                else:
                    self._cpu_mine_round()
            except Exception as e:
                self.on_log(f"挖矿异常: {str(e)[:80]}")
                time.sleep(5)

    def _gpu_mine_round(self):
        batch = self.gpu.batch_size
        base_salt = random.getrandbits(64)
        nonce = base_salt & ((1 << 48) - 1)
        round_start = time.time()
        round_scanned = 0
        last_log = 0

        while self.running:
            result = self.gpu.search(self.miner_bytes, self.deployer_bytes,
                                     self.bytecode_hash, nonce, batch)
            round_scanned += batch
            self.total_scanned += batch

            now = time.time()
            if now - last_log >= 5:
                rate = round_scanned / (now - round_start) if now > round_start else 0
                self.on_log(f"算力: {fmt_hashrate(rate):>10}  "
                            f"已扫描: {round_scanned:>8}  "
                            f"总扫描: {self.total_scanned:>8}  "
                            f"耗时: {now - round_start:.0f}s")
                last_log = now

            if result is not None:
                salt, count = result
                esalt = compute_effective_salt(self.miner_bytes, salt)
                addr_bytes = compute_create2_address(self.deployer_bytes, esalt, self.bytecode_hash)
                valid, trailing, leading, total, digit, streak = check_address_valid(addr_bytes, self.required_run)

                if valid:
                    addr_hex = "0x" + addr_bytes.hex()
                    elapsed = time.time() - round_start
                    rate = round_scanned / elapsed if elapsed > 0 else 0
                    self.on_log(f"找到! salt={salt} 地址={addr_hex[:16]}... "
                                f"digit={digit} streak={streak} 尾部={trailing} 开头={leading} 总数={total} 算力={fmt_hashrate(rate)}")
                    self._submit(salt, streak, addr_hex)
                    return
                else:
                    self.on_log(f"GPU 候选 salt={salt} 复核不通过 "
                                f"(digit={digit} trailing={trailing} leading={leading} total={total}), 继续")

            nonce += batch

    def _cpu_mine_round(self):
        if IS_WINDOWS:
            ctx = multiprocessing.get_context("spawn")
        else:
            try:
                ctx = multiprocessing.get_context("fork")
            except ValueError:
                ctx = multiprocessing.get_context()

        stop_event = ctx.Event()
        result_q = ctx.Queue()
        procs = []

        for wid in range(self.n_workers):
            p = ctx.Process(
                target=cpu_worker,
                args=(wid, self.n_workers, self.miner_bytes, self.deployer_bytes,
                      self.bytecode_hash, stop_event, result_q),
                daemon=True)
            p.start()
            procs.append(p)

        round_start = time.time()
        last_log = 0
        try:
            while self.running:
                now = time.time()
                if now - last_log >= 5:
                    self.on_log(f"CPU 挖矿中...  "
                                f"已发送: {self.sent}  成功: {self.won}  失败: {self.lost}  "
                                f"耗时: {now - round_start:.0f}s")
                    last_log = now

                try:
                    salt, count, esalt_bytes, addr_bytes = result_q.get(timeout=1.0)
                except Exception:
                    continue

                esalt_verify = compute_effective_salt(self.miner_bytes, salt)
                addr_verify = compute_create2_address(self.deployer_bytes, esalt_verify, self.bytecode_hash)
                valid, trailing, leading, total, digit, streak = check_address_valid(addr_verify, self.required_run)

                if valid:
                    addr_hex = "0x" + addr_verify.hex()
                    elapsed = time.time() - round_start
                    self.on_log(f"找到! salt={salt} 地址={addr_hex[:16]}... "
                                f"digit={digit} streak={streak} 尾部={trailing} 开头={leading} 总数={total} 耗时={elapsed:.1f}s")
                    self._submit(salt, streak, addr_hex)
                    break
        finally:
            stop_event.set()
            for p in procs:
                p.join(timeout=3)
                if p.is_alive():
                    p.terminate()

    def _submit(self, salt, count, addr_hex):
        """提交 mine(salt) 交易."""
        # 刷新当前奖励
        try:
            reward_wei = self.c.functions.currentReward().call()
            reward_str = f"{Web3.from_wei(reward_wei, 'ether'):.4f} ADD"
        except Exception:
            reward_str = "unknown"
        self.on_log(f"预期奖励: {reward_str} (streak={count})")

        if self.dry:
            self.on_log(f"[DRY] 试运行, 不提交 (salt={salt})")
            self.won += 1
            self.on_win(salt, count, addr_hex, reward_str)
            return

        # 模拟
        try:
            self.c.functions.mine(salt).call({"from": self.me})
        except Exception as e:
            self.on_log(f"模拟失败: {str(e)[:80]}")
            self.lost += 1
            self.on_lose()
            return

        # 发送交易
        try:
            self.gas_wei = gas_price_wei(self.w3, self.cfg)
            with self.nlock:
                tx_nonce = self.nonce
                self.nonce += 1

            tx = self.c.functions.mine(salt).build_transaction({
                "from": self.me,
                "nonce": tx_nonce,
                "gas": self.gas_limit,
                "gasPrice": self.gas_wei,
                "chainId": self.chain_id,
            })
            signed = self.acct.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            self.sent += 1
            self.on_log(f"交易已发送: {tx_hash.hex()[:20]}...")

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 1:
                cost = Web3.from_wei(receipt.gasUsed * self.gas_wei, "ether")
                self.won += 1
                self.on_log(f"Mine 成功! 区块={receipt.blockNumber} "
                            f"Gas={receipt.gasUsed} 花费={cost} BNB")
                self.on_win(salt, count, addr_hex, reward_str)
            else:
                self.lost += 1
                self.on_log("Mine 失败 (reverted)")
                self.on_lose()
        except Exception as e:
            self.lost += 1
            self.on_log(f"提交异常: {str(e)[:80]}")
            self.on_lose()
            try:
                chain_n = self.w3.eth.get_transaction_count(self.me, "pending")
                with self.nlock:
                    self.nonce = chain_n
            except Exception:
                pass

    def _stats_loop(self):
        while self.running:
            time.sleep(5)
            el = time.time() - self.start_time
            settled = self.won + self.lost
            wr = (self.won / settled * 100) if settled else 0
            rate = self.total_scanned / el if el > 0 else 0
            stats = {
                "elapsed": el, "sent": self.sent, "won": self.won,
                "lost": self.lost, "win_rate": wr,
                "hashrate": rate,
                "mode": self.mode.upper(),
                "total_scanned": self.total_scanned,
            }
            self.on_stats(stats)


# ─── 配色 ──────────────────────────────────────────────────────────────────

COLORS = {
    'bg':           '#0d1117',
    'bg_card':      '#161b22',
    'bg_card2':     '#1c2333',
    'bg_input':     '#0d1117',
    'bg_hover':     '#21262d',
    'accent':       '#00d4aa',
    'accent_dark':  '#00b894',
    'green':        '#3fb950',
    'green_dim':    '#238636',
    'red':          '#f85149',
    'red_dim':      '#da3633',
    'blue':         '#58a6ff',
    'purple':       '#bc8cff',
    'text':         '#e6edf3',
    'text2':        '#8b949e',
    'text3':        '#484f58',
    'border':       '#30363d',
    'border_light': '#3d444d',
    'white':        '#ffffff',
    'black':        '#000000',
}

# ─── 国际化 ──────────────────────────────────────────────────────────────────

LANG = {
    'en': {
        'title': 'PremiumNumber Miner',
        'subtitle': 'BSC CREATE2 Address Mining (v2)',
        'tab_wallet': 'Wallet',
        'tab_mine': 'Mine',
        'tab_history': 'History',
        'tab_settings': 'Settings',
        'connection': 'Connection',
        'rpc_url': 'RPC Endpoint',
        'private_key': 'Private Key',
        'show': 'Show', 'hide': 'Hide',
        'connect': 'Connect Wallet',
        'disconnect': 'Disconnect',
        'wallet_overview': 'Wallet Overview',
        'address': 'Address',
        'bnb_balance': 'BNB Balance',
        'addr_balance': 'ADDRESS Balance',
        'total_mined': 'Total Mined',
        'current_reward': 'Current Reward',
        'current_era': 'Current Era',
        'total_supply': 'Total Supply',
        'refresh': 'Refresh',
        'mining_dashboard': 'Mining Dashboard',
        'start_mining': 'Start Mining',
        'stop_mining': 'Stop Mining',
        'mining_log': 'Mining Log',
        'clear_log': 'Clear',
        'time': 'Time', 'salt': 'Salt', 'reward': 'Reward',
        'tx_hash': 'TX Hash', 'status': 'Status',
        'gas_settings': 'Gas Settings',
        'gas_price': 'Gas Price (Gwei)',
        'gas_limit': 'Gas Limit',
        'contract': 'Contract Address',
        'save_settings': 'Save Settings',
        'about': 'About',
        'about_text': (
            "PremiumNumber (ADD) Miner v3.1\n"
            "Adapted for PremiumNumber v3.1 Contract\n"
            "Mining: trailing-or-leading digit (0-9) repeated >= requiredRun\n"
            "requiredRun set by contract owner (range 9-20)\n"
            "Rewards: Dynamic, based on window frequency\n"
            "Max Supply: 21,000,000 ADD (18 decimals)\n"
            "Chain: BSC Mainnet\n"
            "Contract: 0x1805...E6d8"
        ),
        'not_connected': 'Disconnected',
        'connected': 'Connected',
        'success': 'Success', 'failed': 'Failed', 'error': 'Error',
        'no_history': 'No mining history yet',
        'mining_started': 'CREATE2 address mining started...',
        'mining_stopped': 'Mining stopped',
        'connect_first': 'Please connect wallet first',
        'enter_rpc': 'Please enter RPC URL',
        'enter_pk': 'Please enter private key',
        'conn_failed': 'Connection failed',
        'settings_saved': 'Settings saved',
        'copy': 'Copy', 'copied': 'Copied!',
        'mining_active': 'MINING ACTIVE',
        'mining_idle': 'IDLE',
        'history_title': 'Mining History',
        'no_records': 'No records yet. Start mining to see results here.',
        'save_pk': 'Save Private Key Locally',
        'save_pk_tip': '(Base64 obfuscated, not plaintext)',
        'hashrate': 'Hashrate',
        'solver_mode': 'Solver Mode',
        'win_rate': 'Win Rate',
        'sent_count': 'TX Sent',
        'won_count': 'Won',
        'lost_count': 'Lost',
    },
    'zh': {
        'title': 'PremiumNumber 矿机',
        'subtitle': 'BSC CREATE2 地址挖矿 (v2)',
        'tab_wallet': '钱包',
        'tab_mine': '挖矿',
        'tab_history': '记录',
        'tab_settings': '设置',
        'connection': '连接设置',
        'rpc_url': 'RPC 节点',
        'private_key': '私钥',
        'show': '显示', 'hide': '隐藏',
        'connect': '连接钱包',
        'disconnect': '断开连接',
        'wallet_overview': '钱包总览',
        'address': '地址',
        'bnb_balance': 'BNB 余额',
        'addr_balance': 'ADDRESS 余额',
        'total_mined': '已挖数量',
        'current_reward': '当前奖励',
        'current_era': '当前纪元',
        'total_supply': '总供应量',
        'refresh': '刷新',
        'mining_dashboard': '挖矿面板',
        'start_mining': '开始挖矿',
        'stop_mining': '停止挖矿',
        'mining_log': '挖矿日志',
        'clear_log': '清除',
        'time': '时间', 'salt': 'Salt', 'reward': '奖励',
        'tx_hash': '交易哈希', 'status': '状态',
        'gas_settings': 'Gas 设置',
        'gas_price': 'Gas 价格 (Gwei)',
        'gas_limit': 'Gas 上限',
        'contract': '合约地址',
        'save_settings': '保存设置',
        'about': '关于',
        'about_text': (
            "PremiumNumber (ADD) 矿机 v3.1\n"
            "适配 PremiumNumber v3.1 合约\n"
            "挖矿: 尾部或开头 digit (0-9) 连续 >= requiredRun\n"
            "requiredRun 由合约 owner 设置 (范围 9-20)\n"
            "奖励: 动态, 基于窗口频率\n"
            "最大供应量: 21,000,000 ADD (18位精度)\n"
            "链: BSC 主网\n"
            "合约: 0x1805...E6d8"
        ),
        'not_connected': '未连接',
        'connected': '已连接',
        'success': '成功', 'failed': '失败', 'error': '错误',
        'no_history': '暂无挖矿记录',
        'mining_started': 'CREATE2 地址挖矿已启动...',
        'mining_stopped': '挖矿已停止',
        'connect_first': '请先连接钱包',
        'enter_rpc': '请输入 RPC 地址',
        'enter_pk': '请输入私钥',
        'conn_failed': '连接失败',
        'settings_saved': '设置已保存',
        'copy': '复制', 'copied': '已复制!',
        'mining_active': '挖矿中',
        'mining_idle': '空闲',
        'history_title': '挖矿记录',
        'no_records': '暂无记录。开始挖矿后将在此显示结果。',
        'save_pk': '保存私钥到本地',
        'save_pk_tip': '(Base64 混淆存储，非明文)',
        'hashrate': '算力',
        'solver_mode': '求解模式',
        'win_rate': '胜率',
        'sent_count': '已发送',
        'won_count': '成功',
        'lost_count': '失败',
    }
}


# ─── Icon ──────────────────────────────────────────────────────────────────

def get_icon_path():
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'icon_circle.png')


# ─── GUI 主程序 ──────────────────────────────────────────────────────────────

class PremiumNumberMinerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PremiumNumber Miner v3.0")
        self.root.geometry("980x780")
        self.root.minsize(880, 680)
        self.root.configure(bg=COLORS['bg'])

        self.w3 = None
        self.contract = None
        self.account = None
        self.miner = None
        self.mining = False
        self.history = []
        self.cur_lang = 'zh'
        self.i18n_widgets = []
        self.start_time = None
        self.logo_img = None
        self.logo_img_small = None
        self.yaml_cfg = load_yaml_config()

        try:
            ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
            if os.path.exists(ico_path):
                self.root.iconbitmap(ico_path)
        except:
            pass

        self._load_config()
        self._load_history()
        self._load_logo()
        self._build_ui()

    def _load_logo(self):
        if not HAS_PIL:
            return
        try:
            icon_path = get_icon_path()
            if os.path.exists(icon_path):
                img = Image.open(icon_path).convert("RGBA")
                self.logo_img = ImageTk.PhotoImage(img.resize((42, 42), Image.LANCZOS))
                self.logo_img_small = ImageTk.PhotoImage(img.resize((24, 24), Image.LANCZOS))
        except:
            pass

    def t(self, key):
        return LANG[self.cur_lang].get(key, key)

    def _register_i18n(self, widget, key, attr='text'):
        self.i18n_widgets.append((widget, key, attr))

    def _apply_lang(self):
        for widget, key, attr in self.i18n_widgets:
            try:
                widget.config(**{attr: self.t(key)})
            except:
                pass
        if self.mining:
            self.mine_btn.config(text=self.t('stop_mining'))
            self.mining_status_label.config(text=self.t('mining_active'), fg=COLORS['green'])
        else:
            self.mine_btn.config(text=self.t('start_mining'))
            self.mining_status_label.config(text=self.t('mining_idle'), fg=COLORS['text3'])
        self._update_status_display()

    def _toggle_lang(self):
        self.cur_lang = 'zh' if self.cur_lang == 'en' else 'en'
        self.lang_btn.config(text='EN' if self.cur_lang == 'zh' else u'中文')
        self._apply_lang()

    @staticmethod
    def _obfuscate_key(pk):
        if not pk: return ""
        return base64.b64encode(pk.encode('utf-8')).decode('utf-8')

    @staticmethod
    def _deobfuscate_key(obf):
        if not obf: return ""
        try:
            return base64.b64decode(obf.encode('utf-8')).decode('utf-8')
        except Exception:
            return obf

    def _load_config(self):
        self.config = {"rpc": DEFAULT_RPC, "gas_price": "0.05", "gas_limit": "2200000",
                        "private_key_saved": "", "save_private_key": False}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE) as f:
                    self.config.update(json.load(f))
            except:
                pass

    def _save_config(self):
        pk_to_save = ""
        save_pk = self.save_pk_var.get() if hasattr(self, 'save_pk_var') else False
        if save_pk and hasattr(self, 'pk_var'):
            pk_to_save = self._obfuscate_key(self.pk_var.get().strip())
        to_save = {
            "rpc": self.rpc_var.get(),
            "gas_price": self.gas_price_var.get(),
            "gas_limit": self.gas_limit_var.get(),
            "save_private_key": save_pk,
            "private_key_saved": pk_to_save,
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(to_save, f)
        self._show_toast(self.t('settings_saved'))

    def _load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE) as f:
                    self.history = json.load(f)
            except:
                self.history = []

    def _save_history(self):
        with open(HISTORY_FILE, "w") as f:
            json.dump(self.history[-200:], f, indent=2)

    def _show_toast(self, msg, duration=3000):
        toast = tk.Frame(self.root, bg=COLORS['bg_card'], highlightbackground=COLORS['accent'],
                         highlightthickness=1)
        inner = tk.Label(toast, text=f"  {msg}  ", bg=COLORS['bg_card'], fg=COLORS['accent'],
                         font=('Segoe UI', 11, 'bold'), padx=20, pady=10)
        inner.pack()
        toast.place(relx=0.5, y=60, anchor='n')
        self.root.after(duration, toast.destroy)

    def _build_ui(self):
        self.main_container = tk.Frame(self.root, bg=COLORS['bg'])
        self.main_container.pack(fill='both', expand=True)
        self._build_sidebar()
        self._build_content_area()
        self._build_panels()
        self._show_panel('wallet')

    def _build_sidebar(self):
        self.sidebar = tk.Frame(self.main_container, bg=COLORS['bg_card'], width=220)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)

        logo_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], pady=20, padx=16)
        logo_frame.pack(fill='x')
        logo_row = tk.Frame(logo_frame, bg=COLORS['bg_card'])
        logo_row.pack(anchor='center')
        if self.logo_img:
            tk.Label(logo_row, image=self.logo_img, bg=COLORS['bg_card']).pack(side='left', padx=(0, 10))
        title_col = tk.Frame(logo_row, bg=COLORS['bg_card'])
        title_col.pack(side='left')
        title_lbl = tk.Label(title_col, text=self.t('title'), font=('Segoe UI', 12, 'bold'),
                              fg=COLORS['white'], bg=COLORS['bg_card'])
        title_lbl.pack(anchor='w')
        self._register_i18n(title_lbl, 'title')
        subtitle_lbl = tk.Label(title_col, text=self.t('subtitle'), font=('Segoe UI', 8),
                                 fg=COLORS['text3'], bg=COLORS['bg_card'])
        subtitle_lbl.pack(anchor='w')
        self._register_i18n(subtitle_lbl, 'subtitle')

        tk.Frame(self.sidebar, bg=COLORS['border'], height=1).pack(fill='x', padx=16)

        self.status_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], padx=16, pady=12)
        self.status_frame.pack(fill='x')
        status_row = tk.Frame(self.status_frame, bg=COLORS['bg_card'])
        status_row.pack(fill='x')
        self.status_dot = tk.Canvas(status_row, width=10, height=10, bg=COLORS['bg_card'],
                                     highlightthickness=0)
        self.status_dot.pack(side='left', padx=(0, 8))
        self.status_dot.create_oval(1, 1, 9, 9, fill=COLORS['red_dim'], outline='')
        self.status_label = tk.Label(status_row, text=self.t('not_connected'),
                                      font=('Segoe UI', 9), fg=COLORS['text2'], bg=COLORS['bg_card'])
        self.status_label.pack(side='left')

        tk.Frame(self.sidebar, bg=COLORS['border'], height=1).pack(fill='x', padx=16)

        nav_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], pady=8)
        nav_frame.pack(fill='x')
        self.tab_buttons = {}
        tabs = [('wallet', 'tab_wallet', '\u229a'), ('mine', 'tab_mine', '\u26cf'),
                ('history', 'tab_history', '\u2630'), ('settings', 'tab_settings', '\u2699')]
        for tab_id, lang_key, icon in tabs:
            btn_frame = tk.Frame(nav_frame, bg=COLORS['bg_card'], cursor='hand2')
            btn_frame.pack(fill='x', padx=8, pady=1)
            icon_lbl = tk.Label(btn_frame, text=icon, font=('Segoe UI', 13),
                                fg=COLORS['text3'], bg=COLORS['bg_card'], width=2)
            icon_lbl.pack(side='left', padx=(12, 6), pady=10)
            text_lbl = tk.Label(btn_frame, text=self.t(lang_key), font=('Segoe UI', 11),
                                fg=COLORS['text2'], bg=COLORS['bg_card'], anchor='w')
            text_lbl.pack(side='left', fill='x', expand=True, pady=10)
            self._register_i18n(text_lbl, lang_key)
            self.tab_buttons[tab_id] = (btn_frame, icon_lbl, text_lbl)
            for widget in (btn_frame, icon_lbl, text_lbl):
                widget.bind('<Button-1>', lambda e, t=tab_id: self._show_panel(t))

        spacer = tk.Frame(self.sidebar, bg=COLORS['bg_card'])
        spacer.pack(fill='both', expand=True)
        tk.Frame(self.sidebar, bg=COLORS['border'], height=1).pack(fill='x', padx=16)
        bottom_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], pady=12, padx=16)
        bottom_frame.pack(fill='x', side='bottom')
        self.lang_btn = tk.Button(bottom_frame, text='EN', font=('Segoe UI', 9, 'bold'),
                                   bg=COLORS['bg_card2'], fg=COLORS['text2'],
                                   activebackground=COLORS['bg_hover'], activeforeground=COLORS['accent'],
                                   relief='flat', padx=12, pady=4, cursor='hand2', bd=0,
                                   command=self._toggle_lang)
        self.lang_btn.pack(side='left')
        tk.Label(bottom_frame, text='v2.0', font=('Segoe UI', 8),
                 fg=COLORS['text3'], bg=COLORS['bg_card']).pack(side='right')

    def _build_content_area(self):
        self.content_area = tk.Frame(self.main_container, bg=COLORS['bg'])
        self.content_area.pack(side='left', fill='both', expand=True)
        topbar = tk.Frame(self.content_area, bg=COLORS['bg'], pady=12, padx=24)
        topbar.pack(fill='x')
        self.page_title = tk.Label(topbar, text='', font=('Segoe UI', 18, 'bold'),
                                    fg=COLORS['white'], bg=COLORS['bg'])
        self.page_title.pack(side='left')
        self.mining_status_label = tk.Label(topbar, text=self.t('mining_idle'),
                                             font=('Segoe UI', 9, 'bold'),
                                             fg=COLORS['text3'], bg=COLORS['bg_card2'], padx=12, pady=4)
        self.mining_status_label.pack(side='right')
        tk.Frame(self.content_area, bg=COLORS['border'], height=1).pack(fill='x')
        self.content_frame = tk.Frame(self.content_area, bg=COLORS['bg'])
        self.content_frame.pack(fill='both', expand=True)

    def _show_panel(self, name):
        self._active_tab = name
        for tid, (bf, il, tl) in self.tab_buttons.items():
            if tid == name:
                bf.config(bg=COLORS['bg_card2'])
                il.config(fg=COLORS['accent'], bg=bf.cget('bg'))
                tl.config(fg=COLORS['white'], bg=bf.cget('bg'), font=('Segoe UI', 11, 'bold'))
            else:
                bf.config(bg=COLORS['bg_card'])
                il.config(fg=COLORS['text3'], bg=COLORS['bg_card'])
                tl.config(fg=COLORS['text2'], bg=COLORS['bg_card'], font=('Segoe UI', 11))
        title_map = {'wallet': 'tab_wallet', 'mine': 'tab_mine',
                     'history': 'tab_history', 'settings': 'tab_settings'}
        self.page_title.config(text=self.t(title_map.get(name, name)))
        for child in self.content_frame.winfo_children():
            child.pack_forget()
        if hasattr(self, 'panels') and name in self.panels:
            self.panels[name].pack(fill='both', expand=True)
        if name == 'history':
            self._populate_history()

    def _build_panels(self):
        self.panels = {}
        self._build_wallet_panel()
        self._build_mine_panel()
        self._build_history_panel()
        self._build_settings_panel()

    def _make_scrollable_panel(self, parent_frame):
        canvas = tk.Canvas(parent_frame, bg=COLORS['bg'], highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(parent_frame, orient='vertical', command=canvas.yview,
                                  bg=COLORS['bg_card2'], troughcolor=COLORS['bg'])
        content = tk.Frame(canvas, bg=COLORS['bg'])
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas_window = canvas.create_window((0, 0), window=content, anchor='nw')
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width - 2)
        canvas.bind('<Configure>', _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        return canvas, content

    def _make_card(self, parent):
        return tk.Frame(parent, bg=COLORS['bg_card'], padx=20, pady=16,
                         highlightbackground=COLORS['border'], highlightthickness=1)

    def _make_separator(self, parent):
        tk.Frame(parent, bg=COLORS['border'], height=1).pack(fill='x', pady=(10, 12))

    def _make_entry(self, parent, **kwargs):
        return tk.Entry(parent, bg=COLORS['bg_input'], fg=COLORS['text'],
                          insertbackground=COLORS['accent'], relief='flat',
                          font=('Consolas', 11), highlightthickness=1,
                          highlightcolor=COLORS['accent'],
                          highlightbackground=COLORS['border'], **kwargs)

    def _make_accent_btn(self, parent, text='', command=None):
        btn = tk.Button(parent, text=text, command=command,
                         bg=COLORS['accent'], fg=COLORS['black'],
                         activebackground=COLORS['accent_dark'], activeforeground=COLORS['black'],
                         font=('Segoe UI', 12, 'bold'), relief='flat', cursor='hand2', bd=0)
        btn.bind('<Enter>', lambda e: btn.config(bg=COLORS['accent_dark']))
        btn.bind('<Leave>', lambda e: btn.config(bg=COLORS['accent']))
        return btn

    # ── WALLET PANEL ──

    def _build_wallet_panel(self):
        panel = tk.Frame(self.content_frame, bg=COLORS['bg'])
        self.panels['wallet'] = panel
        canvas, content = self._make_scrollable_panel(panel)
        pad = {'padx': 24, 'pady': (0, 16)}

        conn_card = self._make_card(content)
        conn_card.pack(fill='x', padx=24, pady=(16, 16))
        conn_header = tk.Frame(conn_card, bg=COLORS['bg_card'])
        conn_header.pack(fill='x')
        tk.Label(conn_header, text='\u26a1', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        conn_title = tk.Label(conn_header, text=self.t('connection'),
                               font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        conn_title.pack(side='left')
        self._register_i18n(conn_title, 'connection')
        self._make_separator(conn_card)

        rpc_lbl = tk.Label(conn_card, text=self.t('rpc_url'), font=('Segoe UI', 9, 'bold'),
                            fg=COLORS['text2'], bg=COLORS['bg_card'])
        rpc_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(rpc_lbl, 'rpc_url')
        self.rpc_var = tk.StringVar(value=self.config['rpc'])
        self._make_entry(conn_card, textvariable=self.rpc_var).pack(fill='x', pady=(0, 12), ipady=8)

        pk_lbl = tk.Label(conn_card, text=self.t('private_key'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        pk_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(pk_lbl, 'private_key')
        pk_row = tk.Frame(conn_card, bg=COLORS['bg_card'])
        pk_row.pack(fill='x', pady=(0, 16))
        self.pk_var = tk.StringVar()
        yaml_pk = self.yaml_cfg.get("private_key", "")
        if yaml_pk and yaml_pk != "YOUR_PRIVATE_KEY_HERE":
            self.pk_var.set(yaml_pk)
        elif self.config.get('save_private_key') and self.config.get('private_key_saved'):
            self.pk_var.set(self._deobfuscate_key(self.config['private_key_saved']))
        self.pk_entry = self._make_entry(pk_row, textvariable=self.pk_var, show='*')
        self.pk_entry.pack(side='left', fill='x', expand=True, ipady=8)
        self.show_pk_var = tk.BooleanVar(value=False)
        show_btn = tk.Button(pk_row, text=self.t('show'), font=('Segoe UI', 9),
                              bg=COLORS['bg_card2'], fg=COLORS['text2'],
                              activebackground=COLORS['bg_hover'], relief='flat',
                              padx=12, cursor='hand2', bd=0, command=self._toggle_pk)
        show_btn.pack(side='left', padx=(8, 0), ipady=8)

        save_pk_row = tk.Frame(conn_card, bg=COLORS['bg_card'])
        save_pk_row.pack(fill='x', pady=(0, 12))
        self.save_pk_var = tk.BooleanVar(value=self.config.get('save_private_key', False))
        tk.Checkbutton(save_pk_row, text=self.t('save_pk'), variable=self.save_pk_var,
                        font=('Segoe UI', 9), fg=COLORS['text2'], bg=COLORS['bg_card'],
                        selectcolor=COLORS['bg_input'], activebackground=COLORS['bg_card'],
                        highlightthickness=0, bd=0, cursor='hand2').pack(side='left')

        self.connect_btn = self._make_accent_btn(conn_card, text=self.t('connect'), command=self._connect)
        self.connect_btn.pack(fill='x', ipady=6)
        self._register_i18n(self.connect_btn, 'connect')

        balance_card = self._make_card(content)
        balance_card.pack(fill='x', **pad)
        bal_header = tk.Frame(balance_card, bg=COLORS['bg_card'])
        bal_header.pack(fill='x')
        bal_title = tk.Label(bal_header, text=self.t('wallet_overview'),
                              font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        bal_title.pack(side='left')
        self._register_i18n(bal_title, 'wallet_overview')
        refresh_btn = tk.Button(bal_header, text=self.t('refresh'), font=('Segoe UI', 9),
                                 bg=COLORS['bg_card2'], fg=COLORS['text2'],
                                 activebackground=COLORS['bg_hover'], relief='flat',
                                 padx=10, pady=2, cursor='hand2', bd=0, command=self._refresh_info)
        refresh_btn.pack(side='right')
        self._register_i18n(refresh_btn, 'refresh')
        self._make_separator(balance_card)

        self.main_balance_frame = tk.Frame(balance_card, bg=COLORS['bg_card'], pady=8)
        self.main_balance_frame.pack(fill='x')
        tk.Label(self.main_balance_frame, text='A', font=('Segoe UI', 28, 'bold'),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        bal_col = tk.Frame(self.main_balance_frame, bg=COLORS['bg_card'])
        bal_col.pack(side='left')
        self.big_balance_label = tk.Label(bal_col, text='0.000 ADDRESS',
                                           font=('Segoe UI', 24, 'bold'),
                                           fg=COLORS['white'], bg=COLORS['bg_card'])
        self.big_balance_label.pack(anchor='w')
        self.address_label = tk.Label(bal_col, text='--', font=('Consolas', 10),
                                       fg=COLORS['text3'], bg=COLORS['bg_card'])
        self.address_label.pack(anchor='w')
        self._make_separator(balance_card)

        stats_frame = tk.Frame(balance_card, bg=COLORS['bg_card'])
        stats_frame.pack(fill='x')
        stat_defs = [
            ('bnb_balance', 'bnb_balance', COLORS['text']),
            ('addr_balance', 'addr_balance', COLORS['accent']),
            ('total_mined', 'total_mined', COLORS['text']),
            ('total_supply', 'total_supply', COLORS['text']),
            ('current_reward', 'current_reward', COLORS['accent']),
            ('current_era', 'current_era', COLORS['green']),
        ]
        self.stat_labels = {}
        for i, (sid, lang_key, color) in enumerate(stat_defs):
            r, c = divmod(i, 2)
            cell = tk.Frame(stats_frame, bg=COLORS['bg_card2'], padx=14, pady=10)
            cell.grid(row=r, column=c, padx=(0 if c == 0 else 4, 4 if c == 0 else 0),
                      pady=3, sticky='nsew')
            lbl = tk.Label(cell, text=self.t(lang_key).upper(), font=('Segoe UI', 8, 'bold'),
                           fg=COLORS['text3'], bg=COLORS['bg_card2'])
            lbl.pack(anchor='w')
            self._register_i18n(lbl, lang_key)
            val = tk.Label(cell, text='--', font=('Segoe UI', 13, 'bold'),
                           fg=color, bg=COLORS['bg_card2'])
            val.pack(anchor='w', pady=(2, 0))
            self.stat_labels[sid] = val
        stats_frame.columnconfigure(0, weight=1)
        stats_frame.columnconfigure(1, weight=1)

    # ── MINE PANEL ──

    def _build_mine_panel(self):
        panel = tk.Frame(self.content_frame, bg=COLORS['bg'])
        self.panels['mine'] = panel
        canvas, content = self._make_scrollable_panel(panel)

        ctrl_card = self._make_card(content)
        ctrl_card.pack(fill='x', padx=24, pady=(16, 16))
        ctrl_header = tk.Frame(ctrl_card, bg=COLORS['bg_card'])
        ctrl_header.pack(fill='x')
        tk.Label(ctrl_header, text='\u26cf', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        ctrl_title = tk.Label(ctrl_header, text=self.t('mining_dashboard'),
                               font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        ctrl_title.pack(side='left')
        self._register_i18n(ctrl_title, 'mining_dashboard')
        self._make_separator(ctrl_card)

        self.mine_btn = tk.Button(ctrl_card, text=self.t('start_mining'),
                                   font=('Segoe UI', 14, 'bold'),
                                   bg=COLORS['accent'], fg=COLORS['black'],
                                   activebackground=COLORS['accent_dark'],
                                   relief='flat', cursor='hand2', bd=0,
                                   command=self._toggle_mining)
        self.mine_btn.pack(fill='x', ipady=12)

        stats_row = tk.Frame(ctrl_card, bg=COLORS['bg_card'])
        stats_row.pack(fill='x', pady=(16, 0))
        mining_stats = [
            ('hashrate', '0 H/s', COLORS['blue']),
            ('won_count', '0', COLORS['green']),
            ('lost_count', '0', COLORS['red']),
            ('sent_count', '0', COLORS['accent']),
            ('win_rate', '0%', COLORS['purple']),
        ]
        self.mining_stat_labels = {}
        for i, (key, default, color) in enumerate(mining_stats):
            cell = tk.Frame(stats_row, bg=COLORS['bg_card2'], padx=10, pady=8)
            cell.pack(side='left', fill='x', expand=True,
                      padx=(0 if i == 0 else 3, 3 if i < len(mining_stats)-1 else 0))
            lbl = tk.Label(cell, text=self.t(key).upper(), font=('Segoe UI', 7, 'bold'),
                           fg=COLORS['text3'], bg=COLORS['bg_card2'])
            lbl.pack(anchor='w')
            self._register_i18n(lbl, key)
            val_lbl = tk.Label(cell, text=default, font=('Segoe UI', 13, 'bold'),
                               fg=color, bg=COLORS['bg_card2'])
            val_lbl.pack(anchor='w', pady=(2, 0))
            self.mining_stat_labels[key] = val_lbl

        log_card = self._make_card(content)
        log_card.pack(fill='x', padx=24, pady=(0, 16))
        log_header = tk.Frame(log_card, bg=COLORS['bg_card'])
        log_header.pack(fill='x')
        tk.Label(log_header, text='\u2630', font=('Segoe UI', 13),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        log_title = tk.Label(log_header, text=self.t('mining_log'),
                              font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        log_title.pack(side='left')
        self._register_i18n(log_title, 'mining_log')
        clear_btn = tk.Button(log_header, text=self.t('clear_log'), font=('Segoe UI', 9),
                               bg=COLORS['bg_card2'], fg=COLORS['text2'],
                               activebackground=COLORS['bg_hover'], relief='flat',
                               padx=10, pady=2, cursor='hand2', bd=0,
                               command=lambda: self.log_text.delete('1.0', 'end'))
        clear_btn.pack(side='right')
        self._register_i18n(clear_btn, 'clear_log')
        self._make_separator(log_card)
        self.log_text = scrolledtext.ScrolledText(
            log_card, height=14, bg=COLORS['bg'], fg=COLORS['green'],
            font=('Consolas', 9), insertbackground=COLORS['green'],
            relief='flat', highlightthickness=1, bd=0,
            highlightcolor=COLORS['border'], highlightbackground=COLORS['border'])
        self.log_text.pack(fill='both', expand=True)

    # ── HISTORY PANEL ──

    def _build_history_panel(self):
        panel = tk.Frame(self.content_frame, bg=COLORS['bg'])
        self.panels['history'] = panel
        header_card = self._make_card(panel)
        header_card.pack(fill='x', padx=24, pady=(16, 0))
        h_header = tk.Frame(header_card, bg=COLORS['bg_card'])
        h_header.pack(fill='x')
        h_title = tk.Label(h_header, text=self.t('history_title'),
                            font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        h_title.pack(side='left')
        self._register_i18n(h_title, 'history_title')

        col_frame = tk.Frame(panel, bg=COLORS['bg_card2'], padx=24, pady=10)
        col_frame.pack(fill='x', padx=24, pady=(12, 2))
        cols = [('time', 16), ('salt', 14), ('reward', 14), ('tx_hash', 22), ('status', 8)]
        for key, w in cols:
            lbl = tk.Label(col_frame, text=self.t(key).upper(), font=('Segoe UI', 8, 'bold'),
                           fg=COLORS['accent'], bg=COLORS['bg_card2'], width=w, anchor='w')
            lbl.pack(side='left', padx=2)
            self._register_i18n(lbl, key)

        h_canvas = tk.Canvas(panel, bg=COLORS['bg'], highlightthickness=0, bd=0)
        h_scroll = tk.Scrollbar(panel, orient='vertical', command=h_canvas.yview,
                                 bg=COLORS['bg_card2'], troughcolor=COLORS['bg'])
        self.history_list_frame = tk.Frame(h_canvas, bg=COLORS['bg'])
        self.history_list_frame.bind('<Configure>',
                                      lambda e: h_canvas.configure(scrollregion=h_canvas.bbox('all')))
        h_canvas_window = h_canvas.create_window((0, 0), window=self.history_list_frame, anchor='nw')
        h_canvas.configure(yscrollcommand=h_scroll.set)
        def _on_h(event): h_canvas.itemconfig(h_canvas_window, width=event.width)
        h_canvas.bind('<Configure>', _on_h)
        h_canvas.pack(side='left', fill='both', expand=True, padx=(24, 0), pady=(0, 16))
        h_scroll.pack(side='right', fill='y', padx=(0, 24), pady=(0, 16))
        self._populate_history()

    def _populate_history(self):
        for w in self.history_list_frame.winfo_children():
            w.destroy()
        if not self.history:
            tk.Label(self.history_list_frame, text=self.t('no_records'),
                     font=('Segoe UI', 11), fg=COLORS['text3'], bg=COLORS['bg'], pady=40).pack()
            return
        for entry in reversed(self.history):
            self._add_history_row(entry, prepend=False)

    def _add_history_row(self, entry, prepend=True):
        bg = COLORS['bg_card']
        row = tk.Frame(self.history_list_frame, bg=bg, padx=24, pady=8)
        if prepend:
            for c in self.history_list_frame.winfo_children():
                if isinstance(c, tk.Label): c.destroy()
            existing = self.history_list_frame.winfo_children()
            if existing:
                row.pack(fill='x', pady=1, before=existing[0])
            else:
                row.pack(fill='x', pady=1)
        else:
            row.pack(fill='x', pady=1)
        status = entry.get('status', '')
        status_color = COLORS['green'] if status == 'Success' else COLORS['red']
        vals = [
            (entry.get('time', ''), 16, COLORS['text2']),
            (str(entry.get('salt', ''))[:14], 14, COLORS['text']),
            (entry.get('reward', ''), 14, COLORS['accent']),
            ((entry.get('tx_hash', '')[:20] + '...' if len(entry.get('tx_hash', '')) > 20
              else entry.get('tx_hash', '')), 22, COLORS['blue']),
            (status, 8, status_color),
        ]
        for text, w, fg in vals:
            tk.Label(row, text=text, font=('Consolas', 9), fg=fg, bg=bg,
                     width=w, anchor='w').pack(side='left', padx=2)

    # ── SETTINGS PANEL ──

    def _build_settings_panel(self):
        panel = tk.Frame(self.content_frame, bg=COLORS['bg'])
        self.panels['settings'] = panel
        canvas, content = self._make_scrollable_panel(panel)

        gas_card = self._make_card(content)
        gas_card.pack(fill='x', padx=24, pady=(16, 16))
        gas_header = tk.Frame(gas_card, bg=COLORS['bg_card'])
        gas_header.pack(fill='x')
        tk.Label(gas_header, text='\u2699', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        gas_title = tk.Label(gas_header, text=self.t('gas_settings'),
                              font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        gas_title.pack(side='left')
        self._register_i18n(gas_title, 'gas_settings')
        self._make_separator(gas_card)

        gp_lbl = tk.Label(gas_card, text=self.t('gas_price'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        gp_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(gp_lbl, 'gas_price')
        self.gas_price_var = tk.StringVar(value=self.config.get('gas_price', '0.05'))
        self._make_entry(gas_card, textvariable=self.gas_price_var).pack(fill='x', pady=(0, 12), ipady=8)

        gl_lbl = tk.Label(gas_card, text=self.t('gas_limit'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        gl_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(gl_lbl, 'gas_limit')
        self.gas_limit_var = tk.StringVar(value=self.config.get('gas_limit', '500000'))
        self._make_entry(gas_card, textvariable=self.gas_limit_var).pack(fill='x', pady=(0, 12), ipady=8)

        ct_lbl = tk.Label(gas_card, text=self.t('contract'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        ct_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(ct_lbl, 'contract')
        tk.Label(gas_card, text=CONTRACT_ADDRESS, font=('Consolas', 10),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(anchor='w', pady=(0, 16))
        save_btn = self._make_accent_btn(gas_card, text=self.t('save_settings'), command=self._save_config)
        save_btn.pack(fill='x', ipady=6)
        self._register_i18n(save_btn, 'save_settings')

        about_card = self._make_card(content)
        about_card.pack(fill='x', padx=24, pady=(0, 24))
        about_header = tk.Frame(about_card, bg=COLORS['bg_card'])
        about_header.pack(fill='x')
        tk.Label(about_header, text='\u2139', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        about_title = tk.Label(about_header, text=self.t('about'),
                                font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        about_title.pack(side='left')
        self._register_i18n(about_title, 'about')
        self._make_separator(about_card)
        about_label = tk.Label(about_card, text=self.t('about_text'),
                                 font=('Segoe UI', 10), fg=COLORS['text2'],
                                 bg=COLORS['bg_card'], justify='left', wraplength=550)
        about_label.pack(anchor='w', fill='x')
        self._register_i18n(about_label, 'about_text')

    # ── Actions ──

    def _toggle_pk(self):
        self.show_pk_var.set(not self.show_pk_var.get())
        self.pk_entry.config(show='' if self.show_pk_var.get() else '*')

    def _update_status_display(self):
        if self.w3 and self.account:
            self.status_dot.delete('all')
            self.status_dot.create_oval(1, 1, 9, 9, fill=COLORS['green'], outline='')
            self.status_label.config(text=self.t('connected'), fg=COLORS['green'])
        else:
            self.status_dot.delete('all')
            self.status_dot.create_oval(1, 1, 9, 9, fill=COLORS['red_dim'], outline='')
            self.status_label.config(text=self.t('not_connected'), fg=COLORS['text2'])

    def _log(self, msg):
        def _do():
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert('end', f"[{ts}] {msg}\n")
            self.log_text.see('end')
        self.root.after(0, _do)

    def _connect(self):
        rpc = self.rpc_var.get().strip()
        pk = self.pk_var.get().strip()
        if not pk:
            messagebox.showerror(self.t('error'), self.t('enter_pk'))
            return
        try:
            if not rpc or rpc == DEFAULT_RPC:
                self._log("多 RPC 测速中...")
                best_rpc, best_lat = select_best_rpc(DEFAULT_RPC_LIST, on_log=self._log)
                if best_rpc:
                    rpc = best_rpc
                    self.rpc_var.set(rpc)
                    self._log(f"选中最快节点: {rpc} ({best_lat:.0f}ms)")
                else:
                    rpc = DEFAULT_RPC

            self.w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
            if not self.w3.is_connected():
                raise Exception("Cannot connect to RPC")

            self.account = Account.from_key(pk)
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

            self._log(f"已连接  钱包: {self.account.address}")
            self._update_status_display()
            self._show_toast(self.t('connected'))
            self._save_config()
            self._refresh_info()
        except Exception as e:
            messagebox.showerror(self.t('error'), f"{self.t('conn_failed')}: {e}")
            self._log(f"[Error] {e}")

    def _refresh_info(self):
        if not self.w3 or not self.account:
            return
        now = time.monotonic()
        if hasattr(self, '_last_refresh_time') and (now - self._last_refresh_time) < 5.0:
            return
        self._last_refresh_time = now
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        try:
            addr = self.account.address
            bnb = self.w3.eth.get_balance(addr)
            addr_bal = self.contract.functions.balanceOf(addr).call()
            total_supply = self.contract.functions.totalSupply().call()
            total_mined = self.contract.functions.totalMined().call()
            current_reward = self.contract.functions.currentReward().call()
            current_era = self.contract.functions.era().call()

            def _update():
                self.address_label.config(text=addr)
                self.big_balance_label.config(
                    text=f"{Web3.from_wei(addr_bal, 'ether'):.4f} ADDRESS")
                self.stat_labels['bnb_balance'].config(
                    text=f"{self.w3.from_wei(bnb, 'ether'):.6f}")
                self.stat_labels['addr_balance'].config(
                    text=f"{Web3.from_wei(addr_bal, 'ether'):.4f}")
                self.stat_labels['total_mined'].config(text=f"{total_mined}")
                self.stat_labels['total_supply'].config(
                    text=f"{Web3.from_wei(total_supply, 'ether'):.0f} / 21M")
                self.stat_labels['current_reward'].config(
                    text=f"{Web3.from_wei(current_reward, 'ether'):.4f} ADDR")
                self.stat_labels['current_era'].config(
                    text=f"Era {current_era}")
            self.root.after(0, _update)
        except Exception as e:
            self._log(f"[Error] 刷新: {e}")

    def _toggle_mining(self):
        if self.mining:
            self._stop_mining()
        else:
            self._start_mining()

    def _start_mining(self):
        if not self.w3 or not self.account:
            messagebox.showerror(self.t('error'), self.t('connect_first'))
            return
        self.mining = True
        self.start_time = time.time()
        self.mine_btn.config(text=self.t('stop_mining'), bg=COLORS['red'])
        self.mining_status_label.config(text=self.t('mining_active'), fg=COLORS['green'])
        self._log(self.t('mining_started'))

        cfg = dict(self.yaml_cfg)
        pk = self.pk_var.get().strip()
        cfg["_pk"] = pk if pk.startswith("0x") else "0x" + pk
        cfg["private_key"] = pk
        cfg["gas_limit"] = int(self.gas_limit_var.get())

        def on_log(msg, lv="INFO"):
            self._log(msg)

        def on_win(salt, count, addr_hex, reward_str):
            entry = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "salt": str(salt), "reward": reward_str,
                "tx_hash": f"addr={addr_hex[:16]}...", "status": "Success"
            }
            self.history.append(entry)
            self._save_history()
            self.root.after(0, lambda: self._add_history_row(entry))
            self._refresh_info()

        def on_lose():
            entry = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "salt": "", "reward": "0",
                "tx_hash": "failed/reverted", "status": "Failed"
            }
            self.history.append(entry)
            self._save_history()
            self.root.after(0, lambda: self._add_history_row(entry))

        def on_stats(s):
            def _upd():
                rate = s.get('hashrate', 0)
                if rate >= 1_000_000:
                    hr = f"{rate / 1_000_000:.2f} MH/s"
                elif rate >= 1_000:
                    hr = f"{rate / 1_000:.2f} KH/s"
                else:
                    hr = f"{rate:.0f} H/s"
                self.mining_stat_labels['hashrate'].config(text=hr)
                self.mining_stat_labels['won_count'].config(text=str(s.get('won', 0)))
                self.mining_stat_labels['lost_count'].config(text=str(s.get('lost', 0)))
                self.mining_stat_labels['sent_count'].config(text=str(s.get('sent', 0)))
                self.mining_stat_labels['win_rate'].config(text=f"{s.get('win_rate', 0):.0f}%")
            self.root.after(0, _upd)

        try:
            self.miner = MiningEngine(cfg, on_log=on_log, on_win=on_win,
                                       on_lose=on_lose, on_stats=on_stats)
            self.miner.start()
            self._log(f"挖矿引擎启动  模式: {self.miner.mode.upper()}  "
                      f"Gas: {Web3.from_wei(self.miner.gas_wei, 'gwei')} Gwei")
            if self.miner.dry:
                self._log("*** DRY_RUN 模式: 只算不提交 ***")
        except Exception as e:
            self._log(f"[Error] 启动失败: {e}")
            self.mining = False
            self.mine_btn.config(text=self.t('start_mining'), bg=COLORS['accent'])
            self.mining_status_label.config(text=self.t('mining_idle'), fg=COLORS['text3'])

    def _stop_mining(self):
        self.mining = False
        if self.miner:
            self.miner.stop()
            self.miner = None
        self.mine_btn.config(text=self.t('start_mining'), bg=COLORS['accent'])
        self.mining_status_label.config(text=self.t('mining_idle'), fg=COLORS['text3'])
        self._log(self.t('mining_stopped'))


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def main():
    multiprocessing.freeze_support()
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    app = PremiumNumberMinerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
