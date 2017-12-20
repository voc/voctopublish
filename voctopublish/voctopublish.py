#!/usr/bin/python3
#    Copyright (C) 2017  derpeter
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

import configparser
import socket
import sys
import logging
import os
import subprocess

from api_client.c3tt_rpc_client import C3TTClient
from api_client.voctoweb_client import VoctowebClient
from api_client.youtube_client import YoutubeAPI
import api_client.twitter_client as twitter
from model.ticket_module import Ticket


class Publisher:
    """
    This is the main class for the Voctopublish application
    It is meant to be used with the c3tt ticket tracker
    """
    def __init__(self):
        # load config
        if not os.path.exists('client.conf'):
            raise IOError("Error: config file not found")

        self.config = configparser.ConfigParser()
        self.config.read('client.conf')

        # set up logging
        logging.addLevelName(logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
        logging.addLevelName(logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
        logging.addLevelName(logging.INFO, "\033[1;32m%s\033[1;0m" % logging.getLevelName(logging.INFO))
        logging.addLevelName(logging.DEBUG, "\033[1;85m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))

        self.logger = logging.getLogger()

        sh = logging.StreamHandler(sys.stdout)
        if self.config['general']['debug']:
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s {%(filename)s:%(lineno)d} %(message)s')
        else:
            formatter = logging.Formatter('%(asctime)s - %(message)s')

        sh.setFormatter(formatter)
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)

        level = self.config['general']['debug']
        if level == 'info':
            self.logger.setLevel(logging.INFO)
        elif level == 'warning':
            self.logger.setLevel(logging.WARNING)
        elif level == 'error':
            self.logger.setLevel(logging.ERROR)
        elif level == 'debug':
            self.logger.setLevel(logging.DEBUG)

        if self.config['C3Tracker']['host'] == "None":
            self.host = socket.getfqdn()
        else:
            self.host = self.config['C3Tracker']['host']

        self.ticket_type = self.config['C3Tracker']['ticket_type']
        self.to_state = self.config['C3Tracker']['to_state']

        # instance variables we need later
        self.ticket = None

        logging.debug('creating C3TTClient')
        try:
            self.c3tt = C3TTClient(self.config['C3Tracker']['url'],
                                   self.config['C3Tracker']['group'],
                                   self.host,
                                   self.config['C3Tracker']['secret'])
        except Exception as e_:
            raise PublisherException('Config parameter missing or empty, please check config') from e_

    def publish(self):
        """
        Decide based on the information provided by the tracker where to publish.
        """
        self.ticket = self._get_ticket_from_tracker()

        if not self.ticket:
            return

        # check source file and filesystem permissions
        if not os.path.isfile(os.path.join(self.ticket.publishing_path, self.ticket.local_filename)):
            raise IOError('Source file does not exist ' + os.path.join(self.ticket.publishing_path, self.ticket.local_filename))
        if not os.path.exists(os.path.join(self.ticket.publishing_path)):
            raise IOError('Output path does not exist ' + os.path.join(self.ticket.publishing_path))
        if os.path.getsize(os.path.join(self.ticket.publishing_path, self.ticket.local_filename)) == 0:
            raise PublisherException("Input file size is 0 " + os.path.join(self.ticket.publishing_path))
        else:
            if not os.access(self.ticket.publishing_path, os.W_OK):
                raise IOError("Output path is not writable (%s)" % self.ticket.publishing_path)

        # voctoweb
        if self.ticket.profile_media_enable == 'yes' and self.ticket.media_enable == 'yes':
            logging.debug(
                'encoding profile media flag: ' + self.ticket.profile_media_enable + " project media flag: " + self.ticket.media_enable)
            self._publish_to_voctoweb()

        # YouTube
        if self.ticket.profile_youtube_enable == 'yes' and self.ticket.youtube_enable == 'yes':
            if self.ticket.has_youtube_url:
                raise PublisherException('YoutTube URLs already exist in ticket, wont publish to youtube')
            else:
                logging.debug(
                    "encoding profile youtube flag: " + self.ticket.profile_youtube_enable + ' project youtube flag: ' + self.ticket.youtube_enable)
                self._publish_to_youtube()

        self.c3tt.set_ticket_done()

        # Twitter
        if self.ticket.twitter_enable == 'yes' and self.ticket.master:
            twitter.send_tweet(self.ticket, self.config['twitter'])

    def _get_ticket_from_tracker(self):
        """
        Request the next unassigned ticket for the configured states
        :return: a ticket object or None in case no ticket is available
        """
        logging.info('requesting ticket from tracker')
        t = None
        ticket_id = self.c3tt.assign_next_unassigned_for_state(self.ticket_type, self.to_state)
        if ticket_id:
            logging.info("Ticket ID:" + str(ticket_id))
            try:
                tracker_ticket = self.c3tt.get_ticket_properties()
                logging.debug("Ticket: " + str(tracker_ticket))
            except Exception as e_:
                self.c3tt.set_ticket_failed(e_)
                raise e_
            t = Ticket(tracker_ticket, ticket_id)
        else:
            logging.info('No ticket of type ' + self.ticket_type + ' for state ' + self.to_state)

        return t

    def _publish_to_voctoweb(self):
        """
        Create a event on an voctomix instance. This includes creating a recording for each media file.
        """
        logging.info("publishing to voctoweb")
        try:
            vw = VoctowebClient(self.ticket,
                                self.config['voctoweb']['api_key'],
                                self.config['voctoweb']['api_url'])
        except Exception as e_:
            raise PublisherException('Error initializing voctoweb client. Config parameter missing') from e_

        if self.ticket.master:
            # if this is master ticket we need to check if we need to create an event on voctoweb
            logging.debug('this is a master ticket')
            if self.ticket.voctoweb_event_id or self.ticket.recording_id:
                logging.debug('ticket has a voctoweb_event_id or recording_id')
                # ticket has an recording id or voctoweb event id. We assume the event exists on media
                # todo ask media api if event exists
            else:
                # ticket has no recording id therefore we create the event on voctoweb
                r = vw.create_event()
                if r.status_code in [200, 201]:
                    logging.info("new event created")
                    # generate the thumbnails for video releases (will not overwrite existing thumbs)
                    if self.ticket.mime_type.startswith('video'):
                        # if not os.path.isfile(self.ticket.publishing_path + self.ticket.local_filename_base + ".jpg"):
                        vw.generate_thumbs()
                        vw.upload_thumbs()
                        # else:
                        #    logging.info("thumbs exist. skipping")

                    logging.debug('response: ' + str(r.json()))
                    try:
                        self.c3tt.set_ticket_properties({'Voctoweb.EventId': r.json()['id']})
                    except Exception as e_:
                        raise PublisherException('failed to set EventID on ticket') from e_

                elif r.status_code == 422:
                    # If this happens tracker and voctoweb are out of sync regarding the recording id
                    logging.warning("event already exists => publishing")
                else:
                    raise RuntimeError(("ERROR: Could not add event: " + str(r.status_code) + " " + r.text))

                # in case of a multi language release we create here the single language files
                if len(self.ticket.languages) > 1:
                    logging.info('remuxing multi-language video into single audio files')
                    self._mux_to_single_language(vw)

        # set hq filed based on ticket encoding profile slug
        if 'hd' in self.ticket.profile_slug:
            hq = True
        else:
            hq = False

        # For multi language or slide recording we don't set the html5 flag
        if len(self.ticket.languages) > 1 or 'slides' in self.ticket.profile_slug :
            html5 = False
        else:
            html5 = True

        if self.ticket.mime_type.startswith('audio'):
            # probably deprecated, just kept for reference
            # if we have the language index we use it else we assume its 0
            # if self.ticket.language_index and len(self.ticket.language_index) > 0:
            #     index = int(self.ticket.language_index)
            # else:
            #     index = 0
            # filename = self.ticket.language_template % self.ticket.languages[index] + '.' + self.ticket.profile_extension
            filename = self.ticket.language_template % self.ticket.languages[0] + '.' + self.ticket.profile_extension
            language = self.ticket.languages[0]
        else:
            filename = self.ticket.filename
            language = self.ticket.language

        vw.upload_file(self.ticket.local_filename, filename, self.ticket.folder)

        recording_id = vw.create_recording(self.ticket.local_filename,
                                           filename,
                                           self.ticket.folder,
                                           language,
                                           hq,
                                           html5)

        self.c3tt.set_ticket_properties({'Voctoweb.RecordingId.Master': recording_id})

    def _mux_to_single_language(self, vw):
        """
        Mux a multi language video file into multiple single language video files.
        This is only implemented for the h264 hd files as we only do it for them
        :return:
        """
        logging.debug('Languages: ' + str(self.ticket.languages))
        for language in self.ticket.languages:
            out_filename = self.ticket.fahrplan_id + "-" + self.ticket.profile_slug + "-audio" + str(language) + "." + self.ticket.profile_extension
            out_path = os.path.join(self.ticket.publishing_path, out_filename)
            filename = self.ticket.language_template % self.ticket.languages[language] + '.' + self.ticket.profile_extension

            logging.info('remuxing ' + self.ticket.local_filename + ' to ' + out_path)

            try:
                subprocess.call(['ffmpeg', '-y', '-v', 'warning', '-nostdin', '-i',
                                 os.path.join(self.ticket.publishing_path, self.ticket.local_filename), '-map', '0:0',
                                 '-map',
                                 '0:a:' + str(language), '-c', 'copy', '-movflags', 'faststart', out_path])
            except Exception as e_:
                raise PublisherException('error remuxing ' + self.ticket.local_filename + ' to ' + out_path) from e_

            try:
                vw.upload_file(out_path, filename, self.ticket.folder)
            except Exception as e_:
                raise PublisherException('error uploading ' + out_path) from e_

            try:
                recording_id = vw.create_recording(out_filename, filename, self.ticket.folder, str(self.ticket.languages[language]), True, True)
            except Exception as e_:
                raise PublisherException('creating recording ' + out_path) from e_

            try:
                self.c3tt.set_ticket_properties({'Voctoweb.RecordingId.' + self.ticket.languages[language]: str(recording_id)})
            except Exception as e_:
                raise PublisherException('failed to set RecordingId to ticket') from e_

    def _publish_to_youtube(self):
        """
        Publish the file to YouTube.
        """
        logging.debug("publishing to youtube")

        yt = YoutubeAPI(self.config)
        yt.setup(self.ticket.youtube_token)

        # second YoutubeAPI instance for playlist management at youtube.com/mediacccde
        # todo this code should not be specific for the media.ccc.de installation => make it general usable
        if 'playlist_token' in self.config['youtube'] and self.ticket.youtube_token != self.config['youtube']['playlist_token']:
            yt_voctoweb = YoutubeAPI(self.config)
            yt_voctoweb.setup(self.config['youtube']['playlist_token'])
        else:
            logging.info('using same token for publishing and playlist management')
            yt_voctoweb = yt

        youtube_urls = yt.publish(self.ticket)
        props = {}
        for i, youtubeUrl in enumerate(youtube_urls):
            props['YouTube.Url' + str(i)] = youtubeUrl

        self.c3tt.set_ticket_properties(props)

        # now, after we reported everything back to the tracker, we try to add the videos to our own playlists
        for url in youtube_urls:
            video_id = url.split('=', 2)[1]
            yt_voctoweb.add_to_playlists(video_id, self.ticket.youtube_playlists)


class PublisherException(Exception):
    pass


if __name__ == '__main__':
    try:
        publisher = Publisher()
    except Exception as e:
        logging.error(e)
        logging.exception(e)
        sys.exit(-1)

    try:
        publisher.publish()
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        publisher.c3tt.set_ticket_failed('%s: %s' % (exc_type.__name__, e))
        logging.exception(e)
        sys.exit(-1)
