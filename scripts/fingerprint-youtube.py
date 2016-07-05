#!/usr/bin/env python
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from enum import Enum
import acoustid
import json
import os
import subprocess
import sys
import tempfile
import time

CHANNELS = 2
SAMPLERATE = 44100
MAX_DURATION = 45

class Errors(Enum):
    too_short = "Too short, probably a sound effect"
    bad_fingerprint = "Fingerprint failed for unknown reasons"

def render_track(filename, offset, duration):
    with tempfile.NamedTemporaryFile("rb") as fd:
        subprocess.call([
            "mplayer",
            "-nolirc",
            "-benchmark",
            "-vc", "null",
            "-vo", "null",
            "-ss", str(offset),
            "-endpos", str(duration),
            "-af", "resample=%d,format=s16le" % SAMPLERATE,
            "-ao", "pcm:fast:nowaveheader:file=" + fd.name,
            filename
        ], stdout=subprocess.DEVNULL)
        fd.seek(0)
        return fd.read()

def do_fingerprint(track):
    if track["duration"] < 5:
        return (track["offset"], track["title"], Errors.too_short)
    data = render_track(track["filename"], track["offset"], track["duration"])
    fingerprint = acoustid.fingerprint(SAMPLERATE, CHANNELS, [data])
    if len(fingerprint) > 6:
        return (track["offset"], track["title"], fingerprint.decode("utf-8"))
    return (track["offset"], track["title"], Errors.bad_fingerprint)

def decorate_tracks(filename, tracks):
    for i, (offset, title) in enumerate(tracks):
        yield {
            "filename": filename,
            "title": title,
            "offset": offset,
            "duration": min(MAX_DURATION, tracks[i + 1][0] - tracks[i][0]
                            if len(tracks) > (i + 1) else MAX_DURATION)
        }

def count_tracks(data):
    return sum(len(x["tracks"]) for x in data)

def fingerprint(data):
    t0 = time.time()
    last_stats = 0
    n_tracks = count_tracks(data)
    processed = 0
    calculated = 0
    errors = []
    ignored = []

    def skip(dest, game, title, offset):
        dest.append((game["url"], game["title"], title, offset))

    def print_stats(last_ts):
        t1 = time.time()
        if (t1 - last_ts) < 0.7:
            return last_ts
        speed = calculated / (t1 - t0)
        remaining = (n_tracks - processed) / speed
        sys.stdout.write("\rProcessing... %5d of %d @ %4.2f/s, finished in %02d:%02d [errors: %d, ignored: %d]" %
                         (processed, n_tracks, speed, remaining / 60, remaining % 60, len(errors), len(ignored)))
        sys.stdout.flush()
        return t1

    with ProcessPoolExecutor() as executor:
        for game in data:
            filename = os.path.join("videos", os.path.basename(game["url"]) + ".m4a")
            if not os.path.isfile(filename):
                processed += len(game["tracks"])
                skip(errors, game, "missing video", -1)
                continue # TODO: Download once the other scripts have been updated to pull new videos
            updated_tracks = []
            for offset, title, fingerprint in executor.map(do_fingerprint, decorate_tracks(filename, game["tracks"])):
                if fingerprint == Errors.too_short:
                    skip(ignored, game, title, offset)
                elif fingerprint == Errors.bad_fingerprint:
                    skip(errors, game, title, offset)
                else:
                    updated_tracks.append((offset, title, fingerprint))
                    calculated += 1
                processed += 1
                last_stats = print_stats(last_stats)
            game["tracks"] = updated_tracks

    sys.stdout.write("\n")
    sys.stdout.flush()

    return data, ignored, errors, calculated

def print_skipped(entries):
    by_game = defaultdict(list)
    for filename, game, title, offset in entries:
        by_game[(filename, game)].append((title, offset))

    for (filename, game), skipped in by_game.items():
        print("* %s [%s]" % (game, filename))
        for title, offset in skipped:
            print("  - [%02d:%02d] %s" % (offset / 60, offset % 60, title))

if __name__ == "__main__":
    t0 = time.time()
    with open("massaged.json") as fd:
        data = json.load(fd)
    t1 = time.time()

    data, ignored, errors, processed = fingerprint(data)
    t2 = time.time()

    with open("massaged-fp.json", "w") as fd:
        json.dump(data, fd)
    t3 = time.time()

    if ignored:
        print("\nIgnored:")
        print_skipped(ignored)
    if errors:
        print("\nErrors:")
        print_skipped(errors)

    print("\nStats:")
    print("%7.2fs load data" % (t1 - t0))
    print("%7.2fs fingerprint tracks (%d tracks/s)" % (t2 - t1, processed/(t2 - t1)))
    print("%7.2fs write data" % (t3 - t2))
    print("")
    print("...a total of %.2fs" % (t3 - t0))
