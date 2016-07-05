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
#import distance
import Levenshtein
import operator

def query_games(cursor):
    return dict((game_id, {"game_id": game_id,
                           "title": title,
                           "filename": filename,
                           "total_tracks": total_tracks,
                           "matches": []})
                for game_id, title, filename, total_tracks in cursor.execute("""
                SELECT game_id, title, file, total_tracks
                    FROM games"""))

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

        try:
            with open("manual-mapping.json") as fd:
                manual_mapping = json.load(fd)
        except:
            manual_mapping = {}

        matched_by_id = set([])
        unmatched_yt = []
        for entry in youtube:
            if "Super Famicom" in entry["title"]:
                continue
            matched = False
            title = manual_mapping.get(entry["url"])
            if title is None:
                title = entry["title"]
            for game in by_name.get(title, []):
                game["matches"].append(entry)
                matched_by_id.add(game["game_id"])
                matched = True
            if not matched:
                unmatched_yt.append(entry)

        unmatched_by_title = defaultdict(list)
        for name, entries in by_name.items():
            for entry in entries:
                if entry["game_id"] in matched_by_id:
                    continue
                unmatched_by_title[entry["title"]].append(entry)

        print("total games:", len(games))
        print("unmatched nesouri:", len(unmatched_by_title))
        print("unmatched youtube: ", len(unmatched_yt))

        t0 = time.time()

        for youtube in unmatched_yt:
            yt_title = youtube["title"]
            if yt_title == "Kung Fu":
                yt_title = "Kung Fu Master"
            yt_title = yt_title.replace("Kung-Fu Heroes", "Super Chinese")
            yt_title = yt_title.replace("DuckTales", "Disney DuckTales")
            yt_title = yt_title.replace("Fire Emblem", "Fire Emblem: Ankoku Ryu to Hikari no Tsurugi")
            yt_title = yt_title.replace("Super Robin Hood", "Quattro Adventure: Super Robin Hood")
            yt_title = yt_title.replace("Bad Dudes", "Bad Dudes vs dragon ninja")
            yt_title = yt_title.replace("grad1u5's archive video - NES:", "")
            yt_title = yt_title.replace("Dragon Warrior", "Dragon Quest")

            yt_title2 = yt_title.lower()
            shortest = sys.maxsize
            shortest_sel = []
            for title, entry in by_name.items():
                title2 = title.lower() #entry[0]["filename"].lower()
                d = Levenshtein.distance(yt_title2, title2)
                if yt_title2.startswith("the "):
                    yt_title2 = yt_title2[4:]
                if title2.startswith("the "):
                    title2 = title2[4:]
                yt_title2 = yt_title2.replace(" the ", "")
                title2 = title2.replace(" the ", "")
                d2 = Levenshtein.distance(yt_title2, title2)
                if d2 < d:
                    d = d2
                d2 = Levenshtein.distance(yt_title2, title2)
                if d2 < d:
                    d = d2
                for i,x in enumerate(["I", "II", "III", "IV", "V", "VI", "VII"]):
                    yt_title3 = yt_title2.replace(str(i+1), x)
                    d3 = Levenshtein.distance(yt_title2, title2)
                    if d3 < d:
                        d = d3
                    #yt_title3 = yt_title2.replace(" %s " % x, str(i+1
                if yt_title.lower() in title.lower():
                    d = 0
                for e in entry:
                    if yt_title.lower() in e["filename"]:
                        d = 0

                shortest = d
                shortest_sel.append((d, title, ", ".join(x["filename"] for x in entry), ", ".join(str(x["total_tracks"]) for x in entry)))
            shortest_sel.sort(key=operator.itemgetter(0))
            youtube["maybe"] = shortest_sel
        t1 = time.time()

        for j, x in enumerate(unmatched_yt):
            if x["maybe"][0][0] == 0:
                manual_mapping[x["url"]] = x["maybe"][0][1]
            else:
                print("[%3d/%3d] YouTube: %s -- %s" % (j+1, len(unmatched_yt), x["title"], x["url"]))
                for i, (diff, title, filename, tracks) in enumerate(x["maybe"][:30]):
                    print("%2d) %3d - %-40s (%s) [%s]" % (i, diff, title, tracks, filename))
                t = input().strip()
                try:
                    manual_mapping[x["url"]] = x["maybe"][int(t)][1]
                except Exception as e:
                    pass
                if t == "q":
                    break

        for i, x in enumerate(unmatched_yt):
            if x["url"] in manual_mapping:
                continue
            print("%2d) %-40s %s %d" % (i, x["title"], x["url"], len(x["tracks"])))

        while True:
            num = input().strip()
            if num == "q":
                break
            try:
                num = int(num)
            except:
                break
            print("Enter title for: " + unmatched_yt[num]["title"])
            title = input().strip()
            if title == "q":
                break
            print("'%s' == '%s' ?" % (unmatched_yt[num]["title"], title))
            ok = input().strip()
            if ok == "y":
                manual_mapping[unmatched_yt[num]["url"]] = title
            elif ok == "q":
                break

        with open("manual-mapping.json", "w") as fd:
            json.dump(manual_mapping, fd)
