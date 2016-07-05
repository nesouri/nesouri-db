from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from gme import *
import acoustid
import json
import os
import sqlite3
import sys
import time

CHANNELS = 2
SAMPLERATE = 44100
MAX_DURATION = 45

def do_fingerprint(game):
    fingerprints = []
    engine = Gme.from_file(game["filename"], SAMPLERATE)
    buf = engine.create_buffer(seconds=MAX_DURATION)
    for position in range(engine.track_count()):
        t = game["tracks"].get(position + 1, {})
        if t.get("looping") == False and t.get("duration", MAX_DURATION * 1000) < 5000:
            continue
        try:
            engine.start_track(position)
            engine.play(buf)
            data = buf.get_bytes(trim=True)
            if len(data) < 480644: # too short
                continue
            fingerprint = acoustid.fingerprint(SAMPLERATE, CHANNELS, [data])
            fingerprints.append((position + 1, t.get("title"), fingerprint.decode("utf-8")))
            buf.clear()
        except Exception as e:
            print("Error[id: %d, pos: %d]: %s" % (game["game_id"], position, e))
    return game["game_id"], game["total_tracks"], fingerprints
