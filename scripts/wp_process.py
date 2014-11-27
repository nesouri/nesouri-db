# Used to automate most wikipedia connections, a nasty hack that was modified to filter
# each levenshtein distance level... ugh.. but quite useful.

import sqlite3
from bs4 import BeautifulSoup
import re
from urllib.request import urlopen
import html5lib
import xml.etree.ElementTree as ET
import os
import Levenshtein
from pprint import pformat
import operator

conn2 = sqlite3.connect("metadata.db")

c1 = conn2.cursor()
c1.execute("SELECT _id, title FROM games WHERE url IS NULL")
titles = [(x[0], x[1]) for x in c1.fetchall()]
c1.execute("SELECT url FROM games WHERE url IS NOT NULL GROUP BY url")
urls = set([x[0] for x in c1.fetchall()])

conn = sqlite3.connect("raw_data.db")

c = conn.cursor()

c.execute("SELECT title, key FROM data WHERE key IS NOT NULL")

rows = [(x[0], x[1]) for x in c.fetchall() if x[1] not in urls]

pattern = re.compile("([0-9]|I|II|III|IV|V|VI|VII|VIII|IX|X|The)")

absolute_blacklist = set([
    "Mega Man 10", "Final Fantasy VII", "Gun Hed", "Sunman" # wp edited
])

blacklist = {
    1: {
        "Aliens": ("Alien3"),
        "Bases Loaded 2": ("Bases Loaded 3"),
        "Adventure Island 4": ("Adventure Island II"),
    },
    3: {
        "Faria": ("Daiva", "Barbie"),
        "Madara": ("Mad Max"),
        "Lone Ranger": ("Moon Ranger"),
    }
}
res = list()
for gid, r_title in titles:
    if r_title in absolute_blacklist:
        continue
    alternatives = []
    if pattern.findall(r_title):
        alternatives = [
            ("10", "X"),
            ("1", ""),
            ("1", "I"),
            ("2", "II"),
            ("3", "III"),
            ("4", "IV"),
            ("5", "V"),
            ("6", "VI"),
            ("7", "VII"),
            ("8", "VIII"),
            ("9", "IX"),
            (" I", ""),
            (" I", " 1"),
            (" II", " 2"),
            (" III", " 3"),
            (" IV", " 4"),
            (" V", " 5"),
            (" VI", " 6"),
            (" VII", " 7"),
            (" VIII", " 8"),
            (" IX", " 9"),
            (" X", " 10"),
            ("^The ", ""),
        ]

    title_res = list()
    for title, key, *rest in rows:
        if alternatives:
            for p, s in alternatives:
                rr_title = re.sub(p, s, r_title)
                if rr_title == r_title:
                    continue
                s0 = Levenshtein.distance(rr_title, title)
                if title in blacklist.get(s0, {}).get(rr_title, []):
                    continue
                title_res.append((title, key, s0))
                #if s0 == 3:
                #    #c1.execute("UPDATE games SET url=? WHERE _id=?", (key, gid))
                #    break

        s0 = Levenshtein.distance(r_title, title)
        if title in blacklist.get(s0, {}).get(r_title, []):
            continue
        title_res.append((title, key, s0))
        #if s0 == 3:
        #    #c1.execute("UPDATE games SET url=? WHERE _id=?", (key, gid))
        #    break
    title_res.sort(key=operator.itemgetter(2))
    res.append(((gid, r_title), title_res[0], title_res[1:10]))

for (gid, r_title), (title, key, distance), alts in res:
    if distance != 6:
        continue
    print("%2d - %s" % (distance, r_title))
    print("   = %s                 (https://en.wikipedia.org%s)" % (title, key))
    print("")
    inp = input()
    if inp == 'y':
        c1.execute("UPDATE games SET url=? WHERE _id=?", (key, gid))

print(len(titles))
conn2.commit()
conn2.close()
conn.close()
