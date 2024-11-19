#!/usr/bin/env python3
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

import logging
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from time import sleep

try:
    # python 3.11
    from tomllib import loads as toml_load
except ImportError:
    from rtoml import load as toml_load

import api_client.bluesky_client as bluesky
import api_client.googlechat_client as googlechat
import api_client.mastodon_client as mastodon
import api_client.twitter_client as twitter
import api_client.webhook_client as webhook
from api_client.rclone_client import RCloneClient
from api_client.voctoweb_client import VoctowebClient
from api_client.youtube_client import YoutubeAPI
from c3tt_rpc_client import C3TTClient
from model.ticket_module import PublishingTicket, RecordingTicket, Ticket
from tools.thumbnails import ThumbnailGenerator

MY_PATH = os.path.abspath(os.path.dirname(__file__))
POSSIBLE_CONFIG_PATHS = [
    os.getenv("VOCTOPUBLISH_CONFIG", ""),
    os.path.expanduser("~/voctopublish.conf"),
    os.path.join(MY_PATH, "voctopublish.conf"),
    os.path.join(MY_PATH, "client.conf"),
]

for path in POSSIBLE_CONFIG_PATHS:
    if path:
        if os.path.isfile(path):
            my_config_path = path
            break
else:
    raise FileNotFoundError(
        f'Could not find a valid config in any of these paths: {" ".join(POSSIBLE_CONFIG_PATHS)}'
    )

with open(my_config_path) as f:
    CONFIG = toml_load(f.read())


