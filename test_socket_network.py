import os,sys,time,json,subprocess,urllib.request,urllib.error,shutil
from pathlib import Path
from core import Ledger,Wallet,make_transfer,make_vote,canon

ROOT=Path(__file__).parent; TMP=ROOT/'socket_test'; shutil.rmtree(TMP,ignore_errors=True); TMP.mkdir()
# deterministic shared validator and funded sender state across three independent DBs
vals=[Wallet.create() for _ in range(3)]; sender=Wallet.create(); recipient=Wallet.create()
for i in range(3):
    db=TMP/f'n{i+1}.sqlite3'; l=Ledger(str(db))
    for w in vals:l.add_validator(w)
    l._set(sender.address,10_000_000,0)
    l.db.commit()

def start(i,port,peers):
    env=os.environ.copy(); env.update(HNK_DB=str(TMP/f'n{i}.sqlite3'),HNK_PEER_TOKEN='peer-secret',HNK_PEERS=','.join(peers),HNK_SYNC_INTERVAL='0.2')
    return subprocess.Popen([sys.executable,'-m','uvicorn','server:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def get(url):
    req=urllib.request.Request(url,headers={'Authorization':'Bearer peer-secret'})
    with urllib.request.urlopen(req,timeout=3) as r:return json.loads(r.read())
def post(url,obj):
    raw=json.dumps(obj).encode(); req=urllib.request.Request(url,data=raw,method='POST',headers={'Authorization':'Bearer peer-secret','Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=3) as r:return json.loads(r.read())

ports=[18101,18102,18103]
procs=[]
try:
    peers=[[f'http://127.0.0.1:{ports[j]}' for j in range(3) if j!=i] for i in range(3)]
    for i in range(3): procs.append(start(i+1,ports[i],peers[i]))
    for _ in range(30):
        try:
            if all(get(f'http://127.0.0.1:{p}/health')['height']==0 for p in ports):break
        except:time.sleep(.2)
    tx=make_transfer(sender,0,recipient.address,1234)
    # quorum vote for deterministic height-1 proposal
    l=Ledger(str(TMP/'n1.sqlite3')); height=1; proposer=vals[sorted(range(3), key=lambda i: vals[i].address)[height%3]]; prev=l.db.execute('select hash from blocks order by height desc limit 1').fetchone()[0]
    payload={'height':height,'prev_hash':prev,'proposer':proposer.address,'txids':[__import__('core').txid(tx)]}
    import hashlib
    ph=hashlib.sha256(canon(payload)).hexdigest(); votes=[make_vote(w,ph,height) for w in vals]
    res=post(f'http://127.0.0.1:{ports[0]}/api/produce',{'proposer':proposer.address,'txs':[tx],'votes':votes}); assert res['committed']
    tip=res['hash']
    # real socket P2P sync convergence
    for _ in range(40):
        hs=[get(f'http://127.0.0.1:{p}/health') for p in ports]
        if all(x['height']==1 and x['tip']==tip for x in hs):break
        time.sleep(.25)
    assert all(x['height']==1 and x['tip']==tip for x in hs),hs
    assert all(get(f'http://127.0.0.1:{p}/balance/{recipient.address}')['balance']==1234 for p in ports)
    # Byzantine proposal must fail on node2: alter tx amount while retaining original votes/hash relation
    bad=dict(tx); bad['payload']=dict(tx['payload']); bad['payload']['amount']=9999
    try: post(f'http://127.0.0.1:{ports[1]}/api/produce',{'proposer':vals[1].address,'txs':[bad],'votes':votes}); raise AssertionError('bad proposal accepted')
    except urllib.error.HTTPError as e: assert e.code==400
    # partition: stop node3, commit next block on node1, then restart node3 and verify catch-up
    procs[2].terminate(); procs[2].wait(timeout=5)
    l=Ledger(str(TMP/'n1.sqlite3')); tx2=make_transfer(sender,1,recipient.address,2222); height=2; proposer2=vals[sorted(range(3), key=lambda i: vals[i].address)[height%3]]; prev=tip
    payload={'height':height,'prev_hash':prev,'proposer':proposer2.address,'txids':[__import__('core').txid(tx2)]}; ph=hashlib.sha256(canon(payload)).hexdigest(); votes2=[make_vote(w,ph,height) for w in vals]
    r2=post(f'http://127.0.0.1:{ports[0]}/api/produce',{'proposer':proposer2.address,'txs':[tx2],'votes':votes2}); tip2=r2['hash']
    procs[2]=start(3,ports[2],peers[2])
    for _ in range(50):
        try:
            h3=get(f'http://127.0.0.1:{ports[2]}/health')
            if h3['height']==2 and h3['tip']==tip2:break
        except:pass
        time.sleep(.2)
    assert h3['height']==2 and h3['tip']==tip2,h3
    print('PASS 6/6: socket startup, P2P sync, convergence, Byzantine rejection, partition/rejoin, state recovery')
finally:
    for p in procs:
        try:p.terminate();p.wait(timeout=3)
        except:pass
