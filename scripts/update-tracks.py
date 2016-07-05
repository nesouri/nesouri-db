from contextlib import closing
import json
import sqlite3


def gen_tracks():
    with open("best-matches.json") as fd:
        matches = json.load(fd)
        for game_id, tracks in matches.items():
            for track, title, similarity in tracks:
                title, *rest = title.split("～")
                title = title.encode("ascii", errors="ignore").decode("utf-8")
                title = title.replace("()", "").strip()
                yield {
                    "game_id": game_id,
                    "track": track,
                    "title": title
                }

def query_games(cursor):
    return dict((game_id, title)
                for game_id, title
                in cursor.execute("SELECT game_id, title FROM games"))

if __name__ == "__main__":
    with closing(sqlite3.connect("../metadata.db")) as conn, closing(conn.cursor()) as cursor:
        games = query_games(cursor)
        with open("best-matches.json") as fd:
            matches = json.load(fd)
            for g in matches.keys():
                print(games[int(g)])
