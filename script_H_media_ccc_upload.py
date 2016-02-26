#!/usr/bin/python3
#    Copyright (C) 2015  derpeter
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

import argparse
import sys
import os
import urllib.request, urllib.parse, urllib.error
import requests
import subprocess
import xmlrpc.client
import socket
import xml.etree.ElementTree as ET
import json
import configparser
import paramiko
import inspect
import logging

from ticket_module import Ticket
from c3t_rpc_client import *
from media_ccc_de_api_client import *
from auphonic_client import *
from youtube_client import *
from twitter_client import *

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

logging.addLevelName(logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
logging.addLevelName(logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
logging.addLevelName(logging.INFO, "\033[1;32m%s\033[1;0m" % logging.getLevelName(logging.INFO))
logging.addLevelName(logging.DEBUG, "\033[1;85m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# uncomment the next line to add filename and linenumber to logging output
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s {%(filename)s:%(lineno)d} %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

logging.info("C3TT publishing")
logging.debug("reading config")

### handle config
# make sure we have a config file
if not os.path.exists('client.conf'):
    logging.error("Error: config file not found")
    sys.exit(1)

config = configparser.ConfigParser()
config.read('client.conf')
source = config['general']['source']
dest = config['general']['dest']

source = "c3tt"  # TODO quickfix for strange parser behavior

if source == "c3tt":
    ################### C3 Tracker ###################
    # project = "projectslug"
    group = config['C3Tracker']['group']
    secret = config['C3Tracker']['secret']

    if config['C3Tracker']['host'] == "None":
        host = socket.getfqdn()
    else:
        host = config['C3Tracker']['host']

    url = config['C3Tracker']['url']
    from_state = config['C3Tracker']['from_state']
    to_state = config['C3Tracker']['to_state']
    token = config['twitter']['token']
    token_secret = config['twitter']['token_secret']
    consumer_key = config['twitter']['consumer_key']
    consumer_secret = config['twitter']['consumer_secret']

if True:
    ################### media.ccc.de #################
    # API informations
    api_url = config['media.ccc.de']['api_url']
    api_key = config['media.ccc.de']['api_key']
    # download_thumb_base_url = config['media.ccc.de']['download_thumb_base_url']
    # download_base_url = config['media.ccc.de']['download_base_url']

    # release host information
    # upload_host = config['media.ccc.de']['uplod_host']
    # upload_user = config['media.ccc.de']['upload_user']
    # upload_pw = config['media.ccc.de']['upload_pw'] #it is recommended to use key login. PW musts be set but can be random
    # upload_path = config['media.ccc.de']['upload_path']

# if we don't use the tracker we need to get the informations from the config file
if source != 'c3tt':
    #################### conference information ######################
    rec_path = config['conference']['rec_path']
    image_path = config['conference']['image_path']
    webgen_loc = config['conference']['webgen_loc']

    ################### script environment ########################
    # base dir for video input files (local)
    video_base = config['env']['video_base']
    # base dir for video output files (local)
    output = config['env']['output']

# internal vars
filesize = 0
length = 0
sftp = None
ssh = None
debug = 0
rpc_client = None
mime_type = None
lang = None


def choose_target_from_properties(ticket):
    """
    :param ticket:
    :return:
    """

    logging.debug(
        "encoding profile youtube flag: " + ticket.profile_youtube_enable + ' project youtube flag: ' + ticket.youtube_enabel)

    if ticket.profile_youtube_enable == 'yes' and ticket.youtube_enabel == 'yes' and not ticket.has_youtube_url:
        logging.debug("publishing on youtube")
        youtube_from_tracker(ticket)

    logging.debug(
        'encoding profile media flag: ' + ticket.profile_media_enable + " project media flag: " + ticket.media_enabel)

    if ticket.profile_media_enable == "yes" and ticket.media_enabel == "yes":
        logging.debug("publishing on media")
        media_from_tracker(ticket)


def get_ticket_from_tracker():
    """
    Get a ricket from the tracker an populate local variables
    """

    logging.info('getting ticket from ' + url)
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


def media_from_tracker(t):
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
            r = create_event(t, api_url, api_key, orig_language)
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

    else:
        # get the language of the encoding. We handle here multi lang video files
        language = languages[t.language_index]
        filename = t.language_template % language
        filename = filename + '.' + t.profile_extension
        logging.debug('Choosing ' + language + ' with LanguageIndex ' + str(t.language_index) + ' and filename ' + filename)

    if t.profile_slug == 'hd' and re.match('(..)-(..)', t.language):
        # if a second language is configured, remux the video to only have the one audio track and upload it twice
        logger.debug('remuxing dual-language video into two parts')

        # remember that this is multi language release
        multi_language = True

            # publish the media file on media
    if 'Publishing.Media.MimeType' not in t:
        setTicketFailed(t.ticket_id,
                        'Publishing failed: No mime type, please use property Publishing.Media.MimeType in encoding '
                        'profile! \n' + str('Error '), url, group, host, secret)

    mime_type = t['Publishing.Media.MimeType']

    # set hq filed based on ticket encoding profile slug
    if 'hd' in t['EncodingProfile.Slug']:
        hq = True
    else:
        hq = False

    # if we have before decided to do two language web release we don't want to set the html5 flag for the master
    if multi_language:
        html5 = False
    else:
        html5 = True

    try:
        upload_file(t, local_filename, filename, folder, ssh)
        create_recording(local_filename, filename, api_url, download_base_url, api_key, guid, mime_type, folder,
                         video_base, language, hq, html5, t)
    except RuntimeError as err:
        setTicketFailed(ticket_id, "Publishing failed: \n" + str(err), url, group, host, secret)
        logging.error('Publishing failed: \n' + str(err))
        sys.exit(-1)

def mux_to_single_language(t):
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


def youtube_from_tracker():
    """
    Publish the file to YouTube.
    """
    try:
        youtube_urls = publish_youtube(ticket, config['youtube']['client_id'], config['youtube']['secret'])
        props = {}
        for i, youtubeUrl in enumerate(youtube_urls):
            props['YouTube.Url' + str(i)] = youtubeUrl

        setTicketProperties(ticket_id, props, url, group, host, secret)

    except RuntimeError as err:
        setTicketFailed(ticket_id, 'Publishing failed: \n' + str(err), url, group, host, secret)
        logging.error('Publishing failed: \n' + str(err))
        sys.exit(-1)


_ticket = get_ticket_from_tracker()
choose_target_from_properties(_ticket)
logging.info("set ticket done")
setTicketDone(_ticket.ticket_id, url, group, host, secret)
send_tweet(_ticket, token, token_secret, consumer_key, consumer_secret)
