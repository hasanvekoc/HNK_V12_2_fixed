import os, tempfile, hashlib, pytest
from core import Ledger, Wallet, make_transfer, make_vote, canon, txid, valid_address

def setup():
    d=tempfile.mktemp(); l=Ledger(d); ws=[Wallet.create() for _ in range(3)]
    for w in ws:l.add_validator(w)
    return d,l,ws

def close(d,l):
    l.db.close();
    if os.path.exists(d): os.unlink(d)

def test_malformed_vote_is_rejected_without_type_error():
    d,l,ws=setup()
    try:
        with pytest.raises(ValueError, match='invalid vote'): l.verify_vote(None,'0'*64,1)
    finally: close(d,l)

def test_unsupported_contract_kinds_are_not_silent_fee_transactions():
    d,l,ws=setup(); a,b=Wallet.create(),Wallet.create()
    try:
        l._set(a.address,200000,0); l.db.commit()
        tx=make_transfer(a,0,b.address,1); tx['kind']='call'; tx['signature']=a.sign(canon({k:v for k,v in tx.items() if k!='signature'}))
        with pytest.raises(ValueError, match='unsupported transaction kind'): l.verify_tx(tx)
    finally: close(d,l)

def test_chain_integrity_detects_tampering():
    d,l,ws=setup()
    try:
        assert l.verify_block_integrity()
        l.db.execute("UPDATE blocks SET hash=? WHERE height=0",('f'*64,))
        with pytest.raises(ValueError, match='invalid genesis hash'): l.verify_block_integrity()
    finally: close(d,l)

def test_block_prev_hash_mismatch_is_rejected():
    d,l,ws=setup(); a,b=Wallet.create(),Wallet.create()
    try:
        l._set(a.address,200000,0); l.db.commit()
        tx=make_transfer(a,0,b.address,1); h=1; proposer=l.expected_proposer(h)
        payload={'height':h,'prev_hash':'1'*64,'proposer':proposer,'txids':[txid(tx)]}; ph=hashlib.sha256(canon(payload)).hexdigest(); votes=[make_vote(w,ph,h) for w in ws]
        with pytest.raises(ValueError, match='prev|proposer|quorum|invalid vote signature'): l.commit_block(proposer,[tx],votes)
    finally: close(d,l)

def test_address_shape_strict():
    assert not valid_address('HNK1'+'g'*40)
    assert not valid_address('HNK1'+'a'*39)
