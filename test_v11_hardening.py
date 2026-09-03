import hashlib, tempfile, os
import pytest
import core
from core import Ledger, Wallet, make_transfer, make_vote

def setup():
    d=tempfile.mktemp(); l=Ledger(d); ws=[Wallet.create() for _ in range(3)]
    for w in ws:l.add_validator(w)
    return d,l,ws

def test_invalid_address_rejected():
    d,l,ws=setup(); a=Wallet.create(); b=Wallet.create(); l._set(a.address,1_000_000,0); l.db.commit()
    tx=make_transfer(a,0,b.address,1); tx['payload']['to']='HNK1'+'z'*40
    # signature must also be recomputed after mutation; invalid payload is then caught deterministically
    tx['signature']=a.sign(core.canon({k:v for k,v in tx.items() if k!='signature'}))
    with pytest.raises(ValueError): l.verify_tx(tx)
    l.db.close(); os.unlink(d)

def test_validator_stored_key_cannot_be_swapped():
    d,l,ws=setup(); h=1; proposer=l.expected_proposer(h); prev=l.db.execute('select hash from blocks where height=0').fetchone()[0]
    a=Wallet.create(); tx=make_transfer(a,0,Wallet.create().address,1)
    payload={'height':h,'prev_hash':prev,'proposer':proposer,'txids':[core.txid(tx)]}; ph=hashlib.sha256(core.canon(payload)).hexdigest()
    vote=make_vote(ws[0],ph,h); vote['public_key']=core.b64(Wallet.create().public_bytes)
    with pytest.raises(ValueError, match='validator key mismatch|voter key mismatch'): l.verify_vote(vote,ph,h)
    l.db.close(); os.unlink(d)
