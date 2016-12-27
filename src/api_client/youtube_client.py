#!/usr/bin/python3
#    Copyright (C) 2016  derpeter, andi
#    <add andis mail here>
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

    def __init__(self, ticket: Ticket, config):
        self.channelId = None
        self.accessToken = self._get_fresh_token(ticket.youtube_token, config['youtube']['client_id'],
                                                 config['youtube']['secret'])
        self.channelId = self._get_channel_id(self.accessToken)
        self.ticket = ticket
        self.config = config
        self.youtube_urls = []
        self.lang_map = {'deu': 'German', 'eng': 'English', 'spa': 'Spanish', 'gsw': 'Schweizerdeutsch',
                         'fra': 'French'}
        self.translation_strings = {'deu': 'deutsche Übersetzung', 'eng': 'english translation',
                                    'spa': 'La traducción española', 'gsw': '  Schwizerdüütschi Übersetzig',
                                    'fra': 'traduction française'}

    def publish(self):
        """
        publish a file on youtube
        :return: returns a list containing a youtube url for each released file
        """
        logging.info("publishing Ticket %s (%s) to youtube" % (self.ticket.fahrplan_id, self.ticket.title))

        # handle multi language events
        # todo merge publishing for voctoweb and youtube
        if len(self.ticket.languages) > 1:
            logging.debug('Languages: ' + str(self.ticket.languages))
            for key in self.ticket.languages:
                out_filename = self.ticket.fahrplan_id + "-" + self.ticket.profile_slug + "-audio" + str(
                    key) + "." + self.ticket.profile_extension
                out_path = os.path.join(self.ticket.publishing_path, out_filename)

                logging.info('remuxing ' + self.ticket.local_filename + ' to ' + out_path)

                # todo check if the file is already there from the voctoweb release
                try:
                    subprocess.call(['ffmpeg', '-y', '-v', 'warning', '-nostdin', '-i',
                                     os.path.join(self.ticket.publishing_path, self.ticket.local_filename), '-map',
                                     '0:0',
                                     '-map',
                                     '0:a:' + str(key), '-c', 'copy', '-movflags', 'faststart', out_path])
                except Exception as e_:
                    raise YouTubeException('error remuxing ' + self.ticket.local_filename + ' to ' + out_path) from e_

                if int(key) == 0:
                    lang = None
                else:
                    lang = self.ticket.languages[key]

                video_id = self.upload(out_path, lang)
                self.youtube_urls.append('https://www.youtube.com/watch?v=' + video_id)

        else:
            video_id = self.upload(os.path.join(self.ticket.publishing_path, self.ticket.local_filename),
                                   self.ticket.language)

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
        title = self.ticket.title
        if self.ticket.subtitle:
            subtitle = self.ticket.subtitle
        else:
            subtitle = ''
        if self.ticket.abstract:
            abstract = self.strip_tags(self.ticket.abstract)
        else:
            abstract = ''
        if self.ticket.description:
            description = self.strip_tags(self.ticket.description)
        else:
            description = ''

        description = '\n\n'.join([subtitle, abstract, description, str(self.ticket.people)])

        if self.ticket.media_enable and self.ticket.profile_media_enable:
            if self.ticket.media_url:
                description = os.path.join(self.ticket.media_url, self.ticket.slug) + '\n\n' + description

        if self.ticket.people:
            # prepend user names if only 1 or 2 speaker
            if len(self.ticket.people) < 3:
                title = str(self.ticket.people) + ': ' + title

        if self.ticket.youtube_title_prefix:
            title = self.ticket.youtube_title_prefix + ' ' + title
            logging.debug('adding ' + str(self.ticket.youtube_title_prefix) + ' as title prefix')
        else:
            logging.warning('No youtube title prefix found')

        if self.ticket.youtube_title_suffix:
            title = title + ' ' + self.ticket.youtube_title_suffix
            logging.debug('adding ' + str(self.ticket.youtube_title_suffix) + ' as title suffix')
        else:
            logging.warning('No YouTube title suffix found')

        if self.ticket.youtube_privacy:
            privacy = self.ticket.youtube_privacy
        else:
            privacy = 'private'

        metadata = {
            'snippet':
                {
                    'title': title,
                    'description': description,
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

        # if tags are set - copy them into the metadata dict
        if self.ticket.youtube_tags:
            metadata['snippet']['tags'] = list(map(str.strip, self.ticket.youtube_tags.split(',')))

        if lang:
            if lang in self.translation_strings.keys():
                metadata['snippet']['title'] += ' - ' + self.translation_strings[lang]
            else:
                raise YouTubeException('language not defined in translation strings')

        # limit title length to 100 (youtube api conformity)
        metadata['snippet']['title'] = metadata['snippet']['title'].replace('<', '(').replace('>', ')')
        metadata['snippet']['title'] = metadata['snippet']['title'][:100]

        if self.ticket.youtube_category:
            metadata['snippet']['categoryId'] = int(self.ticket.youtube_category)

        (mimetype, encoding) = mimetypes.guess_type(file)
        size = os.stat(file).st_size

        logging.debug('guessed mime type for file %s as %s and its size as %u bytes' % (file, mimetype, size))

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
                'X-Upload-Content-Length': size,
            },
            data=json.dumps(metadata)
        )

        if 200 != r.status_code:
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

    def _add_to_playlist(self, video_id, playlist_id):
        """
        documentation: https://developers.google.com/youtube/v3/docs/playlistItems/insert
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
                'Adding video add to playlist failed with error-code %u: %s' % (r.status_code, r.text))

        logging.info('video added to playlist: ' + playlist_id)

    # todo do something with this or remove it
    def get_playlist(self, playlist_id):
        """
        currently a method to help with debugging --Andi, August 2016
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
                'Authorization': 'Bearer ' + self.accessToken,
                'Content-Type': 'application/json; charset=UTF-8',
            },
        )

        if 200 != r.status_code:
            raise YouTubeException('Video add to playlist failed with error-code %u: %s' % (r.status_code, r.text))

        logging.debug(json.dumps(r.json(), indent=4))

    @staticmethod
    def _get_fresh_token(refresh_token, client_id, client_secret):
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
    def _get_channel_id(access_token):
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

    def _select_tags(self, lang=None):
        """
        Build the tag list
        :param lang: if present the language will be added to the tags
        :return: Returns an array of tag strings
        """
        tags = []

        if self.ticket.track:
            tags.append(self.ticket.track)

        if self.ticket.day:
            tags.append('Day %s' % self.ticket.day)

        if self.ticket.room:
            tags.append(self.ticket.room)

        if lang:
            if lang in self.lang_map.keys():
                if self.ticket.languages[0] == lang:
                    tags.append(self.lang_map[lang])
                else:
                    tags.append(self.lang_map[lang] + ' (' + self.translation_strings[lang] + ')')
            else:
                raise YouTubeException('language not in lang map')

        tags.extend(self.ticket.people)
        logging.debug('YouTube Tags: ' + str(tags))

        return tags

    def update_thumbnail(self, video_id, thumbnail):
        """
        https://developers.google.com/youtube/v3/docs/thumbnails/set
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
                'Authorization': 'Bearer ' + self.accessToken,
                'Content-Type': 'image/png',
            },
            data=fp.read()
        )

        if 200 != r.status_code:
            raise YouTubeException('Video update failed with error-code %u: %s' % (r.status_code, r.text))

        logging.info('Thumbnails for ' + str(id) + ' updated')

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
