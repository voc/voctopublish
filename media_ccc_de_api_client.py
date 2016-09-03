#!/usr/bin/python3
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
# generate thumbs

import subprocess
import urllib.request, urllib.parse, urllib.error
import requests
import json
import sys
import os
import time
import logging
import paramiko
import errno
logger = logging.getLogger()


class MediaAPI:
    
    config = {}
    
    def __init__(self, config):
        self.config = config
    
    #=== make a new event on media
    def create_event(self, ticket, orig_language):
        logger.info(("## generating new event on " + self.config['api_url'] + " ##"))
        
        #prepare some variables for the api call
        local_filename_base = ticket['local_filename_base']
        url = api_url + 'events'
        
        if 'Fahrplan.Person_list' in ticket:
            people = ticket['Fahrplan.Person_list'].split(', ') 
        else:
            people = [ ]
         
        if 'Media.Tags' in ticket:
            tags = ticket['Media.Tags'].replace(' ', '').split(',')
        else:
            tags = [ ticket['Project.Slug'] ]
     
        if orig_language == None:
            orig_language = ''
        
         
        # have a look at https://github.com/voc/media.ccc.de/blob/master/app/controllers/api/events_controller.rb this changes in blink of an eye
        # DONT EVEN BLINK !!!!    
        headers = {'CONTENT-TYPE' : 'application/json'}
        payload = {'api_key' : self.config['api_key'],
                   'acronym' : str(ticket['Publishing.Media.Slug']),
                   'event' : {
                              'guid' : str(ticket['Fahrplan.GUID']),
                              'slug' : str(ticket['Fahrplan.Slug']),
                              'title' : str(ticket['Fahrplan.Title']),
                              'subtitle' : str(ticket['Fahrplan.Subtitle']),
                              'link' : "https://c3voc.de",
                              'original_language': orig_language,
                              'thumb_filename' : str(local_filename_base) + ".jpg",
                              'poster_filename' : str(local_filename_base) + "_preview.jpg",
                              'conference_id' : str(ticket['Publishing.Media.Slug']),
                              'description' : str(ticket['Fahrplan.Abstract']),
                              'date' : str(ticket['Fahrplan.Date']),
                              'persons': people,
                              'tags': tags,
                              'promoted' : False,
                              'release_date' : str(time.strftime("%Y-%m-%d"))
                            }
        }     
        logger.debug(payload)
    
        #call media api (and ignore SSL this should be fixed on media site)
        try:
            r = requests.post(self.config['api_url'], headers=headers, data=json.dumps(payload), verify=False)
        except requests.packages.urllib3.exceptions.MaxRetryError as err:
            raise RuntimeError("Error during creating of event: " + str(err))
    
        return r
    
     #=== create_recording a file on media
    def create_recording(self, ticket, local_filename, filename, download_base_url, mime_type, folder, video_base, language, hq, html5):
        logger.info(("## publishing "+ filename + " to " + self.config['api_url'] + " ##"))
        
        # make sure we have the file size and length
        file_details = get_file_details(ticket, local_filename, video_base)

        # have a look at https://github.com/voc/media.ccc.de/blob/master/app/controllers/api/recordings_controller.rb and DONT EVEN BLINK!!!
        url = self.config['api_url'] + 'recordings'
        headers = {'CONTENT-TYPE' : 'application/json'}
        payload = {'api_key' : self.config['api_key'],
                   'guid' :  str(ticket['Fahrplan.GUID']),
                   'acronym' : str(ticket['Publishing.Media.Slug']),
                   'recording' : {'folder' : folder,
                                  'filename' : filename,
                                  'mime_type' : mime_type,
                                  'language' : language,
                                  'high_quality' : hq,
                                  'html5' : html5,
                                  'size' : str(file_details['size']),
                                  'width' : str(file_details['width']),
                                  'height' : str(file_details['height']),
                                  'length' : str(file_details['length'])
                                }
                   }
        logger.debug(payload)
        try:
            r = requests.post(self.config['api_url'], headers=headers, data=json.dumps(payload), verify=False)
        except requests.exceptions.SSLError:
            raise RuntimeError("ssl cert error")
        except requests.packages.urllib3.exceptions.MaxRetryError as err:
            raise RuntimeError("Error during creating of event: " + str(err))
        except:
            raise RuntimeError("Unhandled ssl / retry problem")

        
        if r.status_code != 200 and r.status_code != 201:
            raise RuntimeError(("ERROR: Could not create_recording talk: " + str(r.status_code) + " " + r.text))
        
        logger.info(("publishing " + filename + " done"))
        return True

    



# SCP functions  
# Connect to the upload host.  
def connect_ssh(ticket):
    logger.info("## Establishing SSH connection ##")
    client = paramiko.SSHClient()
    #client.get_host_keys().add(upload_host,'ssh-rsa', key)
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ticket['Publishing.Media.Host'], username=ticket['Publishing.Media.User'], password="notused")
    except paramiko.SSHException:
        logger.error("SSH negotiation failed")
        raise RuntimeError("SFTP-Error: SSH negotiation failed")
    except paramiko.AuthenticationException:
        logger.error("Authentication failed. Please check credentials")
        raise RuntimeError("SFTP-Error: Authentication failed. Please check credentials")
    except paramiko.BadHostKeyException:
        logger.error ("Bad host key. Check your known_hosts file")
        raise RuntimeError ("SFTP-Error: Bad host key. Check your known_hosts file")
    except paramiko.PasswordRequiredException:
        logger.error("Password required. No ssh key in the agent?")
        raise RuntimeError("SFTP-Error: Password required. No ssh key in the agent?")
    except:
        logger.error("Could not open ssh connection")
        raise RuntimeError("SFTP-Error: Could not open ssh connection")
        
    logger.info("SSH connection established")
    sftp_client = paramiko.SFTPClient.from_transport(client.get_transport())
    sftp_client.keep_ssh = client #this prevents the garbage collector from stealing our client instance
    return sftp_client

