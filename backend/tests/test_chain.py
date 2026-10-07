import copy

from foodtrace.ledger import chain


def make_chain(n_blocks=4, difficulty=2):
    blocks, prev = [], chain.GENESIS_PREV
    for i in range(n_blocks):
        records = [{"kind": "shipment", "source_ref": f"r{i}-{j}", "payload": {"qty_kg": j * 10.0}}
                   for j in range(3)]
        b = chain.build_block(i, f"2020-{i + 1:02d}", prev, records, difficulty)
        blocks.append(b)
        prev = b.hash
    return blocks


def test_valid_chain_has_no_problems():
    assert chain.verify(make_chain(), 2) == []


def test_mined_hash_meets_difficulty():
    for b in make_chain(difficulty=3):
        assert b.hash.startswith("000")


def test_editing_a_record_is_caught_in_that_block():
    blocks = make_chain()
    blocks[2].records[1]["payload"]["qty_kg"] = 999999.0
    problems = chain.verify(blocks, 2)
    assert {p.block_index for p in problems} == {2}
    assert any(p.kind == "merkle" for p in problems)


def test_remining_one_block_breaks_the_next_link():
    blocks = make_chain()
    tampered = copy.deepcopy(blocks[1])
    tampered.records[0]["payload"]["qty_kg"] = -1
    blocks[1] = chain.build_block(1, tampered.period, tampered.prev_hash, tampered.records, 2)
    problems = chain.verify(blocks, 2)
    assert any(p.kind == "link" and p.block_index == 2 for p in problems)


def test_merkle_root_depends_on_order():
    a, b = chain.sha256("a"), chain.sha256("b")
    assert chain.merkle_root([a, b]) != chain.merkle_root([b, a])


def test_canonical_json_ignores_key_order():
    assert chain.record_hash({"a": 1, "b": 2}) == chain.record_hash({"b": 2, "a": 1})
