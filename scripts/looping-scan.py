from concurrent.futures import ProcessPoolExecutor
import os
import subprocess
import sys
from ctypes import *
from enum import Enum

lib = cdll.LoadLibrary("libgme.so")

class Music_Emu(Structure):
    pass

class GmeError(Exception):
    pass

class Gme(object):
    @staticmethod
    def from_file(path, rate):
        open_file = lib.gme_open_file
        open_file.argtypes = [c_char_p, POINTER(POINTER(Music_Emu)), c_int]
        emu = POINTER(Music_Emu)()
        err = open_file(c_char_p(path.encode("utf-8")), byref(emu), int(rate))
        if err != 0:
            raise GmeError("Could not open file: " + path)
        return Gme(emu, rate)

    def __init__(self, emu, rate):
        self.emu = emu
        self.rate = rate

    def create_buffer(self, seconds=10):
        return (c_short * (2 * self.rate * seconds))()

    def track_count(self):
        return lib.gme_track_count(self.emu)

    def start_track(self, track):
        err = lib.gme_start_track(self.emu, track)
        if err != 0:
            raise GmeError("Could not start track: %d" % track)

    def play(self, buf):
        err = lib.gme_play(self.emu, len(buf), buf)
        if err != 0:
            raise GmeError("Could not decode")

    def track_ended(self):
        return lib.gme_track_ended(self.emu) == 1

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
