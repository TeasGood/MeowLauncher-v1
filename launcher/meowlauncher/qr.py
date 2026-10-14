_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(degree):
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        for j, coef in enumerate(poly):
            nxt[j] ^= _mul(coef, 1)
            nxt[j + 1] ^= _mul(coef, _EXP[i])
        poly = nxt
    return poly


def _rs_remainder(data, degree):
    gen = _rs_generator(degree)
    rem = [0] * degree
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        for i, coef in enumerate(gen[1:]):
            rem[i] ^= _mul(coef, factor)
    return rem


_BLOCKS = {
    1: {"L": (7, 1, 19, 0, 0), "M": (10, 1, 16, 0, 0),
        "Q": (13, 1, 13, 0, 0), "H": (17, 1, 9, 0, 0)},
    2: {"L": (10, 1, 34, 0, 0), "M": (16, 1, 28, 0, 0),
        "Q": (22, 1, 22, 0, 0), "H": (28, 1, 16, 0, 0)},
    3: {"L": (15, 1, 55, 0, 0), "M": (26, 1, 44, 0, 0),
        "Q": (18, 2, 17, 0, 0), "H": (22, 2, 13, 0, 0)},
    4: {"L": (20, 1, 80, 0, 0), "M": (18, 2, 32, 0, 0),
        "Q": (26, 2, 24, 0, 0), "H": (16, 4, 9, 0, 0)},
    5: {"L": (26, 1, 108, 0, 0), "M": (24, 2, 43, 0, 0),
        "Q": (18, 2, 15, 2, 16), "H": (22, 2, 11, 2, 12)},
    6: {"L": (18, 2, 68, 0, 0), "M": (16, 4, 27, 0, 0),
        "Q": (24, 4, 19, 0, 0), "H": (28, 4, 15, 0, 0)},
    7: {"L": (20, 2, 78, 0, 0), "M": (18, 4, 31, 0, 0),
        "Q": (18, 2, 14, 4, 15), "H": (26, 4, 13, 1, 14)},
    8: {"L": (24, 2, 97, 0, 0), "M": (22, 2, 38, 2, 39),
        "Q": (22, 4, 18, 2, 19), "H": (26, 4, 14, 2, 15)},
    9: {"L": (30, 2, 116, 0, 0), "M": (22, 3, 36, 2, 37),
        "Q": (20, 4, 16, 4, 17), "H": (24, 4, 12, 4, 13)},
    10: {"L": (18, 2, 68, 2, 69), "M": (26, 4, 43, 1, 44),
         "Q": (24, 6, 19, 2, 20), "H": (28, 6, 15, 2, 16)},
}

_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
          7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}

_ECL_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}

MAX_VERSION = 10


class QRError(ValueError):
    pass


def capacity(version, level):
    ec, g1, d1, g2, d2 = _BLOCKS[version][level]
    return g1 * d1 + g2 * d2


def _pick_version(length, level):
    for version in range(1, MAX_VERSION + 1):
        header = 4 + (8 if version < 10 else 16)
        if (header + 7) // 8 + length <= capacity(version, level):
            return version
    raise QRError("ссылка слишком длинная для QR версии %d" % MAX_VERSION)


