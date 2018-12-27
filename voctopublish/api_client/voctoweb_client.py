#    Copyright (C) 2018  derpeter
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

import errno
import json
import logging
import os
import subprocess
import time
import tempfile
import operator
import paramiko
import requests
import glob

from model.ticket_module import Ticket
from api_client.select_thumbnail import calc_score


class VoctowebClient:
    def __init__(self, t: Ticket, api_key, api_url, ssh_host, ssh_port, ssh_user):
        self.t = t
        self.api_key = api_key
        self.api_url = api_url
        self.ssh = None
        self.sftp = None
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user

    def _connect_ssh(self):
        """
        Open an SSH connection to the voctoweb storage host
        """
        logging.info('Establishing SSH connection')
        self.ssh = paramiko.SSHClient()
        logging.getLogger("paramiko").setLevel(logging.INFO)
        # TODO set hostkey handling via config
        # client.get_host_keys().add(upload_host,'ssh-rsa', key)
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.ssh.connect(self.ssh_host, port=self.ssh_port, username=self.ssh_user, )
        except paramiko.AuthenticationException as e:
            raise VoctowebException('Authentication failed. Please check credentials ' + str(e)) from e
        except paramiko.BadHostKeyException:
            raise VoctowebException('Bad host key. Check your known_hosts file')
        except paramiko.SSHException as e:
            raise VoctowebException('SSH negotiation failed ' + str(e)) from e

        self.sftp = self.ssh.open_sftp()
        logging.info('SSH connection established to ' + str(self.ssh_host))

    def generate_thumbs(self):
        """
        This function generates thumbnails to be used on voctoweb
        :return:
        """
        source = os.path.join(self.t.publishing_path, self.t.local_filename)
        logging.info("generating thumbs for " + source)

        try:
            r = subprocess.check_output(
                'ffprobe -print_format flat -show_format -loglevel quiet ' + source + ' 2>&1 | grep format.duration | cut -d= -f 2 | sed -e "s/\\"//g" -e "s/\..*//g" ',
                shell=True)
        except Exception as e_:
            raise VoctowebException("ERROR: could not get duration " + r.decode('utf-8')) from e_

        length = int(r.decode())
