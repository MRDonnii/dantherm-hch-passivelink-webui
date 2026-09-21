"""Small local authentication store with salted hashes and server-side sessions."""
import hashlib, hmac, json, os, secrets, threading, time
from http.cookies import SimpleCookie
from pathlib import Path

class AuthManager:
    def __init__(self, path="/var/lib/dantherm-hch5-ha/webui-auth.json"):
        self.path=Path(path); self.lock=threading.Lock(); self.sessions={}; self.failures={}
    def load(self):
        try: return json.loads(self.path.read_text())
        except (OSError,ValueError): return None
    def configured(self): return bool(self.load())
    def enabled(self):
        data=self.load(); return bool(data and data.get("enabled",True))
    @staticmethod
    def _hash(password,salt): return hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),310000).hex()
    def verify(self,username,password):
        data=self.load()
        return bool(data and hmac.compare_digest(str(data.get("username","")),username) and hmac.compare_digest(str(data.get("password_hash","")),self._hash(password,data["salt"])))
    def save(self,username,password,enabled=True):
        if len(username.strip())<3 or len(password)<10: raise ValueError("Brugernavn skal være mindst 3 tegn og adgangskoden mindst 10 tegn")
        salt=secrets.token_hex(16); data={"version":1,"username":username.strip(),"salt":salt,"password_hash":self._hash(password,salt),"enabled":bool(enabled)}
        self.path.parent.mkdir(parents=True,exist_ok=True); tmp=self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(data)); os.chmod(tmp,0o600); tmp.replace(self.path)
    def update(self,current_password,username,password,enabled):
        data=self.load()
        if not data or not self.verify(data["username"],current_password): raise PermissionError("Forkert nuværende adgangskode")
        self.save(username or data["username"],password or current_password,enabled); self.sessions.clear()
    def allow_attempt(self,ip):
        now=time.time(); values=[t for t in self.failures.get(ip,[]) if now-t<300]; self.failures[ip]=values; return len(values)<5
    def failed(self,ip): self.failures.setdefault(ip,[]).append(time.time())
    def session(self,username):
        sid=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24); self.sessions[sid]={"username":username,"csrf":csrf,"expires":time.time()+43200}; return sid,csrf
    def authenticate_cookie(self,header):
        data=self.load()
        if not data: return None
        if not data.get("enabled",True): return {"username":data.get("username"),"csrf":None}
        try: cookie=SimpleCookie(header); sid=cookie["dantherm_session"].value; session=self.sessions.get(sid)
        except (KeyError,AttributeError): return None
        if not session or session["expires"]<time.time(): self.sessions.pop(sid,None); return None
        session["expires"]=time.time()+43200; return session
    def logout(self,header):
        try: cookie=SimpleCookie(header); self.sessions.pop(cookie["dantherm_session"].value,None)
        except (KeyError,AttributeError): pass
