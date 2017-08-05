#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Kleines Helferskript mit dem man Fuckups bei der Tracker/Youtube Konfiguration beheben kann
# Initital bekonnen im Rahmen der EMF2016, weil ich keine Lust mehr hatte mich mit der alten 
# Youtube API (v2) rumzuschalgen --Andi, August 2016


import logging, requests, json
from api_client import youtube_client
import configparser, argparse

config = configparser.ConfigParser()
config.read('../client.conf')

parser = argparse.ArgumentParser(description='Kleines Helferskript mit dem man Fuckups bei der Tracker/Youtube Konfiguration beheben kann')
parser.add_argument('conference', help='conference slug, e.g. emf16 ')
parser.add_argument('--token', help='youtube token of the channel owning the videos, defaults to from \'cleanup_tool_token\' from client.conf', 
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
           yt.fix_video_description(videoId)

    #print( "%i of %i published files (including webm and audio releases) are on youtube" % (i, len(videos)) )


# Extend YoutubeAPI class from youtube_client.py with a small feature...
class YoutubeAPI (youtube_client.YoutubeAPI):
    
    def fix_video_description(self, videoId):
        r = requests.get(
            'https://www.googleapis.com/youtube/v3/videos',
            params={
                'id': videoId,
                'part': 'snippet',
            },
            headers={
                'Authorization': 'Bearer ' + self.accessToken,
            }
        )
        item = r.json()['items'][0]
        old_description = item['snippet']['description']

        description = old_description.replace('https://media.ccc.de/c/' + args.conference + '/', 'https://media.ccc.de/v/');

        if description == old_description:
            print(' nothing todo')
            return
        
        metadata = {
            'id': videoId, 
            'snippet': {
                'title': item['snippet']['title'], # required
                'categoryId' : item['snippet']['categoryId'], # required
                'description': description,
            },
        }
        r = requests.put(
            'https://www.googleapis.com/youtube/v3/videos',
            params={
                'part': 'snippet'
            },
            headers={
                'Authorization': 'Bearer ' + self.accessToken,
                'Content-Type': 'application/json; charset=UTF-8',
            },
            data=json.dumps(metadata)
        )

        if 200 != r.status_code:
            raise RuntimeError('Video update failed with error-code %u: %s' % (r.status_code, r.text))

        print(' updated');
        return

if __name__ == "__main__":
    main()
