"""logbuf.py — keep the last N log lines in RAM so the web UI can show them.

The firmware already narrates itself with print(). Rather than retrofit every
call site, we tee builtins.print once at boot: each line still goes to the USB
REPL AND lands in a bounded ring buffer the web server reads. Reassigning
builtins.print is picked up by every module because MicroPython resolves the
builtin dynamically at each call (verified on 1.28).

Bounded on purpose — this runs on a microcontroller. MAX lines × ~80 chars is
the whole cost; the oldest line falls off the front.
"""
import builtins
import time

_MAX = 150
_buf = []
_seq = 0                 # monotonic id so the client can fetch only new lines
_orig_print = builtins.print


def _stamp():
    t = time.gmtime()
    if t[0] >= 2024:                       # NTP has landed → wall clock
        return "%02d:%02d:%02d" % (t[3], t[4], t[5])
    return "+%ds" % (time.ticks_ms() // 1000)  # pre-NTP → uptime, still meaningful


def _tee(*args, **kw):
    _orig_print(*args, **kw)               # never lose the USB console
    global _seq
    try:
        sep = kw.get("sep", " ")
        msg = sep.join(str(a) for a in args)
        _seq += 1
        _buf.append((_seq, _stamp(), msg))
        if len(_buf) > _MAX:
            del _buf[0]
    except Exception:
        pass                               # logging must never break the caller


def install():
    builtins.print = _tee


def since(after=0):
    """Lines with id > after, as [[id, 'hh:mm:ss', 'text'], ...]. The client
    passes the last id it has so each poll ships only what's new."""
    return [[s, ts, m] for (s, ts, m) in _buf if s > after]


def head():
    return _seq
