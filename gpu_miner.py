#!/usr/bin/env python3
"""GPU 挖矿引擎 (PyOpenCL + keccak256) — PremiumNumber v3.1 CREATE2 地址挖矿.

适配 PremiumNumber v3.1 合约:
  PremiumNumber: 0x1805eE5F34d7434FefCFf0CA2d2383E06823E6d8
  AddressManager: 0x78B11198268619728E4b53c642E8d68941004c11

CREATE2 地址挖矿流程:
  1. effectiveSalt = keccak256(miner(20) ++ salt(32))
  2. addr = keccak256(0xff ++ deployer(20) ++ effectiveSalt(32) ++ bytecodeHash(32))[12:]
  3. 验证 addr 满足: 尾部或开头 digit (0-9) 连续 >= requiredRun

本模块提供 GpuMiner 类, 被主程序导入使用.
"""

import os
import sys
import time
import random
import signal
import yaml
from web3 import Web3

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

# PremiumNumber v3.1 合约 ABI (只需挖矿相关)
ABI = [
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
    {"inputs": [], "name": "totalMined", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
]

# v2 合约常量
INITIAL_REWARD = 50

running = True

COLORS = {
    "INFO": "\033[37m", "OK": "\033[92m", "WARN": "\033[93m",
    "ERROR": "\033[91m", "HASH": "\033[36m", "MINE": "\033[95m", "RESET": "\033[0m",
}


def log(msg, level="INFO"):
    ts = time.strftime("%H:%M:%S")
    c = COLORS.get(level, COLORS["INFO"])
    print(f"{c}[{ts}] [{level:>5}] {msg}{COLORS['RESET']}", flush=True)


def calc_mining_reward(token_id):
    return 0  # 使用合约 currentReward() 查询


# OpenCL 内核: CREATE2 地址挖矿
KERNEL_SRC = r"""
__constant ulong RC[24] = {
  0x0000000000000001UL, 0x0000000000008082UL, 0x800000000000808aUL, 0x8000000080008000UL,
  0x000000000000808bUL, 0x0000000080000001UL, 0x8000000080008081UL, 0x8000000000008009UL,
  0x000000000000008aUL, 0x0000000000000088UL, 0x0000000080008009UL, 0x000000008000000aUL,
  0x000000008000808bUL, 0x800000000000008bUL, 0x8000000000008089UL, 0x8000000000008003UL,
  0x8000000000008002UL, 0x8000000000000080UL, 0x000000000000800aUL, 0x800000008000000aUL,
  0x8000000080008081UL, 0x8000000000008080UL, 0x0000000080000001UL, 0x8000000080008008UL
};

__constant int ROTC[24] = {
  1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14,
  27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44
};

__constant int PILN[24] = {
  10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4,
  15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1
};

static inline ulong rotl64(ulong x, int n) {
    return (x << n) | (x >> (64 - n));
}

static void keccacf(ulong st[25]) {
    ulong bc[5], t;
    for (int round = 0; round < 24; round++) {
        for (int i = 0; i < 5; i++)
            bc[i] = st[i] ^ st[i+5] ^ st[i+10] ^ st[i+15] ^ st[i+20];
        for (int i = 0; i < 5; i++) {
            t = bc[(i+4)%5] ^ rotl64(bc[(i+1)%5], 1);
            for (int j = 0; j < 25; j += 5)
                st[j+i] ^= t;
        }
        t = st[1];
        for (int i = 0; i < 24; i++) {
            int j = PILN[i];
            bc[0] = st[j];
            st[j] = rotl64(t, ROTC[i]);
            t = bc[0];
        }
        for (int j = 0; j < 25; j += 5) {
            for (int i = 0; i < 5; i++) bc[i] = st[j+i];
            for (int i = 0; i < 5; i++)
                st[j+i] ^= (~bc[(i+1)%5]) & bc[(i+2)%5];
        }
        st[0] ^= RC[round];
    }
}

static void do_keccak256(const uchar *msg, int len, uchar *out) {
    ulong st[25];
    for (int i = 0; i < 25; i++) st[i] = 0;

    int off = 0;
    while (len - off >= 136) {
        for (int j = 0; j < 17; j++) {
            ulong lane = 0;
            for (int k = 0; k < 8; k++)
                lane |= ((ulong)msg[off + j*8 + k]) << (8*k);
            st[j] ^= lane;
        }
        keccacf(st);
        off += 136;
    }

    uchar pad[136];
    for (int i = 0; i < 136; i++) pad[i] = 0;
    int rem = len - off;
    for (int i = 0; i < rem; i++) pad[i] = msg[off + i];
    pad[rem] = 0x01;
    pad[135] = 0x80;

    for (int j = 0; j < 17; j++) {
        ulong lane = 0;
        for (int k = 0; k < 8; k++)
            lane |= ((ulong)pad[j*8 + k]) << (8*k);
        st[j] ^= lane;
    }
    keccacf(st);

    for (int i = 0; i < 32; i++) {
        out[i] = (uchar)((st[i/8] >> (8*(i%8))) & 0xff);
    }
}

static int count_trailing_same(const uchar *addr20, int digit) {
    int count = 0;
    for (int i = 19; i >= 0; i--) {
        if ((addr20[i] & 0x0f) == digit) { count++; } else { return count; }
        if (((addr20[i] >> 4) & 0x0f) == digit) { count++; } else { return count; }
    }
    return count;
}

static int count_leading_same(const uchar *addr20, int digit) {
    int count = 0;
    for (int i = 0; i < 20; i++) {
        if (((addr20[i] >> 4) & 0x0f) == digit) { count++; } else { return count; }
        if ((addr20[i] & 0x0f) == digit) { count++; } else { return count; }
    }
    return count;
}

static int count_total_digit(const uchar *addr20, int digit) {
    int count = 0;
    for (int i = 0; i < 20; i++) {
        if ((addr20[i] & 0x0f) == digit) count++;
        if (((addr20[i] >> 4) & 0x0f) == digit) count++;
    }
    return count;
}

static int is_address_valid(const uchar *addr20, int required_run) {
    int tDigit = addr20[19] & 0x0f;
    int trailing = 0;
    if (tDigit <= 9) {
        trailing = count_trailing_same(addr20, tDigit);
    }

    int lDigit = (addr20[0] >> 4) & 0x0f;
    int leading = 0;
    if (lDigit <= 9) {
        leading = count_leading_same(addr20, lDigit);
    }

    return (trailing >= required_run) || (leading >= required_run);
}

__kernel void mine_create2(
    __global const uchar* miner20,
    __global const uchar* deployer20,
    __global const uchar* bytecodeHash,
    const ulong start_salt,
    const int required_run,
    __global ulong* result
) {
    ulong salt = start_salt + (ulong)get_global_id(0);

    uchar esalt_in[52];
    for (int i = 0; i < 20; i++) esalt_in[i] = miner20[i];
    for (int i = 0; i < 24; i++) esalt_in[20 + i] = 0;
    for (int i = 0; i < 8; i++)
        esalt_in[51 - i] = (uchar)((salt >> (8*i)) & 0xff);

    uchar esalt_hash[32];
    do_keccak256(esalt_in, 52, esalt_hash);

    uchar c2_in[85];
    c2_in[0] = 0xff;
    for (int i = 0; i < 20; i++) c2_in[1 + i] = deployer20[i];
    for (int i = 0; i < 32; i++) c2_in[21 + i] = esalt_hash[i];
    for (int i = 0; i < 32; i++) c2_in[53 + i] = bytecodeHash[i];

    uchar addr_hash[32];
    do_keccak256(c2_in, 85, addr_hash);

    if (is_address_valid(addr_hash + 12, required_run)) {
        const uchar *addr20 = addr_hash + 12;
        int tDigit = addr20[19] & 0x0f;
        int trailing = (tDigit <= 9) ? count_trailing_same(addr20, tDigit) : 0;
        int lDigit = (addr20[0] >> 4) & 0x0f;
        int leading = (lDigit <= 9) ? count_leading_same(addr20, lDigit) : 0;
        int streak = (trailing >= leading) ? trailing : leading;
        result[0] = salt;
        result[1] = (ulong)streak;
    }
}
"""


class GpuMiner:
    def __init__(self, cfg):
        import pyopencl as cl
        import numpy as np
        self.cl = cl
        self.np = np

        self.batch_size = int(cfg.get("gpu_batch_size", 4_000_000))

        util = cfg.get("gpu_target_util", 100)
        try:
            util = float(util)
        except (TypeError, ValueError):
            util = 100.0
        self.target_util = min(100.0, max(1.0, util))

        want = str(cfg.get("gpu_device", "") or "").lower()
        gpus = []
        for platform in cl.get_platforms():
            for d in platform.get_devices():
                if d.type & cl.device_type.GPU:
                    gpus.append(d)
        device = None
        if want:
            for d in gpus:
                if want in d.name.strip().lower():
                    device = d
                    break
        if device is None and gpus:
            device = gpus[0]
        if device is None:
            device = cl.get_platforms()[0].get_devices()[0]

        self.device = device
        self.ctx = cl.Context([device])
        self.queue = cl.CommandQueue(self.ctx)
        self.program = cl.Program(self.ctx, KERNEL_SRC).build()
        self.kernel = self.program.mine_create2

        self.device_name = device.name.strip()

    def search(self, miner_bytes, deployer_bytes, bytecode_hash, start_salt, count, required_run=9):
        """扫描 [start_salt, start_salt+count), 找合格地址.
        返回 (salt, streak) 或 None."""
        cl = self.cl
        np = self.np
        mf = cl.mem_flags

        miner_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR,
                              hostbuf=np.frombuffer(miner_bytes, dtype=np.uint8))
        deployer_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR,
                                 hostbuf=np.frombuffer(deployer_bytes, dtype=np.uint8))
        bch_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR,
                            hostbuf=np.frombuffer(bytecode_hash, dtype=np.uint8))
        result = np.array([0, 0], dtype=np.uint64)
        result_buf = cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=result)

        t0 = time.time()
        self.kernel(self.queue, (int(count),), None,
                    miner_buf, deployer_buf, bch_buf,
                    np.uint64(start_salt), np.int32(required_run), result_buf)
        cl.enqueue_copy(self.queue, result, result_buf)
        self.queue.finish()
        t_batch = time.time() - t0

        if self.target_util < 100.0:
            sleep_s = t_batch * (100.0 - self.target_util) / self.target_util
            if sleep_s > 0:
                time.sleep(sleep_s)

        if result[1] > 0:
            return (int(result[0]), int(result[1]))
        return None