def _bitstream(data, version, level):
    bits = []

    def put(value, count):
        for shift in range(count - 1, -1, -1):
            bits.append((value >> shift) & 1)

    put(0b0100, 4)
    put(len(data), 8 if version < 10 else 16)
    for byte in data:
        put(byte, 8)

    total = capacity(version, level) * 8
    if len(bits) > total:
        raise QRError("данные не помещаются")
    put(0, min(4, total - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    pad = [0xEC, 0x11]
    i = 0
    while len(bits) < total:
        put(pad[i % 2], 8)
        i += 1

    codewords = [int("".join(str(b) for b in bits[k:k + 8]), 2)
                 for k in range(0, len(bits), 8)]
    return codewords


def _interleave(codewords, version, level):
    ec_len, g1, d1, g2, d2 = _BLOCKS[version][level]
    blocks, pos = [], 0
    for count, size in ((g1, d1), (g2, d2)):
        for _ in range(count):
            blocks.append(codewords[pos:pos + size])
            pos += size
    ec_blocks = [_rs_remainder(b, ec_len) for b in blocks]

    out = []
    for i in range(max(len(b) for b in blocks)):
        for block in blocks:
            if i < len(block):
                out.append(block[i])
    for i in range(ec_len):
        for block in ec_blocks:
            out.append(block[i])
    return out


def _blank(version):
    size = version * 4 + 17
    return [[None] * size for _ in range(size)], size


def _place_function(matrix, size, version):
    def square(row, col):
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = row + r, col + c
                if 0 <= rr < size and 0 <= cc < size:
                    edge = r in (0, 6) and 0 <= c <= 6
                    edge = edge or (c in (0, 6) and 0 <= r <= 6)
                    core = 2 <= r <= 4 and 2 <= c <= 4
                    matrix[rr][cc] = 1 if (edge or core) else 0

    square(0, 0)
    square(0, size - 7)
    square(size - 7, 0)

    for i in range(8, size - 8):
        bit = 1 - (i % 2)
        matrix[6][i] = bit
        matrix[i][6] = bit

    centers = _ALIGN[version]
    for row in centers:
        for col in centers:
            if (row < 8 and col < 8) or (row < 8 and col > size - 9) \
                    or (row > size - 9 and col < 8):
                continue
            for r in range(-2, 3):
                for c in range(-2, 3):
                    ring = max(abs(r), abs(c))
                    matrix[row + r][col + c] = 1 if ring != 1 else 0

    matrix[size - 8][8] = 1

    for i in range(9):
        if matrix[8][i] is None:
            matrix[8][i] = 0
        if matrix[i][8] is None:
            matrix[i][8] = 0
    for i in range(8):
        if matrix[8][size - 1 - i] is None:
            matrix[8][size - 1 - i] = 0
        if matrix[size - 1 - i][8] is None:
            matrix[size - 1 - i][8] = 0

    if version >= 7:
        for i in range(6):
            for j in range(3):
                matrix[size - 11 + j][i] = 0
                matrix[i][size - 11 + j] = 0


def _reserved(size, version):
    mask, _ = _blank(version)
    _place_function(mask, size, version)
    return [[cell is not None for cell in row] for row in mask]


def _place_data(matrix, size, reserved, codewords):
    bits = []
    for word in codewords:
        for shift in range(7, -1, -1):
            bits.append((word >> shift) & 1)
    index = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for offset in (0, 1):
                cc = col - offset
                if reserved[row][cc]:
                    continue
                matrix[row][cc] = bits[index] if index < len(bits) else 0
                index += 1
        upward = not upward
        col -= 2


_MASKS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]


def _apply_mask(matrix, size, reserved, number):
    rule = _MASKS[number]
    out = [row[:] for row in matrix]
    for r in range(size):
        for c in range(size):
            if not reserved[r][c] and rule(r, c):
                out[r][c] ^= 1
    return out


def _format_bits(level, mask):
    data = (_ECL_BITS[level] << 3) | mask
    rem = data << 10
    for i in range(14, 9, -1):
        if rem >> i & 1:
            rem ^= 0x537 << (i - 10)
    return ((data << 10) | rem) ^ 0x5412


def _place_format(matrix, size, level, mask):
    bits = _format_bits(level, mask)
    for i in range(15):
        bit = (bits >> (14 - i)) & 1
        if i < 6:
            matrix[8][i] = bit
        elif i == 6:
            matrix[8][7] = bit
        elif i == 7:
            matrix[8][8] = bit
        elif i == 8:
            matrix[7][8] = bit
        else:
            matrix[14 - i][8] = bit
        if i < 7:
            matrix[size - 1 - i][8] = bit
        else:
            matrix[8][size - 15 + i] = bit


def _place_version(matrix, size, version):
    if version < 7:
        return
    rem = version << 12
    for i in range(17, 11, -1):
        if rem >> i & 1:
            rem ^= 0x1F25 << (i - 12)
    bits = (version << 12) | rem
    for i in range(18):
        bit = (bits >> i) & 1
        row, col = i // 3, i % 3
        matrix[size - 11 + col][row] = bit
        matrix[row][size - 11 + col] = bit


_N3 = "1011101"


def _n3_line(text, size):
    score = 0
    idx = text.find(_N3)
    while idx != -1:
        offset = idx + 7
        before = text[max(idx - 4, 0):idx]
        after = text[offset:offset + 4]
        if idx == 0 or idx == size - 7 or "1" not in before or "1" not in after:
            score += 40
        else:
            offset = idx + 4
        idx = text.find(_N3, offset)
    return score


def _penalty(matrix, size):
    score = 0
    for line in list(matrix) + [list(col) for col in zip(*matrix)]:
        run, prev = 1, line[0]
        for cell in line[1:]:
            if cell == prev:
                run += 1
            else:
                if run >= 5:
                    score += 3 + run - 5
                run, prev = 1, cell
        if run >= 5:
            score += 3 + run - 5
        score += _n3_line("".join(str(c) for c in line), size)
    for r in range(size - 1):
        for c in range(size - 1):
            block = {matrix[r][c], matrix[r][c + 1],
                     matrix[r + 1][c], matrix[r + 1][c + 1]}
            if len(block) == 1:
                score += 3
    dark = sum(sum(row) for row in matrix)
    percent = dark * 100.0 / (size * size)
    score += 10 * int(abs(percent - 50) / 5)
    return score


def encode(text, level="L", mask=None):
    data = text.encode("utf-8")
    version = _pick_version(len(data), level)
    codewords = _interleave(_bitstream(data, version, level), version, level)

    matrix, size = _blank(version)
    _place_function(matrix, size, version)
    reserved = _reserved(size, version)
    _place_data(matrix, size, reserved, codewords)

    def build(number):
        candidate = _apply_mask(matrix, size, reserved, number)
        _place_format(candidate, size, level, number)
        _place_version(candidate, size, version)
        return candidate

    if mask is not None:
        return build(mask)
    best, best_score = None, None
    for number in range(8):
        candidate = build(number)
        score = _penalty(candidate, size)
        if best_score is None or score < best_score:
            best, best_score = candidate, score
    return best


def size_in_cells(text, level="L", quiet=2):
    version = _pick_version(len(text.encode("utf-8")), level)
    side = version * 4 + 17 + quiet * 2
    return side, (side + 1) // 2


def render(text, level="L", quiet=2):
    matrix = encode(text, level)
    size = len(matrix)
    side = size + quiet * 2
    grid = [[0] * side for _ in range(side)]
    for r in range(size):
        for c in range(size):
            grid[r + quiet][c + quiet] = matrix[r][c]

    black = "\x1b[38;2;0;0;0m"
    white_bg = "\x1b[48;2;255;255;255m"
    black_bg = "\x1b[48;2;0;0;0m"
    white = "\x1b[38;2;255;255;255m"
    reset = "\x1b[0m"

    lines = []
    for top in range(0, side, 2):
        bottom = top + 1
        out = []
        for col in range(side):
            upper = grid[top][col]
            lower = grid[bottom][col] if bottom < side else 0
            fg = black if upper else white
            bg = black_bg if lower else white_bg
            out.append(fg + bg + "▀")
        lines.append("".join(out) + reset)
    return lines
