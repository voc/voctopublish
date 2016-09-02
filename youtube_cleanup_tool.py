#!/usr/bin/python3
#
# Kleines Helferskript mit dem man Fuckups bei der Tracker/Youtube Konfiguration beheben kann
# mit zusätzlicher Playlist-Füll-Funktion auf Basis der Youtube-URLs die im Tracker stehen.
# Initital bekonnen im Rahmen der EMF2016, weil ich keine Lust mehr hatte mich mit der alten 
# Youtube API (v2) rumzuschalgen --Andi, August 2016


import logging, requests, json
import youtube_client
import configparser

logger = logging.getLogger()

def main():    
    config = configparser.ConfigParser()
    config.read('client.conf')
    
    ticket = {}
    ticket['Publishing.YouTube.Token'] = config['youtube']['cleanup_tool_token']
    
    #conference_slug = 'emf16'  # see tracker project
    #targetPlaylist  = 'PL_IxoDz1Nq2auQyvwcmhMhCPrCKC_Jatj'
    
    conference_slug = 'froscon16'  # see tracker project
    targetPlaylist  = 'PL_IxoDz1Nq2aMepxIuDN7Ek8lcjc32B1D'

    
    yt = YoutubeAPI(ticket, config) 

    r = requests.get('https://tracker.c3voc.de/api/v1/' + conference_slug + '/tickets/released.json')
    videos = r.json()

    i = 0
    for video_file in videos:
        if video_file['youtube_url']:
           i = i+1
           print(video_file['youtube_url'])
           videoId = video_file['youtube_url'].split('=', 2)[1]
           #yt.fix_video_description(videoId)
           yt.add_to_playlist(videoId, targetPlaylist)
           #break

    print( "%i of %i published files (including webm and audio releases) are on youtube" % (i, len(videos)) )


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
        
        old_description = item['snippet']['description']

        description = old_description.replace('https://media.ccc.de/c/emf16/emf2016', 'https://media.ccc.de/v/emf2016');

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
