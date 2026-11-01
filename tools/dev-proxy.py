"""Local dashboard, live data: serves cloud/dashboard from disk and forwards
/api/* to the droplet, so a change can be seen against real readings before it
is deployed. Verification only — nothing here ships.

A board opens a dozen API calls at once and the upstream occasionally drops one
mid-handshake, which showed up as a page of skeletons; each request gets three
tries before it gives up."""
import http.server, os, socketserver, ssl, sys, time, urllib.error, urllib.request

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "cloud", "dashboard")
UP = os.environ.get("FORSYTH_UPSTREAM", "https://live.forsyth.starstucklab.com")
# this python build ships no CA store of its own; use the system bundle
CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")


class H(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self.proxy()
        if self.path in ("/", "/index.html"):
            self.path = "/board.html"
        return super().do_GET()

    def fetch(self):
        last = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(UP + self.path,
                                             headers={"accept": "application/json"})
                with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
                    return r.read(), r.status, r.headers.get("content-type", "application/json")
            except urllib.error.HTTPError as e:
                return e.read(), e.code, "application/json"     # a real answer
            except Exception as e:
                last = e
                time.sleep(0.25 * (attempt + 1))
        print(f"proxy giving up on {self.path}: {last}", file=sys.stderr, flush=True)
        return str(last).encode(), 502, "text/plain"

    def proxy(self):
        body, code, ctype = self.fetch()
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # ?v=NN is a fixed URL, so the browser kept serving the build from
        # before the last edit — which is a trap, not a test
        self.send_header("cache-control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, *a):
        pass


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64


with S(("127.0.0.1", 4180), H) as s:
    print("dashboard on http://localhost:4180 (api -> " + UP + ")", flush=True)
    s.serve_forever()
