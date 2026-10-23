from __future__ import annotations

from collagio.core.rng import derive_rng, derive_seed


def test_same_inputs_give_same_sequence() -> None:
    a = derive_rng(42, "layout", "grid")
    b = derive_rng(42, "layout", "grid")
    assert [a.random() for _ in range(5)] == [b.random() for _ in range(5)]


def test_keys_and_seed_change_the_stream() -> None:
    seeds = {
        derive_seed(42, "layout"),
        derive_seed(43, "layout"),
        derive_seed(42, "style"),
        derive_seed(42, "style", "p001"),
        derive_seed(42, "style", "p002"),
    }
    assert len(seeds) == 5


def test_key_boundaries_are_unambiguous() -> None:
    assert derive_seed(1, "ab", "c") != derive_seed(1, "a", "bc")


def test_seed_is_stable_across_runs_and_platforms() -> None:
    # Pinned value: changing the derivation would silently change every saved collage.
    assert derive_seed(42, "layout", "grid") == 0x8D7374B38DC3A365
