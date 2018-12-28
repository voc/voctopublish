#!/usr/bin/python3
#    Copyright (C) 2017  andi, derpeter
#    andi@muc.ccc.de
#    derpeter@berlin.ccc.de
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from html.parser import HTMLParser
import subprocess
import logging
import requests
import json
import mimetypes
import os

from model.ticket_module import Ticket

logging = logging.getLogger()


class YoutubeAPI:
    """
    This class implements the YouTube API v3
    https://developers.google.com/youtube/v3/docs
    """

    def __init__(self, t: Ticket, client_id: str, secret: str):
        self.t = t
        self.client_id = client_id
        self.secret = secret

        self.lang_map = {'deu': 'German', 'eng': 'English', 'spa': 'Spanish', 'gsw': 'Schweizerdeutsch',
                         'fra': 'French', 'rus': 'Russian', 'fas': 'Farsi', 'chi': 'Chinese'}

        self.translation_strings = {'deu': 'deutsche Übersetzung', 'eng': 'english translation',
                                    'spa': 'La traducción española', 'gsw': 'Schwizerdüütschi Übersetzig',
                                    'fra': 'traduction française', 'rus': 'Russian (русский) translation',
                                    'chi': '中文翻译'}

        self.youtube_urls = []
        self.channelId = None
        self.accessToken = None

    def setup(self, token):
        """
        fetch access token and channel if form youtube
        :param token: youtube token to be used
        """
        self.accessToken = self.get_fresh_token(token, self.client_id, self.secret)
        self.channelId = self.get_channel_id(self.accessToken)

    def publish(self):
        """
        publish a file on youtube
        :return: returns a list containing a youtube url for each released file
        """
        logging.info("publishing Ticket %s (%s) to youtube" % (self.t.fahrplan_id, self.t.title))

        # handle multi language events
        if len(self.t.languages) > 1:
            logging.debug('Languages: ' + str(self.t.languages))
            for lang in self.t.languages:
                out_filename = self.t.fahrplan_id + "-" + self.t.profile_slug + "-audio" + str(lang) + "." + self.t.profile_extension
                out_path = os.path.join(self.t.publishing_path, out_filename)

                logging.info('remuxing ' + self.t.local_filename + ' to ' + out_path)

                try:
                    subprocess.check_output('ffmpeg -y -v warning -nostdin -i ' +
                                            os.path.join(self.t.publishing_path, self.t.local_filename) +
                                            ' -map 0:0 -map 0:a:' + str(lang) + ' -c copy ' + out_path, shell=True)
                except Exception as e_:
                    raise YouTubeException('error remuxing ' + self.t.local_filename + ' to ' + out_path) from e_

                if int(lang) == 0:
                    lang = None
                else:
                    lang = self.t.languages[lang]

                video_id = self.upload(out_path, lang)
                self.youtube_urls.append('https://www.youtube.com/watch?v=' + video_id)
        else:
            video_id = self.upload(os.path.join(self.t.publishing_path, self.t.local_filename), None)

            video_url = 'https://www.youtube.com/watch?v=' + video_id
            logging.info("published Ticket to %s" % video_url)
            self.youtube_urls.append(video_url)

        return self.youtube_urls

    def upload(self, file, lang):
        """
        Call the youtube API and push the file to youtube
        :param file: file to upload
        :param lang: language of the file
        :return:
        """
        # todo split up event creation and upload
        # todo change function name
        # todo add the license properly

        title = self.t.title
        if self.t.subtitle:
            subtitle = self.t.subtitle
        else:
            subtitle = ''
        if self.t.abstract:
            abstract = self.strip_tags(self.t.abstract)
        else:
            abstract = ''

        if self.t.description:
            description = self.strip_tags(self.t.description)
        else:
            description = ''

        if self.t.url:
            if self.t.url.startswith('//'):
                url = 'https:' + self.t.url
            else:
                url = self.t.url
        else:
            url = ''

        description = '\n\n'.join([subtitle, abstract, description, ' '.join(self.t.people), url])
        description = self.strip_tags(description)

        if self.t.voctoweb_enable and self.t.profile_voctoweb_enable:
            if self.t.voctoweb_url:
                description = os.path.join(self.t.voctoweb_url, self.t.slug) + '\n\n' + description

        if self.t.youtube_title_prefix:
            title = self.t.youtube_title_prefix + ' ' + title
            logging.debug('adding ' + str(self.t.youtube_title_prefix) + ' as title prefix')

        # when self.t.youtube_title_prefix_speakers is set, prepend up to x people to title, where x is defined by the integer in self.t.youtube_title_prefix_speakers
        if self.t.youtube_title_prefix_speakers and len(self.t.people) <= int(self.t.youtube_title_prefix_speakers):
            title = (', '.join(self.t.people)) + ': ' + title
            logging.debug('adding speaker names as title prefix: ' + title)

        if self.t.youtube_title_suffix:
            title = title + ' ' + self.t.youtube_title_suffix
            logging.debug('adding ' + str(self.t.youtube_title_suffix) + ' as title suffix')

        if self.t.youtube_privacy:
            privacy = self.t.youtube_privacy
        else:
            privacy = 'private'

        metadata = {
            'snippet':
                {
                    # YouTube does not allow <> in titles – even not as &gt;&lt;
                    'title': title.replace('<', '(').replace('>', ')'),
                    # YouTube does not allow <> in description -> escape them
                    'description': description.replace('<', '&lt').replace('>', '&gt'),
                    'channelId': self.channelId,
                    'tags': self._select_tags(lang)
                },
            'status':
                {
                    'privacyStatus': privacy,
                    'embeddable': True,
                    'publicStatsViewable': True,
                    'license': 'creativeCommon',
                },
        }

        # todo refactor this to make lang more flexible
        if lang:
            if lang in self.translation_strings.keys():
                metadata['snippet']['title'] += ' - ' + self.translation_strings[lang]
            else:
                raise YouTubeException('language not defined in translation strings')

        # limit title length to 100 (YouTube api conformity)
        metadata['snippet']['title'] = metadata['snippet']['title'][:100]

        if self.t.youtube_category:
            metadata['snippet']['categoryId'] = int(self.t.youtube_category)

        (mimetype, encoding) = mimetypes.guess_type(file)
        size = os.stat(file).st_size

        logging.debug('guessed mime type for file %s as %s and its size as %u bytes' % (file, mimetype, size))


        # https://developers.google.com/youtube/v3/docs/videos#resource
        r = requests.post(
            'https://www.googleapis.com/upload/youtube/v3/videos',
            params={
                'uploadType': 'resumable',
                'part': 'snippet,status'
            },
            headers={
                'Authorization': 'Bearer ' + self.accessToken,
                'Content-Type': 'application/json; charset=UTF-8',
                'X-Upload-Content-Type': mimetype,
                'X-Upload-Content-Length': str(size),
            },
            data=json.dumps(metadata)
        )

        if 200 != r.status_code:
            if 400 == r.status_code:
                raise YouTubeException(r.json()['error']['message'] + '\n' + r.text)
            else:
                raise YouTubeException('Video creation failed with error-code %u: %s' % (r.status_code, r.text))

        if 'location' not in r.headers:
            raise YouTubeException('Video creation did not return a location-header to upload to: %s' % (r.headers,))

        logging.info('successfully created video and received upload-url from %s' % (r.headers['server'] if 'server' in r.headers else '-'))
        logging.debug('uploading video-data to %s' % r.headers['location'])

        with open(file, 'rb') as fp:
            r = requests.put(
                r.headers['location'],
                headers={
                    'Authorization': 'Bearer ' + self.accessToken,
                    'Content-Type': mimetype,
                },
                data=fp
            )

            if 200 != r.status_code and 201 != r.status_code:
                raise YouTubeException('uploading video failed with error-code %u: %s' % (r.status_code, r.text))

        video = r.json()

        youtube_url = 'https://www.youtube.com/watch?v=' + video['id']
        logging.info('successfully uploaded video as %s', youtube_url)

        return video['id']

    def _select_tags(self, lang=None):
        """
        Build the tag list
        :param lang: if present the language will be added to the tags
        :return: Returns an array of tag strings
        """
        tags = []

        # if tags are set - copy them into the metadata dict
        if self.t.youtube_tags:
            tags.extend(map(str.strip, self.t.youtube_tags.split(',')))

        if self.t.track:
            tags.append(self.t.track)

        if self.t.day:
            tags.append('Day %s' % self.t.day)

        if self.t.room:
            tags.append(self.t.room)

        if lang:
            if lang in self.lang_map.keys():
                if self.t.languages[0] == lang:
                    tags.append(self.t.acronym + self.lang_map[lang])
                    tags.append(self.t.acronym + ' ov')
                else:
                    tags.append(self.lang_map[lang] + ' (' + self.translation_strings[lang] + ')')
                    tags.append(self.t.acronym + ' ' + lang)
            else:
                raise YouTubeException('language not in lang map')
        else:
            tags.append(self.t.acronym + ' ov')
            tags.append(self.t.acronym + ' ' + self.t.languages[0])

        tags.extend(self.t.people)
        tags.append(self.t.acronym)

        logging.debug('YouTube Tags: ' + str(tags))

        return tags

    def add_to_playlists(self, video_id: str, playlist_ids):
        for p in playlist_ids:
            YoutubeAPI.add_to_playlist(self, video_id, p)

    def add_to_playlist(self, video_id: str, playlist_id: str):
        """
        documentation: https://developers.google.com/youtube/v3/docs/playlistItems/insert
        :param access_token:
        :param video_id:
        :param playlist_id:
        """
        r = requests.post(
            'https://www.googleapis.com/youtube/v3/playlistItems',
            params={
                'part': 'snippet'
            },
            headers={
                'Authorization': 'Bearer ' + self.accessToken,
                'Content-Type': 'application/json; charset=UTF-8',
            },
            data=json.dumps({
                'snippet': {
                    'playlistId': playlist_id,  # required
                    'resourceId': {'kind': 'youtube#video', 'videoId': video_id},  # required
                },
            })
        )

        if 200 != r.status_code:
            raise YouTubeException(
                'Adding video to playlist failed with error-code %u: %s' % (r.status_code, r.text))

        logging.info('video added to playlist: ' + playlist_id)

    @staticmethod
    def update_thumbnail(access_token: str, video_id: str, thumbnail: str):
        """
        https://developers.google.com/youtube/v3/docs/thumbnails/set
        :param access_token:
        :param video_id:
        :param thumbnail:
        """
        fp = open(thumbnail, 'rb')

        r = requests.post(
            'https://www.googleapis.com/upload/youtube/v3/thumbnails/set',
            params={
                'videoId': video_id
            },
            headers={
                'Authorization': 'Bearer ' + access_token,
                'Content-Type': 'image/png',
            },
            data=fp.read()
        )

        if 200 != r.status_code:
            raise YouTubeException('Video update failed with error-code %u: %s' % (r.status_code, r.text))

        logging.info('Thumbnails for ' + str(id) + ' updated')

    @staticmethod
    def get_playlist(access_token: str, playlist_id: str):
        """
        currently a method to help with debugging --Andi, August 2016
        :param access_token:
        :param playlist_id:
        :return:
        """
        r = requests.get(
            'https://www.googleapis.com/youtube/v3/playlistItems',
            params={
                'part': 'snippet',
                'playlistId': playlist_id
            },
            headers={
                'Authorization': 'Bearer ' + access_token,
                'Content-Type': 'application/json; charset=UTF-8',
            },
        )

        if 200 != r.status_code:
            raise YouTubeException('Video add to playlist failed with error-code %u: %s' % (r.status_code, r.text))

        logging.debug(json.dumps(r.json(), indent=4))

    @staticmethod
    def get_fresh_token(refresh_token: str, client_id: str, client_secret: str):
        """
        request a 'fresh' youtube token
        :param refresh_token:
        :param client_id:
        :param client_secret:
        :return: YouTube access token
        """
        logging.debug('fetching fresh Access-Token on behalf of the refreshToken %s' % refresh_token)
        r = requests.post(
            'https://accounts.google.com/o/oauth2/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token'
            }
        )

        if 200 != r.status_code:
            raise YouTubeException('fetching a fresh authToken failed with error-code %u: %s' % (r.status_code, r.text))

        data = r.json()
        if 'access_token' not in data:
            raise YouTubeException('fetching a fresh authToken did not return a access_token: %s' % r.text)

        logging.info("successfully fetched Access-Token %s" % data['access_token'])
        return data['access_token']

    @staticmethod
    def get_channel_id(access_token: str):
        """
        request the channel id associated with the access token
        :param access_token: Youtube access token
        :return: YouTube channel id
        """
        logging.debug('fetching Channel-Info on behalf of the accessToken %s' % access_token)
        r = requests.get(
            'https://www.googleapis.com/youtube/v3/channels',
            headers={
                'Authorization': 'Bearer ' + access_token,
            },
            params={
                'part': 'id,brandingSettings',
                'mine': 'true',
            }
        )

        if 200 != r.status_code:
            raise YouTubeException('fetching channelID failed with error-code %u: %s' % (r.status_code, r.text))

        data = r.json()
        channel = data['items'][0]

        logging.info("successfully fetched Channel-ID %s " % (channel['id']))
        return channel['id']

    @staticmethod
    def strip_tags(html):
        """
        wrapper around MLStripper to clean html input
        :return: stripped input
        """
        s = MLStripper()
        s.feed(html)
        return s.get_data()


class MLStripper(HTMLParser):
    """

    """

    def error(self, message):
        pass

    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ''.join(self.fed)


class YouTubeException(Exception):
    pass
