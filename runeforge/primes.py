"""Small, dependency-free prime utilities.

Used for Gematria Primus values, GP-sum primality checks and the totient keystream
(page 56 subtracts phi(p_n) = p_n - 1 for the n-th prime).
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

# Deterministic Miller-Rabin witnesses: correct for every n < 3.3e24.
_MR_WITNESSES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41)


def is_prime(n: int) -> bool:
    """Deterministic primality test for any integer below 3.3e24."""
    n = int(n)
    if n < 2:
        return False
    for p in _MR_WITNESSES:
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in _MR_WITNESSES:
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _sieve(limit: int) -> np.ndarray:
    flags = np.ones(limit + 1, dtype=bool)
    flags[:2] = False
    for p in range(2, math.isqrt(limit) + 1):
        if flags[p]:
            flags[p * p :: p] = False
    return np.flatnonzero(flags)


@lru_cache(maxsize=8)
def _first_primes_cached(count: int) -> tuple[int, ...]:
    # p_n < n (ln n + ln ln n) for n >= 6 (Rosser's theorem)
    limit = 15 if count < 6 else int(count * (math.log(count) + math.log(math.log(count)))) + 1
    primes = _sieve(limit)
    return tuple(int(p) for p in primes[:count])


def first_primes(count: int) -> np.ndarray:
    """The first ``count`` primes, starting at 2."""
    if count < 0:
        raise ValueError("count must be non-negative")
    if count == 0:
        return np.zeros(0, dtype=np.int64)
    return np.array(_first_primes_cached(count), dtype=np.int64)