#== push the thumbs to the upload host
def upload_thumbs(ticket, sftp):
    logger.info("## uploading thumbs ##")
    
    # check if ssh connection is open
    if sftp is None:
        sftp = connect_ssh(ticket)
    thumbs_ext = {".jpg","_preview.jpg"}
    for ext in thumbs_ext:
        try:
            logger.debug("Uploading " + ticket['Publishing.Path'] + ticket['local_filename_base'] + ext + " to " + ticket['Publishing.Media.Thumbpath'] + str(ticket['local_filename_base']) + ext)
            sftp.put(str(ticket['Publishing.Path']) + str(ticket['local_filename_base']) + ext, str(ticket['Publishing.Media.Thumbpath']) + str(ticket['local_filename_base']) + ext)
        except paramiko.SSHException as err:
            logger.error("could not upload thumb because of SSH problem")
            logger.error(err)
            raise RuntimeError("SFTP-Error: could not upload thumb because of SSH problem - "+str(err))
        except IOError as err:
            logger.error("could not create file in upload directory")
            logger.error(err)
            raise RuntimeError("SFTP-Error: could not create file in upload directory - "+str(err))
            
    print ("uploading thumbs done")

#== uploads a file from path relative to the output dir to the same path relative to the upload_dir
def upload_file(ticket, local_filename, filename, folder, sftp):
    logger.info("## uploading "+ ticket['Publishing.Path'] + filename + " ##")
    
    # Check if ssh connection is open.
    if sftp is None:
        sftp = connect_ssh(ticket)
  
    # Check if the directory exists and if not create it.
    # This only works for the format subdiers not for the event itself
    try:
        sftp.stat(ticket['Publishing.Media.Path'] + folder)
    except IOError as e:
        if e.errno == errno.ENOENT:
            try:
                sftp.mkdir(ticket['Publishing.Media.Path'] + folder)
            except IOError as e:
                logger.error(e)
    
    # Check if the file already exists and remove it
    try: 
        sftp.stat(ticket['Publishing.Media.Path'] + folder + "/" + filename)
    except IOError:
        pass #if the file not exists we can can go to the upload
    else:   
        try:
            sftp.remove(ticket['Publishing.Media.Path'] + folder + "/" +  filename )
        except IOError as e:
            logger.error(e)
            
    # Upload the file
    try:
        sftp.put(str(ticket['Publishing.Path']) + local_filename, ticket['Publishing.Media.Path'] + folder + "/" +  filename )
    except paramiko.SSHException as err:
        logger.error("could not upload recording because of SSH problem")
        logger.error(err)
        raise RuntimeError("SFTP-Error: could not upload recording because of SSH problem - " +str(err))
    except IOError as err:
        logger.error("could not create file in upload directory")
        logger.error(err)
        raise RuntimeError("SFTP-Error: could not create file in upload directory - " +str(err))
            
    logger.info("uploading " + filename + " done")


#== generate thumbnails for media.ccc.de
def make_thumbs(ticket):    
    logger.info(("## generating thumbs for "  + str(ticket['Publishing.Path'])  + str(ticket['local_filename']) + " ##"))

    try:
        #todo this doesnt have to be a subprocess, build thumbs in python
        subprocess.check_call(["postprocessing/generate_thumb_autoselect_compatible.sh", str(ticket['Publishing.Path']) + str(ticket['local_filename']), str(ticket['Publishing.Path'])])
    except subprocess.CalledProcessError as err:
        logger.error("A fault occurred")
        logger.error("Fault code: %d" % err.returncode)
        logger.error("Fault string: %s" % err.output)
        logger.error("Command %s" % err.cmd)
        raise RuntimeError("ERROR: Generating thumbs:" + err.cmd)
         
    logger.info("thumbnails created")
    return True

#=== get filesize and length of the media file
def get_file_details(ticket, local_filename, video_base):
    if local_filename == None:
        raise RuntimeError("Error: No filename supplied.")
        
    filesize = os.stat(video_base + local_filename).st_size
    filesize = int(filesize / 1024 / 1024)
                              
    try:
        r = subprocess.check_output('ffprobe -print_format flat -show_format -loglevel quiet ' + video_base + local_filename +' 2>&1 | grep format.duration | cut -d= -f 2 | sed -e "s/\\"//g" -e "s/\..*//g" ', shell=True)
        length = int(r.decode())
    except:
        raise RuntimeError("ERROR: could not file details: " + str(r))
    #result = commands.getstatusoutput("ffprobe " + output + path + filename + " 2>&1 | grep Duration | cut -d ' ' -f 4 | sed s/,// ")
    
    if length == 0:
        raise RuntimeError("Error: file length is 0")
    
    width = 0
    height = 0
    if ticket['EncodingProfile.Slug'] not in ["mp3", "opus", "mp3-2", "opus-2"]:    
        try:
            r = subprocess.check_output('ffmpeg -i ' + video_base + local_filename + ' 2>&1 | grep Stream | grep -oP ", \K[0-9]+x[0-9]+"',shell=True)
            resolution = r.decode()
            resolution = resolution.partition('x')
            width = resolution[0].strip()
            height = resolution[2].strip()
        except:
            raise RuntimeError("ERROR: could not get duration ")
    
    logger.debug("filesize: " + str(filesize) + " length: " + str(length))
    
    return {
        'size' : filesize,
        'length' : length, 
        'width' : width,
        'height' : height
    }
