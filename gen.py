#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Mint one-time download links for an arbitrary file.

Usage:
    python gen.py <file> [count]

What it does:
    1. Copies <file> into ./store under a random INTERNAL name, so the public
       URL never leaks the real filename or location.
    2. Writes <count> token files. Each token file holds two lines:
           <internal_store_name>
           <original_display_name>
    3. Prints <count> public URLs of the form  <host>/dl/<token>

Every URL works exactly once. After the first successful download the token
is atomically consumed and the link returns 404 forever.

Re-run with the same <file> and a bigger count to mint more links for the
same file, or point it at a different file to share something else entirely.
"""
import os
import sys
import shutil

BASE = os.environ.get("ONEDL_BASE", "/opt/onedl")
TOKENS = os.path.join(BASE, "tokens")
STORE = os.path.join(BASE, "store")
LINKS = os.path.join(BASE, "links.log")
HOST = os.environ.get("ONEDL_PUBLIC_HOST", "http://117.72.15.132")


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


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: gen.py <file> [count]\n")
        sys.exit(2)
    src = sys.argv[1]
    if not os.path.isfile(src):
        sys.stderr.write("file not found: %s\n" % src)
        sys.exit(2)
    count = 1
    if len(sys.argv) > 2:
        try:
            count = int(sys.argv[2])
        except ValueError:
            count = 1
    if count < 1:
        count = 1

    mkdirs(TOKENS)
    mkdirs(STORE)
    disp = os.path.basename(src)
    internal = rand_hex(16)
    shutil.copyfile(src, os.path.join(STORE, internal))

    out = []
    for _ in range(count):
        tok = rand_hex(16)
        with open(os.path.join(TOKENS, tok), "w") as f:
            f.write("%s\n%s\n" % (internal, disp))
        out.append("%s/dl/%s" % (HOST, tok))
    txt = "\n".join(out)
    print(txt)
    try:
        with open(LINKS, "a") as f:
            f.write(txt + "\n")
    except IOError:
        pass


if __name__ == "__main__":
    main()
