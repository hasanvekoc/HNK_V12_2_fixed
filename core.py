from __future__ import annotations
import base64, hashlib, json, sqlite3, time, re
from pathlib import Path
from typing import Any
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

TOTAL_SUPPLY=1_000_000_000
CHAIN_ID='HNK-TESTNET-2'
BASE_GAS={'transfer':21_000,'deploy':100_000,'call':50_000}
MAX_TX_BYTES=64*1024; MAX_BLOCK_TXS=2000; MAX_GAS_PER_BLOCK=20_000_000

def canon(x:Any)->bytes:return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def b64(b:bytes)->str:return base64.urlsafe_b64encode(b).decode().rstrip('=')
def ub64(s:str)->bytes:
    if not isinstance(s,str) or len(s)>4096: raise ValueError('invalid base64')
    try: return base64.urlsafe_b64decode(s+'='*(-len(s)%4))
    except Exception as e: raise ValueError('invalid base64') from e
def address(pub:bytes)->str:return 'HNK1'+hashlib.sha256(pub).hexdigest()[:40]
def valid_address(a:str)->bool:return isinstance(a,str) and re.fullmatch(r'HNK1[0-9a-f]{40}',a) is not None
def txid(tx):return hashlib.sha256(canon({k:v for k,v in tx.items() if k!='signature'})).hexdigest()

class Wallet:
    def __init__(self,private):self.private=private
    @classmethod
    def create(cls):return cls(Ed25519PrivateKey.generate())
    @property
    def public_bytes(self):return self.private.public_key().public_bytes_raw()
    @property
    def address(self):return address(self.public_bytes)
    def sign(self,payload):return b64(self.private.sign(payload))

