#!/usr/bin/env python
import subprocess
import json
import os

if __name__ == "__main__":
    if not os.path.isdir("videos"):
        os.mkdir("videos")
    with open("massaged.json") as fd:
        for entry in json.load(fd):
            video_id = os.path.basename(entry["url"])
            subprocess.call(["youtube-dl", "-f", "140", "-o", "videos/%s.m4a" % video_id, entry["url"]])
