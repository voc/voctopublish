#!/usr/bin/python3
#    Copyright (C) 2016  derpeter
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
    This is the main class for the publishing application
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

        ch = logging.StreamHandler(sys.stdout)
        if self.config['general']['debug']:
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s {%(filename)s:%(lineno)d} %(message)s')
        else:
            formatter = logging.Formatter('%(asctime)s - %(message)s')

        ch.setFormatter(formatter)
        self.logger.addHandler(ch)
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

        # get a ticket from the tracker and initialize the ticket object
        if self.config['C3Tracker']['host'] == "None":
            self.host = socket.getfqdn()
        else:
            self.host = self.config['C3Tracker']['host']

        self.from_state = self.config['C3Tracker']['from_state']
        self.to_state = self.config['C3Tracker']['to_state']

        try:
            self.c3tt = C3TTClient(self.config['C3Tracker']['url'], self.config['C3Tracker']['group'],
                                   self.host, self.config['C3Tracker']['secret'])
        except Exception as e_:
            raise PublisherException('Config parameter missing or empty, please check config') from e_

        try:
            self.ticket = self._get_ticket_from_tracker()
        except Exception as e_:
            raise PublisherException("Could not get ticket from tracker") from e_

        # voctoweb
        if self.ticket.profile_media_enable == 'yes' and self.ticket.media_enable:
            api_url = self.config['voctoweb']['api_url']
            api_key = self.config['voctoweb']['api_key']
            self.vw = VoctowebClient(self.ticket, api_key, api_url)

        # YouTube
        if self.ticket.profile_youtube_enable == 'yes' and self.ticket.youtube_enable:
            self.yt = YoutubeAPI(self.ticket, self.config)

        # twitter
        if self.ticket.twitter_enable == 'yes':
            self.token = self.config['twitter']['token']
            self.token_secret = self.config['twitter']['token_secret']
            self.consumer_key = self.config['twitter']['consumer_key']
            self.consumer_secret = self.config['twitter']['consumer_secret']

    def publish(self):
        """
        Decide based on the information provided by the tracker where to publish.
        """
        logging.debug(
            "encoding profile youtube flag: " + self.ticket.profile_youtube_enable + ' project youtube flag: ' + self.ticket.youtube_enable)

        if self.ticket.profile_youtube_enable == 'yes' and self.ticket.youtube_enable == 'yes' and not self.ticket.has_youtube_url:
            logging.debug("publishing_test on youtube")
            self._publish_to_youtube()

        logging.debug(
            'encoding profile media flag: ' + self.ticket.profile_media_enable + " project media flag: " + self.ticket.media_enable)

        if self.ticket.profile_media_enable == "yes" and self.ticket.media_enable == "yes":
            logging.debug("publishing_test on media")
            self._publish_to_voctoweb()

        self.c3tt.set_ticket_done()

        if self.ticket.twitter_enable == 'yes':
            twitter.send_tweet(self.ticket, self.token, self.token_secret, self.consumer_key, self.consumer_secret)

    def _get_ticket_from_tracker(self):
        """
        Get a ticket from the tracker an populate local variables
        """
        logging.info('requesting ticket from tracker')

        # check if we got a new ticket
        ticket_id = self.c3tt.assign_next_unassigned_for_state(self.from_state, self.to_state)
        if ticket_id:
            logging.info("Ticket ID:" + str(ticket_id))
            tracker_ticket = self.c3tt.get_ticket_properties()
            logging.debug("Ticket: " + str(tracker_ticket))

            t = Ticket(tracker_ticket, ticket_id)

            # todo this should happen later so we can report these error to the tracker
            if not os.path.isfile(t.publishing_path + t.local_filename):
                raise IOError('Source file does not exist (%s)' % (t.publishing_path + t.local_filename))
            if not os.path.exists(t.publishing_path):
                raise IOError("Output path does not exist (%s)" % t.publishing_path)
            else:
                if not os.access(t.publishing_path, os.W_OK):
                    raise IOError("Output path is not writable (%s)" % t.publishing_path)
        else:
            logging.info("No ticket to publish, exiting")
            return None

        return t

    def _publish_to_voctoweb(self):
        """
        Create a event on an voctomix instance. This includes creating a event and a recording for each media file.
        This methods also start the scp uploads and handles multi language audio
        """
        logging.info("creating event on voctoweb")

        # audio files don't need the following steps
        if self.ticket.mime_type.startswith('video'):

            # create the event on voctoweb
            # TODO at the moment we just try this and look on the error. We should store event id and ask the api
            r = self.vw.create_event()
            if r.status_code in [200, 201]:
                logging.info("new event created")
                # generate the thumbnails (will not overwrite existing thumbs)
                if not os.path.isfile(self.ticket.publishing_path + self.ticket.local_filename_base + ".jpg"):
                    self.vw.generate_thumbs()
                    self.vw.upload_thumbs()
                else:
                    logging.info("thumbs exist. skipping")

            elif r.status_code == 422:
                logging.info("event already exists => publishing_test")
            else:
                raise RuntimeError(("ERROR: Could not add event: " + str(r.status_code) + " " + r.text))

        if self.ticket.master and len(self.ticket.languages) > 1:
            logging.info('remuxing multi-language video into single audio files')

        # set hq filed based on ticket encoding profile slug
        if 'hd' in self.ticket.profile_slug:
            hq = True
        else:
            hq = False

        # if multi language release we don't want to set the html5 flag for the master
        if len(self.ticket.languages) > 1:
            html5 = False
        else:
            html5 = True

        self.vw.upload_file(self.ticket.local_filename, self.ticket.filename, self.ticket.folder)

        recording_id = self.vw.create_recording(self.ticket.local_filename, self.ticket.filename,
                                                self.ticket.folder, self.ticket.languages[0], hq, html5)

        self.c3tt.set_ticket_properties({'Voctoweb.RecordingId.Master': recording_id})

    def _mux_to_single_language(self):
        """
        Mux a multi language video file into multiple single language video files.
        This is only implemented for the h264 hd files as we only do it for them
        :return:
        """
        for i, lang in self.ticket.languages:
            out_filename = self.ticket.fahrplan_id + "-" + self.ticket.profile_slug + "-audio" + i + "." + self.ticket.profile_extension
            out_path = os.path.join(self.ticket.publishing_path, out_filename)
            filename = self.ticket.language_template % lang + '.' + self.ticket.profile_extension

            logging.info('remuxing ' + self.ticket.local_filename + ' to ' + out_path)

            try:
                subprocess.call(['ffmpeg', '-y', '-v', 'warning', '-nostdin', '-i',
                                 os.path.join(self.ticket.publishing_path, self.ticket.local_filename), '-map', '0:0',
                                 '-map',
                                 '0:1', '-c', 'copy', '-movflags', 'faststart', out_path])
            except Exception as e_:
                raise PublisherException('error remuxing ' + self.ticket.local_filename + ' to ' + out_path) from e_

            try:
                self.vw.upload_file(out_path, filename, self.ticket.folder)
            except Exception as e_:
                raise PublisherException('error uploading ' + out_path) from e_

            try:
                self.vw.create_recording(out_filename, filename, self.ticket.publishing_path, str(lang), True, True)
            except Exception as e_:
                raise PublisherException('creating recording ' + out_path) from e_

    def _publish_to_youtube(self):
        """
        Publish the file to YouTube.
        """
        youtube_urls = self.yt.publish()
        props = {}
        for i, youtubeUrl in enumerate(youtube_urls):
            props['YouTube.Url' + str(i)] = youtubeUrl

        self.c3tt.set_ticket_properties(props)


class PublisherException(Exception):
    pass


if __name__ == '__main__':
    try:
        publisher = Publisher()
    except Exception as e:
        logging.error(e)
        logging.exception(e)
        sys.exit(-1)

    if publisher.ticket:
        try:
            publisher.publish()
        except Exception as e:
            publisher.c3tt.set_ticket_failed(str(e))
            logging.error(e)
            logging.exception(e)
            sys.exit(-1)
