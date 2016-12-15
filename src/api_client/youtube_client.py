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
import re

from ticket_module import Ticket

logging = logging.getLogger()


class YoutubeAPI:
    def __init__(self, ticket: Ticket, config):
        self.channelId = None
        if 'Publishing.YouTube.Token' not in ticket:
            raise YouTubeException(
                'Property "Publishing.YouTube.Token" missing in ticket - did you set the YouTube-Properties on the Project?')

        self.accessToken = self.get_fresh_token(ticket.youtube_token, config['client_id'], config['secret'])
        self.channelId = self.get_channel_id(self.accessToken)

    def publish(self):
        """
        publish a file on youtube
        :return:
        """
        logging.info("publishing_test Ticket %s (%s) to youtube" % (self.ticket.fahrplan_id, self.ticket.title))
        infile = os.path.join(self.ticket.publishing_path,
                              str(self.ticket.fahrplan_id) + "-" + self.ticket.profile_slug + "." + self.ticket.profile_extension)

        # replace this with dynamic code that can handle multilang
        # # if a second language is configured, remux the video to only have the one audio track and upload it twice
        # multi_lang = re.match('(..)-(..)', ticket['Record.Language'])
        # if multi_lang:
        #     logging.debug('remuxing dual-language video into two parts')
        #
        #     outfile1 = os.path.join(ticket['Publishing.Path'],
        #                             + str(ticket['Fahrplan.ID']) + "-" + ticket['EncodingProfile.Slug'] + "-audio1." +
        #                             ticket['EncodingProfile.Extension'])
        #     outfile2 = os.path.join(ticket['Publishing.Path'] + str(ticket['Fahrplan.ID']) + "-" + ticket[
        #         'EncodingProfile.Slug'] + "-audio2." + ticket['EncodingProfile.Extension'])
        #     youtubeUrls = []
        #
        #     logging.debug('remuxing with original audio to ' + outfile1)
        #     ticket['Publishing.Infile'] = outfile1
        #
        #     if subprocess.call(
        #             ['ffmpeg', '-y', '-v', 'warning', '-nostdin', '-i', infile, '-map', '0:0', '-map', '0:1', '-c',
        #              'copy', outfile1]) != 0:
        #         raise YouTubeException('error remuxing ' + infile + ' to ' + outfile1)
        #
        #     videoId = uploadVideo(ticket)
        #     youtubeUrls.append('https://www.youtube.com/watch?v=' + videoId)
        #
        #     logging.debug('remuxing with translated audio to ' + outfile2)
        #     ticket['Publishing.Infile'] = outfile2
        #     ticket['Publishing.InfileIsTranslated'] = multi_lang.group(2)
        #     if subprocess.call(
        #             ['ffmpeg', '-y', '-v', 'warning', '-nostdin', '-i', infile, '-map', '0:0', '-map', '0:2', '-c',
        #              'copy', outfile2]) != 0:
        #         raise YouTubeException('error remuxing ' + infile + ' to ' + outfile2)
        #
        #     videoId = uploadVideo(ticket)
        #     youtubeUrls.append('https://www.youtube.com/watch?v=' + videoId)
        #
        #     logging.info("deleting remuxed versions: %s and %s" % (outfile1, outfile2))
        #     os.remove(outfile1)
        #     os.remove(outfile2)
        #
        #     return youtubeUrls
        #
        # else:
        #     ticket['Publishing.Infile'] = infile
        #     videoId = self.upload(ticket)
        #
        #     videoUrl = 'https://www.youtube.com/watch?v=' + videoId
        #     logging.info("successfully published Ticket to %s" % videoUrl)
        #     return [videoUrl, ]

    def upload(self):
        """
        Call the youtube API and push the file to youtube
        :param ticket:
        :return:
        """
        title = self.ticket.title
        subtitle = self.ticket.subtitle
        abstract = strip_tags(self.ticket.abstract)
        description = strip_tags(self.ticket.description)
        person_list = self.ticket.persons

        description = '\n\n'.join([abstract, description, person_list])
        if self.ticket.media_enable and self.ticket.profile_media_enable:
            if self.ticket.media_url:
                description = os.path.join(self.ticket.media_url, self.ticket.slug) + '\n\n' + description

        # if persons-list is set
        if 'Fahrplan.Person_list' in ticket:
            persons = ticket['Fahrplan.Person_list'].split(',')

            # prepend usernames if only 1 or 2 speaker
            if len(persons) < 3:
                title = str(ticket['Fahrplan.Person_list']) + ': ' + title

        if 'Publishing.YouTube.TitlePrefix' in ticket:
            title = str(ticket['Publishing.YouTube.TitlePrefix']) + ' ' + title
            logging.debug('adding ' + str(ticket['Publishing.YouTube.TitlePrefix']) + ' as title prefix')
        else:
            logging.warn("No youtube title prefix found")

        if 'Publishing.YouTube.TitleSuffix' in ticket:
            title = title + ' ' + str(ticket['Publishing.YouTube.TitleSuffix'])

        metadata = {
            'snippet':
                {
                    'title': title,
                    'description': description,
                    'channelId': self.channelId,
                    'tags': self.select_tags(ticket)
                },
            'status':
                {
                    'privacyStatus': ticket.get('Publishing.YouTube.Privacy', 'private'),
                    'embeddable': True,
                    'publicStatsViewable': True,
                    'license': 'creativeCommon',  # TODO
                },
        }

        # if tags are set - copy them into the metadata dict
        if 'Publishing.YouTube.Tags' in ticket:
            metadata['snippet']['tags'] = list(map(str.strip, ticket['Publishing.YouTube.Tags'].split(',')))

        translation = ticket.get('Publishing.InfileIsTranslated')
        if translation == 'de':
            metadata['snippet']['title'] += ' (deutsche Übersetzung)'

        elif translation == 'en':
            metadata['snippet']['title'] += ' (english translation)'

        # recure limit title length to 100 (youtube api conformity)
        metadata['snippet']['title'] = metadata['snippet']['title'].replace('<', '(').replace('>', ')')
        metadata['snippet']['title'] = metadata['snippet']['title'][:100]

        # 1 => Film & Animation
        # 2 => Autos & Vehicles
        # 10 => Music
        # 15 => Pets & Animals
        # 17 => Sports
        # 18 => Short Movies
        # 19 => Travel & Events
        # 20 => Gaming
        # 21 => Videoblogging
        # 22 => People & Blogs
        # 23 => Comedy
        # 24 => Entertainment
        # 25 => News & Politics
        # 26 => Howto & Style
        # 27 => Education
        # 28 => Science & Technology
        # 30 => Movies
        # 31 => Anime/Animation
        # 32 => Action/Adventure
        # 33 => Classics
        # 34 => Comedy
        # 35 => Documentary
        # 36 => Drama
        # 37 => Family
        # 38 => Foreign
        # 39 => Horror
        # 40 => Sci-Fi/Fantasy
        # 41 => Thriller
        # 42 => Shorts
        # 43 => Shows
        # 44 => Trailers
        if 'Publishing.YouTube.Category' in ticket:
            metadata['snippet']['categoryId'] = int(ticket['Publishing.YouTube.Category'])

        (mimetype, encoding) = mimetypes.guess_type(ticket['Publishing.Infile'])
        size = os.stat(ticket['Publishing.Infile']).st_size

        logging.debug('guessed mimetype for file %s as %s and its size as %u bytes' % (
            ticket['Publishing.Infile'], mimetype, size))

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
        with open(ticket['Publishing.Infile'], 'rb') as fp:
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

    def add_to_playlist(self, video_id, playlist_id):
        """
        documentation: https://developers.google.com/youtube/v3/docs/playlistItems/insert
        :param video_id:
        :param playlist_id:
        :return:
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
            raise YouTubeException('Video add to playlist failed with error-code %u: %s' % (r.status_code, r.text))

        print(' added')

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

        print(json.dumps(r.json(), indent=4))

    def get_fresh_token(self, refresh_token, client_id, client_secret):
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

    def get_channel_id(self, access_token):
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

        # logging.info("successfully fetched Channel-ID %s with name %s" % (channel['id'], channel['brandingSettings']['channel']['title']))
        logging.info("successfully fetched Channel-ID %s " % (channel['id']))
        return channel['id']

    def select_tags(self, ticket):
        """
        Build the tag list
        :param ticket:
        :return:
        """
        tags = []

        if ticket.track:
            tags.append(ticket.track)

        if ticket.day:
            tags.append('Day %s' % ticket.day)

        if ticket.room:
            tags.append(ticket.room)

        # replace this with dynamic code
        # # append language-specific tag
        # language = ticket.get('Record.Language')
        # if language == 'de':
        #     tags.append('German')
        # elif language == 'en':
        #     tags.append('English')
        #
        # elif language == 'de-en':
        #     if 'Publishing.InfileIsTranslated' in ticket:
        #         tags.append('German (english translation)')
        #     else:
        #         tags.append('German')
        #
        # elif language == 'en-de':
        #     if 'Publishing.InfileIsTranslated' in ticket:
        #         ## TODO
        #         tags.append('English (deutsche Übersetzung)')
        #     else:
        #         tags.append('English')

        # append person-names to tags
        tags.extend(ticket.persons)

        return tags

    def update_thumbnail(self, video_id, thumbnail):
        """
        https://developers.google.com/youtube/v3/docs/thumbnails/set
        :param video_id:
        :param thumbnail:
        :return:
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

        print(' updated')
        return


class MLStripper(HTMLParser):
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


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()


class YouTubeException(Exception):
    pass
