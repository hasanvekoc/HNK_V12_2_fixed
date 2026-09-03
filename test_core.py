import tempfile,os
from core import Ledger,Wallet,make_transfer,make_vote

def setup():
 d=tempfile.mktemp();l=Ledger(d);ws=[Wallet.create() for _ in range(3)]
 for w in ws:l.add_validator(w)
 return d,l,ws

def test_restart_and_genesis():
 d,l,_=setup();assert l.db.execute('select count(*) from blocks').fetchone()[0]==1;l.db.close();b=Ledger(d);assert b.db.execute('select count(*) from blocks').fetchone()[0]==1;os.unlink(d)

def test_signature_spoof_rejected():
 d,l,ws=setup();a,v=Wallet.create(),Wallet.create();l._set(a.address,1_000_000,0);l.db.commit();tx=make_transfer(a,0,v.address,1);tx['sender']=v.address
 try:l.verify_tx(tx);assert False
 except Exception:pass
 os.unlink(d)

def test_atomic_rollback():
 d,l,ws=setup();a,v=Wallet.create(),Wallet.create();l._set(a.address,100_000,0);l.db.commit();tx=make_transfer(a,0,v.address,999_999)
 before=l.snapshot();votes=[];height=1;payload={'height':height,'prev_hash':l.db.execute('select hash from blocks where height=0').fetchone()[0],'proposer':l.expected_proposer(height),'txids':[__import__('core').txid(tx)]};import core;ph=__import__('hashlib').sha256(core.canon(payload)).hexdigest();votes=[{'voter':w.address,'public_key':core.b64(w.public_bytes),'signature':w.sign(core.canon({'chain_id':core.CHAIN_ID,'height':height,'block_hash':ph}))} for w in ws]
 try:l.commit_block(l.expected_proposer(height),[tx],votes);assert False
 except Exception:pass
 assert l.snapshot()==before;os.unlink(d)

def test_quorum_and_persistence():
 d,l,ws=setup();a,v=Wallet.create(),Wallet.create();l._set(a.address,100_000,0);l.db.commit();tx=make_transfer(a,0,v.address,1);height=1;prev=l.db.execute('select hash from blocks order by height desc limit 1').fetchone()[0];import core,hashlib;payload={'height':height,'prev_hash':prev,'proposer':l.expected_proposer(height),'txids':[core.txid(tx)]};ph=hashlib.sha256(core.canon(payload)).hexdigest();votes=[core.make_vote(w,ph,height) for w in ws];h=l.commit_block(l.expected_proposer(height),[tx],votes);assert l.balance(v.address)==1;l.db.close();b=Ledger(d);assert b.db.execute('select height from blocks order by height desc limit 1').fetchone()[0]==1;assert b.balance(v.address)==1;os.unlink(d)
