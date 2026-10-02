"""Column ordering check: python test_reading_order.py"""
from ocr_pdf import reading_order

W = 1000
head = ("HEADING", (50, 0, 950, 30))
# Gutter off-centre at x~570, as in real scans.
L = [(f"L{i}", (50, 100 + 20 * i, 540, 115 + 20 * i)) for i in range(3)]
R = [(f"R{i}", (575, 100 + 20 * i, 950, 115 + 20 * i)) for i in range(3)]

got = [t for t, _ in reading_order([head] + [x for p in zip(L, R) for x in p], W)]
assert got == ["HEADING", "L0", "L1", "L2", "R0", "R1", "R2"], got

# Single column stays top-to-bottom.
one = [(f"S{i}", (50, 20 * i, 900, 15 + 20 * i)) for i in range(3)]
assert [t for t, _ in reading_order(one, W)] == ["S0", "S1", "S2"]
print("ok")
