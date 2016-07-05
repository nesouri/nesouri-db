import json
from pprint import pformat
import re
from unidecode import unidecode

def load(filename):
    with open(filename) as fd:
        return json.load(fd)

def ts_to_offset(ts):
    mins, secs = ts.split(":")
    return int(mins) * 60 + int(secs)

def handle_world_of_longplays(entry):
    pass



def handle_grad1u52(entry):
    title = entry["title"]
    if not title.startswith("Nes"):
        return
    result = {}
    title = title[3:]
    if title[0] == ":":
        title = title[1:]
    title = title.replace("Soundtrack", "")
    if "(FDS)" in title:
        title = title.replace("(FDS)", "")
        result["platform"] = "FDS"
    else:
        result["platform"] = "NES"
    result["title"] = unidecode(title.strip())
    result["url"] = "http://youtu.be/" + entry["resourceId"]["videoId"]
    result["tracks"] = []
    entries = re.findall("(\d+:\d+) / (.+)", entry["description"])
    for ts, title in entries:
        offset = ts_to_offset(ts)
        result["tracks"].append((offset, title))

    if not result["tracks"]:
        return

    return result


def handle_wiiguy309(entry):
    result = {}

    title = entry["title"]
    if "(NES)" in title:
        result["platform"] = "NES"
        result["title"] = title.replace(" (NES) Soundtrack - Stereo", "")
    elif "(FC)" in title:
        result["platform"] = "FC"
        result["title"] = title.replace(" (FC) Soundtrack - Stereo", "")
    else:
        return

    result["url"] = "http://youtu.be/" + entry["resourceId"]["videoId"]
    result["tracks"] = []
    entries = re.findall("(\d+:\d+) (.+)", entry["description"])
    for x in range(len(entries)):
        ts, track_title = entries[x]
        offset = ts_to_offset(ts)
        result["tracks"].append((offset, track_title))
    if not result["tracks"]:
        return
    return result

def handle_mrnorbert1994(entry):
    title = entry["title"]
    if "SNES" in title or not "Soundtrack" in title or not ("NES" in title or "Famicom" in title or "Famiclone" in title):
        return
    result = {}
    if "Famicom Disk System" in title:
        result["title"] = title.replace(" (Nintendo Famicom Disk System) Music / Soundtrack", "")
        result["platform"] = "FDS"
    elif "Famicom" in title:
        result["title"] = title.replace(" (Nintendo Famicom) Music / Soundtrack", "")
        result["platform"] = "FC"
    elif "Dendy" in title:
        result["title"] = title.replace(" (Nintendo Dendy / Nintendo Famiclone) Music / Soundtrack", "").replace(" (Nintendo Dendy / Nintendo  Famiclone) Music / Soundtrack", "")
        result["platform"] = "Dendy"
    else:
        result["title"] = title.replace(" (NES) Music / Soundtrack", "")
        result["platform"] = "NES"
    decoded = result["title"].encode("ascii", errors="ignore").decode("utf-8")
    if decoded != result["title"]:
        decoded = decoded.replace("( )", "").strip()
        parts = decoded.split("/")
        longest = ""
        for p in parts:
            if len(p) > len(longest):
                longest = p
        decoded = longest.strip()
    result["title"] = decoded
    result["tracks"] = []
    result["url"] = "http://youtu.be/" + entry["resourceId"]["videoId"]
    entries = re.findall("(\d+:\d+) (.+)", entry["description"])
    for x in range(len(entries)):
        ts, track_title = entries[x]
        offset = ts_to_offset(ts)
        result["tracks"].append((offset, track_title))
    if not result["tracks"]:
        return
    return result

data = load("youtube-metadata.json")

res = []
for entry in data:
    x = None
    channelTitle = entry["channelTitle"]
    if channelTitle == "World of Longplays":
        handle_world_of_longplays(entry)
    elif channelTitle == "grad1u52":
        x = handle_grad1u52(entry)
    elif channelTitle == "Wiiguy309":
        x = handle_wiiguy309(entry)
    elif channelTitle == "MrNorbert1994":
        x = handle_mrnorbert1994(entry)
    else:
        print(entry["title"])
        print(pformat(entry))
    if x:
        res.append(x)

with open("massaged.json", "w") as fd:
    json.dump(res, fd)
