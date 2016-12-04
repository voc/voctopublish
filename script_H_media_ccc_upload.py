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

# import configparser

from c3t_rpc_client import *
from media_ccc_de_api_client import *
from twitter_client import *
from youtube_client import *


class Publisher:
    def __init__(self):
        self.logger = logging.getLogger()

        logging.addLevelName(logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
        logging.addLevelName(logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
        logging.addLevelName(logging.INFO, "\033[1;32m%s\033[1;0m" % logging.getLevelName(logging.INFO))
        logging.addLevelName(logging.DEBUG, "\033[1;85m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))

        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # uncomment the next line to add filename and line number to logging output
        # formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s {%(filename)s:%(lineno)d} %(message)s')
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        logging.info("C3TT publishing")
        logging.debug("reading config")

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
                self.get_ticket_from_tracker()
            except:
                logger.error("Could not get ticket from tracker")
                sys.exit(-1)

        # media
        if self.config['media.ccc.de']['enable']:
            self.api_url = self.config['media.ccc.de']['api_url']
            self.api_key = self.config['media.ccc.de']['api_key']
            self.media = MediaApiClient(self.ticket)

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
            "encoding profile youtube flag: " + self.t.profile_youtube_enable + ' project youtube flag: ' + ticket.youtube_enabel)

        if ticket.profile_youtube_enable == 'yes' and ticket.youtube_enabel == 'yes' and not ticket.has_youtube_url:
            logging.debug("publishing on youtube")
            youtube_from_tracker(ticket)

        logging.debug(
            'encoding profile media flag: ' + ticket.profile_media_enable + " project media flag: " + ticket.media_enabel)

        if ticket.profile_media_enable == "yes" and ticket.media_enabel == "yes":
            logging.debug("publishing on media")
            media_from_tracker(ticket)

    def get_ticket_from_tracker(self):
        """
        Get a ticket from the tracker an populate local variables
        """

        logging.info('getting ticket from tracker')
        logging.info('=========================================')

        # check if we got a new ticket
        ticket_id = assignNextUnassignedForState(from_state, to_state, url, group, host, secret)
        if ticket_id:
            # copy ticket details to local variables
            logging.info("Ticket ID:" + str(ticket_id))
            tracker_ticket = getTicketProperties(str(ticket_id), url, group, host, secret)
            logging.debug("Ticket: " + str(tracker_ticket))

            t = Ticket(tracker_ticket, ticket_id)

            if not os.path.isfile(t.video_base + t.local_filename):
                logging.error("Source file does not exist (%s)" % (t.video_base + t.local_filename))
                setTicketFailed(t.ticket_id, "Source file does not exist (%s)" % (t.video_base + t.local_filename), url, group,
                                host, secret)
                sys.exit(-1)

            if not os.path.exists(t.output):
                logging.error("Output path does not exist (%s)" % t.output)
                setTicketFailed(t.ticket_id, "Output path does not exist (%s)" % t.output, url, group, host, secret)
                sys.exit(-1)
            else:
                if not os.access(output, os.W_OK):
                    logging.error("Output path is not writable (%s)" % t.output)
                    setTicketFailed(t.ticket_id, "Output path is not writable (%s)" % t.output, url, group, host, secret)
                    sys.exit(-1)
        else:
            logging.warn("No ticket for this task, exiting")
            sys.exit(0)

        return t


    def media_from_tracker(self):
        """
        Create a event on media a media.ccc.de instance. This includes creating a event and a recording for each media file.
        This methods also start the scp uploads and handles multi language audio
        :param t: ticket
        """
        logging.info("creating event on " + api_url)
        logging.info("=========================================")
        multi_language = False
        languages = t.language.rsplit('-')

        # if we have an audio file we skip this part
        if t.profile_slug not in ["mp3", "opus", "mp3-2", "opus-2"]:

            # get original language. We assume this is always the first language
            orig_language = str(languages[0])

            # create the event
            # TODO at the moment we just try this and look on the error. We should store event id and ask the api
            try:
                r = create_event(api_url, api_key, orig_language)
                if r.status_code in [200, 201]:
                    logger.info("new event created")
                    # generate the thumbnails (will not overwrite existing thumbs)
                    if not os.path.isfile(t.video_base + t.local_filename_base + ".jpg"):
                        if not make_thumbs(t):
                            raise RuntimeError("ERROR: Generating thumbs:")
                        else:
                            # upload thumbnails
                            upload_thumbs(t, sftp)
                    else:
                        logger.info("thumbs exist. skipping")

                elif r.status_code == 422:
                    logger.info("event already exists. => publishing")
                else:
                    raise RuntimeError(("ERROR: Could not add event: " + str(r.status_code) + " " + r.text))

            except RuntimeError as err:
                logging.error("Creating event failed")
                setTicketFailed(t.ticket_id,
                                "Creating event failed, in case of audio releases make sure event exists: \n" + str(err),
                                url, group, host, secret)
                sys.exit(-1)

        if t.profile_slug == 'hd' and re.match('(..)-(..)', t.language):
            # if a second language is configured, remux the video to only have the one audio track and upload it twice
            logger.debug('remuxing dual-language video into two parts')


        # publish the original file on media
        if 'Publishing.Media.MimeType' not in t:
            setTicketFailed(t.ticket_id,
                            'Publishing failed: No mime type, please use property Publishing.Media.MimeType in encoding '
                            'profile! \n' + str('Error '), url, group, host, secret)

        # set hq filed based on ticket encoding profile slug
        if 'hd' in t.profile_slug:
            hq = True
        else:
            hq = False

        # if we have decided before to do multi language release we don't want to set the html5 flag for the master
        if multi_language:
            html5 = False
        else:
            html5 = True

        try:
            upload_file(t, t.local_filename, t.filename, t.folder, ssh)
            create_recording(t.local_filename, t.filename, api_url, t.download_base_url, api_key, t.guid, t.mime_type, t.folder,
                             video_base, language, hq, html5, t)
        except RuntimeError as err:
            setTicketFailed(ticket_id, "Publishing failed: \n" + str(err), url, group, host, secret)
            logging.error('Publishing failed: \n' + str(err))
            sys.exit(-1)

    def mux_to_single_language(self):
        """

        :return:
        """
        languages = t.language.rsplit('-')

        for i, lang in enumerate(languages):
            outfilename = t.fahrplan_id + "-" + t.profile_slug + "-audio" + str(i) + "." + t.profile_extension
            outfile = t.video_base + outfile
            filename = t.language_template % languages[i] + '.' + t.profile_extension

            logger.debug('remuxing' + t.local_filename + ' to ' + outfile)
            try:
                subprocess.call(['ffmpeg', '-y', '-v', 'warning', '-nostdin', '-i', t.video_base + t.local_filename, '-map', '0:0', '-map',
                 '0:1', '-c', 'copy', '-movflags', 'faststart', outfile])
            except:
                raise RuntimeError('error remuxing ' + t.local_filename + ' to ' + outfile)

            try:
                upload_file(t, outfile, filename, folder, sftp)
            except:
                raise RuntimeError('error uploading ' + outfile)

            try:
                create_recording(outfilename, filename, api_url, t.download_base_url, api_key, t.guid, 'video/mp4',
                             'h264-hd-web', t.video_base, str(languages[i]), True, True, t)
            except:
                raise RuntimeError('creating recording ' + outfile)


    def youtube_from_tracker(self):
        """
        Publish the file to YouTube.
        """
        try:
            youtube_urls = publish_youtube(self.ticket, config['youtube']['client_id'], config['youtube']['secret'])
            props = {}
            for i, youtubeUrl in enumerate(youtube_urls):
                props['YouTube.Url' + str(i)] = youtubeUrl

            setTicketProperties(ticket_id, props, url, group, host, secret)

        except RuntimeError as err:
            setTicketFailed(ticket_id, 'Publishing failed: \n' + str(err), url, group, host, secret)
            logging.error('Publishing failed: \n' + str(err))
            sys.exit(-1)


if __name__ == '__main__':

    publisher = Publisher()

    publisher.choose_target_from_properties()
    publisher.logger.info("set ticket done")
    publisher.setTicketDone()
    publisher.send_tweet()
