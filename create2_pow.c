#include <Python.h>
#include <stdint.h>
#include <string.h>

/*
 * PremiumNumber CREATE2 地址挖矿 C 加速
 *
 * CREATE2 地址计算:
 *   addr = keccak256(0xff ++ deployer(20) ++ effectiveSalt(32) ++ bytecodeHash(32))[12:]
 *
 * effectiveSalt = keccak256(miner(20) ++ salt(32))
 *
 * 检查 addr 末尾连续 hex '8' 的数量 >= min_trailing
 */

#define ROTL64(x, y) (((x) << (y)) | ((x) >> (64 - (y))))

static const uint64_t keccakf_rndc[24] = {
    0x0000000000000001ULL, 0x0000000000008082ULL, 0x800000000000808aULL,
    0x8000000080008000ULL, 0x000000000000808bULL, 0x0000000080000001ULL,
    0x8000000080008081ULL, 0x8000000000008009ULL, 0x000000000000008aULL,
    0x0000000000000088ULL, 0x0000000080008009ULL, 0x000000008000000aULL,
    0x000000008000808bULL, 0x800000000000008bULL, 0x8000000000008089ULL,
    0x8000000000008003ULL, 0x8000000000008002ULL, 0x8000000000000080ULL,
    0x000000000000800aULL, 0x800000008000000aULL, 0x8000000080008081ULL,
    0x8000000000008080ULL, 0x0000000080000001ULL, 0x8000000080008008ULL
};

static const int keccakf_rotc[24] = {
    1,  3,  6,  10, 15, 21, 28, 36, 45, 55, 2,  14,
    27, 41, 56,  8, 25, 43, 62, 18, 39, 61, 20, 44
};

static const int keccakf_piln[24] = {
    10, 7,  11, 17, 18, 3,  5,  16, 8,  21, 24, 4,
    15, 23, 19, 13, 12, 2,  20, 14, 22, 9,  6,  1
};

static void keccakf(uint64_t st[25]) {
    int i, j, r;
    uint64_t t, bc[5];
    for (r = 0; r < 24; r++) {
        for (i = 0; i < 5; i++) bc[i] = st[i] ^ st[i + 5] ^ st[i + 10] ^ st[i + 15] ^ st[i + 20];
        for (i = 0; i < 5; i++) {
            t = bc[(i + 4) % 5] ^ ROTL64(bc[(i + 1) % 5], 1);
            for (j = 0; j < 25; j += 5) st[j + i] ^= t;
        }
        t = st[1];
        for (i = 0; i < 24; i++) {
            j = keccakf_piln[i];
            bc[0] = st[j];
            st[j] = ROTL64(t, keccakf_rotc[i]);
            t = bc[0];
        }
        for (j = 0; j < 25; j += 5) {
            for (i = 0; i < 5; i++) bc[i] = st[j + i];
            for (i = 0; i < 5; i++) st[j + i] ^= (~bc[(i + 1) % 5]) & bc[(i + 2) % 5];
        }
        st[0] ^= keccakf_rndc[r];
    }
}

static void keccak256(const uint8_t *in, size_t len, uint8_t *out) {
    uint64_t st[25];
    uint8_t temp[144];
    size_t rsiz = 136;
    memset(st, 0, sizeof(st));
    while (len >= rsiz) {
        for (size_t i = 0; i < rsiz / 8; i++) st[i] ^= ((uint64_t *)in)[i];
        keccakf(st);
        in += rsiz; len -= rsiz;
    }
    memset(temp, 0, sizeof(temp));
    memcpy(temp, in, len);
    temp[len] = 0x01;
    temp[rsiz - 1] |= 0x80;
    for (size_t i = 0; i < rsiz / 8; i++) st[i] ^= ((uint64_t *)temp)[i];
    keccakf(st);
    memcpy(out, st, 32);
}

/* 计算地址 (keccak256 结果的后 20 字节) 末尾连续 hex '8' 的数量 */
static int count_trailing_8s(const uint8_t *addr20) {
    int count = 0;
    /* addr20[19] 是最后一个字节, 低 nibble 是最后一个 hex 字符 */
    for (int i = 19; i >= 0; i--) {
        uint8_t lo = addr20[i] & 0x0f;
        if (lo == 8) {
            count++;
        } else {
            return count;
        }
        uint8_t hi = (addr20[i] >> 4) & 0x0f;
        if (hi == 8) {
            count++;
        } else {
            return count;
        }
    }
    return count;
}