def fmt_hashrate(rate):
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:.2f} MH/s"
    if rate >= 1_000:
        return f"{rate / 1_000:.2f} KH/s"
    return f"{rate:.0f} H/s"


def _norm_key(k):
    k = str(k).strip()
    return k if k.startswith("0x") else "0x" + k


def load_config():
    with open(CONFIG_PATH, "r") as f:
        cfg = yaml.safe_load(f)
    keys = cfg.get("private_keys") or []
    if keys:
        cfg["private_keys"] = [_norm_key(k) for k in keys]
    else:
        pk = cfg.get("private_key")
        if not pk or pk == "YOUR_PRIVATE_KEY_HERE":
            log("请先在 config.yaml 中填写 private_key 或 private_keys", "ERROR")
            sys.exit(1)
        cfg["private_keys"] = [_norm_key(pk)]
    return cfg


def select_rpc(cfg):
    urls = cfg.get("rpc_urls") or []
    if not urls:
        return cfg["rpc_url"]
    log(f"测速 {len(urls)} 个 RPC 节点...")
    best, best_lat = None, None
    for url in urls:
        try:
            t0 = time.time()
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 6}))
            if not w3.is_connected():
                continue
            _ = w3.eth.block_number
            lat = (time.time() - t0) * 1000
            log(f"  {url}  {lat:.0f}ms")
            if best_lat is None or lat < best_lat:
                best, best_lat = url, lat
        except Exception:
            pass
    if best is None:
        return cfg.get("rpc_url") or urls[0]
    log(f"选中: {best}  ({best_lat:.0f}ms)", "OK")
    return best


