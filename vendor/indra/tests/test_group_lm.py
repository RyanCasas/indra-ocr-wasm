import json

import numpy as np

from indra_ocr.lm import NgramLM, beam_search


def write_lm(path, vocab_size, bits=None, order=3, seen=(2500, 2600, 9000)):
    """A tiny backoff table: the ``seen`` tokens as unigrams (log p -1), and one
    unreachable key per longer history length."""
    b = bits or 11
    arrays = {"order": np.int64(order), "vocab_size": np.int64(vocab_size)}
    if bits is not None:
        arrays["bits"] = np.int64(bits)
    seen = [t for t in seen if t < vocab_size]
    for n in range(order):
        if n == 0:
            k = np.array(sorted(t + 1 for t in seen), np.uint64)
            hk = np.array([0], np.uint64)
        else:
            k = np.array([(1 << min(b * (n + 1), 63)) - 1], np.uint64)
            hk = np.array([(1 << min(b * n, 63)) - 1], np.uint64)
        arrays[f"k{n}"] = k
        arrays[f"v{n}"] = np.full(len(k), -1.0, np.float32)
        arrays[f"hk{n}"] = hk
        arrays[f"hb{n}"] = np.zeros(len(hk), np.float32)
    np.savez(path, **arrays)


def test_a_large_vocab_lm_packs_wider_keys(tmp_path):
    write_lm(tmp_path / "lm_cjk.npz", 11749, bits=14, order=4)
    lm = NgramLM(tmp_path / "lm_cjk.npz")
    assert lm.bits == 14
    # a token id over 2047 needs more than the default 11 bits
    assert np.isclose(lm.logp_keys([(5 << 14) | 9001])[0], -1.0)  # token 9000 (+1)


def test_beam_search_reads_a_wide_vocab(tmp_path):
    write_lm(tmp_path / "lm.npz", 3000, bits=12, order=3)
    lm = NgramLM(tmp_path / "lm.npz")
    T = 4
    blank = np.log(np.array([0.1, 0.9, 0.1, 0.9], np.float32))
    topi = np.array([[2500, 0], [0, 2500], [2600, 0], [0, 2600]], np.int64)
    topv = np.log(
        np.array([[0.9, 0.1], [0.9, 0.1], [0.9, 0.1], [0.9, 0.1]], np.float32)
    )
    ids, steps = beam_search(blank, topv, topi, lm, 0.5, 1.5, 4)
    assert ids == [2500, 2600]


def test_an_lm_that_does_not_fit_a_key_is_refused(tmp_path):
    import pytest

    write_lm(tmp_path / "lm.npz", 11749, bits=14, order=5)
    with pytest.raises(ValueError, match="do not fit"):
        NgramLM(tmp_path / "lm.npz")
