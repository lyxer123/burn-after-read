#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""onedl - one-time download (burn-after-read) service.

Serves files mapped by unguessable tokens. On the FIRST GET for a token the
token is atomically consumed (renamed into ./consumed) and the file is
streamed. Any subsequent request for the same token returns 404, so the link
is spent after a single successful download.

File-type agnostic: the Content-Type and the download filename are taken from
the token's metadata, never hardcoded. A PDF, a ZIP, an image, a video, a
binary release - anything works the same way.

nginx proxies  /dl/<token>  ->  http://<ONEDL_HOST>:<ONEDL_PORT>/<token>

Python 2.7 / 3.x compatible (the host only has python2.7).
"""
import os
import mimetypes
import SocketServer
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler

BASE = os.environ.get("ONEDL_BASE", "/opt/onedl")
TOKENS = os.path.join(BASE, "tokens")
CONSUMED = os.path.join(BASE, "consumed")
STORE = os.path.join(BASE, "store")
PORT = int(os.environ.get("ONEDL_PORT", "8777"))
# When nginx runs INSIDE a Docker container it cannot reach 127.0.0.1 of the
# host. Set ONEDL_HOST to the docker bridge gateway IP (e.g. 177.7.0.1) so the
# container can reach the host where this service listens. 127.0.0.1 is fine
# when nginx runs directly on the host.
HOST_BIND = os.environ.get("ONEDL_HOST", "127.0.0.1")
CHUNK = 65536


def mkdirs(p):
    try:
        os.makedirs(p)
    except OSError:
        pass


def rand_hex(n=16):
    r = os.urandom(n)
    try:
        return r.encode("hex")
    except AttributeError:
        return r.hex()


class Handler(BaseHTTPRequestHandler):
    server_version = "OneDL/1.1"
    protocol_version = "HTTP/1.1"

    def _consume(self, token):
        """Atomically move token -> consumed. Returns consumed path or None."""
        tok = os.path.join(TOKENS, token)
        dst = os.path.join(CONSUMED, token)
        try:
            os.rename(tok, dst)
            return dst
        except OSError:
            return None

    def _token_meta(self, dst):
        """Read token file: line1 = internal store name, line2 = display name."""
        store_rel = None
        disp = None
        try:
            with open(dst) as f:
                lines = f.read().splitlines()
        except IOError:
            return None, None
        if lines:
            store_rel = lines[0].strip()
            if len(lines) > 1:
                disp = lines[1].strip()
        return store_rel, disp

    def do_GET(self):
        token = self.path.split('?')[0].strip('/')
        if not token:
            self.send_error(404)
            return
        # Consume first -> guarantees only ONE client ever wins the file.
        dst = self._consume(token)
        if dst is None:
            self.send_error(404, "Link expired or invalid")
            return
        store_rel, disp = self._token_meta(dst)
        if not store_rel:
            self.send_error(404, "Token metadata missing")
            return
        # basename only -> no path traversal out of STORE.
        target = os.path.join(STORE, os.path.basename(store_rel))
        if not os.path.isfile(target):
            self.send_error(404, "Target file missing")
            return
        ctype, _ = mimetypes.guess_type(disp or store_rel)
        if not ctype:
            ctype = "application/octet-stream"
        if not disp:
            disp = os.path.basename(store_rel)
        try:
            size = os.path.getsize(target)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header(
                "Content-Disposition",
                'attachment; filename="%s"' % disp)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with open(target, "rb") as fh:
                while True:
                    chunk = fh.read(CHUNK)
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except Exception:
                        break
        except Exception:
            try:
                self.send_error(500)
            except Exception:
                pass

    def log_message(self, *args):
        pass


class ThreadingHTTPServer(SocketServer.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    mkdirs(TOKENS)
    mkdirs(CONSUMED)
    mkdirs(STORE)
    srv = ThreadingHTTPServer((HOST_BIND, PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