def connect(cfg):
    rpc = select_rpc(cfg)
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        log(f"无法连接 RPC: {rpc}", "ERROR")
        sys.exit(1)
    cfg["rpc_url"] = rpc
    log(f"已连接 RPC: {rpc}  Chain ID: {w3.eth.chain_id}")
    accounts = [w3.eth.account.from_key(k) for k in cfg["private_keys"]]
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(cfg["contract_address"]), abi=ABI)
    return w3, accounts, contract


def show_status(w3, contract, miner_addr):
    try:
        total_supply = contract.functions.totalSupply().call()
        total_mined = contract.functions.totalMined().call()
        token_balance = contract.functions.balanceOf(miner_addr).call()
        bnb_balance = w3.eth.get_balance(miner_addr)
        current_reward = contract.functions.currentReward().call()
        current_era = contract.functions.era().call()
        log(f"已挖出: {total_mined} 个地址  总供应: {Web3.from_wei(total_supply, 'ether')} / 21,000,000 ADD")
        log(f"当前纪元: {current_era}  当前奖励: {Web3.from_wei(current_reward, 'ether')} ADD")
        log(f"余额: {Web3.from_wei(bnb_balance, 'ether')} BNB  |  {Web3.from_wei(token_balance, 'ether')} ADD", "OK")
    except Exception as e:
        log(f"读取链上状态失败: {e}", "WARN")


