#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Kleines Helferskript zum Playlisten füllen auf Basis der Youtube-URLs die im Tracker stehen.
# Initital bekonnen im Rahmen der EMF2016, weil ich keine Lust mehr hatte mich mit der alten 
# Youtube API (v2) rumzuschalgen --Andi, August 2016


import logging, requests, json
from api_client.youtube_client import YoutubeAPI
import configparser, argparse

config = configparser.ConfigParser()
config.read('../client.conf')

parser = argparse.ArgumentParser(description='add all youtube videos of $conference to $playlist (lookup at public tracker API) ')
parser.add_argument('conference', help='conference slug, e.g. emf16 ')
parser.add_argument('playlist', help='target playlist to add the video to, e.g. PL_IxoDz1Nq2auQyvwcmhMhCPrCKC_Jatj')
parser.add_argument('--token', help='youtube token of the playlist owning channel, defaults to from \'cleanup_tool_token\' from client.conf', 
                               default = config['youtube']['cleanup_tool_token'] )
args = parser.parse_args()

logger = logging.getLogger()

def main():
    yt = YoutubeAPI(config)
    yt.setup(args.token)

    r = requests.get('https://tracker.c3voc.de/api/v1/' + args.conference + '/tickets/released.json')
    videos = r.json()

    i = 0
    for video_file in videos:
        if video_file['youtube_url']:
           i = i+1
           print(video_file['youtube_url'])
           videoId = video_file['youtube_url'].split('=', 2)[1]
           yt.add_to_playlist(videoId, args.playlist)

    print( "%i of %i published files (including webm and audio releases) are on youtube" % (i, len(videos)) )

if __name__ == "__main__":
    main()
