import tempfile, os, json
from fastapi.testclient import TestClient
import server
from core import Ledger,Wallet,make_transfer,make_vote,canon,txid
from wallet import EncryptedWallet

def test_encrypted_wallet_roundtrip():
 p=tempfile.mktemp(); w=EncryptedWallet.create(); w.save(p,'strong-password-123'); assert w.core_wallet().address==EncryptedWallet.load(p,'strong-password-123').core_wallet().address
 try: EncryptedWallet.load(p,'wrong') ; assert False
 except Exception: pass
 os.unlink(p)

def test_mempool_and_produce():
 d=tempfile.mktemp(); l=Ledger(d); ws=[Wallet.create() for _ in range(3)]
 for w in ws:l.add_validator(w)
 a,b=Wallet.create(),Wallet.create();l._set(a.address,100000,0);l.db.commit()
 tx=make_transfer(a,0,b.address,1)
 old=server.ledger; server.ledger=l; server.MEMPOOL.clear()
 c=TestClient(server.app)
 r=c.post('/api/tx/submit',json=tx); assert r.status_code==200
 height=1; prev=l.db.execute('select hash from blocks order by height desc limit 1').fetchone()[0]
 payload={'height':height,'prev_hash':prev,'proposer':l.expected_proposer(height),'txids':[txid(tx)]}
 import hashlib; ph=hashlib.sha256(canon(payload)).hexdigest(); votes=[make_vote(w,ph,height) for w in ws]
 r=c.post('/api/produce',json={'proposer':l.expected_proposer(height),'votes':votes,'txids':[txid(tx)]}); assert r.status_code==200; assert l.balance(b.address)==1
 server.ledger=old; l.db.close(); os.unlink(d)
