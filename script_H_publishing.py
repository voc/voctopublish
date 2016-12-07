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
import re
import subprocess

import c3t_rpc_client as c3t
from voctoweb_client import VoctowebClient
import twitter_client as twitter
import youtube_client as youtube
from ticket_module import Ticket


class Publisher:
    def __init__(self):
        logging.addLevelName(logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
        logging.addLevelName(logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
        logging.addLevelName(logging.INFO, "\033[1;32m%s\033[1;0m" % logging.getLevelName(logging.INFO))
        logging.addLevelName(logging.DEBUG, "\033[1;85m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))

        self.logger = logging.getLogger()

        ch = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s - %(filename)s - %(lineno)s - %(name)s - %(levelname)s - %(message)s')
        # uncomment the next line to add filename and line number to logging output
        # formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s {%(filename)s:%(lineno)d} %(message)s')

        ch.setFormatter(formatter)

        self.logger.addHandler(ch)
        self.logger.setLevel(logging.DEBUG)
        logging.info("reading config")

        # handle config
        if not os.path.exists('client.conf'):
            logging.error("Error: config file not found")
            sys.exit(1)

        self.config = configparser.ConfigParser()
        self.config.read('client.conf')

        level = self.config['general']['debug']
        if level == 'info':
            self.logger.setLevel(logging.INFO)
        elif level == 'warning':
            self.logger.setLevel(logging.WARNING)
        elif level == 'error':
            self.logger.setLevel(logging.ERROR)
        elif level == 'debug':
            self.logger.setLevel(logging.DEBUG)

        source = self.config['general']['source']

        # c3tt
        if source == 'c3tt':
            self.group = self.config['C3Tracker']['group']
            self.secret = self.config['C3Tracker']['secret']

            if self.config['C3Tracker']['host'] == "None":
                self.host = socket.getfqdn()
            else:
                self.host = self.config['C3Tracker']['host']

            self.tracker_url = self.config['C3Tracker']['url']
            self.from_state = self.config['C3Tracker']['from_state']
            self.to_state = self.config['C3Tracker']['to_state']
            self.ticket = None
            try:
                self.ticket = self.get_ticket_from_tracker()
            except Exception as e:
                logging.error("Could not get ticket from tracker")
                logging.debug(e)
                sys.exit(-1)

        # media
        if self.config['media.ccc.de']['enable']:
            self.api_url = self.config['media.ccc.de']['api_url']
            self.api_key = self.config['media.ccc.de']['api_key']
            self.vw = VoctowebClient(self.ticket)

        # twitter
        if self.config['twitter']['enable'] == 'True':
            self.token = self.config['twitter']['token']
            self.token_secret = self.config['twitter']['token_secret']
            self.consumer_key = self.config['twitter']['consumer_key']
            self.consumer_secret = self.config['twitter']['consumer_secret']

    def choose_target_from_properties(self):
        """
        Decide based on the information provided by the tracker where to publish.
        """
        logging.debug(
            "encoding profile youtube flag: " + self.ticket.profile_youtube_enable + ' project youtube flag: ' + self.ticket.youtube_enable)

        if self.ticket.profile_youtube_enable == 'yes' and self.ticket.youtube_enable == 'yes' and not self.ticket.has_youtube_url:
            logging.debug("publishing on youtube")
            self.youtube_from_tracker()

        logging.debug(
            'encoding profile media flag: ' + self.ticket.profile_media_enable + " project media flag: " + self.ticket.media_enable)

        if self.ticket.profile_media_enable == "yes" and self.ticket.media_enable == "yes":
            logging.debug("publishing on media")
            try:
                self.media_from_tracker()
            except Exception as err:
                c3t.setTicketFailed(self.ticket.ticket_id, 'Publishing failed: \n' + str(err), self.tracker_url, self.group,
                                    self.host, self.secret)
                logging.error(err)
                sys.exit(-1)

    def get_ticket_from_tracker(self):
        """
        Get a ticket from the tracker an populate local variables
        """

        logging.info('requesting ticket from tracker')

        # check if we got a new ticket
        ticket_id = c3t.assignNextUnassignedForState(self.from_state, self.to_state, self.tracker_url, self.group,
                                                     self.host, self.secret)
        if ticket_id:
            # copy ticket details to local variables
            logging.info("Ticket ID:" + str(ticket_id))
            tracker_ticket = c3t.getTicketProperties(str(ticket_id), self.tracker_url, self.group, self.host,
                                                     self.secret)
            logging.debug("Ticket: " + str(tracker_ticket))

            t = Ticket(tracker_ticket, ticket_id)

            if not os.path.isfile(t.video_base + t.local_filename):
                logging.error("Source file does not exist (%s)" % (t.video_base + t.local_filename))
                c3t.setTicketFailed(t.ticket_id, "Source file does not exist (%s)" % (t.video_base + t.local_filename),
                                    self.tracker_url, self.group,
                                    self.host, self.secret)
                sys.exit(-1)

            if not os.path.exists(t.output):
                logging.error("Output path does not exist (%s)" % t.output)
                c3t.setTicketFailed(t.ticket_id, "Output path does not exist (%s)" % t.output, self.tracker_url,
                                    self.group, self.host, self.secret)
                sys.exit(-1)
            else:
                if not os.access(t.output, os.W_OK):
                    logging.error("Output path is not writable (%s)" % t.output)
                    c3t.setTicketFailed(t.ticket_id, "Output path is not writable (%s)" % t.output, self.tracker_url,
                                        self.group, self.host, self.secret)
                    sys.exit(-1)
        else:
            logging.warning("No ticket for this task, exiting")
            sys.exit(0)

        return t

    def media_from_tracker(self):
        """
        Create a event on media a media.ccc.de instance. This includes creating a event and a recording for each media file.
        This methods also start the scp uploads and handles multi language audio
        """
        logging.info("creating event on " + self.api_url)
        #multi_language = False




        # if we have an audio file we skip this part
        if self.ticket.profile_slug not in ["mp3", "opus", "mp3-2", "opus-2"]:

            # get original language. We assume this is always the first language
            orig_language = str(languages[0])

            # create the event
            # TODO at the moment we just try this and look on the error. We should store event id and ask the api
            try:
                r = self.vw.create_event(self.api_url, self.api_key, orig_language)
                if r.status_code in [200, 201]:
                    logging.info("new event created")
                    # generate the thumbnails (will not overwrite existing thumbs)
                    if not os.path.isfile(self.ticket.video_base + self.ticket.local_filename_base + ".jpg"):
                        if not self.vw.make_thumbs():
                            raise RuntimeError("ERROR: Generating thumbs:")
                        else:
                            # upload thumbnails
                            self.vw.upload_thumbs()
                    else:
                        logging.info("thumbs exist. skipping")

                elif r.status_code == 422:
                    logging.info("event already exists. => publishing")
                else:
                    raise RuntimeError(("ERROR: Could not add event: " + str(r.status_code) + " " + r.text))

            except Exception as err:
                logging.error("Creating event failed")
                logging.debug(err)
                c3t.setTicketFailed(self.ticket.ticket_id,
                                "Creating event failed, in case of audio releases make sure event exists: \n" + str(
                                    err),
                                self.tracker_url, self.group, self.host, self.secret)
                sys.exit(-1)


        if self.ticket.profile_slug == 'hd' and re.match('(..)-(..)', self.ticket.language): # todo make this more readable
            # if a second language is configured, remux the video to only have the one audio track and upload it twice
            logging.debug('remuxing dual-language video into two parts')

        # set hq filed based on ticket encoding profile slug
        if 'hd' in self.ticket.profile_slug:
            hq = True
        else:
            hq = False

        # if we have decided before to do multi language release we don't want to set the html5 flag for the master
        if multi_language:
            html5 = False
        else:
            html5 = True

        try:
            self.vw.upload_file(self.ticket.local_filename, self.ticket.filename, self.ticket.folder)
            self.vw.create_recording(self.ticket.local_filename, self.ticket.filename, self.api_url, self.api_key,
                                     self.ticket.folder,  self.language, hq, html5)

        except RuntimeError as err:
            c3t.setTicketFailed(self.ticket_id, "Publishing failed: \n" + str(err), self.tracker_url, self.group,
                                self.host, self.secret)

            logging.error('Publishing failed: \n' + str(err))
            sys.exit(-1)

    def mux_to_single_language(self):
        """

        :return:
        """
        languages = self.ticket.language.rsplit('-')

        for i, lang in enumerate(languages):
            outfilename = self.ticket.fahrplan_id + "-" + self.ticket.profile_slug + "-audio" + str(
                i) + "." + self.ticket.profile_extension
            outfile = self.ticket.video_base + outfilename
            filename = self.ticket.language_template % languages[i] + '.' + self.ticket.profile_extension

            logging.debug('remuxing' + self.ticket.local_filename + ' to ' + outfile)
            try:
                subprocess.call(['ffmpeg', '-y', '-v', 'warning', '-nostdin', '-i',
                                 self.ticket.video_base + self.ticket.local_filename, '-map', '0:0', '-map',
                                 '0:1', '-c', 'copy', '-movflags', 'faststart', outfile])
            except:
                raise RuntimeError('error remuxing ' + self.ticket.local_filename + ' to ' + outfile)

            try:
                self.vw.upload_file(outfile, filename, folder)
            except:
                raise RuntimeError('error uploading ' + outfile)

            try:
                self.vw.create_recording(outfilename, filename, self.api_url, self.api_key, 'video/mp4',
                                 'h264-hd-web', self.ticket.video_base, str(languages[i]), True, True)
            except:
                raise RuntimeError('creating recording ' + outfile)

    def youtube_from_tracker(self):
        """
        Publish the file to YouTube.
        """
        try:
            youtube_urls = youtube.publish_youtube(self.ticket, self.config['youtube']['client_id'], self.config['youtube']['secret'])
            props = {}
            for i, youtubeUrl in enumerate(youtube_urls):
                props['YouTube.Url' + str(i)] = youtubeUrl

            c3t.setTicketProperties(self.ticket_id, props, self.tracker_url, self.group, self.host, self.secret)

        except RuntimeError as err:
            c3t.setTicketFailed(self.ticket_id, 'Publishing failed: \n' + str(err), self.tracker_url, self.group,
                                self.host, self.secret)

            logging.error('Publishing failed: \n' + str(err))
            sys.exit(-1)


if __name__ == '__main__':
    publisher = Publisher()
    publisher.choose_target_from_properties()
    publisher.c3t.setTicketDone()
    publisher.twitter.send_tweet()
