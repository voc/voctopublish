#!/usr/bin/env python3.4
#    Copyright (C) 2014  derpeter
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
import re
import traceback

import c3t_rpc_client
import media_ccc_de_api_client as media
import youtube_client
import twitter_client


'''
TODO
* remove globals
* remove str()
* replace all/most setTicketFailed with raise RuntimeError()

'''

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

logging.addLevelName( logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
logging.addLevelName( logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
logging.addLevelName( logging.INFO, "\033[1;32m%s\033[1;0m" % logging.getLevelName(logging.INFO))
logging.addLevelName( logging.DEBUG, "\033[1;85m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# uncomment the next line to add filename and linenumber to logging output
#formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s {%(filename)s:%(lineno)d} %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

logging.info("C3TT publishing")
logging.debug("reading config")

### handle config
#make sure we have a config file
if not os.path.exists('client.conf'):
    logging.error("Error: config file not found")
    sys.exit(1)
    
config = configparser.ConfigParser()
config.read('client.conf')


tracker = c3t_rpc_client.C3TrackerAPI(config['C3Tracker'])
mediaAPI = media.MediaAPI(config['media.ccc.de'])

sftp = None
ssh = None

#internal vars
ticket = None



################################# Here be dragons #################################
def get_ticket_from_tracker():
    logging.info("getting ticket from " + config['C3Tracker']['url'])
    logging.info("=========================================")
    
    #check if we got a new ticket
    ticket_id = tracker.assignNextUnassignedForState(config['C3Tracker']['from_state'], config['C3Tracker']['to_state'])
    if ticket_id == False:
        logging.info("No ticket for this task, exiting")
        return False
    
    logging.info("Ticket ID:" + str(ticket_id))
    ticket = tracker.getTicketProperties(ticket_id)
    ticket['Id'] = ticket_id
    
    logging.debug("Ticket: " + str(ticket))

    return ticket

def process_ticket(ticket):
    

    #slug = ticket['Fahrplan.Slug']    

    acronym = ticket['Project.Slug']
    filename = str(ticket['EncodingProfile.Basename']) + "." + str(ticket['EncodingProfile.Extension'])
    title = ticket['Fahrplan.Title']
    if 'Fahrplan.Person_list' in ticket:
            people = ticket['Fahrplan.Person_list'].split(', ') 
    else:
            people = [ ]
    if 'Media.Tags' in ticket:
            tags = ticket['Media.Tags'].replace(' ', ''). \
                                        split(',')
    else:
            tags = [ ticket['Project.Slug'] ]

    ticket['local_filename_base'] = str(ticket['Fahrplan.ID']) + "-" + ticket['EncodingProfile.Slug']
    ticket['local_filename'] = ticket['local_filename_base'] + "." + ticket['EncodingProfile.Extension']
    
    
    download_base_url =  str(ticket['Publishing.Base.Url'])
    profile_extension = ticket['EncodingProfile.Extension']

    if 'Record.Language' in ticket:
        # FIXME:
        language = str(ticket['Record.Language'])

    else:
        logging.error("No Record.Language property in ticket")
        raise RuntimeError("No Record.Language property in ticket")
    
    logging.debug("Language from ticket " + str(language))
    
    
    if not 'Fahrplan.Abstract' in ticket:
        ticket['Fahrplan.Abstract'] = ''
    #TODO add here some try magic to catch missing properties
    if not 'Fahrplan.Subtitle' in ticket:
        ticket['Fahrplan.Subtitle'] = ''

    

    title = ticket['Fahrplan.Title']
    folder = ticket['EncodingProfile.MirrorFolder']
    

         
    if not os.path.isfile(ticket['Publishing.Path'] + ticket['local_filename']):
        raise RuntimeError("Source file does not exist (%s)" % (ticket['Publishing.Path'] + ticket['local_filename']))
    if not os.path.exists(ticket['Publishing.Path']):
        raise RuntimeError("Output path does not exist (%s)" % (ticket['Publishing.Path']))
    else: 
        if not os.access(ticket['Publishing.Path'], os.W_OK):
            raise RuntimeError("Output path is not writable (%s)" % (ticket['Publishing.Path']))


    return True

def mediaFromTracker(ticket):
    logging.info("creating event on " + api_url)
    logging.info("=========================================")

    mutlilang = False
    
    
    
    #** create a event on media
    # if we have an audio file we skip this part, as we need to generate thumbs 
    if ticket['EncodingProfile.Slug'] not in ["mp3", "opus", "mp3-2", "opus-2"]:
         
        # FIXME: media does not create events when wrong language is set
        langs = language.rsplit('-')


        
        #create the event
        #TODO at the moment we just try this and look on the error. 
        #         maybe check if event exists; lookup via uuid
        r = mediaAPI.create_event(ticket)
        if r.status_code in [200, 201]:
            logger.info("new event created")
        elif r.status_code == 422:
            logger.info("event already exists. => publishing")
            logger.info("  server said: " + r.text)
        else:
            raise RuntimeError(("ERROR: Could not add event: " + str(r.status_code) + " " + r.text))
        
        #generate the thumbnails (will not overwrite existing thumbs)
        if not os.path.isfile(ticket['Publishing.Path'] + ticket['local_filename_base'] + ".jpg"):
            media.make_thumbs(ticket)
            media.upload_thumbs(ticket, sftp)
        else:
            logger.info("thumbs exist. skipping")

            
    # audio release
    else: 
        # get the language of the encoding. We handle here multi lang releases
        if not 'Encoding.LanguageIndex' in ticket:
            raise RuntimeError("Creating event failed, Encoding.LanguageIndex not defined")

        #TODO when is Encoding.LanguageIndex set?
        lang_id = int(ticket['Encoding.LanguageIndex'])
        langs = language.rsplit('-')
        # FIXME: media does not create recordings when wrong language is set
        language = str(langs[lang_id])
        filename = str(ticket['Encoding.LanguageTemplate']) % (language)
        filename = filename + '.' + str(ticket['EncodingProfile.Extension'])
        #filename = str(slug + '-' + str(ticket['Fahrplan.ID']) + '-' + language + '-' + str(ticket['Encoding.LanguageTemplate']) + '.' + str(ticket['EncodingProfile.Extension'] )
        logging.debug('Choosing ' + language +' with LanguageIndex ' + str(lang_id) + ' and filename ' + filename)

    #publish the media file on media
    if not 'Publishing.Media.MimeType' in ticket:
        raise RuntimeError("No mime type, please use property Publishing.Media.MimeType in encoding profile!")
    
    
    multilang = False
    if re.match('(...?)-(...?)', ticket['Record.Language']):
        #remember that this is multilang release
        multilang = True

    #if a second language is configured, remux the video to only have the one audio track and upload it twice
    if multilang and profile_slug == 'hd':
        logger.debug('remuxing dual-language video into two parts')

        #prepare filenames 
        outfilename1 = str(ticket['Fahrplan.ID']) + "-" +ticket['EncodingProfile.Slug'] + "-audio1." + ticket['EncodingProfile.Extension']
        outfile1 = str(ticket['Publishing.Path']) + "/" + outfilename1
        outfilename2 = str(ticket['Fahrplan.ID']) + "-" +ticket['EncodingProfile.Slug'] + "-audio2." + ticket['EncodingProfile.Extension']
        outfile2 = str(ticket['Publishing.Path']) + "/" + outfilename2
        langs = language.rsplit('-')
        filename1 = str(ticket['Encoding.LanguageTemplate']) % (str(langs[0])) + '.' + str(ticket['EncodingProfile.Extension'])
        filename2 = str(ticket['Encoding.LanguageTemplate']) % (str(langs[1])) + '.' + str(ticket['EncodingProfile.Extension'])
        
        #mux two videos wich one language each
        logger.debug('remuxing with original audio to '+outfile1)
        
        if subprocess.call(['ffmpeg', '-y', '-v', 'warning', '-nostdin', '-i', ticket['Publishing.Path'] + ticket['local_filename'], '-map', '0:0', '-map', '0:1', '-c', 'copy', '-movflags', 'faststart', outfile1]) != 0:
            raise RuntimeError('error remuxing '+infile+' to '+outfile1)

        logger.debug('remuxing with translated audio to '+outfile2)

        if subprocess.call(['ffmpeg', '-y', '-v', 'warning', '-nostdin', '-i', ticket['Publishing.Path'] + ticket['local_filename'], '-map', '0:0', '-map', '0:2', '-c', 'copy', '-movflags', 'faststart', outfile2]) != 0:
            raise RuntimeError('error remuxing '+infile+' to '+outfile2)
        
        media.upload_file(ticket, outfilename1, filename1, 'h264-hd-web', sftp);
        mediaAPI.create_recording(ticket, outfilename1, filename1, download_base_url, 'h264-hd-web', str(langs[0]), True)

        media.upload_file(ticket, outfilename2, filename2, 'h264-hd-web', sftp);
        mediaAPI.create_recording(ticket, outfilename2, filename2, download_base_url, 'h264-hd-web', str(langs[1]), True)

         
    #if we have before decided to do two language web release we don't want to set the html5 flag for the master 
    if (multilang):
        html5 = False
    else:
        html5 = True
    

    media.upload_file(ticket, ticket['local_filename'], filename, folder, ssh);
    mediaAPI.create_recording(ticket, ticket['local_filename'], filename, download_base_url, folder, language, html5)

                 
                                      
def youtubeFromTracker(ticket):
    youtube = youtube_client.YoutubeAPI(ticket, config['youtube'])
    youtubeUrls = youtube.publish(ticket)
    props = {}
    for i, youtubeUrl in enumerate(youtubeUrls):
        props['YouTube.Url'+str(i)] = youtubeUrl

    tracker.setTicketProperties(ticket['Id'], props)

#def main():
# 'main method'

try:
    ticket = get_ticket_from_tracker()
    
    if ticket:
        process_ticket(ticket)
        
        published_to_media = False

        logging.debug("encoding profile youtube flag: " + ticket['Publishing.YouTube.EnableProfile'] + " project youtube flag: " + ticket['Publishing.YouTube.Enable'])
        if ticket['Publishing.YouTube.Enable'] == "yes" and ticket['Publishing.YouTube.EnableProfile'] == "yes":
            if 'YouTube.Url0' in ticket and ticket['YouTube.Url0'] != "":        
                logging.debug("publishing on youtube")
                youtubeFromTracker(ticket)
    
        logging.debug("encoding profile media flag: " + ticket['Publishing.Media.EnableProfile'] + " project media flag: " + ticket['Publishing.Media.Enable'])
        if ticket['Publishing.Media.EnableProfile'] == "yes" and ticket['Publishing.Media.Enable'] == "yes":
            logging.debug("publishing on media")
    
            mediaFromTracker(ticket)
            published_to_media = True
            
        logging.info("set ticket done")
        tracker.setTicketDone(ticket['Id'])

        if published_to_media:
            try:
                twitter_client.send_tweet(ticket, config['twitter'])
            except Exception as err:
                logging.error("Error tweeting (but releasing succeeded): \n" + str(err))

except c3t_rpc_client.C3TError as err:
    # we can not notify the tracker, as we might go into an endless loop  
    logging.error("Tracker communication failed: \n" + str(err))

# Runtime errors occur when the script is missing ticket attributes or files
except RuntimeError as err:
    tracker.setTicketFailed(ticket['Id'], str(err))
    logging.error("Publishing failed: " + str(err))
# Exceptions are errors in the publishing Python source code   
except Exception as err:
    tracker.setTicketFailed(ticket['Id'], traceback.format_exc())
    logging.error("Publishing failed: \n" + traceback.format_exc())


#if __name__ == '__main__':
#    main()