class Ledger:
    def __init__(self,db='data/hnk.sqlite3'):
        Path(db).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(db,check_same_thread=False,isolation_level=None,timeout=10.0)
        self.db.execute('PRAGMA busy_timeout=10000')
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA synchronous=FULL'); self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS blocks(height INTEGER PRIMARY KEY,hash TEXT UNIQUE NOT NULL,prev_hash TEXT NOT NULL,proposer TEXT NOT NULL,payload TEXT NOT NULL,state_root TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS state(address TEXT PRIMARY KEY,balance INTEGER NOT NULL,nonce INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS validators(address TEXT PRIMARY KEY,power INTEGER NOT NULL,active INTEGER NOT NULL,jailed INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS validator_keys(address TEXT PRIMARY KEY,public_key TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS txs(txid TEXT PRIMARY KEY,payload TEXT NOT NULL,status TEXT NOT NULL,block_height INTEGER);
        CREATE TABLE IF NOT EXISTS votes(block_hash TEXT NOT NULL,voter TEXT NOT NULL,signature TEXT NOT NULL,PRIMARY KEY(block_hash,voter));
        CREATE TABLE IF NOT EXISTS vote_locks(height INTEGER NOT NULL,voter TEXT NOT NULL,block_hash TEXT NOT NULL,PRIMARY KEY(height,voter));
        CREATE TABLE IF NOT EXISTS peers(url TEXT PRIMARY KEY,last_seen INTEGER NOT NULL);
        '''); self._genesis()
    def _genesis(self):
        if self.db.execute("SELECT 1 FROM meta WHERE k='chain_id'").fetchone(): return
        g={'chain_id':CHAIN_ID,'total_supply':TOTAL_SUPPLY,'version':2,'allocations':{}}
        gh=hashlib.sha256(canon(g)).hexdigest(); sr=self.state_root()
        self.db.execute('BEGIN');
        try:
            self.db.execute("INSERT INTO meta VALUES('chain_id',?)",(CHAIN_ID,));self.db.execute("INSERT INTO meta VALUES('total_supply',?)",(str(TOTAL_SUPPLY),));self.db.execute("INSERT INTO meta VALUES('genesis_hash',?)",(gh,));self.db.execute("INSERT INTO meta VALUES('network_version',?)",('2',))
            self.db.execute('INSERT INTO blocks VALUES(0,?,?,?,?,?)',(gh,'0'*64,'GENESIS',json.dumps(g,sort_keys=True),sr));self.db.execute('COMMIT')
        except: self.db.execute('ROLLBACK');raise
    def state_root(self):
        rows=self.db.execute('SELECT address,balance,nonce FROM state ORDER BY address').fetchall();return hashlib.sha256(canon(rows)).hexdigest()
    def snapshot(self):return self.db.execute('SELECT address,balance,nonce FROM state ORDER BY address').fetchall()
    def balance(self,a):r=self.db.execute('SELECT balance FROM state WHERE address=?',(a,)).fetchone();return r[0] if r else 0
    def nonce(self,a):r=self.db.execute('SELECT nonce FROM state WHERE address=?',(a,)).fetchone();return r[0] if r else 0
    def _set(self,a,b,n):
        if b<0 or n<0:raise ValueError('negative state')
        self.db.execute('INSERT INTO state VALUES(?,?,?) ON CONFLICT(address) DO UPDATE SET balance=excluded.balance,nonce=excluded.nonce',(a,b,n))
    def total_balance(self):return sum(r[0] for r in self.db.execute('SELECT balance FROM state'))
    def verify_tx(self,tx):
        if not isinstance(tx,dict) or len(canon(tx))>MAX_TX_BYTES:raise ValueError('invalid transaction')
        required=('chain_id','nonce','gas_limit','gas_price','kind','sender','public_key','signature','payload')
        if any(k not in tx for k in required):raise ValueError('missing field')
        if tx['chain_id']!=CHAIN_ID:raise ValueError('wrong chain')
        if not valid_address(tx['sender']):raise ValueError('invalid sender address')
        if not isinstance(tx['nonce'],int) or tx['nonce']<0 or tx['nonce']!=self.nonce(tx['sender']):raise ValueError('bad nonce')
        if not isinstance(tx['gas_limit'],int) or not 21_000<=tx['gas_limit']<=2_000_000:raise ValueError('bad gas limit')
        if not isinstance(tx['gas_price'],int) or not 1<=tx['gas_price']<=10**9:raise ValueError('bad gas price')
        pub=ub64(tx['public_key']);
        if address(pub)!=tx['sender']:raise ValueError('sender/public key mismatch')
        unsigned={k:v for k,v in tx.items() if k!='signature'}
        try: Ed25519PublicKey.from_public_bytes(pub).verify(ub64(tx['signature']),canon(unsigned))
        except Exception as e: raise ValueError('invalid transaction signature') from e
        if tx['kind'] not in BASE_GAS:raise ValueError('unknown tx kind')
        if tx['kind'] != 'transfer': raise ValueError('unsupported transaction kind')
        if not isinstance(tx['payload'],dict):raise ValueError('invalid payload')
        if tx['kind']=='transfer':
            to=tx['payload'].get('to'); amount=tx['payload'].get('amount')
            if not valid_address(to) or not isinstance(amount,int) or isinstance(amount,bool) or amount<0:raise ValueError('bad transfer')
        return unsigned
    def apply_tx(self,tx):
        self.verify_tx(tx); p=tx['payload'];gas=BASE_GAS[tx['kind']]
        if tx['gas_limit']<gas:raise ValueError('insufficient gas limit')
        fee=gas*tx['gas_price'] # charge measured intrinsic gas, refund unused limit
        if tx['kind']=='transfer':
            to=p.get('to','');amount=int(p.get('amount',-1))
            if not valid_address(to) or not isinstance(p.get('amount'),int) or isinstance(p.get('amount'),bool) or amount<0:raise ValueError('bad transfer')
            total=amount+fee
            if self.balance(tx['sender'])<total:raise ValueError('insufficient balance')
            self._set(tx['sender'],self.balance(tx['sender'])-total,self.nonce(tx['sender'])+1);self._set(to,self.balance(to)+amount,self.nonce(to))
        else:
            if self.balance(tx['sender'])<fee:raise ValueError('insufficient balance')
            self._set(tx['sender'],self.balance(tx['sender'])-fee,self.nonce(tx['sender'])+1)
        return gas,fee
    def validator_set(self):return [(a,p) for a,p,active,jailed in self.db.execute('SELECT address,power,active,jailed FROM validators WHERE active=1 AND jailed=0 ORDER BY address')]
    def expected_proposer(self,height):
        vs=self.validator_set();
        if not vs:raise ValueError('no active validators')
        return vs[height%len(vs)][0]
    def verify_block_integrity(self, height=None):
        rows=self.db.execute('SELECT height,hash,prev_hash,proposer,payload,state_root FROM blocks ORDER BY height').fetchall()
        if not rows or rows[0][0] != 0: raise ValueError('missing genesis')
        prev='0'*64
        for h,bh,ph,prop,raw,sr in rows:
            if ph != prev: raise ValueError(f'broken chain at height {h}')
            payload=json.loads(raw)
            if h==0:
                expected=hashlib.sha256(canon(payload)).hexdigest()
                if bh != expected: raise ValueError('invalid genesis hash')
            else:
                base={k:payload[k] for k in ('height','prev_hash','proposer','txids')}
                expected_provisional=hashlib.sha256(canon(base)).hexdigest()
                if payload.get('height') != h or payload.get('prev_hash') != ph: raise ValueError(f'invalid block metadata at height {h}')
                if payload.get('proposer') != prop: raise ValueError(f'invalid proposer metadata at height {h}')
                if payload.get('state_root') != sr: raise ValueError(f'invalid state root at height {h}')
                full={**base,'votes':payload.get('votes',[]),'state_root':sr,'gas_used':payload.get('gas_used')}
                if bh != hashlib.sha256(canon(full)).hexdigest(): raise ValueError(f'invalid block hash at height {h}')
                if self.total_power():
                    for v in payload.get('votes',[]):
                        if 'public_key' in v: self.verify_vote(v,expected_provisional,h)
            prev=bh
        return True

    def add_validator(self,w,power=1):
        if power<1:raise ValueError('bad power')
        self.db.execute('INSERT OR REPLACE INTO validators(address,power,active,jailed) VALUES(?,?,1,0)',(w.address,power)); self.db.execute('INSERT OR REPLACE INTO validator_keys(address,public_key) VALUES(?,?)',(w.address,b64(w.public_bytes)))
    def vote_message(self,block_hash,height):return canon({'chain_id':CHAIN_ID,'height':height,'block_hash':block_hash})
    def verify_vote(self,vote,block_hash,height):
        if not isinstance(vote,dict) or not all(k in vote for k in ('voter','public_key','signature')):raise ValueError('invalid vote')
        if vote['voter'] not in dict(self.validator_set()):raise ValueError('unknown voter')
        if not valid_address(vote['voter']):raise ValueError('invalid voter address')
        pub=ub64(vote['public_key']);
        if address(pub)!=vote['voter']:raise ValueError('voter key mismatch')
        stored=self.db.execute('SELECT public_key FROM validator_keys WHERE address=?',(vote['voter'],)).fetchone()
        if not stored or stored[0]!=vote['public_key']:raise ValueError('validator key mismatch')
        try: Ed25519PublicKey.from_public_bytes(pub).verify(ub64(vote['signature']),self.vote_message(block_hash,height))
        except Exception as e: raise ValueError('invalid vote signature') from e
    def quorum_power(self,votes):
        powers=dict(self.validator_set());return sum(powers[v['voter']] for v in votes if v['voter'] in powers)
    def total_power(self):return sum(p for _,p in self.validator_set())
    def detect_fork(self,height,remote_hash):
        row=self.db.execute('SELECT hash FROM blocks WHERE height=?',(height,)).fetchone()
        if not row: return False
        if row[0] != remote_hash: raise ValueError(f'fork detected at height {height}')
        return False
    def commit_block(self,proposer,txs,votes,expected_height=None):
        if not isinstance(txs,list) or not isinstance(votes,list): raise ValueError('invalid block inputs')
        if len(txs)>MAX_BLOCK_TXS:raise ValueError('block too large')
        if len(votes)>len(self.validator_set()): raise ValueError('too many votes')
        height=self.db.execute('SELECT COALESCE(MAX(height)+1,0) FROM blocks').fetchone()[0];
        if expected_height is not None and height != expected_height: raise ValueError('unexpected block height')
        if proposer!=self.expected_proposer(height):raise ValueError('invalid proposer')
        gas_sum=0
        prev=self.db.execute('SELECT hash FROM blocks ORDER BY height DESC LIMIT 1').fetchone()[0]
        # votes are signed and must uniquely represent >=2/3 validator power
        seen=set()
        for v in votes:
            if v['voter'] in seen:raise ValueError('duplicate vote')
            seen.add(v['voter'])
        payload={'height':height,'prev_hash':prev,'proposer':proposer,'txids':[txid(t) for t in txs]}
        provisional=hashlib.sha256(canon(payload)).hexdigest()
        for v in votes:self.verify_vote(v,provisional,height)
        # A validator may not vote for two different blocks at the same height.
        # Persist the lock before applying state so equivocation is rejected atomically.
        for v in votes:
            locked=self.db.execute('SELECT block_hash FROM vote_locks WHERE height=? AND voter=?',(height,v['voter'])).fetchone()
            if locked and locked[0] != provisional: raise ValueError('validator equivocation detected')
        if self.total_power()==0 or self.quorum_power(votes)*3<self.total_power()*2:raise ValueError('quorum not reached')
        self.db.execute('BEGIN')
        try:
            committed_ids={r[0] for r in self.db.execute('SELECT txid FROM txs WHERE status="committed"')}
            block_ids=set()
            for t in txs:
                tid=txid(t)
                if tid in committed_ids or tid in block_ids:raise ValueError('duplicate tx')
                block_ids.add(tid)
                gas,_=self.apply_tx(t);gas_sum+=gas
            if gas_sum>MAX_GAS_PER_BLOCK:raise ValueError('block gas limit exceeded')
            if self.total_balance()>TOTAL_SUPPLY:raise ValueError('supply invariant violated')
            sr=self.state_root();full={**payload,'votes':[{'voter':v['voter'],'signature':v['signature']} for v in votes],'state_root':sr,'gas_used':gas_sum};h=hashlib.sha256(canon(full)).hexdigest()
            self.db.execute('INSERT INTO blocks VALUES(?,?,?,?,?,?)',(height,h,prev,proposer,json.dumps(full,sort_keys=True),sr))
            for t in txs:self.db.execute('INSERT INTO txs VALUES(?,?,?,?)',(txid(t),json.dumps(t,sort_keys=True),'committed',height))
            for v in votes:
                self.db.execute('INSERT INTO votes VALUES(?,?,?)',(h,v['voter'],v['signature']))
                self.db.execute('INSERT INTO vote_locks VALUES(?,?,?)',(height,v['voter'],provisional))
            self.db.execute('COMMIT');return h
        except Exception:self.db.execute('ROLLBACK');raise

def make_transfer(w,nonce,to,amount,gas_limit=21_000,gas_price=1):
    tx={'chain_id':CHAIN_ID,'nonce':nonce,'gas_limit':gas_limit,'gas_price':gas_price,'kind':'transfer','sender':w.address,'public_key':b64(w.public_bytes),'payload':{'to':to,'amount':amount}}
    tx['signature']=w.sign(canon(tx));return tx

def make_vote(w,block_hash,height):
    msg=canon({'chain_id':CHAIN_ID,'height':height,'block_hash':block_hash})
    return {'voter':w.address,'public_key':b64(w.public_bytes),'signature':w.sign(msg)}
