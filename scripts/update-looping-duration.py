#!/usr/bin/env python3.4
# Update duration from csv output from nosefart/scan.py
from collections import defaultdict
from contextlib import closing
from os.path import basename
import csv
import sqlite3

def query_games(cursor):
    return dict((basename(filename).replace(".7z", ".nsf"), game_id)
                for game_id, filename
                in cursor.execute("SELECT game_id, file FROM games"))

def query_tracks(cursor):
    return dict(((game_id, track), title)
                for game_id, track, title
                in cursor.execute("SELECT game_id, track, title FROM tracks"))

def gen_details_fun(games, tracks):
    def do_lookup(filename, track):
        game_id = games.get(filename)
        return game_id, tracks.get((game_id, track), None)
    return do_lookup

def query_extra(path, filter_fun=lambda x: True):
    with open(path) as fd:
        return dict(((filename, int(track)), int(extra))
                     for filename, track, extra
                     in csv.reader(fd)
                     if filter_fun(extra))

def decorate_extra(durations, looping, details_fun):
    for filename, track in frozenset(durations) | frozenset(looping):
        game_id, title = details_fun(filename, track)
        if not game_id:
            continue
        duration = durations.get((filename, track), None)
        looped = looping.get((filename, track), None)
        yield {"game_id": game_id,
               "track": track,
               "title": title,
               "duration": duration,
               "looped": looped}

def update(cursor, duration_path, looping_path):
    game_id_by_file = query_games(cur)
    track_by_game_id = query_tracks(cur)
    duration_by_file = query_extra(duration_path, lambda dur: dur != 0)
    looping_by_file = query_extra(looping_path)

    cursor.executemany("""
    INSERT OR REPLACE INTO tracks (game_id, track, title, duration, looped)
        VALUES (:game_id, :track, :title, :duration, :looped)
    """, decorate_extra(duration_by_file, looping_by_file, gen_details_fun(game_id_by_file, track_by_game_id)))

if __name__ == "__main__":
    with closing(sqlite3.connect("metadata.db")) as conn:
        with closing(conn.cursor()) as cur:
            update(cur, "duration.csv", "looping.csv")
        conn.commit()
