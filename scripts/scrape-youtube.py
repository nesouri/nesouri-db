#!/usr/bin/python
# First do:
# pip3.4 install -t deps google-api-python-client, then PYTHONPATH=deps ..

import httplib2
import os
import sys
import json

from apiclient.discovery import build
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow

from pprint import pformat

def authenticate():
  flow = flow_from_clientsecrets("client_secrets.json",
                                 message="missing client_secrets.json",
                                 scope="https://www.googleapis.com/auth/youtube.readonly")

  storage = Storage("%s-oauth2.json" % sys.argv[0])
  credentials = storage.get()

  if credentials is None or credentials.invalid:
    flags = argparser.parse_args()
    credentials = run_flow(flow, storage, flags)

  return credentials

def youtube_service(credentials):
  return build("youtube", "v3", http=credentials.authorize(httplib2.Http()))

def uploads_by_user(youtube, user):
  channels_response = youtube.channels().list(forUsername=user, part="contentDetails").execute()

  result = []

  for channel in channels_response["items"]:
    uploads_list_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    playlistitems_list_request = youtube.playlistItems().list(playlistId=uploads_list_id, part="snippet", maxResults=50)

    while playlistitems_list_request:
      playlistitems_list_response = playlistitems_list_request.execute()
      for playlist_item in playlistitems_list_response["items"]:
        result.append(playlist_item["snippet"])
        playlistitems_list_request = youtube.playlistItems().list_next(playlistitems_list_request, playlistitems_list_response)

  return result

auth = authenticate()
yt = youtube_service(auth)

data = []
#for user in ("sargakazi", "Wiiguy309", "grad1u52", "cubex55"):
for user in ("sargakazi", "Wiiguy309"):
  data += uploads_by_user(yt, user)

with open("youtube-metadata.json", "w") as fd:
  fd.write(json.dumps(data))
