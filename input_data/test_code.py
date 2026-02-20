def expected(a, b):
    return a**2 + b**2 + a*b

def test_compute():
    assert compute(0, 0) == 0
    assert compute(1, 1) == 3
    assert compute(2, 3) == expected(2, 3)
    assert compute(5, 0) == 25
    assert compute(-2, 3) == expected(-2, 3)
    assert compute(-3, -4) == expected(-3, -4)
    assert isinstance(compute(2, 3), int)
    assert compute(3, 7) == compute(7, 3)