#        length = av.container.open(os.path.join(self.t.publishing_path, self.t.local_filename).duration)

        outjpg = os.path.join(self.t.publishing_path, self.t.local_filename_base + '.jpg')
        outjpg_preview = os.path.join(self.t.publishing_path, self.t.local_filename_base + '_preview.jpg')

        with tempfile.TemporaryDirectory() as tmpdir:
            # now extract candidates and convert to non-anamorphic images
            # we use equidistant sampling, but skip parts of the file that might contain pre-/postroles
            # also, use higher resolution sampling at the beginning, as there's usually some interesting stuff there

            if length > 20:
                scores = {}
                interval = 180
                candidates = [20, 30, 40]  # some fixed candidates we always want to hit
                candidates.extend(list(range(15, length - 60, interval)))  # pick some more candidates based on the file length
                try:
                    for pos in candidates:
                        candidat = os.path.join(tmpdir, str(pos) + '.png')
                        r = subprocess.check_output('ffmpeg -loglevel error -ss ' + str(pos) + ' -i ' +
                                                    source +
                                                    ' -an -r 1 -filter:v "scale=sar*iw:ih" -vframes 1 -f image2 -pix_fmt yuv420p -vcodec png -y ' +
                                                    candidat,
                                                    shell=True)

                        scores[candidat] = calc_score(candidat)

                except Exception as e_:
                    raise VoctowebException("Could not extract candidates: " + str(r)) from e_

                sorted_scores = sorted(scores.items(), key=operator.itemgetter(1), reverse=True)
                winner = sorted_scores[0][0]
                logging.debug('Winner: ' + winner)
            else:
                winner = source

            # lanczos scaling algorithm produces a sharper image for small sizes than the default choice
            # set pix_fmt to create a be more compatible output, otherwise the input format would be kept
            try:
                r = subprocess.check_output(
                    'ffmpeg -loglevel error -i ' + winner + ' -filter_complex:v "scale=400:-1:lanczos" -f image2 -vcodec mjpeg -pix_fmt yuv420p -q:v 0 -y ' + outjpg,
                    shell=True)
            except subprocess.CalledProcessError as e_:
                raise VoctowebException("Could not scale outjpg: " + str(e_)) from e_

            try:
                r = subprocess.check_output(
                    'ffmpeg -loglevel error -i ' + winner + ' -f image2 -vcodec mjpeg -pix_fmt yuv420p -q:v 0 -y ' + outjpg_preview,
                    shell=True)
            except Exception as e_:
                raise VoctowebException("Could not scale outjpg_preview: " + r.decode('utf-8')) from e_

            logging.info("thumbnails generated")

    def upload_thumbs(self):
        """
        Upload thumbnails to the voctoweb storage.
        """
        logging.info("uploading thumbnails")

        # check if ssh connection is open
        if self.ssh is None:
            self._connect_ssh()

        thumbs_ext = {".jpg", "_preview.jpg"}
        for ext in thumbs_ext:
            file = os.path.join(self.t.publishing_path, self.t.local_filename_base + ext)
            if not os.path.isfile(file):
                raise VoctowebException('could not upload thumb because file ' + file + ' does not exist')
            target = os.path.join(self.t.voctoweb_thump_path, self.t.local_filename_base + ext)
            try:
                logging.debug(
                    'Uploading ' + file + " to " + target)
                self.sftp.put(file, target)
            except paramiko.SSHException as e:
                raise VoctowebException('could not upload thumb because of SSH problem: ' + str(e)) from e
            except IOError as e:
                raise VoctowebException('could not upload thumb to ' + target + ' because an remote error occured: ' + str(e)) from e

        logging.info('uploading thumbs done')

    def generate_timelens(self):
        """
        This function generates a visual timeline and thumbnail grids to be used on voctoweb
        """
        source = os.path.join(self.t.publishing_path, self.t.local_filename)
        logging.info("running timelens for " + source)

        outtimeline = os.path.join(self.t.publishing_path, self.t.local_filename_base + '.timeline.jpg')
        outthumbnails = os.path.join(self.t.publishing_path, self.t.local_filename_base + '.thumbnails.vtt')

        try:
            r = subprocess.check_output(['timelens', source, '-w', '1000', '-h', '90', '--timeline', outtimeline, '--thumbnails', outthumbnails])
        except subprocess.CalledProcessError as e_:
            raise VoctowebException("Could not run timelens: " + str(e_)) from e_

        logging.info("ran timelens successfully")

    def upload_timelens(self):
        """
        Upload timelens files to the voctoweb storage.
        """
        logging.info("uploading timelens files")

        # check if ssh connection is open
        if self.ssh is None:
            self._connect_ssh()

        basepath = os.path.join(self.t.publishing_path, self.t.local_filename_base)

        files = [basepath + ".timeline.jpg", basepath + ".thumbnails.vtt"] + glob.glob(basepath + ".thumbnails-*.jpg")
        for file in files:
            target = os.path.join(self.t.voctoweb_thump_path, os.path.basename(file))
            try:
                logging.debug(
                    'Uploading ' + file + " to " + target)
                self.sftp.put(file, target)
            except paramiko.SSHException as e:
                raise VoctowebException('could not upload thumb because of SSH problem ' + str(e)) from e
            except IOError as e:
                raise VoctowebException('could not upload thumb because of ' + str(e)) from e

        logging.info('uploading timelens files done')

    def upload_file(self, local_filename, remote_filename, remote_folder):
        """
        Uploads a file from path relative to the output dir to the same path relative to the upload_dir
        We can't use the file and folder names from the ticket here as we need to change these for multi language audio
        :param local_filename:
        :param remote_filename:
        :param remote_folder:
        """
        logging.info("uploading " + os.path.join(self.t.publishing_path + local_filename))

        # Check if ssh connection is open.
        if self.sftp is None:
            self._connect_ssh()

        format_folder = os.path.join(self.t.voctoweb_path, remote_folder)

        # Check if the directory exists and if not create it.
        # This only works for the format sub directories not for the event itself
        try:
            self.sftp.stat(format_folder)
        except IOError as e:
            if e.errno == errno.ENOENT:
                try:
                    self.sftp.mkdir(format_folder)
                except IOError as e:
                    raise VoctowebException('Could not create format subdir ' + format_folder + ' : ' + str(e)) from e

        upload_target = os.path.join(format_folder, remote_filename)

        # Check if the file already exists and remove it
        try:
            self.sftp.stat(upload_target)
        except IOError:
            pass  # if the file not exists we can go to the upload
        else:
            try:
                self.sftp.remove(upload_target)
            except IOError as e:
                raise VoctowebException('Could not replace recording ' + str(e)) from e

        # Upload the file
        try:
            self.sftp.put(os.path.join(self.t.publishing_path, local_filename), upload_target)
        except paramiko.SSHException as e:
            raise VoctowebException('Could not upload recording because of SSH problem ' + str(e)) from e
        except IOError as e:
            raise VoctowebException('Could not create file in upload directory ' + str(e)) from e

        logging.info("uploading " + remote_filename + " done")

    def create_event(self):
        """
        Create a new event on the voctoweb API host
        :return:
        """
        logging.info('creating event on ' + self.api_url + ' in conference ' + self.t.voctoweb_slug)

        # prepare some variables for the api call
        url = self.api_url + 'events'

        if self.t.url:
            if self.t.url.startswith('//'):
                event_url = 'https:' + self.t.url
            else:
                event_url = self.t.url
        else:
            event_url = "https://c3voc.de"

        if self.t.description is not None:
            if self.t.abstract is not None:
                description = '\n\n'.join([self.t.abstract, self.t.description])
            else:
                description = self.t.description
        else: 
            description = self.t.abstract

        if self.t.links:
            for link in self.t.links:
                description = '\n\n'.join([description, '<a href="' + link + '">' + link + '</a>'])

        # API code https://github.com/voc/voctoweb/blob/master/app/controllers/api/events_controller.rb
        headers = {'CONTENT-TYPE': 'application/json'}
        payload = {'api_key': self.api_key,
                   'acronym': self.t.voctoweb_slug,
                   'event': {
                       'guid': self.t.guid,
                       'slug': self.t.slug,
                       'title': self.t.title,
                       'subtitle': self.t.subtitle,
                       'link': event_url,
                       'original_language': self.t.languages[0],
                       'thumb_filename': self.t.local_filename_base + ".jpg",
                       'poster_filename': self.t.local_filename_base + "_preview.jpg",
                       'timeline_filename': self.t.local_filename_base + ".timeline.jpg",
                       'thumbnails_filename': self.t.local_filename_base + ".thumbnails.vtt",
                       'conference_id': self.t.voctoweb_slug,
                       'description': description,
                       'date': self.t.date,
                       'persons': self.t.people,
                       'tags': self.t.tags,
                       'promoted': False,
                       'release_date': str(time.strftime("%Y-%m-%d"))
                   }
                   }
        logging.debug("api url: " + url + ' header: ' + str(headers) + ' payload: ' + str(payload))

        # call voctoweb api
        try:
            # TODO make ssl verify a config option
            # r = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
            r = requests.post(url, headers=headers, data=json.dumps(payload))
        except requests.packages.urllib3.exceptions.MaxRetryError as e:
            raise VoctowebException("Error during creation of event: " + str(e)) from e
        return r

    def create_recording(self, local_filename, filename, folder, language, hq, html5):
        """
        create_recording a file on the voctoweb API host
        :param local_filename: this is not necessarily the value from the ticket
        :param filename: this is not necessarily the value from the ticket
        :param folder: this is not necessarily the value from the ticket
        :param language:
        :param hq:
        :param html5:
        :return:
        """
        logging.info(("publishing " + filename + " to " + self.api_url))

        # make sure we have the file size and length
        ret = []
        if not self._get_file_details(local_filename, ret):
            raise VoctowebException('could not get file details')

        # API code https://github.com/voc/voctoweb/blob/master/app/controllers/api/recordings_controller.rb
        url = self.api_url + 'recordings'
        headers = {'CONTENT-TYPE': 'application/json'}
        payload = {'api_key': self.api_key,
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

        logging.debug("api url: " + url + ' header: ' + str(headers) + ' payload: ' + str(payload))

        try:
            # todo ssl verify by config
            # r = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
            r = requests.post(url, headers=headers, data=json.dumps(payload))
        except requests.exceptions.SSLError as e:
            raise VoctowebException("ssl cert error " + str(e)) from e
        # except requests.packages.urllib3.exceptions.MaxRetryError as e:
        #    raise VoctowebException("Error during creating of event: " + str(e)) from e
        if r.status_code != 200 and r.status_code != 201:
            raise VoctowebException(("ERROR: Could not create_recording talk: " + str(r.status_code) + " " + r.text))

        logging.info(("publishing " + filename + " done"))
        return r.json()['id']

    def _get_file_details(self, local_filename, ret):
        """
        get file size and length of the media file
        :param local_filename:
        :param ret:
        :return:
        """
        if local_filename is None:
            raise VoctowebException('Error: No filename supplied.')

        file = os.path.join(self.t.publishing_path, local_filename)

        file_size = os.stat(file).st_size
        file_size = int(file_size / 1024 / 1024)

        try:
            r = subprocess.check_output(
                'ffprobe -print_format flat -show_format -loglevel quiet ' + file + ' 2>&1 | grep format.duration | cut -d= -f 2 | sed -e "s/\\"//g" -e "s/\..*//g" ',
                shell=True)
        except Exception as e_:
            raise VoctowebException("ERROR: could not get duration " + str(e_))

        length = int(r.decode())

        if self.t.mime_type.startswith('video'):
            try:
                r = subprocess.check_output(
                    'ffmpeg -i ' + file + ' 2>&1 | grep Stream | grep -oP ", \K[0-9]+x[0-9]+"',
                    shell=True)
            except Exception as e_:
                raise VoctowebException("ERROR: could not get resolution " + str(e_))

            resolution = r.decode()
            resolution = resolution.partition('x')
            width = resolution[0]
            height = resolution[2].strip()
        else:  # we have an audio only release so we set a 0 resolution
            width = 0
            height = 0

        if length == 0:
            raise VoctowebException("Error: file length is 0")
        else:
            logging.debug("filesize: " + str(file_size) + " length: " + str(length))
            ret.append(file_size)
            ret.append(length)
            ret.append(width)
            ret.append(height)
            return True


class VoctowebException(Exception):
    pass
