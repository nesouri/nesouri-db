# Nasty hack to suck down List_of_(NES/FC/FDS)_games pages from wikipedia
# and their game links into a database to help the mapping from game to
# wikipedia url.

import sqlite3
from bs4 import BeautifulSoup
import re
from urllib.request import urlopen
import html5lib
import xml.etree.ElementTree as ET
import os
from pprint import pformat

#conn = sqlite3.connect("datamining.db")
#c = conn.cursor()
#c.execute("""
"""
SELECT
  g.title,
  g.date,
  GROUP_CONCAT(a.name)
 FROM games      AS g,
      authorship AS b,
      authors    AS a
       ON b.game = g._id AND a._id = b.author
 GROUP BY g._id
 ORDER BY g.title COLLATE NOCASE
"""
#)

try:
    os.unlink("raw_data.db")
except:
    pass

conn = sqlite3.connect("raw_data.db")

c = conn.cursor()

c.execute("""
CREATE TABLE data (
    _id INTEGER PRIMARY KEY,
    resource TEXT NOT NULL,
    key TEXT,
    title TEXT NOT NULL,
    other_title TEXT,
    eu_rel TEXT,
    us_rel TEXT,
    jp_rel TEXT,
    publisher1 TEXT,
    publisher1_key TEXT,
    publisher2 TEXT,
    publisher2_key TEXT,
    content TEXT
)""")

"""
https://en.wikipedia.org/wiki/List_of_Nintendo_Entertainment_System_games
https://en.wikipedia.org/wiki/List_of_Family_Computer_games
https://en.wikipedia.org/wiki/List_of_Family_Computer_Disk_System_games
"""

def add_column_with_link(link_key, text_key):
    def column_with_link(node, context):
        a = node.find("a")
        if a:
            if "action=edit" not in a.get("href"):
                context[link_key] = a.get("href")
            context[text_key] = a.string
        else:
            context[text_key] = "".join(x for x in node.strings)
    return column_with_link

def add_column_with_link_many(*keys):
    def column_with_link_many(node, context):
        ass = node.find_all("a")
        if ass:
            assert len(keys) >= len(ass), "Not enough link mappers: '%s' vs '%s'" % (str(keys), str(ass))
            for a, (link_key, text_key) in zip(ass, keys):
                if "action=edit" not in a.get("href"):
                    context[link_key] = a.get("href")
                context[text_key] = a.string
        else:
            text_key = keys[0][1]
            context[text_key] = node.string

    return column_with_link_many

def add_column_with_timestamp(timestamp_key):
    def column_with_timestamp(node, context):
        context[timestamp_key] = "".join(x for x in re.findall("(\d{4}-\d{2}-\d{2})", str(node.next_element.next_element.string)))
    return column_with_timestamp

def add_column_ignored():
    def column_ignored(node, context):
        pass
    return column_ignored

def add_column_with_text(text_key):
    def column_with_text(node, context):
        context[text_key] = ",".join(x.strip() for x in node.strings)
    return column_with_text

def fetch_content(url):
    print("Fetching '%s'..." % ("https://en.wikipedia.org" + url))

    with urlopen("https://en.wikipedia.org" + url) as f:
        document = html5lib.parse(f, encoding=f.info().get_content_charset())
        div = document.find('.//*[@id="content"]')
        [document.remove(x) for x in div.findall("script")]
        return ET.tostring(div, encoding="utf8", method="html")

def fetch_and_insert(node, column_funcs):
    for tr in node.parent.find_next_sibling("table").find_all("tr"):
        data = dict()

        tds = tr.find_all("td")
        if len(tds) != len(column_funcs):
            continue

        for td, func in zip(tds, column_funcs):
            func(td, data)

        if len(data.get("title", "")) == 1 and data.get("title") == data.get("publisher1_key"):
            continue

        content = None
        if data.get("game_url"):
            content = fetch_content(data.get("game_url"))
        c.execute("INSERT OR REPLACE INTO data (resource, key, title, other_title, us_rel, eu_rel, jp_rel, publisher1, publisher1_key, publisher2, publisher2_key, content) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  ["wikipedia"] + [data.get(x) for x in
                                   ("game_url", "title", "other_title", "us_rel", "eu_rel", "jp_rel",
                                    "publisher1", "publisher1_key", "publisher2", "publisher2_key")] + [content])

mappers = {
    "nes.html": {
        "Licensed_games": [
            add_column_with_link("game_url", "title"),
            add_column_with_timestamp("us_rel"),
            add_column_with_timestamp("eu_rel"),
            add_column_with_link_many(("publisher1", "publisher1_key"), ("publisher2", "publisher2_key"))
        ],
        "Unreleased_games": [
            add_column_with_link("game_url", "title"),
            add_column_ignored(),
            add_column_with_link_many(("publisher1", "publisher1_key"), ("publisher2", "publisher2_key"))
        ],
        "Unlicensed_games": [
            add_column_with_link("game_url", "title"),
            add_column_with_timestamp("us_rel"),
            add_column_with_link_many(("publisher1", "publisher1_key"), ("publisher2", "publisher2_key"))
        ]
    },
    "fc.html": {
        "List": [
            add_column_with_link("game_url", "title"),
            add_column_with_text("other_title"),
            add_column_with_timestamp("jp_rel"),
            add_column_with_link_many(("publisher1", "publisher1_key"), ("publisher2", "publisher2_key"))
        ]
    },
    "fds.html": {
        "toctitle": [
            add_column_with_link("game_url", "title"),
            add_column_with_timestamp("jp_rel"),
            add_column_with_link_many(("publisher1", "publisher1_key"), ("publisher2", "publisher2_key")),
            add_column_ignored(),
            add_column_ignored(),
        ]
    },
}


for resource, tables in mappers.items():
    with open(resource) as fd:
        soup = BeautifulSoup(fd)
        for table, column_funcs in tables.items():
            node = soup.find(lambda t: t.get("id") == table)
            fetch_and_insert(node, column_funcs)

conn.commit()
