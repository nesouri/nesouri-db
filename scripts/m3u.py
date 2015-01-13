# the horrors.. should probably have been a real m3u parser.. but most of the work was spent
# on filtering out bad data, and cleaning up semi-correct data, and some files were corrupt.
import re
import os
import sqlite3

m3u_ptrn = re.compile("(\d{3}(\d|[?]))?(.+)?")
def parse_m3u(c, game_id, filename):
    base, ext = os.path.splitext(filename)
    playlist = base + ".m3u"
    if not os.path.exists(playlist):
        return
    authors_line = ""
    authors = []
    game = "Sangokushi 2: Haou no Tairiku"
    year = None
    holder = None
    track = None
    title = None
    first = True
    header = True
    alt = False
    with open(playlist, encoding='utf8') as fd:
        for line in fd:
            if not line.strip():
                continue
            if line.startswith("###############"):
                alt = True
            elif line.strip() == "#":
                continue
            elif line.startswith("#"):
                if first:
                    if alt:
                        if not line.startswith("# Game:"):
                            print("noes!")
                            print(line)
                        game = line[8:].strip()
                    else:
                        game = line[2:].strip()
                    first = False
                    #print("Game:", game)
                else:
                    if "Music by" in line or "Artist:" in line:
                        contrib = line.replace("# Music by", "").replace("# Artist: ", "").strip()
                        authors_line = contrib
                        if "Unknown" not in line and "???" not in line and "< ? >" not in line:
                            contrib = re.sub("(\w)\.(\w)", "\\1 \\2", contrib)
                            contrib = re.sub("(\w)_(\w)", "\\1 \\2", contrib)
                            contrib = re.sub(",and ", ",", contrib)
                            contrib = re.sub(" and ", ",", contrib)
                            contrib = re.sub(" and/or ", ",", contrib)
                            contrib = re.sub(" & ", ",", contrib)
                            for a in contrib.split(","):
                                a = a.strip()
                                if a[0] == '"':
                                    a = a[1:]
                                if a[-1] == '"':
                                    a = a[:-1]
                                authors.append(a)
                            #print("Authors:", authors)
                    if line.startswith("# Copyright"):
                        copyright = line.replace("# Copyright", "").replace(":", "")
                        copyright = re.sub("\([cC]\) ?", "", copyright)
                        copyright = copyright.strip()
                        res = m3u_ptrn.findall(copyright)[0]
                        year = res[0].strip()
                        if not year:
                            year = re.findall("\d{4}", copyright)
                            if not year:
                                year = "    "
                            else:
                                year = year[0].strip()
                        holder = res[-1].strip()
                        #print("Year: %4s Copyright: %-30s %s" % (year, holder, playlist))
            else:
                line = line.replace("''", "\"")
                if playlist.startswith("Sangokushi 2"):
                    line = line.replace(" - ©1992 Namco", "")
                elif playlist.startswith("Over Horizon"):
                    line = line.replace(" - ©1991 Pixel\, Hot-B", "")
                line = line.replace("\\", "").replace(authors_line, "")
                file, rest = line.split("::")
                rest = rest.strip()
                if rest[-1] == ",":
                    if rest[-2] != "," or game == "Karnov":
                        rest = rest[:-1]
                if rest[-1] == "-":
                    rest += ","
                c1 = rest.find(",")
                c2 = rest.find(",", c1+1)
                c5 = rest.rfind(",")
                c4 = rest.rfind(",", 0, c5)
                c3 = rest.rfind(",", 0, c4)
                track = int(rest[c1+1:c2].strip())
                e = rest[c2+1:c3]
                et = e
                e = e.replace(game + " -", "").strip()
                #if e != et:
                #    print(et)
                #    print(e)
                if not e:
                    e = game
                if e.startswith("- "):
                    e = e[2:].strip()
                if e.startswith("- "):
                    e = e[2:].strip()
                if e.strip().endswith(" -"):
                    e = e[:-2].strip()
                for a in authors:
                    e = e.replace(a, "").strip()
                    if not e:
                        print("")
                    if e[0] == ",":
                        e = e[1:].strip()
                    if e == "-" or e == "":
                        break
                e = e.strip()
                if e.startswith("- "):
                    e = e[2:].strip()
                if e.startswith("- "):
                    e = e[2:].strip()
                if e.strip().endswith(" -"):
                    e = e[:-2].strip()
                if e.startswith(", "):
                    e = e[2:]
                if e.startswith("a - "):
                    e = e[4:]
                title = e
                m = re.match("Unknown[.]*(( \d+)|( Track))?", title)
                if title == ("(Track " + str(track) + ")") or title == "Track" or (m and m.group() == title) or (title == ("Track " + str(track))) or (title == "-") or (title == "Unknown (Track %d)" % track) or (title == "Unknown [Track %d]" % track) or (title == "Unknown [track %d]" % track):
                    print("DITCHING", title)
                    continue
                print("[%2s]" % track, title)
                try:
                    c.execute("INSERT INTO tracks (game_id, track, title) VALUES (?, ?, ?)", (game_id, track, title))
                except:
                    print(game_id, track, title) # some m3u's have dupes o_O


def query():
    conn = sqlite3.connect("metadata.db")
    c = conn.cursor()
    c.execute("DELETE FROM tracks")
    g = list(c.execute("SELECT _id, file FROM games"))
    for game_id, filename in g:
        m3u = os.path.basename(filename).replace("7z", "m3u")
        if os.path.exists(m3u):
            parse_m3u(c, game_id, m3u)
    conn.commit()

if __name__ == "__main__":
    #t = "Kirby's Adventure [Hoshi no Kirby - Yume no Izumi no Monogatari] (1993-03-23)(HAL Laboratory)(Nintendo).m3u"
    #t = "Adventures of Bayou Billy, The [Mad City] (1988-08-12)(Konami).m3u"
    #t = "Commando [Senjou no Ookami] (1986-09-27)(Capcom).m3u"
    #t = "Sangokushi 2 - Haou no Tairiku (1992-06-10)(-)(Namco).m3u"
    #t = "Gradius (1986-04-25)(Konami).m3u"
    #t = "Isolated Warrior [Max Warrior - Wakusei Kaigenrei] (1991-02-15)(KID)(VAP).m3u"
    #t = "Little Mermaid, The [Little Mermaid - Ningyo Hime] (1991-07-19)(Capcom).m3u"
    #t = "Choujin Sentai - Jetman (1991-12-21)(Natsume)(Angel).m3u"
    #t = "Mega Man 2 [RockMan 2 - Dr. Wily no Nazo] (1988-12-24)(Capcom).m3u"
    #t = "Dr. Mario (1990-07-27)(Nintendo R&D1)(Nintendo).m3u"
    #parse_m3u(None, t)
    #raise SystemExit
    #for p in (x for x in os.listdir(".") if x.endswith(".m3u")):
    #    parse_m3u(None, p)

    query()
