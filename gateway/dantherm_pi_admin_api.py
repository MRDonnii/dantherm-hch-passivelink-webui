#!/usr/bin/env python3
"""Authenticated, allowlisted privileged actions for the Dantherm Pi."""
import hmac, json, os, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKEN = os.environ["DANTHERM_REBOOT_TOKEN"]
BIND = os.getenv("DANTHERM_ADMIN_BIND", "127.0.0.1")
PORT = int(os.getenv("DANTHERM_ADMIN_PORT", "4198"))
PROFILE_FILE = Path("/var/lib/dantherm-admin/power-profile")
PROFILES = {"powersave": "powersave", "balanced": "ondemand", "performance": "performance"}
SERVICES = {"gateway": os.getenv("DANTHERM_GATEWAY_SERVICE","dantherm-webui-gateway.service"), "onewire": os.getenv("DANTHERM_ONEWIRE_SERVICE","dantherm-webui-onewire.service")}

def set_profile(profile):
    governor = PROFILES[profile]
    for path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_governor"):
        path.write_text(governor)
    PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_FILE.write_text(profile + "\n")

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        body=json.dumps(payload).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def authorized(self): return hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {TOKEN}")
    def do_GET(self):
        if self.path == "/health": return self.reply(200,{"ok":True})
        if not self.authorized(): return self.reply(401,{"error":"unauthorized"})
        if self.path == "/status":
            governor=Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").read_text().strip()
            return self.reply(200,{"power_profile":next((p for p,g in PROFILES.items() if g==governor),governor),"governor":governor})
        self.reply(404,{"error":"not_found"})
    def do_POST(self):
        if self.path != "/action": return self.reply(404,{"error":"not_found"})
        if not self.authorized(): return self.reply(401,{"error":"unauthorized"})
        try:
            length=min(int(self.headers.get("Content-Length","0")),1024); data=json.loads(self.rfile.read(length)); action=data.get("action"); target=data.get("target")
        except (ValueError,TypeError,json.JSONDecodeError): return self.reply(400,{"error":"invalid_json"})
        if action == "power_profile" and target in PROFILES:
            set_profile(target); return self.reply(200,{"ok":True,"power_profile":target})
        if action == "restart_service" and target in SERVICES:
            self.reply(202,{"ok":True,"message":"service restart scheduled"})
            threading.Thread(target=lambda:(time.sleep(.5),subprocess.run(["systemctl","restart",SERVICES[target]],check=False)),daemon=True).start(); return
        command={"reboot":["systemctl","reboot"],"shutdown":["systemctl","poweroff"]}.get(action)
        if command:
            self.reply(202,{"ok":True,"message":f"{action} scheduled"})
            threading.Thread(target=lambda:(time.sleep(1),subprocess.run(command,check=False)),daemon=True).start(); return
        self.reply(400,{"error":"action_not_allowed"})
    def log_message(self,*args): pass

if PROFILE_FILE.exists():
    saved=PROFILE_FILE.read_text().strip()
    if saved in PROFILES:
        try: set_profile(saved)
        except OSError: pass
ThreadingHTTPServer((BIND,PORT),Handler).serve_forever()
