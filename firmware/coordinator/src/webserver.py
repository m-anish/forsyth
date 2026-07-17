"""webserver.py — the box's own window onto itself.

Two jobs, and deliberately no more:
  1. say what this coordinator is doing — status, and a live log console
  2. take WiFi credentials when there's no LAN (the setup portal)

It is NOT a second weather dashboard. The cloud owns the weather; this owns the
device. Everything lives at http://forsyth.local/.

The page is a single self-contained document (inline CSS + JS, no external
loads — the box may have no internet). It polls two tiny JSON endpoints:
  /api/status  the status tiles + the LED-derived health colour
  /api/logs?after=<id>   only log lines newer than the client already has

Non-blocking by construction: poll() accepts at most one connection per
main-loop pass, so a browser can never delay a leaf's ACK.
"""
import json
import socket

import config

try:
    import logbuf
except ImportError:
    logbuf = None

# health → the same colour the LED shows, so the web dot and the physical LED
# always agree (one source of truth for "how are we").
_HEALTH_COLOUR = {
    "ok": "#2ec16b", "bench": "#00c8c8", "spooling": "#e08a20",
    "no-net": "#d64541", "ap": "#c850a0", "boot": "#c9ccd1",
}


def _health(st):
    n, u = st["net"], st["uplink"]
    if n.get("ap"):
        return "ap", "setup — join %s" % n["ap"]["ssid"]
    if not n["connected"]:
        return "no-net", "no network"
    if not u["connected"]:
        return "spooling", "buffering (broker unreachable)"
    if st["mode"] == "bench":
        return "bench", "bench — invented data"
    return "ok", "listening"


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _unquote_plus(s):
    s = s.replace("+", " ")
    out, i = "", 0
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s) + 1:
            try:
                out += chr(int(s[i + 1:i + 3], 16))
                i += 3
                continue
            except (ValueError, IndexError):
                pass
        out += s[i]
        i += 1
    return out


def _form(body):
    d = {}
    for part in body.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            d[_unquote_plus(k)] = _unquote_plus(v)
    return d


# ---- the page (inline, self-contained) -------------------------------------

