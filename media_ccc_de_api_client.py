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
        sys.exit(1)
    except paramiko.AuthenticationException:
        logger.error("Authentication failed. Please check credentials")
        sys.exit(1)
    except paramiko.BadHostKeyException:
        logger.error ("Bad host key. Check your known_hosts file")
        sys.exit(1)
    except paramiko.PasswordRequiredException:
        logger.error("Password required. No ssh key in the agent?")
        sys.exit(1)
    except:
        logger.error("Could not open ssh connection")
        sys.exit(1)
        
    logger.info("SSH connection established")
    sftp_client = paramiko.SFTPClient.from_transport(client.get_transport())
    sftp_client.keep_ssh = client #this prevents the garbage collector from stealing our client instance
    return sftp_client

#== push the thumbs to the upload host
def upload_thumbs(ticket,sftp):
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
            sys.exit(1)
        except IOError as err:
            logger.error("could not create file in upload directory")
            logger.error(err)
            sys.exit(1)
            
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
    except IOError as err:
        logger.error("could not create file in upload directory")
        logger.error(err)
            
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
        raise RuntimeError(err.cmd)
        return False
         
    logger.info("thumbnails created")
    return True
    
#=== make a new event on media
def create_event(ticket, api_url, api_key, orig_language):
    logger.info(("## generating new event on " + api_url + " ##"))
    
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
    payload = {'api_key' : api_key,
	       'acronym' : str(ticket['Project.Slug']),
               'event' : {
      	                  'guid' : str(ticket['Fahrplan.GUID']),
                          'slug' : str(ticket['Publishing.Media.Slug']),
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
        logger.debug("api url: " + url)
        r = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
    except requests.packages.urllib3.exceptions.MaxRetryError as err:
        raise RuntimeError("Error during creating of event: " + str(err))

    return r
#=== get filesize and length of the media file
def get_file_details(ticket, local_filename, video_base, ret):
    if local_filename == None:
        raise RuntimeError("Error: No filename supplied.")
        return False
        
    global filesize    
    filesize = os.stat(video_base + local_filename).st_size
    filesize = int(filesize / 1024 / 1024)
    
    try:
        global r
        r = subprocess.check_output('ffprobe -print_format flat -show_format -loglevel quiet ' + video_base + local_filename +' 2>&1 | grep format.duration | cut -d= -f 2 | sed -e "s/\\"//g" -e "s/\..*//g" ', shell=True)
    except:
        raise RuntimeError("ERROR: could not get duration " + exc_value)
        return False
    #result = commands.getstatusoutput("ffprobe " + output + path + filename + " 2>&1 | grep Duration | cut -d ' ' -f 4 | sed s/,// ")
    global length
    length = int(r.decode())
    
    if ticket['EncodingProfile.Slug'] not in ["mp3", "opus", "mp3-2", "opus-2"]:    
        try:
            r = subprocess.check_output('ffmpeg -i ' + video_base + local_filename + ' 2>&1 | grep Stream | grep -oP ", \K[0-9]+x[0-9]+"',shell=True)
        except:
            raise RuntimeError("ERROR: could not get duration ")
            return False
        resolution = r.decode()
        resolution = resolution.partition('x')
        width = resolution[0]
        height = resolution[2]
    else: #we have an audio only release so we set a 0 resolution
         width = 0
         height = 0
    
    if length == 0:
        raise RuntimeError("Error: file length is 0")
        return False
    else:
        logger.debug("filesize: " + str(filesize) + " length: " + str(length))
        ret.append(filesize)
        ret.append(length)
        ret.append(width)
        ret.append(height)
        return True

#=== create_recording a file on media
def create_recording(local_filename, filename, api_url, download_base_url, api_key, guid, mime_type, folder, video_base, language, hq, html5, ticket):
    logger.info(("## publishing "+ filename + " to " + api_url + " ##"))
    
    # make sure we have the file size and length
    ret = []
    if not get_file_details(ticket, local_filename, video_base, ret):
        return False
        
    # have a look at https://github.com/voc/media.ccc.de/blob/master/app/controllers/api/recordings_controller.rb and DONT EVEN BLINK!!!
    url = api_url + 'recordings'
    headers = {'CONTENT-TYPE' : 'application/json'}
    payload = {'api_key' : api_key,
               'guid' : guid,
	       'acronym' : ticket['Project.Slug'],
               'recording' : {'folder' : folder,
                              'filename' : filename,
                              'mime_type' : mime_type,
                              'language' : language,
                              'high_quality' : hq,
                              'html5' : html5,
                              'size' : str(ret[0]),
                              'width' : str(ret[2]),
                              'height' : str(ret[3]),
                              'length' : str(ret[1])
                            }
               }
    logger.debug(payload)
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
    except requests.exceptions.SSLError:
        raise RuntimeError("ssl cert error")
        return False
    except requests.packages.urllib3.exceptions.MaxRetryError as err:
        raise RuntimeError("Error during creating of event: " + str(err))
        return False
    except:
        raise RuntimeError("Unhandelt ssl / retry problem")
        return False
    
    if r.status_code != 200 and r.status_code != 201:
        raise RuntimeError(("ERROR: Could not create_recording talk: " + str(r.status_code) + " " + r.text))
        return False
    
    logger.info(("publishing " + filename + " done"))
    return True
