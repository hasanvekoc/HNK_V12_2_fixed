from fastapi import FastAPI,HTTPException,Header,Request
from pydantic import BaseModel
from core import Ledger,txid,Wallet,make_vote
import os,time,threading,json,urllib.request,urllib.error

VERSION='12.2.0'
app=FastAPI(title='HNK Node V11',version=VERSION)
ledger=Ledger(os.getenv('HNK_DB','data/hnk.sqlite3'))
try:
    ledger.verify_block_integrity()
except Exception as e:
    raise RuntimeError(f'blockchain integrity check failed: {e}') from e
API_TOKEN=os.getenv('HNK_API_TOKEN'); PEER_TOKEN=os.getenv('HNK_PEER_TOKEN')
RATE={}; RATE_LIMIT=int(os.getenv('HNK_RATE_LIMIT','60')); MEMPOOL={}; LOCK=threading.Lock()
PEERS=[p.strip().rstrip('/') for p in os.getenv('HNK_PEERS','').split(',') if p.strip()]
SYNC_INTERVAL=float(os.getenv('HNK_SYNC_INTERVAL','2'))
class Tx(BaseModel): chain_id:str; nonce:int; gas_limit:int; gas_price:int; kind:str; sender:str; public_key:str; signature:str; payload:dict
class Proposal(BaseModel): proposer:str; votes:list[dict]; txs:list[dict]=[]; txids:list[str]=[]

