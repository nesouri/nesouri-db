#!/usr/bin/env python3
from concurrent.futures import ProcessPoolExecutor
import Levenshtein
import json
import operator
import os
import re
import sqlite3
import subprocess
import sys
import acoustid
import tempfile
from gme import *

from contextlib import closing
from pprint import pformat
from unidecode import unidecode
from chromaprint import decode_fingerprint
from munkres import Munkres


soundtrack_patterns = re.compile(".+\((FC|FDS|NES|NES Prototype|NES Hack|NES / FC|NES /FC|NES / FC / Dendy|NES / Famicom|Nintendo Famicom)\).+")
track_pattern = re.compile("(\d{1,2}:\d{2}) (.+)")


CHANNELS = 2
SAMPLERATE = 44100
MAX_DURATION = 45


def load_metadata(path):
    with open(path) as fd:
        return json.load(fd)


def known_videos(path):
    return set(x["resourceId"]["videoId"] for x in load_metadata(path))


def scrub_title(title):
    title = title.encode("ascii", "ignore").decode()
    title = title.replace("( )", "")
    title = title.strip()
    title = re.sub("^[/] ", "", title)
    title = re.sub("[ ]+", " ", title)
    title = re.sub("\(.+$", "", title)
    return title


def parse_tracks(video_id, description):
    def ts_to_offset(ts):
        mins, secs = ts.split(":")
        return int(mins) * 60 + int(secs)

    def calc_duration(tracks, idx):
        return min(MAX_DURATION, tracks[idx + 1]["offset"] - tracks[idx]["offset"]
                   if len(tracks) > (idx + 1) else MAX_DURATION)

    result = []
    for line in description.split("\n"):
        match = track_pattern.match(line)
        if not match:
            continue
        offset, title = match.groups()
        result.append({
            "filename": "videos/%s.m4a" % video_id,
            "position": len(result),
            "title": title,
            "offset": ts_to_offset(offset)
        })

    for idx, track in enumerate(result):
        track["duration"] = calc_duration(result, idx) * 1000

    return result


def find_new_soundtracks(old_metadata, new_metadata):
    known = known_videos(old_metadata)
    for video in load_metadata(new_metadata):
        #if "Mega Man 2" in video["title"]:
        #if "Super Mario" in video["title"]:
        #    tracks = parse_tracks(video["description"])
        #    if not tracks:
        #        continue
        #    yield (scrub_title(video["title"]), video["resourceId"]["videoId"], tracks)
        #else:
        #    continue

        if video["resourceId"]["videoId"] in known:
            continue

        if not soundtrack_patterns.match(video["title"]):
            continue

        tracks = parse_tracks(video["resourceId"]["videoId"], video["description"])
        if not tracks:
            continue

        yield (scrub_title(video["title"]), video["resourceId"]["videoId"], tracks)


def query_games(cursor):
    return dict((game_id, {"game_id": game_id,
                           "title": title,
                           "filename": filename,
                           "total_tracks": total_tracks,
                           "matches": []})
                for game_id, title, filename, total_tracks in cursor.execute("""
                SELECT game_id, title, file, total_tracks
                    FROM games"""))


def query_tracks(cursor, game_id):
    return list({"track": track,
                 "title": title,
                 "duration": duration,
                 "looping": looped == 1}
                for track, title, duration, looped in cursor.execute("""
                SELECT track, title, duration, looped
                FROM tracks
                WHERE game_id=?""", [game_id]))


def calc_title_distances(games, title):
    title = title.lower()
    distances = [(Levenshtein.distance(title, g["title"].lower()), g) for g in games.values()]
    distances.sort(key=operator.itemgetter(0))
    return distances[:10]