_PAGE = """<!DOCTYPE html><html><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>forsyth coordinator</title><style>
:root{--bg:#0b0c0e;--card:#14171d;--line:#242832;--dim:#9a9ea3;
--mut:#63676e;--ink:#e8e9e6;--acc:#7fa2c4;--mono:ui-monospace,Menlo,monospace}
*{box-sizing:border-box}body{background:var(--bg);color:var(--ink);margin:0;
font:15px/1.5 -apple-system,system-ui,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:22px 18px 60px}
header{display:flex;align-items:center;gap:11px;margin-bottom:4px}
header .dot{width:11px;height:11px;border-radius:50%;flex:none;
box-shadow:0 0 10px currentColor}
h1{font-weight:500;font-size:20px;margin:0}
.sub{color:var(--dim);font-size:13px;margin:0 0 20px 22px}
.sub a{color:var(--acc)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
gap:10px;margin-bottom:24px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:11px 13px}
.tile .k{color:var(--mut);font:11px/1.4 var(--mono);text-transform:uppercase;
letter-spacing:.08em}
.tile .v{font:15px/1.3 var(--mono);margin-top:3px;word-break:break-word}
.ok{color:#7fb98a}.warn{color:#e0a83a}.bad{color:#d47f7f}
.logs h2{font-size:14px;font-weight:500;margin:0 0 8px;color:var(--dim)}
.bar{display:flex;flex-wrap:wrap;gap:14px 18px;align-items:center;
margin-bottom:8px;font:12px/1 var(--mono);color:var(--dim)}
.bar label{display:inline-flex;align-items:center;gap:5px;cursor:pointer}
.bar button{font:12px/1 var(--mono);color:var(--acc);background:none;
border:1px solid var(--line);border-radius:6px;padding:5px 10px;cursor:pointer}
.bar button:hover{border-color:var(--acc)}
#log{background:#0e1014;border:1px solid var(--line);border-radius:10px;
height:340px;overflow:auto;padding:9px 11px;font:12.5px/1.5 var(--mono);
white-space:pre;user-select:text}
#log.wrap{white-space:pre-wrap;word-break:break-word}
#log .t{color:var(--mut)}
#log .l{display:block}
#log .l.warnln{color:#e0a83a}#log .l.badln{color:#d47f7f}
.foot{margin-top:22px;color:var(--mut);font-size:12px}
.foot a{color:var(--acc);margin-right:14px}
</style></head><body><div class=wrap>
<header><span class=dot id=dot style='color:#c9ccd1'></span>
<h1>forsyth · <span id=cid>coordinator</span></h1></header>
<p class=sub id=health>connecting…
&nbsp;·&nbsp;<a href='https://live.forsyth.starstucklab.com'>dashboard ↗</a></p>
<div class=grid id=grid></div>
<div class=logs><h2>system log</h2>
<div class=bar>
<label><input type=checkbox id=follow checked> follow</label>
<label><input type=checkbox id=wrap> wrap</label>
<label><input type=checkbox id=pause> pause</label>
<button id=copy>copy</button><button id=clear>clear view</button>
<span id=count style='margin-left:auto'></span></div>
<div id=log></div></div>
<div class=foot><a href='/wifi'>wifi setup</a>
<a href='/api/status'>status json</a><a href='/reboot'>reboot</a></div>
</div><script>
var lastId=0, logEl=document.getElementById('log');
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function cls(m){m=m.toLowerCase();
 if(/fail|error|traceback|reject|crash|stuck|down/.test(m))return' badln';
 if(/warn|spool|retry|weak|no ap|202|unreach/.test(m))return' warnln';return''}
function tile(k,v,c){return '<div class=tile><div class=k>'+k+
 '</div><div class="v '+(c||'')+'">'+v+'</div></div>'}
function num(n){return n==null?'—':n}
function poll(){
 fetch('/api/status').then(function(r){return r.json()}).then(function(s){
  document.getElementById('cid').textContent=s.id;
  var col={ok:'#2ec16b',bench:'#00c8c8',spooling:'#e08a20','no-net':'#d64541',
   ap:'#c850a0',boot:'#c9ccd1'}[s.health]||'#c9ccd1';
  document.getElementById('dot').style.color=col;
  document.getElementById('health').innerHTML=esc(s.health_text)+
   " · mode "+s.mode+" &nbsp;·&nbsp; <a href='https://live.forsyth.starstucklab.com'>dashboard ↗</a>";
  var n=s.net,u=s.uplink,c=s.clock,g='';
  g+=tile('network', n.connected?esc(n.ssid||'')+'<br>'+n.ip:'down',
       n.connected?'ok':'bad');
  g+=tile('wifi rssi', n.rssi!=null?n.rssi+' dBm':'—');
  g+=tile('uplink', u.connected?'connected':'spooling ('+u.spooled+')',
       u.connected?'ok':'warn');
  g+=tile('clock (utc)', c.utc+(c.ntp_synced?'':' ⚠'), c.ntp_synced?'':'warn');
  g+=tile('rtc chip', c.ds3231?'DS3231':'internal only');
  g+=tile('peripherals','lora '+n0(s.peripherals.lora)+'<br>eth '+n0(s.peripherals.eth));
  g+=tile('chip temp', s.mcu_temp!=null?s.mcu_temp+' °C':'—');
  g+=tile('uptime', s.uptime_s+' s');
  if(n.ap) g+=tile('setup ap', esc(n.ap.ssid)+'<br>'+n.ap.ip,'warn');
  document.getElementById('grid').innerHTML=g;
 }).catch(function(){});
}
function n0(b){return b?'yes':'no'}
function polllog(){
 if(document.getElementById('pause').checked)return;
 fetch('/api/logs?after='+lastId).then(function(r){return r.json()}).then(function(d){
  if(!d.lines.length){document.getElementById('count').textContent=lastId+' lines';return}
  var atBot=logEl.scrollHeight-logEl.scrollTop-logEl.clientHeight<30;
  var html='';
  d.lines.forEach(function(x){lastId=x[0];
   html+='<span class="l'+cls(x[2])+'"><span class=t>'+x[1]+'</span> '+esc(x[2])+'</span>'});
  logEl.insertAdjacentHTML('beforeend',html);
  document.getElementById('count').textContent=lastId+' lines';
  if(document.getElementById('follow').checked||atBot)
    logEl.scrollTop=logEl.scrollHeight;
 }).catch(function(){});
}
document.getElementById('wrap').onchange=function(){logEl.classList.toggle('wrap',this.checked)};
document.getElementById('clear').onclick=function(){logEl.innerHTML=''};
document.getElementById('copy').onclick=function(){
 var t=logEl.innerText;
 if(navigator.clipboard){navigator.clipboard.writeText(t);
  this.textContent='copied';var b=this;setTimeout(function(){b.textContent='copy'},900)}
 else{var r=document.createRange();r.selectNodeContents(logEl);
  var s=getSelection();s.removeAllRanges();s.addRange(r)}};
poll();polllog();setInterval(poll,3000);setInterval(polllog,2000);
</script></body></html>"""

