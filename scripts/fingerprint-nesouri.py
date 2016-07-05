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

def query_games(cursor):
    return cursor.execute("""
    SELECT g.game_id, g.total_tracks, g.title, g.file, s.abbrev, do.name, po.name
        FROM games AS g,
             systems AS s,
             organizations AS do,
             organizations AS po
               ON g.system_id=s.system_id AND
                  g.developer_id=do.organization_id AND
                  g.publisher_id=po.organization_id
               """)

def query_tracks(cursor, game_id):
    return cursor.execute("""
    SELECT track, title, duration, looped
        FROM tracks
        WHERE game_id=?""", [game_id])

def count_tracks():
    with closing(sqlite3.connect("../metadata.db")) as conn:
        with closing(conn.cursor()) as cursor:
            return next(cursor.execute("""
            SELECT sum(total_tracks) FROM games
            """))[0]

def nesouri(path):
    with closing(sqlite3.connect("../metadata.db")) as conn:
        with closing(conn.cursor()) as games_cursor, closing(conn.cursor()) as tracks_cursor:
            for game_id, total_tracks, title, filename, platform, developer, publisher in query_games(games_cursor):
                yield {
                    "game_id": game_id,
                    "total_tracks": total_tracks,
                    "title": title,
                    "filename": os.path.join(path, filename.replace(".7z", ".nsf")),
                    "platform": platform,
                    "developer": developer,
                    "publisher": publisher,
                    "tracks": dict((track, {"track": track, "title": title, "duration": duration, "looping": bool(looping)})
                                   for track, title, duration, looping in query_tracks(tracks_cursor, game_id))
                }


def fingerprint(path):
    t0 = time.time()
    last_stats = 0
    n_tracks = count_tracks()
    processed = 0
    skipped = 0

    result = []

    def print_stats(last_ts):
        t1 = time.time()
        if (t1 - last_ts) < 0.7:
            return last_ts
        speed = (processed - skipped) / (t1 - t0)
        remaining = (n_tracks - processed) / speed
        sys.stdout.write("\rProcessing... %5d of %d @ %4.2f/s, finished in %02d:%02d [skipped: %d]" %
                         (processed, n_tracks, speed, remaining / 60, remaining % 60, skipped))
        sys.stdout.flush()
        return t1

    with ProcessPoolExecutor() as executor:
        for game_id, total_tracks, fingerprints in executor.map(do_fingerprint, nesouri(path)):
            skipped += total_tracks - len(fingerprints)
            processed += total_tracks
            if fingerprints:
                result.append((game_id, fingerprints))
            last_stats = print_stats(last_stats)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return result

if __name__ == "__main__":
    t0 = time.time()
    with open("nesouri-fp.json", "w") as fd:
        json.dump(fingerprint(sys.argv[1]), fd)
    print("Took %.2fs" % (time.time() - t0))
