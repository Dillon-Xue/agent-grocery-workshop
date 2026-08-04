import os

from seed_initial_parts import seed, SEED_PARTS


def test_seed_writes_all(tmp_path):
    r = str(tmp_path / "ws")
    os.makedirs(r)
    n = seed(r)
    assert n == len(SEED_PARTS)
    assert n == 23
    files = 0
    for _, _, fns in os.walk(os.path.join(r, "library")):
        files += len([f for f in fns if f.endswith(".json")])
    assert files == 23
