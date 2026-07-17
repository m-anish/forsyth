# boot.py — runs before main.py. We install the log capture here, first thing,
# so even main.py's earliest prints land in the web-visible ring buffer.
import logbuf
logbuf.install()
