#!/usr/bin/env python3.4
from collections import defaultdict
from contextlib import closing
from gme import *
from pprint import pformat
import acoustid
import chromaprint
import json
import sqlite3
import subprocess
import tempfile
import wave
import numpy
import scipy
import struct
from ctypes import *
from itertools import *
import math
import numpy as np
from scipy.signal import butter, lfilter, freqz
import matplotlib.pyplot as plt

SAMPLERATE=44100
CHANNELS=2
DURATION=45
LP=False
LP_CUTOFF=1200

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

def query_games(cursor):
    return cursor.execute("""
    SELECT g.game_id, g.title, g.file, s.abbrev, do.name, po.name
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

def load_nesouri():
    games = defaultdict(list)
    with closing(sqlite3.connect("../metadata.db")) as conn:
        with closing(conn.cursor()) as games_cursor, closing(conn.cursor()) as tracks_cursor:
            for game_id, title, filename, platform, developer, publisher in query_games(games_cursor):
                games[title].append({
                    "game_id": game_id,
                    "filename": filename,
                    "platform": platform,
                    "developer": developer,
                    "publisher": publisher,
                    "tracks": [{"track": track, "title": title, "duration": duration, "looping": looping}
                               for track, title, duration, looping in query_tracks(tracks_cursor, game_id)]
                })
    return games

def pcm_for_youtube(filename, offset, duration=30):
    def fmt():
        if CHANNELS == 2:
            return "resample=%d,format=s16le" % SAMPLERATE
        return "resample=%d,pan=1:0.5:0.5,format=s16le" % SAMPLERATE

    with tempfile.NamedTemporaryFile("rb") as fd:
        subprocess.call([
            "mplayer",
            "-nolirc",
            "-benchmark",
            "-vc", "null",
            "-vo", "null",
            "-ss", str(offset),
            "-endpos", str(duration),
            #"-af", "resample=%d,pan=1:1:0,format=s16le" % SAMPLERATE,
            #"-af", "resample=%d,format=s16le" % SAMPLERATE,
            #"-af", "resample=%d,pan=1:0.5:0.5,pan=2:0.5:0.5,format=s16le" % SAMPLERATE,
            #"-af", "resample=%d,pan=1:0.5:0.5,format=s16le" % SAMPLERATE,
            "-af", fmt(),
            "-ao", "pcm:fast:nowaveheader:file=" + fd.name,
            filename
        ], stdout=subprocess.DEVNULL)
        #print(fd.name)
        #input()
        fd.seek(0)
        return fd.read()

def fingerprint(data, samplerate=SAMPLERATE, channels=CHANNELS):
    return acoustid.fingerprint(samplerate, channels, [data])

def process_track(meta, pos):
    for t in meta[0]["tracks"]:
        if t["track"] == (pos + 1):
            return t["looping"] or t["duration"] > 5000

def nsf_fingerprints(meta, filename, duration=DURATION):
    b,a = scipy.signal.butter(6, 0.1, "low", False, "ba")
    fingerprints = []
    srate = 44100 # SAMPLERATE
    engine = Gme.from_file(filename, int(srate))
    for track in range(engine.track_count()):
        if not process_track(meta, track):
            continue
        engine.start_track(track)
        buf = engine.create_buffer(seconds=duration)
        engine.play(buf)
        # avg = sum(math.fabs(x) for x in monobuf)/len(monobuf)
        if LP:
            na = numpy.ctypeslib.as_array(buf)
            fa = scipy.signal.filtfilt(b, a, na)
            #fa = butter_lowpass_filter(na, LP_CUTOFF, SAMPLERATE, 6)
            for x in range(len(fa)):
                buf[x] = int(fa[x])
        # fingerprints.append((avg, fingerprint(bytes(monobuf))))#b2[:int(len(b2)/2)]))
        # print(fingerprints[-1])
        # writer = wave.open("nsf-%d.wav" % track, "wb")
        # writer.setparams((1, 2, SAMPLERATE, 0, "NONE", None))
        # writer.writeframes(bytes(monobuf))
        # writer.close()
        if CHANNELS == 2:
            fingerprints.append(fingerprint(bytes(buf), samplerate=srate, channels=CHANNELS))
        else:
            monobuf = (c_short * (int(len(buf)/2)))(*(int((x+y)/2) for x,y in zip(islice(buf, 0, len(buf)-1, 2), islice(buf, 1, None, 2))))
            fingerprints.append(fingerprint(bytes(monobuf), samplerate=srate, channels=CHANNELS))
    return fingerprints

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

def butter_lowpass(cutoff, fs, order=5):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    return b, a

def butter_lowpass_filter(data, cutoff, fs, order=5):
    b, a = butter_lowpass(cutoff, fs, order=order)
    y = lfilter(b, a, data)
    return y

if __name__ == "__main__":
    data = []
    with open("massaged.json") as fd:
        data = json.load(fd)

    db = load_nesouri()

    lfile = "/home/daniel/Development/home/nesouri-web/resources/public/html/nsf/t/Treasure Master (1991-12)(Software Creations)(ASC).nsf"
    #lfile = "/home/daniel/Development/home/nesouri-web/resources/public/html/nsf/s/Super Spy Hunter [Battle Formula] (1991-09-27)(Sunsoft).nsf"
    #lfile = "/home/daniel/Development/home/nesouri-web/resources/public/html/nsf/s/Super Spy Hunter JP [Battle Formula] (1991-09-27)(Sunsoft).nsf"

    t = "Treasure Master"
    #t = "Super Spy Hunter"
    ymeta = [x for x in data if t in x["title"]][0]
    nmeta = db[t]
    yfile = "treasuremaster.m4a"
    #yfile = "superspyhunter.m4a"
    fps = nsf_fingerprints(nmeta, lfile, DURATION)

    b,a = scipy.signal.butter(6, 0.1, "low", False, "ba")

    for ytrack in range(len(ymeta["tracks"])):
        track = ymeta["tracks"][ytrack]
        try:
            next_track = ymeta["tracks"][ytrack + 1]
            duration = min(DURATION, next_track[0] - track[0])
        except:
            duration = DURATION

        pcm1 = pcm_for_youtube(yfile, track[0], duration)
        #print(ytrack, track[0], ymeta["tracks"][ytrack+1][0], len(pcm1), duration)

        if LP:
            r = (c_byte * len(pcm1))(*pcm1)
            sarr = cast(r, POINTER((c_short * int(len(r)/2)))).contents
            na = numpy.ctypeslib.as_array(sarr)
            fa = scipy.signal.filtfilt(b, a, na)
            #fa = butter_lowpass_filter(na, LP_CUTOFF, SAMPLERATE, 6)
            for x in range(len(fa)):
                sarr[x] = int(fa[x])
            fp1 = fingerprint(bytes(sarr), samplerate=SAMPLERATE, channels=CHANNELS)
        else:
            fp1 = fingerprint(bytes(pcm1), samplerate=SAMPLERATE, channels=CHANNELS)

        for ntrack, fp in enumerate(fps):
            # writer = wave.open("ytnsf-%d.wav" % ytrack, "wb")
            # writer.setparams((1, 2, SAMPLERATE, 0, "NONE", None))
            # writer.writeframes(bytes(sarr))
            # writer.close()
            #raise SystemExit(0)

            #fp1 = fingerprint(bytes(sarr))
            perc = 100 * calculate_distance(chromaprint.decode_fingerprint(fp)[0], chromaprint.decode_fingerprint(fp1)[0])
            if perc < 98.5:
                print("%2d=%-2d %.2f%% difference" % (ytrack, ntrack, perc))
