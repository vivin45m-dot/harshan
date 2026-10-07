"""A small proof-of-work provenance chain.

One block per calendar month. A block holds every ledger record dated in
that month (import shipments, FDA recalls, CDC outbreaks), a Merkle root
over those records, the hash of the previous block, and a nonce found by
proof of work. Changing any stored record changes its leaf hash, which
changes the Merkle root, which no longer matches the block hash - so
``verify`` can point at the exact block that was touched.
"""
import hashlib
import json
from dataclasses import dataclass, field

GENESIS_PREV = "0" * 64


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(obj) -> str:
    # Sorted keys and no whitespace so the same record always hashes the same.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def record_hash(record: dict) -> str:
    return sha256(canonical(record))


def merkle_root(leaf_hashes: list[str]) -> str:
    if not leaf_hashes:
        return sha256("")
    level = list(leaf_hashes)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [sha256(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


@dataclass
class Block:
    index: int
    period: str            # "YYYY-MM"
    prev_hash: str
    merkle: str
    record_count: int
    nonce: int = 0
    hash: str = ""
    records: list = field(default_factory=list, repr=False)

    def header(self) -> str:
        return canonical({
            "index": self.index,
            "period": self.period,
            "prev_hash": self.prev_hash,
            "merkle": self.merkle,
            "record_count": self.record_count,
            "nonce": self.nonce,
        })

    def compute_hash(self) -> str:
        return sha256(self.header())

    def mine(self, difficulty: int) -> None:
        target = "0" * difficulty
        self.nonce = 0
        h = self.compute_hash()
        while not h.startswith(target):
            self.nonce += 1
            h = self.compute_hash()
        self.hash = h


def build_block(index: int, period: str, prev_hash: str, records: list[dict], difficulty: int) -> Block:
    leaves = [record_hash(r) for r in records]
    block = Block(index, period, prev_hash, merkle_root(leaves), len(records), records=records)
    block.mine(difficulty)
    return block


@dataclass
class Problem:
    block_index: int
    period: str
    kind: str
    detail: str


def verify(blocks: list[Block], difficulty: int) -> list[Problem]:
    """Recompute everything and report each block that no longer checks out."""
    problems = []
    prev = GENESIS_PREV
    target = "0" * difficulty
    for b in blocks:
        leaves = [record_hash(r) for r in b.records]
        if len(leaves) != b.record_count:
            problems.append(Problem(b.index, b.period, "record_count",
                                    f"header says {b.record_count} records, found {len(leaves)}"))
        if merkle_root(leaves) != b.merkle:
            problems.append(Problem(b.index, b.period, "merkle",
                                    "stored records do not match the block's Merkle root"))
        if b.compute_hash() != b.hash:
            problems.append(Problem(b.index, b.period, "hash", "header hash does not match"))
        if not b.hash.startswith(target):
            problems.append(Problem(b.index, b.period, "pow", "hash does not meet difficulty"))
        if b.prev_hash != prev:
            problems.append(Problem(b.index, b.period, "link", "previous-hash link is broken"))
        prev = b.hash
    return problems