def get_gas_price(w3, cfg):
    net_gwei = None
    try:
        net_gwei = float(Web3.from_wei(w3.eth.gas_price, "gwei"))
    except Exception:
        pass
    if cfg.get("use_network_gas", True) and net_gwei is not None:
        gwei = net_gwei * float(cfg.get("network_gas_multiplier", 1.0))
        floor = float(cfg.get("min_gas_price_gwei", 0.01))
        cap = float(cfg.get("max_gas_price_gwei", 5))
        return max(floor, min(gwei, cap)), net_gwei
    return float(cfg.get("gas_price_gwei", 0.05)), net_gwei


def submit_mine(w3, contract, account, cfg, salt, gas_price_gwei):
    """提交 mine(salt) 交易."""
    miner_addr = account.address

    if cfg.get("simulate_before_submit", True):
        try:
            contract.functions.mine(salt).call({"from": miner_addr})
        except Exception as e:
            log(f"提交前模拟失败 (salt 可能已被使用或地址不合格): {str(e)[:80]}", "WARN")
            return None

    log(f"提交 mine(salt={salt}) ... (gas: {gas_price_gwei:.2f} Gwei)", "WARN")
    tx = contract.functions.mine(salt).build_transaction({
        "from": miner_addr,
        "nonce": w3.eth.get_transaction_count(miner_addr),
        "gas": cfg.get("gas_limit", 2200000),
        "gasPrice": Web3.to_wei(gas_price_gwei, "gwei"),
        "chainId": cfg["chain_id"],
    })
    signed = w3.eth.account.sign_transaction(tx, account.key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    log(f"交易已发送: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status == 1:
        cost = Web3.from_wei(receipt.gasUsed * Web3.to_wei(gas_price_gwei, "gwei"), "ether")
        log(f"Mine 成功! 区块: {receipt.blockNumber}  Gas Used: {receipt.gasUsed}  花费: {cost} BNB", "OK")
        show_status(w3, contract, miner_addr)
        return True
    log("Mine 交易失败 (reverted)", "ERROR")
    return False


def mine_loop(w3, contract, accounts, cfg, gpu):
    """GPU 挖矿主循环."""
    global running

    log_interval = cfg.get("log_interval", 10)

    bytecode_hash = contract.functions.walletBytecodeHash().call()
    deployer_bytes = bytes.fromhex(cfg["contract_address"][2:])
    try:
        required_run = contract.functions.requiredRun().call()
    except Exception:
        required_run = 9

    log(f"合约地址: {cfg['contract_address']}")
    log(f"bytecodeHash: {bytecode_hash.hex()}")
    log(f"挖矿模式: trailing || leading >= {required_run} (digit 0-9)")
    log(f"GPU 设备: {gpu.device_name}  batch={gpu.batch_size}")

    n_wallets = len(accounts)
    wallet_idx = 0
    round_num = 0
    total_hashes = 0
    total_mined = 0
    global_start = time.time()

    while running:
        account = accounts[wallet_idx % n_wallets]
        miner_addr = account.address
        miner_bytes = bytes.fromhex(miner_addr[2:])
        round_num += 1

        gas_price, net_gas = get_gas_price(w3, cfg)

        # 刷新当前奖励信息
        try:
            reward_wei = contract.functions.currentReward().call()
            reward = float(Web3.from_wei(reward_wei, "ether"))
            current_era = contract.functions.era().call()
        except Exception:
            reward = INITIAL_REWARD
            current_era = 0

        log("=" * 55, "MINE")
        log(f"第 {round_num} 轮挖矿  钱包: {miner_addr[:10]}...  Gas: {gas_price:.3f} Gwei", "MINE")
        log(f"当前纪元: {current_era}  奖励: {reward:.4f} ADD", "MINE")

        base_salt = random.getrandbits(64)
        batch = gpu.batch_size
        nonce = base_salt & ((1 << 48) - 1)
        round_hashes = 0
        round_start = time.time()
        last_log = round_start
        found = None

        while running:
            result = gpu.search(miner_bytes, deployer_bytes, bytecode_hash,
                                nonce, batch, required_run)
            round_hashes += batch
            total_hashes += batch

            if result is not None:
                salt, streak = result
                log(f"GPU 候选 salt={salt} streak={streak}, 验证中...", "HASH")
                from Crypto.Hash import keccak as _kc
                salt_be = salt.to_bytes(32, "big")
                k1 = _kc.new(digest_bits=256)
                k1.update(miner_bytes + salt_be)
                esalt = k1.digest()
                k2 = _kc.new(digest_bits=256)
                k2.update(b'\xff' + deployer_bytes + esalt + bytecode_hash)
                addr_hash = k2.digest()
                addr_bytes = addr_hash[12:]

                val = int.from_bytes(addr_bytes, "big")
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
                lDigit = (val >> 156) & 0xf
                lc = 0
                if lDigit <= 9:
                    for i in range(40):
                        shift = (39 - i) * 4
                        if ((val >> shift) & 0xf) == lDigit:
                            lc += 1
                        else:
                            break
                valid = (tc >= required_run) or (lc >= required_run)

                if valid:
                    addr_hex = "0x" + addr_bytes.hex()
                    found = (salt, streak, addr_hex)
                    break
                else:
                    log(f"GPU 候选 salt={salt} 验证不过 (tc={tc} lc={lc} need>={required_run}), 继续", "WARN")

            nonce += batch
            now = time.time()
            if now - last_log >= log_interval:
                rate = round_hashes / (now - round_start) if now > round_start else 0
                log(f"算力: {fmt_hashrate(rate)}  已扫描: {round_hashes}  耗时: {now - round_start:.0f}s", "HASH")
                last_log = now

        if found and running:
            salt, count, addr_hex = found
            elapsed = time.time() - round_start
            rate = round_hashes / elapsed if elapsed > 0 else 0
            log("*" * 55, "OK")
            log(f"找到合格地址!  streak: {count} 个", "OK")
            log(f"  Salt    : {salt}", "OK")
            log(f"  地址    : {addr_hex}", "OK")
            log(f"  奖励    : {reward:.4f} ADD", "OK")
            log(f"  耗时    : {elapsed:.1f}s", "OK")
            log(f"  算力    : {fmt_hashrate(rate)}", "OK")
            log("*" * 55, "OK")

            if cfg.get("dry_run", False):
                log("[DRY] 试运行模式, 不提交交易", "WARN")
            else:
                try:
                    ok = submit_mine(w3, contract, account, cfg, salt, gas_price)
                    if ok:
                        total_mined += 1
                        wallet_idx = (wallet_idx + 1) % n_wallets
                    elif ok is None:
                        log("模拟失败, 跳过提交", "WARN")
                except Exception as e:
                    log(f"提交异常: {e}", "ERROR")

            te = time.time() - global_start
            avg = total_hashes / te if te > 0 else 0
            log(f"累计: 成功 {total_mined} 次  总扫描 {total_hashes}  平均算力 {fmt_hashrate(avg)}  运行 {te:.0f}s", "OK")

            if not cfg.get("auto_restart", True):
                break

    log("GPU 挖矿程序已退出。")


def main():
    global running

    def handle_signal(sig, frame):
        global running
        if running:
            log("收到中断信号，正在停止...", "WARN")
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    cfg = load_config()

    print()
    log("=" * 55, "MINE")
    log("  PremiumNumber (ADD) GPU 挖矿程序 v3.1", "MINE")
    log("  合约: 0x1805...E6d8  链: BSC Mainnet", "MINE")
    log("  挖矿: trailing || leading >= requiredRun (digit 0-9)", "MINE")
    log("  奖励: 动态, 基于窗口频率 + 减半", "MINE")
    log("=" * 55, "MINE")
    print()

    w3, accounts, contract = connect(cfg)
    log(f"钱包数量: {len(accounts)}")

    for i, acc in enumerate(accounts):
        bal = w3.eth.get_balance(acc.address)
        log(f"  钱包[{i + 1}] {acc.address}  {Web3.from_wei(bal, 'ether')} BNB")

    show_status(w3, contract, accounts[0].address)

    try:
        gpu_inst = GpuMiner(cfg)
    except Exception as e:
        log(f"GPU 初始化失败: {e}", "ERROR")
        sys.exit(1)
    log(f"GPU 设备: {gpu_inst.device_name}  batch={gpu_inst.batch_size}")

    mine_loop(w3, contract, accounts, cfg, gpu_inst)


if __name__ == "__main__":
    main()
