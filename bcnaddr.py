"""Bytecoin address check without the node: base58 (Monero-style blocks), prefix and Keccak checksum.

It does not check that the keys are valid curve points; walletd does that when a payout is built, and the
pool then skips that one address instead of failing the whole payout.
"""

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_INDEX = {c: i for i, c in enumerate(ALPHABET)}
_ENCODED_SIZES = [0, 2, 3, 5, 6, 7, 9, 10, 11]  # encoded length of a block of n bytes, n = 0..8
PREFIX_LEGACY = 6           # addresses start with "2"
PREFIX_AMETHYST = 572238    # addresses start with "bcnZ"

# ---- Keccak-256 (original padding 0x01, as cn_fast_hash) ----
_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B,
       0x0000000080000001, 0x8000000080008081, 0x8000000000008009, 0x000000000000008A, 0x0000000000000088,
       0x0000000080008009, 0x000000008000000A, 0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
       0x8000000000008003, 0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
       0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = (1 << 64) - 1


def _rol(v, n):
    return ((v << n) | (v >> (64 - n))) & _M if n else v


def _keccak_f(a):
    for rc in _RC:
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        a = [[a[x][y] ^ d[x] for y in range(5)] for x in range(5)]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol(a[x][y], _ROT[x][y])
        a = [[b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
        a[0][0] ^= rc
    return a


def keccak256(data):
    rate = 136
    msg = bytearray(data) + b"\x01"
    msg += b"\x00" * (-len(msg) % rate)
    msg[-1] |= 0x80
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(msg), rate):
        block = msg[off:off + rate]
        for i in range(rate // 8):
            x, y = i % 5, i // 5
            a[x][y] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        a = _keccak_f(a)
    return b"".join(a[i % 5][i // 5].to_bytes(8, "little") for i in range(4))


def _decode_block(s, size):
    num = 0
    for ch in s:
        num = num * 58 + _INDEX[ch]
    if num >> (8 * size):
        raise ValueError("block overflow")
    return num.to_bytes(size, "big")


def b58decode(s):
    out = bytearray()
    for i in range(0, len(s), 11):
        chunk = s[i:i + 11]
        size = _ENCODED_SIZES.index(len(chunk)) if len(chunk) < 11 else 8
        if len(chunk) < 11 and _ENCODED_SIZES[size] != len(chunk):
            raise ValueError("bad length")
        out += _decode_block(chunk, size)
    return bytes(out)


def _read_varint(b):
    v, shift = 0, 0
    for i, byte in enumerate(b):
        v |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return v, i + 1
        shift += 7
        if shift > 63:
            break
    raise ValueError("bad varint")


def check(address):
    """-> "legacy" or "amethyst" if the address is well formed, else None."""
    if not isinstance(address, str) or not 90 <= len(address) <= 110 or any(c not in _INDEX for c in address):
        return None
    try:
        raw = b58decode(address)
        tag, n = _read_varint(raw)
    except (ValueError, IndexError):
        return None
    body, checksum = raw[:-4], raw[-4:]
    if keccak256(body)[:4] != checksum or len(raw) - n - 4 != 64:
        return None
    return {PREFIX_LEGACY: "legacy", PREFIX_AMETHYST: "amethyst"}.get(tag)
