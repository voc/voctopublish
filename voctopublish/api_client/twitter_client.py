#!/bin/python3
#    Copyright (C) 2017  derpeter, 2023 kunsi
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

from tools.announcements import EmptyAnnouncementMessage, make_message
from twitter import OAuth, Twitter


def send_tweet(ticket, config):
    LOG = logging.getLogger("Twitter")
    LOG.info("tweeting the release")

    try:
        message = make_message(ticket, config, 280, 24)
    except EmptyAnnouncementMessage:
        return

    try:
        t = Twitter(
            auth=OAuth(
                config["twitter"]["token"],
                config["twitter"]["token_secret"],
                config["twitter"]["consumer_key"],
                config["twitter"]["consumer_secret"],
            )
        )
        ret = t.statuses.update(status=message)
        LOG.debug(ret)
    except Exception as e_:
        # we don't care if twitter fails here. We can handle this after rewriting this to oauth2
        LOG.exception("Twittering failed")
