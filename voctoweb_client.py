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
# generate thumbs

import errno
import json
import logging
import os
import subprocess
import sys
import time

import paramiko
import requests

from ticket_module import Ticket


class VoctowebClient:
    def __init__(self, t: Ticket):
        self.t = t
        self.ssh = None
        self.sftp = None

    def connect_ssh(self):
        """
        Open an SSH connection to the media.ccc.de CDN master
        """
        logging.info('Establishing SSH connection')
        self.ssh = paramiko.SSHClient()
        # TODO set hostkey handling via config
        # client.get_host_keys().add(upload_host,'ssh-rsa', key)
        self.ssh.load_system_host_keys()
        # self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.ssh.connect(self.t.media_host, username=self.t.media_user)
        except paramiko.AuthenticationException:
            raise VoctowebException('Authentication failed. Please check credentials')
        except paramiko.BadHostKeyException:
            raise VoctowebException('Bad host key. Check your known_hosts file')
        except paramiko.PasswordRequiredException:
            raise VoctowebException('Password required. No ssh key present?')
        except paramiko.SSHException:
            raise VoctowebException('SSH negotiation failed')

        self.sftp = self.ssh.open_sftp()
        logging.info('SSH connection established to ' + str(self.t.media_host))

    def upload_thumbs(self):
        """
        Upload thumbnails to the media.ccc.de CDN master.
        :param t:
        :param sftp:
        """
        logging.info("## uploading thumbs ##")

        # check if ssh connection is open
        if self.ssh is None:
            self.connect_ssh()

        thumbs_ext = {".jpg", "_preview.jpg"}
        for ext in thumbs_ext:
            try:
                logging.debug(
                    'Uploading ' + self.t.path + self.t.filename_base + ext + " to " + self.t.media_thump_path + self.t.local_filename_base + ext)
                self.sftp.put(self.t.video_base + self.t.local_filename_base + ext,
                              self.t.media_thump_path + self.t.local_filename_base + ext)
            except paramiko.SSHException as err:
                raise VoctowebException('could not upload thumb because of SSH problem ' + str(err))
            except IOError as err:
                raise VoctowebException('could not create file in upload directory ' + str(err))

        logging.info('uploading thumbs done')

    def upload_file(self, local_filename, filename, folder):
        """
        Uploads a file from path relative to the output dir to the same path relative to the upload_dir
        We can't use the file and folder names from the ticket here as we need to change these for multi language audio

        :param local_filename:
        :param filename:
        :param folder:
        """
        logging.info("uploading " + self.t.video_base + filename)

        # Check if ssh connection is open.
        if self.sftp is None:
            self.connect_ssh()

        # Check if the directory exists and if not create it.
        # This only works for the format subdiers not for the event itself
        try:
            self.sftp.stat(self.t.media_path + folder)
        except IOError as e:
            if e.errno == errno.ENOENT:
                try:
                    self.sftp.mkdir(self.t.media_path + folder)
                except IOError as e:
                    logging.error(e)

        # Check if the file already exists and remove it
        try:
            self.sftp.stat(self.t.media_path + folder + "/" + filename)
        except IOError:
            pass  # if the file not exists we can can go to the upload
        else:
            try:
                self.sftp.remove(self.t.media_path + folder + "/" + filename)
            except IOError as e:
                logging.error(e)

        # Upload the file
        try:
            self.sftp.put(self.t.video_base + local_filename,
                          self.t.media_path + folder + "/" + filename)
        except paramiko.SSHException as err:
            logging.error("could not upload recording because of SSH problem")
            logging.error(err)
        except IOError as err:
            logging.error("could not create file in upload directory")
            logging.error(err)

        logging.info("uploading " + filename + " done")

    # generate thumbnails for media.ccc.de
    def make_thumbs(self):
        """
        This function calls the thumbnail generator script
        :return:
        """
        logging.info(
            ("generating thumbs for " + self.t.video_base + self.t.local_filename))

        try:
            # todo this doesn't have to be a subprocess, build thumbs in python
            subprocess.check_call(["postprocessing/generate_thumb_autoselect_compatible.sh",
                                   self.t.video_base + self.t.local_filename,
                                   self.t.video_base])
        except subprocess.CalledProcessError as err:
            logging.error("A fault occurred")
            logging.error("Fault code: %d" % err.returncode)
            logging.error("Fault string: %s" % err.output)
            logging.error("Command %s" % err.cmd)

        logging.info("thumbnails created")

    def create_event(self, api_url, api_key, orig_language):
        """
        # create a new event on the media.ccc.de API host

        :param api_url:
        :param api_key:
        :param orig_language:
        :return:
        """
        logging.info(("generating new event on " + api_url))

        # prepare some variables for the api call
        url = api_url + 'events'

        if orig_language is None:
            orig_language = ''

        # API code https://github.com/voc/media.ccc.de/blob/master/app/controllers/api/events_controller.rb
        headers = {'CONTENT-TYPE': 'application/json'}
        payload = {'api_key': api_key,
                   'acronym': self.t.media_slug,
                   'event': {
                       'guid': self.t.guid,
                       'slug': self.t.slug,
                       'title': self.t.title,
                       'subtitle': self.t.subtitle,
                       'link': "https://c3voc.de",  # todo do something more use full here
                       'original_language': orig_language,
                       'thumb_filename': self.t.local_filename_base + ".jpg",
                       'poster_filename': self.t.local_filename_base + "_preview.jpg",
                       'conference_id': self.t.media_slug,
                       'description': self.t.abstract,
                       'date': self.t.date,
                       'persons': self.t.people,
                       'tags': self.t.tags,
                       'promoted': False,
                       'release_date': str(time.strftime("%Y-%m-%d"))
                   }
                   }
        logging.debug("api url: " + url + ' header: ' + str(headers) + ' payload: ' + str(payload))

        # call media API
        r = ''
        try:
            # TODO make ssl verify a config option
            # r = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
            r = requests.post(url, headers=headers, data=json.dumps(payload))
        except requests.packages.urllib3.exceptions.MaxRetryError as err:
            raise RuntimeError("Error during creating of event: " + str(err))

        return r

    def get_file_details(self, local_filename, ret):
        """
        get file size and length of the media file
        :param local_filename:
        :param ret:
        :return:
        """
        if local_filename is None:
            raise RuntimeError('Error: No filename supplied.')

        file_size = os.stat(self.t.video_base + local_filename).st_size
        file_size = int(file_size / 1024 / 1024)

        try:
            global r
            r = subprocess.check_output(
                'ffprobe -print_format flat -show_format -loglevel quiet ' + self.video_base + local_filename + ' 2>&1 | grep format.duration | cut -d= -f 2 | sed -e "s/\\"//g" -e "s/\..*//g" ',
                shell=True)
        except:
            raise RuntimeError("ERROR: could not get duration " + r)

        length = int(r.decode())

        if self.t.slug not in ["mp3", "opus", "mp3-2", "opus-2"]:
            try:
                r = subprocess.check_output(
                    'ffmpeg -i ' + self.t.video_base + local_filename + ' 2>&1 | grep Stream | grep -oP ", \K[0-9]+x[0-9]+"',
                    shell=True)
            except:
                raise RuntimeError("ERROR: could not get duration ")

            resolution = r.decode()
            resolution = resolution.partition('x')
            width = resolution[0]
            height = resolution[2]
        else:  # we have an audio only release so we set a 0 resolution
            width = 0
            height = 0

        if length == 0:
            raise RuntimeError("Error: file length is 0")
        else:
            logging.debug("filesize: " + str(file_size) + " length: " + str(length))
            ret.append(file_size)
            ret.append(length)
            ret.append(width)
            ret.append(height)
            return True

    def create_recording(self, local_filename, filename, api_url, api_key, folder, language, hq, html5):
        """
        create_recording a file on media
        :param local_filename: this is not necessarily the value from the ticket
        :param filename: this is not necessarily the value from the ticket
        :param api_url:
        :param api_key:
        :param folder: this is not necessarily the value from the ticket
        :param language:
        :param hq:
        :param html5:
        :return:
        """
        logging.info(("publishing " + filename + " to " + api_url))

        # make sure we have the file size and length
        ret = []
        if not self.get_file_details(local_filename, ret):
            return False

        # API code https://github.com/voc/media.ccc.de/blob/master/app/controllers/api/recordings_controller.rb
        url = api_url + 'recordings'
        headers = {'CONTENT-TYPE': 'application/json'}
        payload = {'api_key': api_key,
                   'guid': self.t.guid,
                   'acronym': self.t.slug,
                   'recording': {'folder': folder,
                                 'filename': filename,
                                 'mime_type': self.t.mime_type,
                                 'language': language,
                                 'high_quality': hq,
                                 'html5': html5,
                                 'size': str(ret[0]),
                                 'width': str(ret[2]),
                                 'height': str(ret[3]),
                                 'length': str(ret[1])
                                 }
                   }
        logging.debug(payload)
        try:
            # TODO ssl verify by config
            # r = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
            r = requests.post(url, headers=headers, data=json.dumps(payload))
        except requests.exceptions.SSLError:
            raise RuntimeError("ssl cert error")
        except requests.packages.urllib3.exceptions.MaxRetryError as err:
            raise RuntimeError("Error during creating of event: " + str(err))
        except:
            raise RuntimeError("Unhandelt ssl / retry problem")

        if r.status_code != 200 and r.status_code != 201:
            raise RuntimeError(("ERROR: Could not create_recording talk: " + str(r.status_code) + " " + r.text))

        logging.info(("publishing " + filename + " done"))
        return True


class VoctowebException(Exception):
    pass