_WIFI = """<!DOCTYPE html><html><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>forsyth · wifi</title><style>
body{background:#0b0c0e;color:#e8e9e6;font:15px/1.5 -apple-system,system-ui,
sans-serif;margin:0}.wrap{max-width:460px;margin:0 auto;padding:28px 20px}
h1{font-weight:500;font-size:20px;margin:0 0 4px}
.sub{color:#9a9ea3;font-size:13px;margin-bottom:18px}
label{display:block;color:#63676e;font:12px/1.4 ui-monospace,Menlo,monospace;
margin:12px 0 4px}input{width:100%;padding:10px;background:#14171d;color:#e8e9e6;
border:1px solid #242832;border-radius:8px;font-size:14px}
button{margin-top:16px;padding:10px 18px;background:#7fa2c4;color:#0b0c0e;border:0;
border-radius:999px;font-weight:600;cursor:pointer}
a{color:#7fa2c4}.note{color:#e0a83a;font-size:13px;margin-bottom:10px}
.tip{color:#63676e;font-size:12px;margin-top:18px}
</style></head><body><div class=wrap>
<h1>wifi setup</h1><div class=sub>Saved on the device; survives reboots. It
reconnects on its own.</div>%NOTE%
<form method=post action=/wifi>
<label>network name (ssid)</label>
<input name=ssid value="%SSID%" autocapitalize=off autocorrect=off>
<label>password</label><input name=password type=password autocapitalize=off>
<button type=submit>save &amp; reconnect</button></form>
<div class=tip>Tip: iPhone hotspots use a curly apostrophe (’). Pick the name
from your phone's list rather than typing it.</div>
<div class=tip><a href='/'>← status</a></div></div></body></html>"""


class Web:
    def __init__(self, status_fn, on_wifi):
        self._status = status_fn
        self._on_wifi = on_wifi
        self.sock = None
        if not getattr(config, "WEB", {}).get("enabled", True):
            print("web: disabled by config")
            return
        port = getattr(config, "WEB", {}).get("port", 80)
        try:
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            s.listen(2)
            s.setblocking(False)      # the whole point: never stall the loop
            self.sock = s
            print("web: listening on :%d (http://%s.local/)"
                  % (port, config.HOSTNAME))
        except OSError as e:
            print("web: could not listen (%r)" % e)

    # ---- payloads ----------------------------------------------------------

    def _status_json(self):
        st = self._status()
        h, ht = _health(st)
        st["health"] = h
        st["health_text"] = ht
        return json.dumps(st)

    def _logs_json(self, after):
        if logbuf is None:
            return '{"lines":[],"head":0}'
        return json.dumps({"lines": logbuf.since(after), "head": logbuf.head()})

    def _wifi_page(self, msg=""):
        ssid = self._status()["net"].get("ssid") or ""
        note = ("<div class=note>%s</div>" % _esc(msg)) if msg else ""
        return _WIFI.replace("%NOTE%", note).replace("%SSID%", _esc(ssid))

    # ---- plumbing ----------------------------------------------------------

    def _respond(self, cl, body, ctype="text/html", code="200 OK"):
        cl.send("HTTP/1.0 %s\r\nContent-Type: %s\r\nCache-Control: no-store\r\n"
                "Connection: close\r\n\r\n" % (code, ctype))
        cl.send(body)

    def poll(self):
        """Accept and serve at most one request. Returns immediately when idle."""
        if self.sock is None:
            return
        try:
            cl, _addr = self.sock.accept()
        except OSError:
            return                      # nothing pending — the normal case
        try:
            cl.settimeout(2)
            req = cl.recv(1024)
            if not req:
                return
            line = req.split(b"\r\n", 1)[0].decode()
            parts = line.split(" ")
            method, path = (parts + ["", ""])[:2]

            if path.startswith("/api/status"):
                self._respond(cl, self._status_json(), "application/json")
            elif path.startswith("/api/logs"):
                after = 0
                if "after=" in path:
                    try:
                        after = int(path.split("after=", 1)[1].split("&")[0])
                    except ValueError:
                        pass
                self._respond(cl, self._logs_json(after), "application/json")
            elif path.startswith("/wifi"):
                if method == "POST":
                    body = req.split(b"\r\n\r\n", 1)[-1].decode()
                    ssid = _form(body).get("ssid", "").strip()
                    pw = _form(body).get("password", "")
                    if ssid:
                        self._respond(cl,
                            "<!DOCTYPE html><meta charset=utf-8><body "
                            "style='background:#0b0c0e;color:#e8e9e6;font-family:"
                            "system-ui;padding:28px'><h2>saved</h2><p>Reconnecting "
                            "to %s — this page is about to disappear, which is the "
                            "point.</p>" % _esc(ssid))
                        cl.close()
                        self._on_wifi(ssid, pw)
                        return
                    self._respond(cl, self._wifi_page("ssid can't be empty"))
                else:
                    self._respond(cl, self._wifi_page())
            elif path.startswith("/reboot"):
                self._respond(cl, "<!DOCTYPE html><meta charset=utf-8><body "
                    "style='background:#0b0c0e;color:#e8e9e6;font-family:system-ui;"
                    "padding:28px'><h2>rebooting</h2><p>Back in a few seconds.</p>")
                cl.close()
                import machine
                import time
                time.sleep(1)
                machine.reset()
            else:
                self._respond(cl, _PAGE)
        except Exception as e:
            print("web: request failed (%r)" % e)
        finally:
            try:
                cl.close()
            except Exception:
                pass