class Worker:
    """
    This is the main class for the Voctopublish application
    It is meant to be used with the c3tt ticket tracker
    """

    def __init__(self):
        self.ticket = None
        self.ticket_id = None
        self.thumbs = None

        # set up logging
        logging.addLevelName(
            logging.WARNING,
            "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING),
        )
        logging.addLevelName(
            logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR)
        )
        logging.addLevelName(
            logging.INFO, "\033[1;32m%s\033[1;0m" % logging.getLevelName(logging.INFO)
        )
        logging.addLevelName(
            logging.DEBUG, "\033[1;85m%s\033[1;0m" % logging.getLevelName(logging.DEBUG)
        )

        self.logger = logging.getLogger()

        sh = logging.StreamHandler(sys.stdout)
        if CONFIG["general"]["debug"]:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s {%(filename)s:%(lineno)d} %(message)s"
            )
        else:
            formatter = logging.Formatter("%(asctime)s - %(message)s")

        sh.setFormatter(formatter)
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)

        level = CONFIG["general"]["debug"]
        if level == "info":
            self.logger.setLevel(logging.INFO)
        elif level == "warning":
            self.logger.setLevel(logging.WARNING)
        elif level == "error":
            self.logger.setLevel(logging.ERROR)
        elif level == "debug":
            self.logger.setLevel(logging.DEBUG)

        self.worker_type = CONFIG["general"]["worker_type"]
        if self.worker_type == "releasing":
            self.ticket_type = "encoding"
            self.to_state = "releasing"
        elif self.worker_type == "recording":
            self.ticket_type = "recording"
            self.to_state = "recording"
        else:
            logging.error("Unknown worker type " + self.worker_type)
            raise PublisherException("Unknown worker type " + self.worker_type)

        self.host = CONFIG["C3Tracker"].get("host", "").strip()
        if not self.host:
            self.host = socket.getfqdn()

        logging.debug("creating C3TTClient")
        try:
            self.c3tt = C3TTClient(
                CONFIG["C3Tracker"]["url"],
                CONFIG["C3Tracker"]["group"],
                self.host,
                CONFIG["C3Tracker"]["secret"],
            )
        except Exception as e_:
            raise PublisherException(
                "Config parameter missing or empty, please check config"
            ) from e_

    def publish(self):
        """
        Decide based on the information provided by the tracker where to publish.
        """
        if not self.ticket:
            logging.debug("not ticket, returning")
            return

        # check source file and filesystem permissions
        if not os.path.isfile(
            os.path.join(self.ticket.publishing_path, self.ticket.local_filename)
        ):
            raise IOError(
                "Source file does not exist "
                + os.path.join(self.ticket.publishing_path, self.ticket.local_filename)
            )
        if not os.path.exists(os.path.join(self.ticket.publishing_path)):
            raise IOError(
                "Output path does not exist "
                + os.path.join(self.ticket.publishing_path)
            )
        if (
            os.path.getsize(
                os.path.join(self.ticket.publishing_path, self.ticket.local_filename)
            )
            == 0
        ):
            raise PublisherException(
                "Input file size is 0 " + os.path.join(self.ticket.publishing_path)
            )
        else:
            if not os.access(self.ticket.publishing_path, os.W_OK):
                raise IOError(
                    "Output path is not writable (%s)" % self.ticket.publishing_path
                )

        self.thumbs = ThumbnailGenerator(self.ticket, CONFIG)
        if not self.thumbs.exists and (
            (self.ticket.voctoweb_enable and self.ticket.mime_type.startswith("video"))
            or (self.ticket.youtube_enable and self.ticket.youtube_enable)
        ):
            self.thumbs.generate()

        # voctoweb
        logging.debug(f"#voctoweb {self.ticket.voctoweb_enable}")
        if self.ticket.voctoweb_enable:
            self._publish_to_voctoweb()

        # YouTube
        logging.debug(f"#youtube {self.ticket.youtube_enable}")
        if self.ticket.youtube_enable:
            if (
                self.ticket.has_youtube_url
                and self.ticket.youtube_update != "force"
                and len(self.ticket.languages) <= 1
            ):
                logging.debug(f"{self.ticket.youtube_urls=} {self.ticket.youtube_update=}")
                if self.ticket.youtube_update != "ignore":
                    raise PublisherException(
                        "YouTube URLs already exist in ticket, wont publish to YouTube."
                    )
            else:
                self._publish_to_youtube()

        logging.debug(f"#rclone {self.ticket.rclone_enable}")
        rclone = None
        if self.ticket.rclone_enable:
            if self.ticket.master or not self.ticket.rclone_only_master:
                rclone = RCloneClient(self.ticket, CONFIG)
                ret = rclone.upload()
                if ret not in (0, 9):
                    raise PublisherException(f"rclone failed with exit code {ret}")
                self.c3tt.set_ticket_properties(
                    self.ticket_id,
                    {
                        "Rclone.DestinationFileName": rclone.destination,
                        "Rclone.ReturnCode": str(ret),
                    },
                )
            else:
                logging.debug(
                    "skipping rclone because Publishing.Rclone.OnlyMaster is set to 'yes'"
                )

        if self.ticket.webhook_url:
            if self.ticket.master or not self.ticket.webhook_only_master:
                result = webhook.send(
                    self.ticket,
                    CONFIG,
                    getattr(self, "voctoweb_filename", None),
                    getattr(self, "voctoweb_language", self.ticket.language),
                    rclone,
                )
                if (
                    not isinstance(result, int) or result >= 300
                ) and self.ticket.webhook_fail_on_error:
                    raise PublisherException(
                        f"POSTing webhook to {self.ticket.webhook_url} failed with http status code {result}"
                    )
                elif isinstance(result, int):
                    self.c3tt.set_ticket_properties(
                        self.ticket_id,
                        {
                            "Webhook.StatusCode": result,
                        },
                    )

        self.c3tt.set_ticket_done(self.ticket_id)

        # Twitter
        if self.ticket.twitter_enable and self.ticket.master:
            twitter.send_tweet(self.ticket, CONFIG)

        # Mastodon
        if self.ticket.mastodon_enable and self.ticket.master:
            mastodon.send_toot(self.ticket, CONFIG)

        # Bluesky
        if self.ticket.bluesky_enable and self.ticket.master:
            bluesky.send_post(self.ticket, CONFIG)

        # Google Chat (former Hangouts Chat)
        if self.ticket.googlechat_webhook_url and self.ticket.master:
            googlechat.send_chat_message(self.ticket, CONFIG)

        logging.debug("#done")

    def get_ticket_from_tracker(self):
        """
        Request the next unassigned ticket for the configured states
        :return: a ticket object or None in case no ticket is available
        """
        logging.info("requesting ticket from tracker")
        ticket_meta = self.c3tt.assign_next_unassigned_for_state(
            self.ticket_type, self.to_state, {"EncodingProfile.Slug": "relive"}
        )
        if ticket_meta:
            ticket_id = ticket_meta["id"]
            self.ticket_id = ticket_id
            logging.info("Ticket ID:" + str(ticket_id))
            try:
                ticket_properties = self.c3tt.get_ticket_properties(ticket_id)
                logging.debug("Ticket Properties: " + str(ticket_properties))
            except Exception as e_:
                self.c3tt.set_ticket_failed(ticket_id, e_)
                raise e_
            if self.ticket_type == "encoding":
                self.ticket = PublishingTicket(ticket_properties, ticket_id, CONFIG)
            elif self.ticket_type == "recording":
                self.ticket = RecordingTicket(ticket_properties, ticket_id, CONFIG)
            else:
                logging.info(
                    "Unknown ticket type "
                    + self.ticket_type
                    + " aborting, please check config "
                )
                raise PublisherException("Unknown ticket type " + self.ticket_type)
        else:
            logging.info(
                "No ticket of type " + self.ticket_type + " for state " + self.to_state
            )

    def _publish_to_voctoweb(self):
        """
        Create an event on a voctoweb instance. This includes creating a recording for each media file.
        """
        logging.info("publishing to voctoweb")
        try:
            vw = VoctowebClient(
                self.ticket,
                self.thumbs,
                CONFIG["voctoweb"]["api_key"],
                CONFIG["voctoweb"]["api_url"],
                CONFIG["voctoweb"]["ssh_host"],
                CONFIG["voctoweb"]["ssh_port"],
                CONFIG["voctoweb"]["ssh_user"],
            )
        except Exception as e_:
            raise PublisherException(
                "Error initializing voctoweb client. Config parameter missing"
            ) from e_

        if self.ticket.master:
            # if this is master ticket we need to check if we need to create an event on voctoweb
            logging.debug("this is a master ticket")
            if self.ticket.voctoweb_event_id or self.ticket.recording_id:
                logging.debug("ticket has a voctoweb_event_id or recording_id")
                # ticket has a recording id or voctoweb event id. We assume the event exists on voctoweb
            else:
                # ticket has no recording id therefore we create the event on voctoweb
                r = vw.create_or_update_event()
                if r.status_code in [200, 201]:
                    logging.info("new event created")
                    # generate thumbnails and a visual timeline for video releases (will not overwrite existing files)
                    if self.ticket.mime_type.startswith("video"):
                        vw.generate_thumbs()
                        vw.upload_thumbs()
                        vw.generate_timelens()
                        vw.upload_timelens()
                    logging.debug("response: " + str(r.json()))
                    try:
                        # TODO only set recording id when new recording was created, and not when it was only updated
                        self.c3tt.set_ticket_properties(
                            self.ticket_id, {"Voctoweb.EventId": r.json()["id"]}
                        )
                    except Exception as e_:
                        raise PublisherException(
                            "failed to Voctoweb EventID to ticket"
                        ) from e_

                elif r.status_code == 422:
                    # If this happens tracker and voctoweb are out of sync regarding the event id
                    # TODO write voctoweb event_id to ticket properties --Andi
                    logging.warning("event already exists => publishing")
                else:
                    raise PublisherException(
                        "Voctoweb returned an error while creating an event: "
                        + str(r.status_code)
                        + " - "
                        + str(r.text)
                    )

            # in case of a multi language release we create here the single language files
            if len(self.ticket.languages) > 1:
                logging.info("remuxing multi-language video into single audio files")
                self._mux_to_single_language(vw)

        # set hq filed based on ticket encoding profile slug
        if "hd" in self.ticket.profile_slug:
            hq = True
        else:
            hq = False

        # For multi language or slide recording we don't set the html5 flag
        if len(self.ticket.languages) == 1 and "slides" not in self.ticket.profile_slug:
            html5 = True
        else:
            html5 = False

        # if we have the language index the tracker wants to tell us about an encoding that does not contain all
        # audio tracks of the master we need to reflect that in the target filename
        if self.ticket.language_index:
            index = int(self.ticket.language_index)
            self.voctoweb_filename = (
                self.ticket.language_template % self.ticket.languages[index]
                + "_"
                + self.ticket.profile_slug
                + "."
                + self.ticket.profile_extension
            )
            self.voctoweb_language = self.ticket.languages[index]
        else:
            self.voctoweb_filename = self.ticket.filename
            self.voctoweb_language = self.ticket.language

        vw.upload_file(
            self.ticket.local_filename, self.voctoweb_filename, self.ticket.folder
        )

        recording_id = vw.create_recording(
            self.ticket.local_filename,
            self.voctoweb_filename,
            self.ticket.folder,
            self.voctoweb_language,
            hq,
            html5,
        )

        # when the ticket was created, and not only updated: write recording_id to ticket
        if recording_id:
            self.c3tt.set_ticket_properties(
                self.ticket_id, {"Voctoweb.RecordingId.Master": recording_id}
            )

    def _mux_to_single_language(self, vw):
        """
        Mux a multi language video file into multiple single language video files.
        This is only implemented for the h264 hd files as we only do it for them
        :return:
        """
        logging.debug("Languages: " + str(self.ticket.languages))
        for language in self.ticket.languages:
            out_filename = (
                self.ticket.fahrplan_id
                + "-"
                + self.ticket.profile_slug
                + "-audio"
                + str(language)
                + "."
                + self.ticket.profile_extension
            )
            out_path = os.path.join(self.ticket.publishing_path, out_filename)
            filename = (
                self.ticket.language_template % self.ticket.languages[language]
                + "."
                + self.ticket.profile_extension
            )

            logging.info("remuxing " + self.ticket.local_filename + " to " + out_path)

            try:
                subprocess.call(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "warning",
                        "-nostdin",
                        "-i",
                        os.path.join(
                            self.ticket.publishing_path, self.ticket.local_filename
                        ),
                        "-map",
                        "0:0",
                        "-map",
                        "0:a:" + str(language),
                        "-c",
                        "copy",
                        "-movflags",
                        "faststart",
                        out_path,
                    ]
                )
            except Exception as e_:
                raise PublisherException(
                    "error remuxing " + self.ticket.local_filename + " to " + out_path
                ) from e_

            try:
                vw.upload_file(out_path, filename, self.ticket.folder)
            except Exception as e_:
                raise PublisherException("error uploading " + out_path) from e_

            try:
                recording_id = vw.create_recording(
                    out_filename,
                    filename,
                    self.ticket.folder,
                    str(self.ticket.languages[language]),
                    hq=True,
                    html5=True,
                    single_language=True,
                )
            except Exception as e_:
                raise PublisherException("creating recording " + out_path) from e_

            try:
                # when the ticket was created, and not only updated: write recording_id to ticket
                if recording_id:
                    self.c3tt.set_ticket_properties(
                        self.ticket_id,
                        {
                            "Voctoweb.RecordingId."
                            + self.ticket.languages[language]: str(recording_id)
                        },
                    )
            except Exception as e_:
                raise PublisherException("failed to set RecordingId to ticket") from e_

    def _publish_to_youtube(self):
        """
        Publish the file to YouTube.
        """
        logging.debug("publishing to youtube")

        yt = YoutubeAPI(
            self.ticket,
            self.thumbs,
            CONFIG,
            CONFIG["youtube"]["client_id"],
            CONFIG["youtube"]["secret"],
        )
        yt.setup(self.ticket.youtube_token)

        youtube_urls = yt.publish()
        props = {}
        for i, youtubeUrl in enumerate(youtube_urls):
            props["YouTube.Url" + str(i)] = youtubeUrl

        self.c3tt.set_ticket_properties(self.ticket_id, props)
        self.ticket.youtube_urls = props

        # now, after we reported everything back to the tracker, we try to add the videos to our own playlists
        # second YoutubeAPI instance for playlist management at youtube.com
        if (
            "playlist_token" in CONFIG["youtube"]
            and self.ticket.youtube_token != CONFIG["youtube"]["playlist_token"]
        ):
            yt_voctoweb = YoutubeAPI(
                self.ticket,
                CONFIG["youtube"]["client_id"],
                CONFIG["youtube"]["secret"],
            )
            yt_voctoweb.setup(CONFIG["youtube"]["playlist_token"])
        else:
            logging.info("using same token for publishing and playlist management")
            yt_voctoweb = yt

        for url in youtube_urls:
            video_id = url.split("=", 2)[1]
            yt_voctoweb.add_to_playlists(video_id, self.ticket.youtube_playlists)

    def download(self):
        """
        download or copy a file for processing
        :return:
        """
        # we name our input video file uncut ts so tracker will find it. This is not the nicest way to go
        # TODO find a better integration in to the pipeline
        path = os.path.join(
            self.ticket.fuse_path, self.ticket.fuse_room, self.ticket.fahrplan_id
        )
        file = os.path.join(path, "uncut.ts")
        logging.info(
            "Downloading input file from: " + self.ticket.download_url + " to " + file
        )

        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except Exception as e:
                logging.error(e)
                logging.exception(e)
                raise PublisherException(e)

        if os.path.exists(file) and not self.ticket.redownload_enabled:
            logging.error(
                'video file "' + path + '" already exists, please remove file'
            )
            raise PublisherException("video file already exists, please remove file")

        url = self.ticket.download_url
        url_decoded = urllib.parse.unquote(url)
        if len(url) > len(url_decoded):
            logging.warning(
                f"Download URL {url} was urlencoded, using {url_decoded} instead"
            )
            url = url_decoded

        # if its an URL it probably will start with http ....
        if self.ticket.download_url.startswith(
            "http"
        ) or self.ticket.download_url.startswith("ftp"):
            self._download_file(url, file)
        else:
            self._copy_file(url, file)

        # set recording language TODO multilang
        try:
            self.c3tt.set_ticket_properties(
                self.ticket_id,
                {
                    "Record.Language": self.ticket.language,
                    "Record.Room": self.ticket.fuse_room,
                },
            )
        except AttributeError as err_:
            self.c3tt.set_ticket_failed(
                self.ticket_id,
                "unknown language, please set language in the recording ticket to proceed",
            )
            logging.error(
                "unknown language, please set language in the recording ticket to proceed"
            )

        # tell the tracker that we finished the import
        self.c3tt.set_ticket_done(self.ticket_id)

    def _copy_file(self, source, target):
        """
        copy a file from a local folder to the fake fuse and name it uncut.ts
        this hack to import files not produced with the tracker into the workflow to publish it on the voctoweb / youtube
        :return:
        """
        try:
            shutil.copyfile(source, target)
        except IOError as e_:
            raise PublisherException(e_)

    def _download_file(self, source, target):
        """
        download a file from an http / https / ftp URL an place it as a uncut.ts in the fuse folder.
        this hack to import files not produced with the tracker into the workflow to publish it on the voctoweb / youtube
        :return:
        """
        logging.info("Downloading file from: " + source)
        if self.ticket.download_command in (None, True, False):
            with open(target, "wb") as fh:
                with urllib.request.urlopen(
                    urllib.parse.quote(source, safe=":/")
                ) as df:
                    # original version tried to write whole file to ram and ran out of memory
                    # read in 16 kB chunks instead
                    while True:
                        chunk = df.read(16384)
                        if not chunk:
                            break
                        fh.write(chunk)
        else:
            command = []
            for part in self.ticket.download_command:
                if part == "--TARGETPATH--":
                    command.append(source)
                elif part == "--DOWNLOADURL--":
                    command.append(target)
                else:
                    command.append(part)
            logging.debug(f"download command is: {command}")
            out = None
            try:
                out = subprocess.check_output(command)
            except subprocess.CalledProcessError as e:
                logging.exception("could not download file")
                logging.error(out)
                raise PublisherException from e
            else:
                logging.debug(out)


class PublisherException(Exception):
    pass


def process_single_ticket():
    w = Worker()
    w.get_ticket_from_tracker()

    if w.ticket:
        try:
            if w.worker_type == "releasing":
                w.publish()
            elif w.worker_type == "recording":
                w.download()
            else:
                raise PublisherException(f"unknown worker type {w.worker_type}")
            return True
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            w.c3tt.set_ticket_failed(w.ticket_id, f"{exc_type.__name__}: {e}")
            logging.exception(f"could not process ticket {w.ticket_id}")
    return False


if __name__ == "__main__":
    run_mode = CONFIG["general"].get("run_mode", "single")

    if run_mode == "loop_until_empty" or run_mode == "loop_forever":
        while True:
            have_processed_ticket = process_single_ticket()
            if have_processed_ticket:
                # if we have processed a ticket, sleep a short time
                # and then try to process the next ticket
                sleep(2)
            elif run_mode == "loop_forever":
                # no tickets processed right now, so wait longer
                sleep(30)
            else:
                # no tickets processed right now, so we exit cleanly
                sys.exit(0)

    elif run_mode == "single":
        process_single_ticket()
        sys.exit(0)

    else:
        logging.error(f"unknown run_mode {run_mode}")
        sys.exit(1)
