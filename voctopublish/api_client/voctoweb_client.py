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
import glob
import json
import logging
import operator
import os
import subprocess
import tempfile
import time
from json import loads

import paramiko
import requests
from model.ticket_module import Ticket
from tools.thumbnails import ThumbnailGenerator

LOG = logging.getLogger("Voctoweb")


class VoctowebClient:
    def __init__(
        self,
        t: Ticket,
        thumb: ThumbnailGenerator,
        api_key,
        api_url,
        ssh_host,
        ssh_port,
        ssh_user,
        frontend_url=None,
    ):
        """
        :param t:
        :param thumb:
        :param api_key: Voctoweb API Key
        :param api_url: Voctoweb API URL
        :param ssh_host: SSH Port of the CDN host
        :param ssh_port: SSH Port of the CDN host
        :param ssh_user: SSH user of the CDN host
        """
        self.t = t
        self.thumbnail = thumb
        self.api_key = api_key
        self.api_url = api_url
        self.ssh = None
        self.sftp = None
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.frontend_url = frontend_url

    def _connect_ssh(self):
        """
        Open an SSH connection to the voctoweb storage host
        """
        LOG.info("Establishing SSH connection")
        self.ssh = paramiko.SSHClient()
        logging.getLogger("paramiko").setLevel(logging.INFO)
        # TODO set hostkey handling via config
        # client.get_host_keys().add(upload_host,'ssh-rsa', key)
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.ssh.connect(
                self.ssh_host,
                port=self.ssh_port,
                username=self.ssh_user,
            )
        except paramiko.AuthenticationException as e:
            raise VoctowebException(
                "Authentication failed. Please check credentials " + str(e)
            ) from e
        except paramiko.BadHostKeyException:
            raise VoctowebException("Bad host key. Check your known_hosts file")
        except paramiko.SSHException as e:
            raise VoctowebException("SSH negotiation failed " + str(e)) from e

        self.sftp = self.ssh.open_sftp()
        LOG.info("SSH connection established to " + str(self.ssh_host))

        for dir_type, path in {
            "thumbnail": self.t.voctoweb_thumb_path,
            "video": self.t.voctoweb_path,
        }.items():
            try:
                self.sftp.stat(path)
                LOG.debug(f"{dir_type} directory {path} already exists")
            except IOError as e:
                if e.errno == errno.ENOENT:
                    try:
                        self.sftp.mkdir(path)
                    except IOError as e:
                        raise VoctowebException(
                            f"Could not create {dir_type} dir {path} - {e!r}"
                        ) from e

    def generate_thumbs(self):
        """
        This function generates thumbnails to be used on voctoweb
        :return:
        """
        outjpg = os.path.join(
            self.t.publishing_path, self.t.fahrplan_id + "_voctoweb.jpg"
        )
        outjpg_preview = os.path.join(
            self.t.publishing_path, self.t.fahrplan_id + "_voctoweb_preview.jpg"
        )

        # lanczos scaling algorithm produces a sharper image for small sizes than the default choice
        # set pix_fmt to create a be more compatible output, otherwise the input format would be kept
        try:
            r = subprocess.check_output(
                "ffmpeg -loglevel error -i "
                + self.thumbnail.path
                + ' -filter_complex:v "scale=400:-1:lanczos" -f image2 -vcodec mjpeg -pix_fmt yuv420p -q:v 0 -y '
                + outjpg,
                shell=True,
            )
        except subprocess.CalledProcessError as e_:
            raise VoctowebException("Could not scale outjpg: " + str(e_)) from e_

        try:
            r = subprocess.check_output(
                "ffmpeg -loglevel error -i "
                + self.thumbnail.path
                + " -f image2 -vcodec mjpeg -pix_fmt yuv420p -q:v 0 -y "
                + outjpg_preview,
                shell=True,
            )
        except Exception as e_:
            raise VoctowebException(
                "Could not scale outjpg_preview: " + r.decode("utf-8")
            ) from e_

        LOG.info("thumbnails reformatted for voctoweb")

    def upload_thumbs(self):
        """
        Upload thumbnails to the voctoweb storage.
        """
        LOG.info("uploading thumbnails")

        # check if ssh connection is open
        if self.ssh is None:
            self._connect_ssh()

        thumbs = {
            "_voctoweb.jpg": ".jpg",
            "_voctoweb_preview.jpg": "_preview.jpg",
        }
        for ext_local, ext_vw in thumbs.items():
            file = os.path.join(self.t.publishing_path, self.t.fahrplan_id + ext_local)
            if not os.path.isfile(file):
                raise VoctowebException(
                    "could not upload thumb because file " + file + " does not exist"
                )
            target = os.path.join(
                self.t.voctoweb_thumb_path, self.t.voctoweb_filename_base + ext_vw
            )
            try:
                LOG.debug("Uploading " + file + " to " + target)
                self.sftp.put(file, target)
            except paramiko.SSHException as e:
                raise VoctowebException(
                    "could not upload thumb because of SSH problem: " + str(e)
                ) from e
            except IOError as e:
                raise VoctowebException(
                    "could not upload thumb to "
                    + target
                    + " because an remote error occured: "
                    + str(e)
                ) from e

        LOG.info("uploading thumbs done")

    def generate_timelens(self):
        """
        This function generates a visual timeline and thumbnail grids to be used on voctoweb
        """
        source = os.path.join(self.t.publishing_path, self.t.local_filename)
        LOG.info("running timelens for " + source)

        outtimeline = os.path.join(
            self.t.publishing_path, self.t.voctoweb_filename_base + ".timeline.jpg"
        )
        outthumbnails = os.path.join(
            self.t.publishing_path, self.t.voctoweb_filename_base + ".thumbnails.vtt"
        )

        try:
            r = subprocess.check_output(
                [
                    "timelens",
                    source,
                    "-w",
                    "1000",
                    "-h",
                    "90",
                    "--timeline",
                    outtimeline,
                    "--thumbnails",
                    outthumbnails,
                ]
            )
        except subprocess.CalledProcessError as e_:
            raise VoctowebException("Could not run timelens: " + str(e_)) from e_

        LOG.info("ran timelens successfully")

    def upload_timelens(self):
        """
        Upload timelens files to the voctoweb storage.
        """
        LOG.info("uploading timelens files")

        # check if ssh connection is open
        if self.ssh is None:
            self._connect_ssh()

        basepath = os.path.join(self.t.publishing_path, self.t.voctoweb_filename_base)

        files = [basepath + ".timeline.jpg", basepath + ".thumbnails.vtt"] + glob.glob(
            basepath + ".thumbnails-*.jpg"
        )
        for file in files:
            target = os.path.join(self.t.voctoweb_thumb_path, os.path.basename(file))
            try:
                LOG.debug("Uploading " + file + " to " + target)
                self.sftp.put(file, target)
            except paramiko.SSHException as e:
                raise VoctowebException(
                    "could not upload thumb because of SSH problem " + str(e)
                ) from e
            except IOError as e:
                raise VoctowebException(
                    "could not upload thumb because of " + str(e)
                ) from e

        LOG.info("uploading timelens files done")

    def upload_file(self, local_filename, remote_filename, remote_folder):
        """
        Uploads a file from path relative to the output dir to the same path relative to the upload_dir
        We can't use the file and folder names from the ticket here as we need to change these for multi language audio
        :param local_filename:
        :param remote_filename:
        :param remote_folder:
        """
        LOG.info("uploading " + os.path.join(self.t.publishing_path, local_filename))

        # Check if ssh connection is open.
        if self.sftp is None:
            self._connect_ssh()

        format_folder = os.path.join(self.t.voctoweb_path, remote_folder)

        # Check if the directory exists and if not create it.
        try:
            self.sftp.stat(format_folder)
        except IOError as e:
            if e.errno == errno.ENOENT:
                try:
                    self.sftp.mkdir(format_folder)
                except IOError as e:
                    raise VoctowebException(
                        "Could not create format subdir "
                        + format_folder
                        + " : "
                        + str(e)
                    ) from e

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
                raise VoctowebException("Could not replace recording " + str(e)) from e

        # Upload the file
        try:
            self.sftp.put(
                os.path.join(self.t.publishing_path, local_filename), upload_target
            )
        except paramiko.SSHException as e:
            raise VoctowebException(
                "Could not upload recording because of SSH problem " + str(e)
            ) from e
        except IOError as e:
            raise VoctowebException(
                "Could not create file in upload directory " + str(e)
            ) from e

        LOG.info("uploading " + remote_filename + " done")

    def get_event(self):
        """
        Receive event details from voctoweb API host
        """
        LOG.info("querying event info on " + self.api_url)

        headers = {"CONTENT-TYPE": "application/json"}

        # call voctoweb api
        r = requests.get(
            f"{self.frontend_url}/public/events/{self.t.voctoweb_event_id}",
            headers=headers,
        )
        return r.json()

    def delete_event(self):
        """
        Delete event from voctoweb API host
        """
        event = self.get_event()

        print(event)
        LOG.info("removing event from " + self.api_url)

        # API code https://github.com/voc/voctoweb/blob/master/app/controllers/api/events_controller.rb
        headers = {
            "Authorization": f"Token {self.api_key}",
            "CONTENT-TYPE": "application/json",
        }
        payload = {
            "acronym": self.t.voctoweb_slug,
            "event": {"id": self.t.voctoweb_event_id},
        }

        url = self.api_url + "events/" + str(self.t.voctoweb_event_id)
        LOG.debug(
            "api url: "
            + url
            + " header: "
            + str(headers)
            + " slug: "
            + str(self.t.slug)
            + " payload: "
            + str(payload)
        )

        # call voctoweb api
        r = requests.delete(url, headers=headers, json=payload)

    def delete_file(self, remote_path):
        """
        Deletes a file on the server
        :param remote_path:
        """
        LOG.info("deleting " + remote_path)

        # Check if ssh connection is open.
        if self.sftp is None:
            self._connect_ssh()

        # Check if the file already exists and remove it
        try:
            self.sftp.remove(remote_path)
        except IOError as e:
            if e.errno == errno.ENOENT:
                LOG.info("remote file does not exist " + remote_path)
            else:
                raise
        except:
            raise VoctowebException("Could not delete file from server " + remote_path)

        LOG.info("deleting " + remote_path + " done")

    def create_or_update_event(self):
        """
        Create a new event on the voctoweb API host
        :return:
        """
        LOG.info(
            "creating event on "
            + self.api_url
            + " in conference "
            + self.t.voctoweb_slug
        )

        # prepare some variables for the api call
        if self.t.url:
            if self.t.url.startswith("//"):
                event_url = "https:" + self.t.url
            else:
                event_url = self.t.url
        else:
            event_url = "https://c3voc.de"

        description = []
        if self.t.abstract is not None:
            description.append(self.t.abstract)

        if self.t.description is not None:
            description.append(self.t.description)

        if self.t.links:
            for link in self.t.links:
                description.append('<a href="' + link + '">' + link + "</a>")

        if self.t.license:
            # FIXME <https://github.com/emfcamp/Website/issues/1780>
            description.append(self.t.license)

        # API code https://github.com/voc/voctoweb/blob/master/app/controllers/api/events_controller.rb
        headers = {
            "Authorization": f"Token {self.api_key}",
            "CONTENT-TYPE": "application/json",
        }
        payload = {
            "acronym": self.t.voctoweb_slug,
            "event": {
                "guid": self.t.guid,
                #'slug': self.t.slug,
                "title": self.t.title,
                "subtitle": self.t.subtitle,
                "link": event_url,
                "original_language": self.t.languages[0],
                "thumb_filename": (
                    (self.t.voctoweb_filename_base + ".jpg")
                    if self.t.voctoweb_filename_base
                    else ""
                ),
                "poster_filename": (
                    (self.t.voctoweb_filename_base + "_preview.jpg")
                    if self.t.voctoweb_filename_base
                    else ""
                ),
                "timeline_filename": (
                    (self.t.voctoweb_filename_base + ".timeline.jpg")
                    if self.t.voctoweb_filename_base
                    else ""
                ),
                "thumbnails_filename": (
                    (self.t.voctoweb_filename_base + ".thumbnails.vtt")
                    if self.t.voctoweb_filename_base
                    else ""
                ),
                "description": "\n\n".join(description),
                "date": self.t.date,
                "persons": self.t.people,
                "tags": self.t.voctoweb_tags,
                "promoted": False,
                "release_date": str(time.strftime("%Y-%m-%d")),
            },
        }

        url = self.api_url + "events"
        LOG.debug(
            "api url: "
            + url
            + " header: "
            + str(headers)
            + " slug: "
            + str(self.t.slug)
            + " payload: "
            + str(payload)
        )

        # call voctoweb api
        try:
            # TODO make ssl verify a config option
            # r = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
            if self.t.voctoweb_event_id:
                r = requests.patch(
                    url + "/" + self.t.guid, headers=headers, json=payload
                )
                if r.status_code == 422:
                    # event does not exist, create new one
                    r = requests.post(
                        url,
                        headers=headers,
                        json={
                            **payload,
                            "event": {"slug": self.t.slug, **payload["event"]},
                        },
                    )

            else:
                r = requests.post(
                    url,
                    headers=headers,
                    json={
                        **payload,
                        "event": {"slug": self.t.slug, **payload["event"]},
                    },
                )
                LOG.debug("got response with code %d: %r" % (r.status_code, r.text))
                # event already exists so update metadata
                if r.status_code == 422:
                    r = requests.patch(
                        url + "/" + self.t.guid, headers=headers, json=payload
                    )

        except requests.packages.urllib3.exceptions.MaxRetryError as e:
            raise VoctowebException("Error during creation of event: " + str(e)) from e
        return r

    def create_recording(
        self,
        local_filename,
        filename,
        folder,
        language,
        hq,
        html5,
        single_language=False,
    ):
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
        LOG.info(("publishing " + filename + " to " + self.api_url))

        recording_id = self.t.recording_id
        if single_language:
            recording_id = self.t._get_str(
                f"Voctoweb.RecordingId.{language}", optional=True
            )

        # API code https://github.com/voc/voctoweb/blob/master/app/controllers/api/recordings_controller.rb
        url = self.api_url + "recordings"
        if recording_id:
            url += "/" + recording_id

        if self.t.mime_type.startswith("application/"):
            # this is probably a subtitle or something like that
            recording = {
                "state": "completed",
            }
        else:
            # make sure we have the file size and length
            ret = []
            if not self._get_file_details(local_filename, ret):
                raise VoctowebException("could not get file details")

            recording = {
                "high_quality": hq,
                "html5": html5,
                "size": str(ret[0]),
                "width": str(ret[2]),
                "height": str(ret[3]),
                "length": str(ret[1]),
            }

        headers = {
            "Authorization": f"Token {self.api_key}",
            "CONTENT-TYPE": "application/json",
        }
        payload = {
            "guid": self.t.guid,
            "acronym": self.t.slug,
            "recording": {
                "folder": folder,
                "filename": filename,
                "mime_type": self.t.mime_type,
                "language": language,
                "translated": bool(
                    self.t.language_index
                ),  # this is either None or int. 0 is the original language
                **recording,
            },
        }

        LOG.debug(f"api url: {url}")
        LOG.debug(f"header: {repr(headers)}")
        LOG.debug(f"payload: {repr(payload)}")

        try:
            # todo ssl verify by config
            # r = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
            if recording_id:
                r = requests.patch(url, headers=headers, data=json.dumps(payload))
            else:
                r = requests.post(url, headers=headers, data=json.dumps(payload))

        except requests.exceptions.SSLError as e:
            raise VoctowebException("ssl cert error " + str(e)) from e
        # except requests.packages.urllib3.exceptions.MaxRetryError as e:
        #    raise VoctowebException("Error during creating of event: " + str(e)) from e
        if r.status_code != 200 and r.status_code != 201:
            raise VoctowebException(
                (
                    "ERROR: Could not create_recording talk: "
                    + str(r.status_code)
                    + " "
                    + r.text
                )
            )

        LOG.info(("publishing " + filename + " done"))

        if recording_id:
            # Recording was only updated, we do not need return the recording_id as it is already part of the ticket
            return None
        else:
            # Recording was created, return id to be written to the ticket
            return r.json()["id"]

    def _get_file_details(self, local_filename, ret):
        """
        get file size and length of the media file
        :param local_filename:
        :param ret:
        :return:
        """
        if local_filename is None:
            raise VoctowebException("Error: No filename supplied.")

        file = os.path.join(self.t.publishing_path, local_filename)

        file_size = os.stat(file).st_size
        file_size = int(file_size / 1024 / 1024)

        try:
            r = subprocess.check_output(
                [
                    "ffprobe",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    "-loglevel",
                    "quiet",
                    file,
                ]
            )
            info_json = loads(r.decode())
            length = int(info_json["format"]["duration"])
        except Exception as e_:
            raise VoctowebException("could not get format or streams") from e_

        width = 0
        height = 0

        if self.t.mime_type.startswith("video"):
            try:
                for stream in info_json["streams"]:
                    if "width" in stream and "height" in stream:
                        width = stream["width"]
                        height = stream["height"]
            except Exception:
                # error handling just below
                pass

            if width == 0 or height == 0:
                raise VoctowebException(
                    f"could not determine resolution (found {width=} {height=})"
                )

        if length == 0:
            raise VoctowebException("Error: file length is 0")
        else:
            LOG.debug("filesize: " + str(file_size) + " length: " + str(length))
            ret.append(file_size)
            ret.append(length)
            ret.append(width)
            ret.append(height)
            return True


class VoctowebException(Exception):
    pass
