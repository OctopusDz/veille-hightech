#!/usr/bin/env python3
"""Sert le site en local, sans cache.

`python3 -m http.server` laisse le navigateur garder l'ancien app.js/style.css :
on corrige un bug, on recharge, et rien ne change. Ce serveur envoie
Cache-Control: no-store, donc un simple Cmd+R suffit toujours.

Usage :  python3 tools/serve.py [port]
"""
from __future__ import annotations

import http.server
import socketserver
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8800
RACINE = Path(__file__).resolve().parent.parent / "site"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(RACINE), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # silence : on ne veut pas noyer le terminal


class Serveur(socketserver.ThreadingTCPServer):
    allow_reuse_address = True   # évite « Address already in use » au redémarrage
    daemon_threads = True


if __name__ == "__main__":
    if not RACINE.exists():
        print(f"dossier introuvable : {RACINE}")
        raise SystemExit(1)
    print(f"Site servi sur http://localhost:{PORT}  (Ctrl+C pour arrêter)")
    try:
        with Serveur(("", PORT), Handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\narrêté")
