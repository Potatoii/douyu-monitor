import pytest

from dedup.deduper import Deduper


def test_dedup():
    d = Deduper(max_size=10)
    assert d.is_new("a")
    assert not d.is_new("a")
    assert d.is_new("b")


def test_eviction_fifo():
    d = Deduper(max_size=2)
    assert d.is_new("a")
    assert d.is_new("b")
    assert not d.is_new("a")
    assert d.is_new("c")
    assert d.is_new("a")


def test_invalid_size():
    with pytest.raises(ValueError):
        Deduper(max_size=0)
