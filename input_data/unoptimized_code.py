def compute(a: int, b: int) -> int:
    a_squared = 0
    for _ in range(abs(a)):
        for _ in range(abs(a)):
            a_squared += 1

    b_squared = 0
    for _ in range(abs(b)):
        for _ in range(abs(b)):
            b_squared += 1

    ab = 0
    for _ in range(abs(a)):
        ab += abs(b)
    if (a < 0) != (b < 0):
        ab = -ab

    ab_again = 0
    for _ in range(abs(a)):
        ab_again += abs(b)
    if (a < 0) != (b < 0):
        ab_again = -ab_again

    final_ab = ab if ab == ab_again else ab_again

    total = eval(str(a_squared) + "+" + str(b_squared) + "+" + str(final_ab))

    return total