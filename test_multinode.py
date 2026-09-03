import tempfile, os, hashlib
from core import Ledger, Wallet, make_transfer, make_vote, canon, txid

def test_three_independent_nodes_converge_on_same_block():
    paths=[tempfile.mktemp() for _ in range(3)]
    try:
        nodes=[Ledger(x) for x in paths]
        vals=[Wallet.create() for _ in range(3)]
        for n in nodes:
            for v in vals: n.add_validator(v)
        sender, recipient=Wallet.create(),Wallet.create()
        for n in nodes:
            n._set(sender.address,100000,0); n.db.commit()
        tx=make_transfer(sender,0,recipient.address,7)
        # All three independently verify the exact same signed transaction.
        for n in nodes: n.verify_tx(tx)
        height=1
        prev=nodes[0].db.execute('select hash from blocks order by height desc limit 1').fetchone()[0]
        payload={'height':height,'prev_hash':prev,'proposer':nodes[0].expected_proposer(height),'txids':[txid(tx)]}
        ph=hashlib.sha256(canon(payload)).hexdigest()
        votes=[make_vote(v,ph,height) for v in vals]
        hashes=[n.commit_block(n.expected_proposer(height),[tx],votes) for n in nodes]
        assert len(set(hashes))==1
        assert [n.balance(recipient.address) for n in nodes]==[7,7,7]
        assert [n.db.execute('select hash from blocks where height=1').fetchone()[0] for n in nodes]==hashes
    finally:
        for n in locals().get('nodes',[]): n.db.close()
        for x in paths:
            if os.path.exists(x): os.unlink(x)
