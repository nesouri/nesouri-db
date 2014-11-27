# http://www.vgmpf.com
# http://nintendo.wikia.com/
# http://bootleggames.wikia.com/wiki/BootlegGames_Wiki

import csv
import sqlite3
import os
import re

#conn = sqlite3.connect(":memory:")
try:
    os.unlink("metadata.db")
except:
    pass
conn = sqlite3.connect("metadata.db")

c = conn.cursor()

c.execute("""
CREATE TABLE systems (
    _id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    abbrev TEXT UNIQUE NOT NULL,
    url TEXT
)""")

c.execute("""
CREATE TABLE games (
    _id INTEGER PRIMARY KEY,
    file TEXT UNIQUE,
    system INTEGER NOT NULL REFERENCES systems(_id),
    title TEXT,
    year INTEGER,
    date TEXT,
    url TEXT
)""")

c.execute("""
CREATE TABLE tracks (
    _id INTEGER PRIMARY KEY,
    game INTEGER REFERENCES games(_id),
    track INTEGER,
    title TEXT,
    UNIQUE (game, track)
)""")

c.execute("""
CREATE TABLE authors (
    _id INTEGER PRIMARY KEY,
    name TEXT UNIQUE
)""")

c.execute("""
CREATE TABLE authorship (
    _id INTEGER PRIMARY KEY,
    game INTEGER NOT NULL REFERENCES games(_id),
    author INTEGER NOT NULL REFERENCES authors(_id),
    UNIQUE (game, author)
)""")

def insert_author(c, author, filename):
    authors = author.split(",")
    if not authors:
        return
    for x in authors:
        x = x.strip()
        if not x:
            continue
        c.execute("""
             INSERT OR IGNORE INTO authors (name) VALUES (?)
        """, (x,))

        c.execute("""
             INSERT OR IGNORE INTO authorship (game, author) VALUES (
               (SELECT _id FROM games WHERE file = ?),
               (SELECT _id FROM authors WHERE name = ?)
             )
        """, (filename, author))

pattern = re.compile("^([^\[(]+) ((?:\[(?:[^\]]+)\] )*)?(?:(?:EU|JP) )?(?:\((?:((?:\d{4}-\d{2}-\d{2})|(?:\d{4}-\d{2})|(?:\d{4}))|(?:[^)]+))\) ?)*")
def parse_filename(filename):
    year = None
    try:
        name, original, date = pattern.findall(filename)[0]
    except:
        return None, None, None, None
    if len(date) == 4:
        year = date
    elif len(date) in (10, 7):
        year = date[:4]
    else:
        date = None
    if len(original) == 0:
        original = None
    #if not date and (("198" in filename) or ("199" in filename)):
    #    print(filename)
    return name, original, date, year


m3u_ptrn = re.compile("(\d{4})?(.+)")
def parse_m3u(c, filename):
    base, ext = os.path.splitext(filename)
    playlist = base + ".m3u"
    if not os.path.exists(playlist):
        return
    artits = []
    year = None
    holder = None
    header = True
    with open(playlist, encoding='utf8') as fd:
        for line in fd:
            if not line.strip():
                continue
            if line.startswith("#"):
                if "Music by" in line:
                    if "Unknown" not in line and "???" not in line and "< ? >" not in line:
                        contrib = line[11:]
                        contrib = re.sub("(\w)\.(\w)", "\\1 \\2", contrib)
                        contrib = re.sub("(\w)_(\w)", "\\1 \\2", contrib)
                        contrib = re.sub(",and ", ",", contrib)
                        contrib = re.sub(" and ", ",", contrib)
                        contrib = re.sub(" and/or ", ",", contrib)
                        contrib = re.sub(" & ", ",", contrib)
                        authors = [x.strip() for x in contrib.split(",")]
                if "Copyright" in line:
                    copyright = line[10:]
                    copyright = re.sub("(c) ", "", copyright)
                    copyright = re.sub("(c)", "", copyright)
                    copyright = re.sub("(C)", "", copyright)
                    copyright = re.sub(": ", "", copyright)
                    copyright = copyright.strip()
                    year, holder = m3u_ptrn.findall(copyright)[0]
            else:
                file, rest = line.split("::")
                data = rest.split(",")
                track = data[1]
                title = data[2]
                c.execute("""
                 INSERT OR IGNORE INTO tracks (game, track, title) VALUES (
                   (SELECT _id FROM games WHERE file = ?), ?, ?
                 )
                """, (filename, track, title))



c.execute("INSERT OR IGNORE INTO systems (name, abbrev, url) VALUES (?, ?, ?)",
          ("Nintendo Entertainment System", "NES", "https://en.wikipedia.org/wiki/Nintendo_Entertainment_System"))

with open("metadata.txt", encoding="utf-8") as fd:
    for row in csv.reader(fd):
        try:
            (filename,totaltracks,system,game,song,author,copyright,comment,dumper,length,intro_length,loop_length) = row
            filename = filename[2:]
            name, original, date, year = parse_filename(filename)
            c.execute("INSERT OR IGNORE INTO games (file, title, system, year, date) VALUES (?, ?, ?, ?, ?)", (filename, game, 1, int(year) if year else None, date))
            insert_author(c, author, filename)
            parse_m3u(c, filename)

        except Exception as e:
            print("Error: " + str(e))
            print(row)

conn.commit()