def calc_filename_distances(games, title):
    distances = []
    title = title.lower()
    for g in games.values():
        # "w/World Class Track Meet JP [Family Trainer 02 - Running Stadium] (1986-12-23)(Human)(Bandai).7z"
        # => "world class track meet", "family trainer 02 - running stadium"
        filename = g["filename"][g["filename"].find("/")+1:].replace(" JP ", " ").lower()
        start_idx = filename.find("[")
        if start_idx > 0:
            end_idx = filename.find("]")
            title_a = filename[:start_idx].strip()
            title_b = filename[start_idx+1:end_idx].strip()
        else:
            start_idx = filename.find("(")
            title_a = filename[:start_idx].strip()
            title_b = None

        distance = Levenshtein.distance(title, title_a)
        if title_b:
            distance_b = Levenshtein.distance(title, title_b)
            if distance_b < distance:
                distance = distance_b

        distances.append((distance, g))

    distances.sort(key=operator.itemgetter(0))

    return distances[:10]


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
        print("Skipping track %(position)d - '%(title)s' of %(filename)s, duration too short (%(duration)dms)" % (track))
        return (track["title"], None)  # Probably a sound effect, too short.
    data = render_track(track["filename"], track["offset"], track["duration"])
    fingerprint = acoustid.fingerprint(SAMPLERATE, CHANNELS, [data])
    if len(fingerprint) > 6:
        return (track["title"], fingerprint.decode("utf-8"))
    print("Skipping track %(index)d - '%(title)s' of %(filename)s, fingerprinting failed" % (track))
    return (track["title"], None)  # Fingerprint failed for unknown reasons.


def decorate_youtube_tracks(filename, tracks):
    def ts_to_offset(ts):
        mins, secs = ts.split(":")
        return int(mins) * 60 + int(secs)

    def calc_duration(index):
        return min(MAX_DURATION,
                   ts_to_offset(tracks[index + 1][0]) - ts_to_offset(tracks[index][0])
                   if len(tracks) > (i + 1) else MAX_DURATION)

    for i, (ts, title) in enumerate(tracks):
        yield {
            "index": i,
            "filename": filename,
            "title": title,
            "offset": ts_to_offset(ts),
            "duration": calc_duration(i)
        }


def fingerprint_tracks(filename, tracks):
    if os.path.isfile(filename + ".fp.json"):
        with open(filename + ".fp.json") as fd:
            print(" * Already have " + filename + ".fp.json")
            return json.load(fd)

    result = []
    with ProcessPoolExecutor() as executor:
        for title, fingerprint in executor.map(do_fingerprint, tracks):
#                                               decorate_youtube_tracks(filename, tracks)):
            result.append([title, fingerprint])

    with open(filename + ".fp.json", "w") as fd:
        json.dump(result, fd)

    return result


def do_fingerprint_gme(track):
    engine = Gme.from_file(track["filename"], SAMPLERATE)
    buf = engine.create_buffer(seconds=MAX_DURATION)
    duration = track.get("duration", MAX_DURATION)
    if not track["looping"] and duration < 5000:
        print("Skipping track %(track)d - '%(title)s' of %(filename)s, duration too short (%(duration)dms)" % (track))
        return None
    try:
        engine.start_track(track["track"] - 1)
        engine.play(buf)
        data = buf.get_bytes(trim=True)
        if len(data) < 480644:
            print("Error[%d]: Not enough data" % track["track"])
            return None
        return acoustid.fingerprint(SAMPLERATE, CHANNELS, [data]).decode("utf-8")
    except Exception as e:
        print("Error[%d]: %s" % (track["track"], e))


def decorate_gme_tracks(filename, tracks):
    for track in tracks:
        track["filename"] = filename.replace(".7z", ".nsf")
        yield track


def fingerprint_gme(filename, tracks):
    if os.path.isfile(filename + ".fp.json"):
        with open(filename + ".fp.json") as fd:
            print(" * Already have " + filename + ".fp.json")
            return json.load(fd)

    result = []
    with ProcessPoolExecutor() as executor:
        for fingerprint in executor.map(do_fingerprint_gme,
                                        decorate_gme_tracks(filename, tracks)):
            result.append(fingerprint)

    with open(filename + ".fp.json", "w") as fd:
        json.dump(result, fd)

    return result


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


def decode(fp):
    return decode_fingerprint(fp.encode("utf-8"))[0]


def do_distance(args):
    gme_idx, gme_fp, yt_idx, yt_fp, yt_title = args
    return (gme_idx, yt_idx, calculate_distance(decode(gme_fp), decode(yt_fp)), yt_title)


