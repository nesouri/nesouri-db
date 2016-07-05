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
import Levenshtein
import operator
from chromaprint import decode_fingerprint
from munkres import Munkres

def popcount_lookup8(x):
    popcount_table_8bit = [
        0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4, 1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5,
        1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, 2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6,
        1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, 2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6,
        2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, 3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7,
        1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, 2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6,
        2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, 3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7,
        2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, 3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7,
        3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7, 4, 5, 5, 6, 5, 6, 6, 7, 5, 6, 6, 7, 6, 7, 7, 8,
    ]
    return popcount_table_8bit[x & 255] + \
        popcount_table_8bit[(x >> 8) & 255] + \
        popcount_table_8bit[(x >> 16) & 255] + \
        popcount_table_8bit[(x >> 24)]

# https://zenu.wordpress.com/2011/05/28/audio-fingerprinting-and-matching-using-acoustid-chromaprint-on-windows-with-python/
def calculate_distance(fingerprint1, fingerprint2):
    ACOUSTID_MAX_ALIGN_OFFSET = 120
    ACOUSTID_MAX_BIT_ERROR = 4

    numcounts = len(fingerprint1) + len(fingerprint2) + 1
    counts = [0] * numcounts
    for i in range(len(fingerprint1)):
        jbegin = max(0, i - ACOUSTID_MAX_ALIGN_OFFSET)
        jend = min(len(fingerprint2), i + ACOUSTID_MAX_ALIGN_OFFSET)
        for j in range(jbegin, jend):
            biterror = popcount_lookup8(fingerprint1[i] ^ fingerprint2[j])
            if (biterror <= ACOUSTID_MAX_BIT_ERROR):
                offset = i - j + len(fingerprint2)
                counts[offset] += 1

    return 1.0 - (max(counts) / (1.0 * min(len(fingerprint1), len(fingerprint2))))

def query_games(cursor):
    return dict((game_id, {"game_id": game_id,
                           "title": title,
                           "filename": filename,
                           "total_tracks": total_tracks,
                           "matches": []})
                for game_id, title, filename, total_tracks in cursor.execute("""
                SELECT game_id, title, file, total_tracks
                    FROM games"""))

def decode(fp):
    return decode_fingerprint(fp.encode("utf-8"))[0]

def do_stuff(game):
    best_match = []
    best_score = 99999999999999999999999
    if all(t is None for p,t,f in game.get("tracks", [])):
        if game.get("matches"):
            for m in game["matches"]:
                munk = Munkres()
                by_data = []
                by_score = []
                for position, title, fingerprint in game.get("tracks", []):
                    song_data = []
                    song_score = []
                    for i, (y_position, y_title, y_fingerprint) in enumerate(m["tracks"]):
                        distance = calculate_distance(decode(fingerprint), decode(y_fingerprint))
                        song_score.append(distance)
                        song_data.append((i, position, y_title))
                    by_data.append(song_data)
                    by_score.append(song_score)
                if not by_score:
                    continue
                indices = munk.compute(by_score)
                match = []
                total_score = 1
                for row, column in indices:
                    yt_pos, nsf_pos, title = by_data[row][column]
                    score = by_score[row][column]
                    if score < 0.98:
                        total_score += score
                        match.append((nsf_pos, title, score))
                        #print("%6.2f%% %2d=%-2d %s" % (100.0 - score * 100.0, nsf_pos, yt_pos, title))
                if total_score < best_score:
                    best_score = total_score
                    best_match = match
    return (game["game_id"], best_match)

if __name__ == "__main__":
    with closing(sqlite3.connect("../metadata.db")) as conn, closing(conn.cursor()) as cursor:
        games = query_games(cursor)

        by_name = defaultdict(list)
        for game_id, entry in games.items():
            by_name[entry["title"]].append(entry)

        with open("nesouri-fp.json") as fd:
            for game_id, tracks in json.load(fd):
                games[game_id]["tracks"] = tracks
        with open("massaged-fp.json") as fd:
            youtube = json.load(fd)

        with open("manual-mapping.json") as fd:
            manual_mapping = json.load(fd)

        for entry in youtube:
            title = manual_mapping.get(entry["url"])
            if title is None:
                title = entry["title"]
            for game in by_name.get(title, []):
                game["matches"].append(entry)

        result = {}
        with ProcessPoolExecutor() as executor:
            for game_id, match in executor.map(do_stuff, games.values()):
                if match:
                    print(games[game_id]["title"])
                    for nsf_pos, title, score in match:
                        print("%2d %5.2f%% %s" % (nsf_pos, 100 - 100 * score, title))
                    result[game_id] = match
                    break

        with open("best-matches.json", "w") as fd:
            json.dump(result, fd)
