import sqlite3
import os
import operator
import sys
import csv

if len(sys.argv) == 1:
	conn = sqlite3.connect("metadata.db")
	c = conn.cursor()
	for _id, file, title in c.execute("SELECT _id, file, title FROM games WHERE url IS NULL ORDER BY file LIMIT 30"):
		print('%d,"%s","%s",""' % (_id, file, title))
if len(sys.argv) == 2 and os.path.isfile(sys.argv[1]):
	conn = sqlite3.connect("metadata.db")
	c = conn.cursor()
	with open(sys.argv[1], encoding="utf-8") as fd:
		for _id, filename, title, url in csv.reader(fd):
			c.execute("UPDATE games SET title=?, url=? WHERE _id=?", (title, url, _id))
	print("".join(x for x in c.execute("SELECT COUNT(*) FROM games WHERE url IS NULL")))
	conn.commit()



