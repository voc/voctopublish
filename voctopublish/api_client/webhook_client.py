#!/usr/bin/env python3
#    Copyright (C) 2023 kunsi
#    git@kunsmann.eu
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

from requests import RequestException, post
from tools.announcements import EmptyAnnouncementMessage, make_message

LOG = logging.getLogger("Webhook")

"""
    Webhook gets POSTed to the specified url, format is JSON:

    {
        "announcement": "announcement message like it gets posted to social media", # or null if no message was generated
        "is_master": true,
        "fahrplan": {
            "conference": "democon",
            "id": 123,
            "language": "eng",
            "slug": "my-super-cool-talk",
            "title": "my super cool talk",
        },
        "voctoweb": {
            "cdn_url": "https://cdn.example.com/my-video.mp4",
            "enabled": true,
            "format": "h264-hd",
            "frontend_url": "https://example.com/my-video",
            "title": "media.ccc.de".
        },
        "youtube": {
            "enabled": true,
            "urls": [
                "https://example.com/asdf",
                "https://example.com/uiae",
            ],
        },
        "rclone": {
            "enabled": true,
            "destination": "demo:/my-video.mp4",
        },
    }

    If "enabled" is false, all other fields are missing.
"""


def send(ticket, config, voctoweb_filename, voctoweb_language, rclone):
    LOG.info(f"post webhook to {ticket.webhook_url}")

    r = None
    result = None
    try:
        content = _get_json(ticket, config, voctoweb_filename, language, rclone)
        LOG.debug(f"{content=}")

        if ticket.webhook_user and ticket.webhook_pass:
            r = post(
                ticket.webhook_url,
                auth=(ticket.webhook_user, ticket.webhook_pass),
                json=content,
            )
        else:
            r = post(
                ticket.webhook_url,
                json=content,
            )
        result = r.status_code
    except RequestException as e:
        pass

    if r:
        LOG.debug(f"{r.status_code=} {r.text=}")

    return result


def _get_json(ticket, config, voctoweb_filename, language, rclone):
    try:
        message = make_message(ticket)
    except EmptyAnnouncementMessage:
        message = None

    content = {
        "announcement": message,
        "is_master": ticket.master,
        "fahrplan": {
            "conference": ticket.acronym,
            "id": ticket.fahrplan_id,
            "language": language,
            "slug": ticket.slug,
            "title": ticket.title,
        },
    }

    if ticket.voctoweb_enable:
        content["voctoweb"] = {
            "cdn_url": "{}/{}/{}/{}".format(
                config["voctoweb"]["cdn_url"],
                ticket.voctoweb_path,
                ticket.folder,
                voctoweb_filename,
            ),
            "enabled": True,
            "format": self.folder,
            "frontend_url": "{}/v/{}".format(
                config["voctoweb"]["frontend_url"],
                ticket.slug,
            ),
            "title": config["voctoweb"]["instance_name"],
        }
    else:
        content["voctoweb"] = {"enabled": False}

    if ticket.youtube_enable:
        content["youtube"] = {
            "enabled": True,
            "urls": list(ticket.youtube_urls.values()),
        }
    else:
        content["youtube"] = {"enabled": False}

    if ticket.rclone_enable and rclone:
        content["rclone"] = {
            "destination": rclone.destination,
            "enabled": True,
        }
    else:
        content["rclone"] = {"enabled": False}

    return content