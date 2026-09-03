from __future__ import annotations
import base64, json, os, hashlib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core import Wallet as CoreWallet

class EncryptedWallet:
    def __init__(self, private_bytes: bytes):
        self.private_bytes = private_bytes
    @classmethod
    def create(cls):
        return cls(Ed25519PrivateKey.generate().private_bytes_raw())
    @staticmethod
    def _key(password: str, salt: bytes) -> bytes:
        return Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(password.encode())
    def save(self, path: str, password: str):
        salt=os.urandom(16); nonce=os.urandom(12); key=self._key(password,salt)
        ct=AESGCM(key).encrypt(nonce,self.private_bytes,None)
        pub=Ed25519PrivateKey.from_private_bytes(self.private_bytes).public_key().public_bytes_raw()
        obj={'version':1,'kdf':'scrypt','salt':base64.b64encode(salt).decode(),'nonce':base64.b64encode(nonce).decode(),'ciphertext':base64.b64encode(ct).decode(),'address':'HNK1'+hashlib.sha256(pub).hexdigest()[:40]}
        tmp=path+'.tmp';open(tmp,'w',encoding='utf8').write(json.dumps(obj));os.replace(tmp,path);os.chmod(path,0o600)
    @classmethod
    def load(cls,path,password):
        obj=json.load(open(path,encoding='utf8'));salt=base64.b64decode(obj['salt']);nonce=base64.b64decode(obj['nonce']);ct=base64.b64decode(obj['ciphertext']);
        return cls(AESGCM(cls._key(password,salt)).decrypt(nonce,ct,None))
    def core_wallet(self): return CoreWallet(Ed25519PrivateKey.from_private_bytes(self.private_bytes))
