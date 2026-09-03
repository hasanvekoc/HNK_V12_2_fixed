from fastapi import FastAPI,HTTPException,Header,Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from core import Ledger,txid,Wallet,make_vote
import os,time,threading,json,urllib.request,urllib.error
VERSION='12.2.0'
app=FastAPI(title='HNK Node V11',version=VERSION)

# Allow the deployed HNK static panel to call the public API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'https://hnk-panel-vzxn.onrender.com',
    ],
    allow_credentials=False,
    allow_methods=['GET','POST','OPTIONS'],
    allow_headers=['*'],
)

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
                if p.get('chain_id') not in (None, _import_('core').CHAIN_ID): raise ValueError('peer chain mismatch')
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
        except Exception: pa…
