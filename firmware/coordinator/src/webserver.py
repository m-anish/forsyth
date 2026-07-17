"""webserver.py — the box's own small window onto itself.

Two jobs, and deliberately no more:
  1. say what this coordinator is doing (mode, network, uplink, leaves heard,
     clock) — the things you'd otherwise need a laptop and a USB cable to see
  2. take WiFi credentials when there's no LAN to be had (the setup portal)

It is NOT a second dashboard. The cloud owns the weather; this owns the device.

Non-blocking by construction: `poll()` is called from the main loop and accepts
at most one connection per call, so a browser can never stall the radio. That
matters — the leaf's ACK window is measured in milliseconds.
"""
import json
import socket

import config

_STYLE = """body{background:#0b0c0e;color:#e8e9e6;font:15px/1.6 -apple-system,
system-ui,sans-serif;margin:0;padding:28px}
h1{font-weight:500;font-size:22px;margin:0 0 2px}
.sub{color:#9a9ea3;font-size:13px;margin-bottom:22px}
table{border-collapse:collapse;width:100%;max-width:560px;margin-bottom:22px}
td{padding:7px 0;border-bottom:1px solid #1c1f26;font-family:ui-monospace,
Menlo,monospace;font-size:13px}
td:first-child{color:#63676e;width:44%}
.ok{color:#7fb98a}.bad{color:#c47f7f}.warn{color:#c9a15a}
form{max-width:560px}label{display:block;color:#63676e;font-size:12px;
margin:12px 0 4px}
input{width:100%;padding:9px;background:#14171d;color:#e8e9e6;
border:1px solid #242832;border-radius:6px;font-size:14px;box-sizing:border-box}
button{margin-top:16px;padding:9px 16px;background:#7fa2c4;color:#0b0c0e;
border:0;border-radius:999px;font-weight:600;cursor:pointer}
a{color:#7fa2c4}"""


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _unquote_plus(s):
    s = s.replace("+", " ")
    out, i = "", 0
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s) + 0:
            try:
                out += chr(int(s[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
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


class Web:
    def __init__(self, status_fn, on_wifi):
        """status_fn() -> dict for the status page/JSON.
        on_wifi(ssid, password) -> called when the portal form is submitted."""
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

    # ---- pages -------------------------------------------------------------

    def _page_status(self, st):
        n, c, u = st["net"], st["clock"], st["uplink"]
        rows = [
            ("mode", st["mode"]),
            ("uptime", "%d s" % st["uptime_s"]),
            ("time (utc)", c["utc"] + ("" if c["ntp_synced"] else "  ⚠ not NTP-synced")),
            ("rtc chip", "DS3231" if c["ds3231"] else "none (internal only)"),
            ("interface", n["iface"] or "—"),
            ("network", ('<span class="ok">%s · %s</span>' % (_esc(n["ssid"]), n["ip"]))
                        if n["connected"] else '<span class="bad">down</span>'),
            ("wifi rssi", "%s dBm" % n["rssi"] if n["rssi"] is not None else "—"),
            ("uplink (mqtt)", '<span class="ok">connected</span>' if u["connected"]
                              else '<span class="warn">spooling</span>'),
            ("spooled msgs", u["spooled"]),
            ("peripherals", "lora=%s  eth=%s" % (st["peripherals"]["lora"],
                                                 st["peripherals"]["eth"])),
            ("chip temp", "%s °C" % st["mcu_temp"] if st["mcu_temp"] else "—"),
            ("frames heard", st["frames"] or "none yet"),
        ]
        if n["ap"]:
            rows.append(("setup ap", "%s · %s" % (n["ap"]["ssid"], n["ap"]["ip"])))
        body = "".join("<tr><td>%s</td><td>%s</td></tr>" % (k, v) for k, v in rows)
        return ("<h1>forsyth · coordinator</h1>"
                "<div class=sub>%s — the box, not the weather. "
                "<a href='https://live.forsyth.starstucklab.com'>dashboard ↗</a></div>"
                "<table>%s</table>"
                "<div class=sub><a href='/wifi'>wifi setup</a> · "
                "<a href='/api/status'>json</a> · <a href='/reboot'>reboot</a></div>"
                % (_esc(config.COORDINATOR_ID), body))

    def _page_wifi(self, st, msg=""):
        cur = st["net"]["ssid"] or ""
        note = ("<div class=sub style='color:#c9a15a'>%s</div>" % _esc(msg)) if msg else ""
        return ("<h1>wifi setup</h1>"
                "<div class=sub>Credentials are saved on the device and survive "
                "reboots. It will reconnect on its own.</div>%s"
                "<form method=post action=/wifi>"
                "<label>network name (ssid)</label>"
                "<input name=ssid value=\"%s\" autocapitalize=off autocorrect=off>"
                "<label>password</label>"
                "<input name=password type=password autocapitalize=off>"
                "<button type=submit>save &amp; reconnect</button></form>"
                "<div class=sub style='margin-top:20px'>"
                "Tip: iPhone hotspots use a curly apostrophe (’) — pick the name "
                "from your phone's list rather than typing it.</div>"
                "<div class=sub><a href='/'>← status</a></div>"
                % (note, _esc(cur)))

    def _html(self, inner):
        return ("<!DOCTYPE html><html><head><meta charset=utf-8>"
                "<meta name=viewport content='width=device-width,initial-scale=1'>"
                "<title>forsyth coordinator</title><style>%s</style></head>"
                "<body>%s</body></html>" % (_STYLE, inner))

    # ---- plumbing ----------------------------------------------------------

    def _respond(self, cl, code, body, ctype="text/html"):
        cl.send("HTTP/1.0 %s\r\nContent-Type: %s\r\nConnection: close\r\n\r\n"
                % (code, ctype))
        cl.send(body)

    def poll(self):
        """Accept and serve at most one request. Returns immediately when idle."""
        if self.sock is None:
            return
        try:
            cl, addr = self.sock.accept()
        except OSError:
            return                      # nothing pending — the normal case
        try:
            cl.settimeout(2)
            req = cl.recv(1024)
            if not req:
                return
            head = req.split(b"\r\n", 1)[0].decode()
            parts = head.split(" ")
            method, path = (parts + ["", ""])[:2]
            st = self._status()

            if path.startswith("/api/status"):
                self._respond(cl, "200 OK", json.dumps(st), "application/json")
            elif path.startswith("/wifi"):
                if method == "POST":
                    body = req.split(b"\r\n\r\n", 1)[-1].decode()
                    f = _form(body)
                    ssid = f.get("ssid", "").strip()
                    if ssid:
                        self._respond(cl, "200 OK", self._html(
                            "<h1>saved</h1><div class=sub>Reconnecting to %s — "
                            "this page is about to disappear, which is the "
                            "point.</div>" % _esc(ssid)))
                        cl.close()
                        self._on_wifi(ssid, f.get("password", ""))
                        return
                    self._respond(cl, "200 OK",
                                  self._html(self._page_wifi(st, "ssid can't be empty")))
                else:
                    self._respond(cl, "200 OK", self._html(self._page_wifi(st)))
            elif path.startswith("/reboot"):
                self._respond(cl, "200 OK", self._html(
                    "<h1>rebooting</h1><div class=sub>Back in a few seconds.</div>"))
                cl.close()
                import machine, time
                time.sleep(1)
                machine.reset()
            else:
                self._respond(cl, "200 OK", self._html(self._page_status(st)))
        except Exception as e:
            print("web: request failed (%r)" % e)
        finally:
            try:
                cl.close()
            except Exception:
                pass