/*
 * create2_search(miner_bytes, deployer_bytes, bytecode_hash, start_salt, iterations, min_trailing)
 *
 * 扫描 [start_salt, start_salt + iterations), 对每个 salt:
 *   1. effectiveSalt = keccak256(miner(20) ++ salt(32))
 *   2. addr = keccak256(0xff ++ deployer(20) ++ effectiveSalt(32) ++ bytecodeHash(32))[12:]
 *   3. 检查 addr 末尾连续 '8' >= min_trailing
 *
 * 返回 (salt, trailing_count, effective_salt_bytes, addr_bytes) 或 None
 */
static PyObject* create2_search(PyObject* self, PyObject* args) {
    Py_buffer miner_buf, deployer_buf, bch_buf;
    unsigned long long start_salt;
    unsigned int iterations;
    int min_trailing;

    if (!PyArg_ParseTuple(args, "y*y*y*KIi",
                          &miner_buf, &deployer_buf, &bch_buf,
                          &start_salt, &iterations, &min_trailing))
        return NULL;

    if (miner_buf.len != 20 || deployer_buf.len != 20 || bch_buf.len != 32) {
        PyBuffer_Release(&miner_buf);
        PyBuffer_Release(&deployer_buf);
        PyBuffer_Release(&bch_buf);
        PyErr_SetString(PyExc_ValueError, "miner=20, deployer=20, bytecodeHash=32 bytes");
        return NULL;
    }

    uint8_t *miner = (uint8_t *)miner_buf.buf;
    uint8_t *deployer = (uint8_t *)deployer_buf.buf;
    uint8_t *bch = (uint8_t *)bch_buf.buf;

    /* 预组装 create2 输入前缀: 0xff(1) + deployer(20) = 21 bytes */
    uint8_t create2_input[85]; /* 1 + 20 + 32 + 32 = 85 */
    create2_input[0] = 0xff;
    memcpy(create2_input + 1, deployer, 20);
    /* create2_input[21..52] = effectiveSalt (每轮填充) */
    /* create2_input[53..84] = bytecodeHash (固定) */
    memcpy(create2_input + 53, bch, 32);

    /* 预组装 effectiveSalt 输入前缀: miner(20) */
    uint8_t esalt_input[52]; /* 20 + 32 = 52 */
    memcpy(esalt_input, miner, 20);

    uint8_t esalt_hash[32];
    uint8_t addr_hash[32];

    uint64_t salt = start_salt;
    int found = 0;
    int best_count = 0;
    uint64_t best_salt = 0;
    uint8_t best_esalt[32];
    uint8_t best_addr[20];

    for (unsigned int i = 0; i < iterations; i++) {
        /* salt -> big-endian 32 bytes */
        uint64_t s = salt;
        memset(esalt_input + 20, 0, 24); /* 高 24 字节清零 */
        for (int j = 31; j >= 24; j--) {
            esalt_input[20 + j] = (uint8_t)(s & 0xff);
            s >>= 8;
        }

        /* effectiveSalt = keccak256(miner ++ salt) */
        keccak256(esalt_input, 52, esalt_hash);

        /* 填入 create2 输入 */
        memcpy(create2_input + 21, esalt_hash, 32);

        /* addr = keccak256(0xff ++ deployer ++ effectiveSalt ++ bytecodeHash)[12:] */
        keccak256(create2_input, 85, addr_hash);

        int count = count_trailing_8s(addr_hash + 12);
        if (count >= min_trailing) {
            found = 1;
            best_count = count;
            best_salt = salt;
            memcpy(best_esalt, esalt_hash, 32);
            memcpy(best_addr, addr_hash + 12, 20);
            /* 找到 >= min_trailing 就立即返回 (贪心: 先挖到再说) */
            break;
        }

        salt++;
    }

    PyBuffer_Release(&miner_buf);
    PyBuffer_Release(&deployer_buf);
    PyBuffer_Release(&bch_buf);

    if (found) {
        return Py_BuildValue("(Kiy#y#)",
                             best_salt, best_count,
                             best_esalt, (Py_ssize_t)32,
                             best_addr, (Py_ssize_t)20);
    }
    Py_RETURN_NONE;
}

static PyMethodDef Methods[] = {
    {"create2_search", create2_search, METH_VARARGS,
     "Search for CREATE2 salt with trailing 8s in address.\n"
     "Args: miner(20), deployer(20), bytecodeHash(32), start_salt, iterations, min_trailing\n"
     "Returns: (salt, count, effectiveSalt(32), addr(20)) or None"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "create2_pow", NULL, -1, Methods
};

PyMODINIT_FUNC PyInit_create2_pow(void) {
    return PyModule_Create(&module);
}
