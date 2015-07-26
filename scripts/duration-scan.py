#!/usr/bin/env python3.4
from concurrent.futures import ProcessPoolExecutor
import os
import subprocess
import sys

def find_files(path, pred):
    for root, dirs, files in os.walk(path):
        for f in files:
            if pred(f):
                yield os.path.join(root, f)

def do_scan(nsf):
    args = [ "build/nsfinfo", nsf, "--1-0",
             "--p=\"%s\"" % os.path.basename(nsf),
             ",", "--t", ",", "--Tm", "--nl"
    ]
    return subprocess.check_output(args).decode("utf-8").rstrip()

def scan(path, max_workers):
    pred = lambda x: x.endswith("nsf")
    with ProcessPoolExecutor(max_workers) as executor:
        for res in executor.map(do_scan, find_files(path, pred)):
            print(res)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: %s <path-with-nsf-files-to-scan>" % sys.argv[0])
    scan(sys.argv[1], 1 if "DEBUG" in os.environ else None)
