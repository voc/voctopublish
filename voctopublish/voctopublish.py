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
import api_client.mastodon_client as mastodon
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
        if self.ticket.profile_voctoweb_enable and self.ticket.voctoweb_enable:
            logging.debug(
                'encoding profile media flag: ' + str(self.ticket.profile_voctoweb_enable) + " project media flag: " + str(self.ticket.voctoweb_enable))
            self._publish_to_voctoweb()

        # YouTube
        if self.ticket.profile_youtube_enable and self.ticket.youtube_enable:
            if self.ticket.has_youtube_url:
                raise PublisherException('YouTube URLs already exist in ticket, wont publish to youtube')
            else:
                logging.debug(
                    "encoding profile youtube flag: " + str(self.ticket.profile_youtube_enable) + ' project youtube flag: ' + str(self.ticket.youtube_enable))
                self._publish_to_youtube()

        self.c3tt.set_ticket_done()

        # Twitter
        if self.ticket.twitter_enable and self.ticket.master:
            twitter.send_tweet(self.ticket, self.config)

        # Mastodon
        if self.ticket.mastodon_enable and self.ticket.master:
            mastodon.send_toot(self.ticket, self.config)

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
                                self.config['voctoweb']['api_url'],
                                self.config['voctoweb']['ssh_host'],
                                self.config['voctoweb']['ssh_port'],
                                self.config['voctoweb']['ssh_user'])
        except Exception as e_:
            raise PublisherException('Error initializing voctoweb client. Config parameter missing') from e_

        if self.ticket.master:
            # if this is master ticket we need to check if we need to create an event on voctoweb
            logging.debug('this is a master ticket')
            r = vw.create_or_update_event()
            if r.status_code in [200, 201]:
                logging.info("new event created or existing updated")
                # generate the thumbnails (will not overwrite existing thumbs)
                # todo move the external bash script to python code here
                # if this is an audio only release we don' create thumbs
                if self.ticket.mime_type.startswith('video'):
                    vw.generate_thumbs()
                    vw.upload_thumbs()
                    vw.generate_timelens()
                    vw.upload_timelens()
                    logging.debug('response: ' + str(r.json()))
                try:
                    # todo: only set recording id when new recording was created, and not when it was only updated
                    self.c3tt.set_ticket_properties({'Voctoweb.EventId': r.json()['id']})
                except Exception as e_:
                    raise PublisherException('failed to Voctoweb EventID to ticket') from e_

            elif r.status_code == 422:
                # If this happens tracker and voctoweb are out of sync regarding the event id
                # todo: write voctoweb event_id to ticket properties --Andi
                logging.warning("event already exists => publishing")
            else:
                    raise PublisherException('Voctoweb returned an error while creating an event: ' + str(r.status_code) + ' - ' + str(r.content))

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

        # if we have the language index the tracker wants to tell us about an encoding that does not contain all audio tracks of the master
        # we need to reflect that in the target filename
        if self.ticket.language_index:
            index = int(self.ticket.language_index)
            filename = self.ticket.language_template % self.ticket.languages[index] + '_' + self.ticket.profile_slug + '.' + self.ticket.profile_extension
            language = self.ticket.languages[index]
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
        
        # when the ticket was created, and not only updated: write recording_id to ticket
        if recording_id:
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
                recording_id = vw.create_recording(out_filename, filename, self.ticket.folder, str(self.ticket.languages[language]), hq=True, html5=True, single_language=True)
            except Exception as e_:
                raise PublisherException('creating recording ' + out_path) from e_

            try:
                # when the ticket was created, and not only updated: write recording_id to ticket
                if recording_id:
                    self.c3tt.set_ticket_properties({'Voctoweb.RecordingId.' + self.ticket.languages[language]: str(recording_id)})
            except Exception as e_:
                raise PublisherException('failed to set RecordingId to ticket') from e_

    def _publish_to_youtube(self):
        """
        Publish the file to YouTube.
        """
        logging.debug("publishing to youtube")

        yt = YoutubeAPI(self.ticket, self.config['youtube']['client_id'], self.config['youtube']['secret'])
        yt.setup(self.ticket.youtube_token)

        youtube_urls = yt.publish()
        props = {}
        for i, youtubeUrl in enumerate(youtube_urls):
            props['YouTube.Url' + str(i)] = youtubeUrl

        self.c3tt.set_ticket_properties(props)
        self.ticket.youtube_urls = props

        # now, after we reported everything back to the tracker, we try to add the videos to our own playlists
        # second YoutubeAPI instance for playlist management at youtube.com
        # todo figure out why we need two tokens
        if 'playlist_token' in self.config['youtube'] and self.ticket.youtube_token != self.config['youtube']['playlist_token']:
            yt_voctoweb = YoutubeAPI(self.ticket, self.config['youtube']['client_id'], self.config['youtube']['secret'])
            yt_voctoweb.setup(self.config['youtube']['playlist_token'])
        else:
            logging.info('using same token for publishing and playlist management')
            yt_voctoweb = yt

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
