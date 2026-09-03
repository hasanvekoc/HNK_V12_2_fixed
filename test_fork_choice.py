import hashlib, os, tempfile
import pytest
from core import Ledger, Wallet, make_transfer, make_vote, canon, txid


def _block_material(ledger, tx, height, proposer):
    prev = ledger.db.execute('SELECT hash FROM blocks ORDER BY height DESC LIMIT 1').fetchone()[0]
    payload = {'height': height, 'prev_hash': prev, 'proposer': proposer, 'txids': [txid(tx)]}
    provisional = hashlib.sha256(canon(payload)).hexdigest()
    return payload, provisional


def test_validator_equivocation_is_rejected_at_same_height():
    path = tempfile.mktemp()
    try:
        l = Ledger(path)
        vals = [Wallet.create() for _ in range(3)]
        for v in vals: l.add_validator(v)
        a, b, c = Wallet.create(), Wallet.create(), Wallet.create()
        l._set(a.address, 200_000, 0); l.db.commit()
        proposer = l.expected_proposer(1)
        tx1 = make_transfer(a, 0, b.address, 1)
        _, ph1 = _block_material(l, tx1, 1, proposer)
        votes1 = [make_vote(v, ph1, 1) for v in vals]
        h1 = l.commit_block(proposer, [tx1], votes1)

        # Same validators now sign a conflicting block at the same height.
        # Build it independently from the height-0 parent and different tx.
        prev = l.db.execute('SELECT hash FROM blocks WHERE height=0').fetchone()[0]
        tx2 = make_transfer(a, 0, c.address, 2)
        payload2 = {'height': 1, 'prev_hash': prev, 'proposer': proposer, 'txids': [txid(tx2)]}
        ph2 = hashlib.sha256(canon(payload2)).hexdigest()
        votes2 = [make_vote(v, ph2, 1) for v in vals]
        with pytest.raises(ValueError, match='equivocation|unexpected block height'):
            l.commit_block(proposer, [tx2], votes2, expected_height=1)
        assert l.db.execute('SELECT COUNT(*) FROM blocks').fetchone()[0] == 2
        assert l.db.execute('SELECT hash FROM blocks WHERE height=1').fetchone()[0] == h1
    finally:
        try: l.db.close()
        except Exception: pass
        if os.path.exists(path): os.unlink(path)


def test_conflicting_peer_tip_is_detected_without_overwrite():
    paths = [tempfile.mktemp(), tempfile.mktemp()]
    try:
        a, b = Ledger(paths[0]), Ledger(paths[1])
        vals = [Wallet.create() for _ in range(3)]
        for l in (a, b):
            for v in vals: l.add_validator(v)
        sender, r1, r2 = Wallet.create(), Wallet.create(), Wallet.create()
        for l in (a, b): l._set(sender.address, 200_000, 0); l.db.commit()
        proposer = a.expected_proposer(1)
        tx1 = make_transfer(sender, 0, r1.address, 1)
        _, ph1 = _block_material(a, tx1, 1, proposer)
        votes1 = [make_vote(v, ph1, 1) for v in vals]
        a.commit_block(proposer, [tx1], votes1)
        tx2 = make_transfer(sender, 0, r2.address, 2)
        prev = b.db.execute('SELECT hash FROM blocks WHERE height=0').fetchone()[0]
        payload2 = {'height': 1, 'prev_hash': prev, 'proposer': proposer, 'txids': [txid(tx2)]}
        ph2 = hashlib.sha256(canon(payload2)).hexdigest()
        votes2 = [make_vote(v, ph2, 1) for v in vals]
        b.commit_block(proposer, [tx2], votes2)
        with pytest.raises(ValueError, match='fork detected at height 1'):
            a.detect_fork(1, ph2 + '0')
        assert a.db.execute('SELECT MAX(height) FROM blocks').fetchone()[0] == 1
    finally:
        for l in (locals().get('a'), locals().get('b')):
            try: l.db.close()
            except Exception: pass
        for p in paths:
            if os.path.exists(p): os.unlink(p)
