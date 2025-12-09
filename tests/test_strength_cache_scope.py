import pytest

from world_sim.strength_cache import StrengthCache, strength_cache_scope


def test_strength_cache_scope_clears_new_cache():
    with strength_cache_scope() as cache:
        cache._cache[1] = 42  # direct write to simulate usage
    assert cache._cache == {}, "cache should be cleared after scope exit"


def test_strength_cache_scope_clears_existing_cache():
    reusable = StrengthCache()
    with strength_cache_scope(reusable) as cache:
        cache._cache[2] = 99
        assert cache is reusable
    assert reusable._cache == {}, "existing cache should be cleared after scoped use"
