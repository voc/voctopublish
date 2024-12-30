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
from datetime import datetime, timezone
from re import finditer

import requests
from tools.announcements import EmptyAnnouncementMessage, make_message

LOG = logging.getLogger("Bluesky")


def send_post(ticket, config):
    LOG.info("post the release to bluesky")

    try:
        message = make_message(ticket, config, 280)
    except EmptyAnnouncementMessage:
        return

    try:
        LOG.info(_send_bluesky_post(message, config))
    except Exception as e_:
        LOG.exception("Posting failed")


def _send_bluesky_post(message, config):
    post = {
        "$type": "app.bsky.feed.post",
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "facets": [],
        "text": message,
    }

    for url in _parse_urls(message):
        post["facets"].append(
            {
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#link",
                        "uri": url["url"],
                    }
                ],
                "index": {
                    "byteEnd": url["end"],
                    "byteStart": url["start"],
                },
            }
        )

    for url in _parse_hashtags(message):
        post["facets"].append(
            {
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#tag",
                        "tag": url["tag"],
                    }
                ],
                "index": {
                    "byteEnd": url["end"],
                    "byteStart": url["start"],
                },
            }
        )

    r = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={
            "identifier": config["bluesky"]["username"],
            "password": config["bluesky"]["app_password"],
        },
    )
    r.raise_for_status()
    session = r.json()

    LOG.debug(post)

    r = requests.post(
        "https://bsky.social/xrpc/com.atproto.repo.createRecord",
        headers={
            "Authorization": f'Bearer {session["accessJwt"]}',
        },
        json={
            "collection": "app.bsky.feed.post",
            "record": post,
            "repo": session["did"],
        },
    )
    LOG.debug(r.text)
    r.raise_for_status()
    return r.json()


def _parse_urls(text):
    url_regex = rb"[$|\W](https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
    text_bytes = text.encode("UTF-8")
    for m in finditer(url_regex, text_bytes):
        yield {
            "start": m.start(1),
            "end": m.end(1),
            "url": m.group(1).decode("UTF-8"),
        }


def _parse_hashtags(text):
    tag_regex = rb"[$|\W](#\S+)"
    text_bytes = text.encode("UTF-8")
    for m in finditer(tag_regex, text_bytes):
        yield {
            "start": m.start(1),
            "end": m.end(1),
            "tag": m.group(1).decode("UTF-8")[1:],
        }