def distances_for_tracks(filename, yt_fps, gme_fps):
    by_score = []
    if False and os.path.isfile(filename + ".distance.json"):
        with open(filename + ".distance.json") as fd:
            print(" * Already have " + filename + ".distance.json")
            return json.load(fd)
    else:
        def gen_input():
            for i, fp in enumerate(gme_fps):
                if not fp:
                    continue
                for j, (yt_title, yt_fp) in enumerate(yt_fps):
                    if not yt_fp:
                        continue
                    yield (i, fp, j, yt_fp, yt_title)

        by_gme = []
        with ProcessPoolExecutor() as executor:
            by_gme = {}
            by_gme_d = {}
            by_gme_a = []
            by_gme_a_d = []
            for gme_idx, yt_idx, distance, yt_title in executor.map(do_distance, gen_input()):
#                if distance >= 0.98:
#                    distance = 1.0

                lst = by_gme.get(gme_idx)
                lst_d = by_gme_d.get(gme_idx)
                if not lst:
                    lst = []
                    lst_d = []
                    by_gme[gme_idx] = lst
                    by_gme_a.append(lst)
                    by_gme_d[gme_idx] = lst_d
                    by_gme_a_d.append(lst_d)
                #print(gme_idx, yt_idx, len(by_gme[gme_idx]))
                lst.append(distance)
                lst_d.append((gme_idx, yt_idx, yt_title))

        by_score = by_gme_a

#        for i, yt in enumerate(by_score):
#            print(str(i)+"="+",".join("%.2f" % x for x in yt))

        result = {}

        munk = Munkres()
        for row, col in munk.compute(by_score):
            score = by_gme_a[row][col]
            if score < 0.98:
                gme_idx, yt_idx, _ = by_gme_a_d[row][col]
                result[gme_idx] = (yt_idx, score)

        with open(filename + ".distance.json", "w") as fd:
            json.dump(result, fd)

        return result


if __name__ == "__main__":
    with closing(sqlite3.connect("../metadata.db")) as conn, closing(conn.cursor()) as cursor:
        games = query_games(cursor)
        for idx, (title, video_id, tracks) in enumerate(find_new_soundtracks(sys.argv[1], sys.argv[2])):
            title_distances = calc_title_distances(games, title)
            fname_distances = calc_filename_distances(games, title)

            distances = title_distances + fname_distances

            print("-"*80)
            print(title)
            #for idx, (title, duration) in enumerate(tracks):
            #    print("%2d: %s [%s]" % (idx, title, duration))
            print("-"*80)

            print("\n".join(" %2d. %-50s %s" % (i + 1, x[1]["title"], x[1]["filename"]) for i, x in enumerate(distances)))

            selected_game = None
            while True:
                try:
                    sys.stdout.write("Select match (0=skip): ")
                    sys.stdout.flush()
                    raw = input()
                    if not raw.strip():
                        break
                    number = int(raw)
                    if number == 0:
                        break
                    selected_game = distances[number - 1][1]
                    break
                except ValueError:
                    pass
                except Exception as e:
                    raise SystemExit(0)

            if not selected_game:
                continue

            print("Preparing fingerprints for " + selected_game["title"])

            filename = os.path.join("videos", video_id + ".m4a")

            if not os.path.isfile(filename):
                video_url = "http://youtu.be/" + video_id
                subprocess.call(["youtube-dl", "-f", "140", "-o", filename, video_url])
            else:
                print(" * Already have " + filename)

            fps = fingerprint_tracks(filename, tracks)

            nsf_filename = os.path.join(sys.argv[3], selected_game["filename"])
            db_tracks = query_tracks(cursor, selected_game["game_id"])
            fps_gme = fingerprint_gme(nsf_filename, db_tracks)

            mapping = distances_for_tracks(nsf_filename, fps, fps_gme)
            unmapped = set(range(len(tracks)))
            for track in db_tracks:
                yt_idx = mapping.get(track["track"] - 1)
                if yt_idx:
                    yt = tracks[yt_idx[0]]
                    unmapped.remove(yt_idx[0])
                    print("[%3d%%] %2d - %s => %s (%dms vs %dms)" % ((1.0 - yt_idx[1]) * 100.0, track["track"], track.get("title", "<Unknown>"), yt["title"], track["duration"], yt["duration"]))
                else:
                    print("[----] %2d - %s (%dms)" % (track["track"], track.get("title", "<Unknown>"), track["duration"]))


            print("No mapping for YouTube entries:")
            for yt in (tracks[x] for x in sorted(unmapped)):
                print("[---] %2d - %s (%dms)" % (yt["position"], yt["title"], yt["duration"]))
