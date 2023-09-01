#!/bin/python3
#    Copyright (C) 2018  derpeter, 2023 kunsi
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
from pathlib import Path

from mastodon import Mastodon

from tools.announcements import EmptyAnnouncementMessage, make_message


def send_toot(ticket, config):
    LOG = logging.getLogger("Twitter")
    LOG.info("toot the release")

    try:
        message = make_message(ticket, 500)
    except EmptyAnnouncementMessage:
        return

    try:
        # check if we already have our client token and secret and if not get a new one
        if not Path("./mastodon_clientcred.secret").exists():
            logging.debug("no mastodon client credentials found, get fresh ones")
            Mastodon.create_app(
                "voctopublish",
                api_base_url=config["mastodon"]["api_base_url"],
                to_file="mastodon_clientcred.secret",
            )
        else:
            logging.debug("Using exisiting Mastodon client credentials")

        mastodon = Mastodon(
            client_id="mastodon_clientcred.secret",
            api_base_url=config["mastodon"]["api_base_url"],
        )

        # check if we already have an access token, if not get a fresh one
        if not Path("./mastodon_usercred.secret").exists():
            logging.debug("no mastodon user credentials found, getting a fresh token")
            mastodon.log_in(
                config["mastodon"]["email"],
                config["mastodon"]["password"],
                to_file="mastodon_usercred.secret",
            )
        else:
            logging.debug("Using existing Mastodon user token")

        # Create actual API instance
        mastodon = Mastodon(
            access_token="mastodon_usercred.secret",
            api_base_url=config["mastodon"]["api_base_url"],
        )
        mastodon.toot(message)
    except Exception as e_:
        # we don't care if tooting fails here.
        LOG.exception("Tooting failed")
