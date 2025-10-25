#!/usr/bin/python3
#    Copyright (C) 2022 andi
#    andi@muc.ccc.de
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
import logging
import os
import socket
import sys
import traceback

from api_client.voctoweb_client import VoctowebClient
from api_client.youtube_client import YoutubeAPI
from c3tt_rpc_client import C3TTClient
from model.ticket_module import PublishingTicket, Ticket

try:
    # python 3.11
    from tomllib import loads as toml_load
except ImportError:
    from rtoml import load as toml_load

MY_PATH = os.path.abspath(os.path.dirname(__file__))
POSSIBLE_CONFIG_PATHS = [
    os.getenv("VOCTOPUBLISH_CONFIG", ""),
    os.path.expanduser("~/voctopublish.conf"),
    os.path.join(MY_PATH, "voctopublish.conf"),
    os.path.join(MY_PATH, "client.conf"),
]


class Depublisher:
    """
    This is the main class for the Voctopublish application
    It is meant to be used with the c3tt ticket tracker
    """

    def __init__(self):
        for path in POSSIBLE_CONFIG_PATHS:
            if path:
                if os.path.isfile(path):
                    my_config_path = path
                    break
        else:
            raise FileNotFoundError(
                f"Could not find a valid config in any of these paths: {' '.join(POSSIBLE_CONFIG_PATHS)}"
            )

        with open(my_config_path) as f:
            self.config = toml_load(f.read())

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
        if self.config["general"]["debug"]:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s {%(filename)s:%(lineno)d} %(message)s"
            )
        else:
            formatter = logging.Formatter("%(asctime)s - %(message)s")

        sh.setFormatter(formatter)
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)

        level = self.config["general"]["debug"]
        if level == "info":
            self.logger.setLevel(logging.INFO)
        elif level == "warning":
            self.logger.setLevel(logging.WARNING)
        elif level == "error":
            self.logger.setLevel(logging.ERROR)
        elif level == "debug":
            self.logger.setLevel(logging.DEBUG)

        self.host = self.config["C3Tracker"].get("host", "").strip()
        if not self.host:
            self.host = socket.getfqdn()

        self.ticket_type = "encoding"
        self.to_state = "removing"

        # instance variables we need later
        self.ticket = None
        self.ticket_id = None

        logging.debug("creating C3TTClient")
        try:
            self.c3tt = C3TTClient(
                self.config["C3Tracker"]["url"],
                self.config["C3Tracker"]["group"],
                self.host,
                self.config["C3Tracker"]["secret"],
            )
        except Exception as e_:
            raise PublisherException(
                "Config parameter missing or empty, please check config"
            ) from e_

    def depublish(self):
        """
        Decide based on the information provided by the tracker where to publish.
        """

        self.ticket_id, self.ticket = self._get_ticket_from_tracker()

        if not self.ticket:
            logging.debug("not ticket, returning")
            return

        logging.info(f"trying to depublish ticket {self.ticket_id}")

        errors = set()
        # voctoweb
        if self.ticket.voctoweb_enable and self.ticket.voctoweb_event_id:
            logging.info(
                f"removing {self.ticket_id} from voctoweb, event id {self.ticket.voctoweb_event_id}"
            )
            try:
                self._depublish_from_voctoweb()
            except Exception as e:
                logging.exception("failed to remove video from voctoweb")
                errors.add(f"Removal from voctoweb failed: {e!r}")
        elif self.ticket.voctoweb_event_id:
            logging.warning(
                f"ticket has voctoweb_event_id={self.ticket.voctoweb_event_id} set, but voctoweb is disabled. NOT removing!"
            )
        else:
            logging.info("ticket not on voctoweb")

        if self.ticket.youtube_enable and self.ticket.has_youtube_url:
            try:
                self._depublish_from_youtube()
            except Exception as e:
                logging.exception("failed to remove video from youtube")
                errors.add(f"Removal from youtube failed: {e!r}")
        elif self.ticket.has_youtube_url:
            logging.warning(
                f"ticket has youtube urls set, but youtube is disabled. NOT removing!"
            )
        else:
            logging.info("ticket not on youtube")

        # TODO rclone
        # TODO webhook

        if errors:
            self.c3tt.set_ticket_failed(self.ticket_id, "\n".join(sorted(errors)))
        else:
            self.c3tt.set_ticket_done(
                self.ticket_id,
                f"Video depublished. YouTube videos have been set to private.",
            )

    def _depublish_from_voctoweb(self):
        vw = VoctowebClient(
            self.ticket,
            None,
            self.config["voctoweb"]["api_key"],
            self.config["voctoweb"]["api_url"],
            self.config["voctoweb"]["ssh_host"],
            self.config["voctoweb"]["ssh_port"],
            self.config["voctoweb"]["ssh_user"],
            self.config["voctoweb"]["frontend_url"],
        )

        event = vw.get_event()
        if "recordings" not in event:
            logging.info(
                "Can't find recordings for event. Event has probably been already deleted."
            )
            return

        for recording in event["recordings"]:
            path = recording["recording_url"].replace("https:/", "")
            vw.delete_file(path)

        vw.delete_event()

    def _get_ticket_from_tracker(self):
        """
        Request the next unassigned ticket for the configured states
        :return: a ticket object or None in case no ticket is available
        """
        logging.info("requesting ticket from tracker")
        t = None
        ticket_id = None
        ticket_meta = self.c3tt.assign_next_unassigned_for_state(
            self.ticket_type, self.to_state, {"EncodingProfile.IsMaster": "yes"}
        )
        if ticket_meta:
            ticket_id = ticket_meta["id"]
            logging.info("Ticket ID:" + str(ticket_id))
            try:
                tracker_ticket = self.c3tt.get_ticket_properties(ticket_id)
                logging.debug("Ticket Properties: " + str(tracker_ticket))
            except Exception as e_:
                self.c3tt.set_ticket_failed(ticket_id, e_)
                raise e_
            t = PublishingTicket(tracker_ticket, ticket_id, self.config)
        else:
            logging.info(
                "No ticket of type " + self.ticket_type + " for state " + self.to_state
            )

        return ticket_id, t

    def _depublish_from_youtube(self):
        """
        Depublish all videos from YouTube which belong to this ticket.
        """
        logging.debug("depublishing to youtube")

        yt = YoutubeAPI(
            self.ticket,
            None,
            self.config,
            self.config["youtube"]["client_id"],
            self.config["youtube"]["secret"],
        )
        yt.setup(self.ticket.youtube_token)

        youtube_urls, props = yt.depublish()
        props["Publishing.YouTube.UrlHistory"] = " ".join(
            [
                *self.ticket._get_list(
                    "Publishing.YouTube.UrlHistory", optional=True, split_by=" "
                ),
                *youtube_urls,
            ]
        )

        self.c3tt.set_ticket_properties(self.ticket_id, props)
        return youtube_urls


class DepublisherException(Exception):
    pass


if __name__ == "__main__":
    try:
        worker = Depublisher()
    except Exception as e:
        logging.error(e)
        logging.exception(e)
        sys.exit(-1)

    try:
        worker.depublish()
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        worker.c3tt.set_ticket_failed(
            worker.ticket_id, "%s: %s" % (exc_type.__name__, e)
        )
        logging.exception(e)
        sys.exit(-1)
