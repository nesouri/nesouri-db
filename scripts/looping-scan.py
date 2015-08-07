from concurrent.futures import ProcessPoolExecutor
import os
import subprocess
import sys
from gme import *

def find_files(path, pred):
    for root, dirs, files in os.walk(path):
        for f in files:
            if pred(f):
                yield os.path.join(root, f)

def do_scan(nsf):
    def is_looping(engine, track, max_minutes=1):
        engine.start_track(track)
        buf = engine.create_buffer(seconds=60)
        for _ in range(5):
            engine.play(buf)
            if engine.track_ended():
                return 0
        return 1

    result = []

    try:
        engine = Gme.from_file(nsf, 8000)
        for track in range(engine.track_count()):
            looping = is_looping(engine, track, max_minutes=5)
            result.append("\"%s\",%d,%d" % (os.path.basename(nsf), track + 1, looping))
    except GmeError:
        pass # Some FDS files are unreadable by game-music-emu

    return result

def scan(path, max_workers):
    pred = lambda x: x.endswith("nsf")
    with ProcessPoolExecutor(max_workers) as executor:
        for res in executor.map(do_scan, find_files(path, pred)):
            if res:
                print("\n".join(res))

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: %s <path-with-nsf-files-to-scan>" % sys.argv[0])
    scan(sys.argv[1], 1 if "DEBUG" in os.environ else None)