def guard(req,authorization):
    if API_TOKEN and authorization!=f'Bearer {API_TOKEN}': raise HTTPException(401,'authentication required')
    ip=req.client.host if req.client else 'unknown'; now=int(time.time()); key=(ip,now//60); RATE[key]=RATE.get(key,0)+1
    if RATE[key]>RATE_LIMIT: raise HTTPException(429,'rate limit exceeded')
    if len(RATE)>10000:
        RATE.clear()
def peer_guard(authorization):
    if PEER_TOKEN and authorization!=f'Bearer {PEER_TOKEN}': raise HTTPException(401,'peer authentication required')

def block_row(height):
    r=ledger.db.execute('SELECT height,hash,prev_hash,proposer,payload,state_root FROM blocks WHERE height=?',(height,)).fetchone()
    if not r: return None
    return {'height':r[0],'hash':r[1],'prev_hash':r[2],'proposer':r[3],'payload':json.loads(r[4]),'state_root':r[5]}

def http_json(url,method='GET',data=None):
    req=urllib.request.Request(url,method=method,headers={'Authorization':f'Bearer {PEER_TOKEN}'} if PEER_TOKEN else {})
    if data is not None:
        raw=json.dumps(data).encode(); req.data=raw; req.add_header('Content-Type','application/json')
    with urllib.request.urlopen(req,timeout=2) as r:return json.loads(r.read())

def sync_once():
    if not PEERS:return
    local_h=ledger.db.execute('SELECT MAX(height) FROM blocks').fetchone()[0]
    for peer in PEERS:
        try:
            remote=http_json(peer+'/peer/status')
            rh=int(remote['height'])
            if rh == local_h and remote.get('tip'):
                ledger.detect_fork(local_h,remote['tip'])
                continue
            if rh<local_h: continue
            for h in range(local_h+1,rh+1):
                p=http_json(peer+f'/peer/proposal/{h}')
                if p.get('chain_id') not in (None, __import__('core').CHAIN_ID): raise ValueError('peer chain mismatch')
                if int(p.get('height',-1)) != h: raise ValueError('peer height mismatch')
                expected_prev=ledger.db.execute('SELECT hash FROM blocks WHERE height=?',(h-1,)).fetchone()[0]
                if p.get('prev_hash') not in (None, expected_prev): raise ValueError('peer previous hash mismatch')
                local_hash=ledger.commit_block(p['proposer'],p['txs'],p['votes'],expected_height=h)
                if local_hash != p.get('hash'): raise ValueError('peer block hash mismatch')
            local_h=rh
        except Exception:
            continue

def sync_loop():
    while True:
        try: sync_once()
        except Exception: pass
        time.sleep(SYNC_INTERVAL)
if PEERS:
    threading.Thread(target=sync_loop,daemon=True).start()

@app.get('/health')
def health():
    h=ledger.db.execute('SELECT height,hash FROM blocks ORDER BY height DESC LIMIT 1').fetchone(); return {'ok':True,'version':VERSION,'chain_id':ledger.db.execute("SELECT v FROM meta WHERE k='chain_id'").fetchone()[0],'height':h[0],'tip':h[1],'mempool':len(MEMPOOL),'peers':PEERS}
@app.get('/balance/{address}')
def balance(address:str):
    if not __import__('core').valid_address(address): raise HTTPException(400,'invalid address')
    return {'address':address,'balance':ledger.balance(address),'nonce':ledger.nonce(address)}
@app.post('/api/tx/verify')
def verify(tx:Tx,request:Request,authorization:str|None=Header(default=None)):
    guard(request,authorization)
    try:return {'valid':True,'txid':txid(tx.model_dump()),'sender':ledger.verify_tx(tx.model_dump())['sender']}
    except Exception as e: raise HTTPException(400,str(e))
@app.post('/api/tx/submit')
def submit(tx:Tx,request:Request,authorization:str|None=Header(default=None)):
    guard(request,authorization); raw=tx.model_dump(); tid=txid(raw)
    if len(MEMPOOL) >= int(os.getenv('HNK_MAX_MEMPOOL','10000')) and tid not in MEMPOOL: raise HTTPException(429,'mempool full')
    try: ledger.verify_tx(raw)
    except Exception as e: raise HTTPException(400,str(e))
    with LOCK:
        if tid in MEMPOOL:return {'accepted':True,'txid':tid,'duplicate':True}
        MEMPOOL[tid]=raw
    return {'accepted':True,'txid':tid}
@app.get('/api/mempool')
def mempool(request:Request,authorization:str|None=Header(default=None)):
    guard(request,authorization);return {'txs':list(MEMPOOL.values())}
@app.get('/api/blocks/{height}')
def block(height:int):
    r=block_row(height)
    if not r: raise HTTPException(404,'block not found')
    return r
@app.get('/api/peers')
def peers(request:Request,authorization:str|None=Header(default=None)):
    guard(request,authorization);return {'peers':PEERS}
@app.post('/api/produce')
def produce(req:Proposal,request:Request,authorization:str|None=Header(default=None)):
    guard(request,authorization)
    txs=list(req.txs)
    if not txs and req.txids:
        with LOCK:
            for tid in req.txids:
                if tid not in MEMPOOL: raise HTTPException(400,f'tx not in mempool: {tid}')
                txs.append(MEMPOOL[tid])
    try:
        h=ledger.commit_block(req.proposer,txs,req.votes)
        with LOCK:
            for t in txs: MEMPOOL.pop(txid(t),None)
        return {'committed':True,'height':ledger.db.execute('SELECT MAX(height) FROM blocks').fetchone()[0],'hash':h}
    except Exception as e: raise HTTPException(400,str(e))
@app.get('/peer/status')
def peer_status(authorization:str|None=Header(default=None)):
    peer_guard(authorization); h=ledger.db.execute('SELECT height,hash FROM blocks ORDER BY height DESC LIMIT 1').fetchone(); return {'height':h[0],'tip':h[1],'chain_id':ledger.db.execute("SELECT v FROM meta WHERE k='chain_id'").fetchone()[0]}
@app.get('/peer/proposal/{height}')
def peer_proposal(height:int,authorization:str|None=Header(default=None)):
    peer_guard(authorization); r=block_row(height)
    if not r: raise HTTPException(404,'block not found')
    p=r['payload']; txs=[]
    for tid in p['txids']:
        x=ledger.db.execute('SELECT payload FROM txs WHERE txid=?',(tid,)).fetchone()
        if not x: raise HTTPException(409,'transaction body unavailable')
        tx=json.loads(x[0])
        if txid(tx)!=tid: raise HTTPException(409,'transaction id mismatch')
        txs.append(tx)
    votes=[]
    for v in p.get('votes',[]):
        vr=ledger.db.execute('SELECT voter,signature FROM votes WHERE block_hash=? AND voter=?',(r['hash'],v['voter'])).fetchone()
        # public key is recovered from tx/validator metadata in this reference network; proposal requires it in validator table extension below.
        pk=ledger.db.execute('SELECT public_key FROM validator_keys WHERE address=?',(v['voter'],)).fetchone()
        if not pk: raise HTTPException(409,'validator key unavailable')
        votes.append({'voter':v['voter'],'public_key':pk[0],'signature':v['signature']})
    return {'height':height,'proposer':r['proposer'],'prev_hash':r['prev_hash'],'txs':txs,'votes':votes,'hash':r['hash'],'chain_id':__import__('core').CHAIN_ID}
@app.get('/peer/blocks/{height}')
def peer_blocks(height:int,authorization:str|None=Header(default=None)):
    peer_guard(authorization);return block(height)
