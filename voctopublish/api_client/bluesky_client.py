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

POST_MAX_LENGTH = 295  # actually 300, but allow room for some whitespace
LOG = logging.getLogger('Bluesky')

def send_post(ticket, config):
    LOG.info("post the release to bluesky")

    targets = []
    youtube = False
    if ticket.voctoweb_enable and ticket.profile_voctoweb_enable:
        voctoweb_url = config['voctoweb']['frontend_url'] + '/v/' + ticket.slug
        targets.append(config['voctoweb']['instance_name'])
        LOG.debug(f'voctoweb url is {voctoweb_url}')

    if ticket.youtube_enable and ticket.profile_youtube_enable and ticket.youtube_privacy == 'public':
        youtube = True
        youtube_url = ticket.youtube_urls['YouTube.Url0']
        targets.append('YouTube')
        LOG.debug(f'youtube url is {youtube_url}')

    if not targets:
        LOG.warning("Notification requested, but we don't have any links to show - aborting")
        return

    msg = ' has been released on {}'.format(' and '.join(targets))

    length_for_title = POST_MAX_LENGTH - len(msg)

    title = ticket.title
    if len(title) >= length_for_title:
        title = title[0:length_for_title]

    message = title + msg

    if (
        ticket.voctoweb_enable
        and ticket.profile_voctoweb_enable
        and len(voctoweb_url) <= (POST_MAX_LENGTH - len(message))
    ):
        message = message + ' ' + voctoweb_url

    if (
        youtube
        and len(youtube_url) <= (POST_MAX_LENGTH - len(message))
    ):
        message = message + ' ' + youtube_url

    LOG.info(f'post text: {message}')

    try:
        LOG.info(_send_bluesky_post(message, config))
    except Exception as e_:
        LOG.exception('Posting failed')


def _send_bluesky_post(message, config):
    post = {
        '$type': 'app.bsky.feed.post',
        'createdAt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'facets': [],
        'text': message,
    }

    for url in _parse_urls(message):
        post['facets'].append(
            {
                'features': [
                    {
                        '$type': 'app.bsky.richtext.facet#link',
                        'uri': url['url'],
                    }
                ],
                'index': {
                    'byteEnd': url['end'],
                    'byteStart': url['start'],
                },
            }
        )

    r = requests.post(
        'https://bsky.social/xrpc/com.atproto.server.createSession',
        json={
            'identifier': config['bluesky']['username'],
            'password': config['bluesky']['app_password'],
        },
    )
    r.raise_for_status()
    session = r.json()

    LOG.debug(post)

    r = requests.post(
        'https://bsky.social/xrpc/com.atproto.repo.createRecord',
        headers={
            'Authorization': f'Bearer {session["accessJwt"]}',
        },
        json={
            'collection': 'app.bsky.feed.post',
            'record': post,
            'repo': session['did'],
        },
    )
    LOG.debug(r.text)
    r.raise_for_status()
    return r.json()


def _parse_urls(text):
    spans = []
    url_regex = rb"[$|\W](https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
    text_bytes = text.encode("UTF-8")
    for m in finditer(url_regex, text_bytes):
        spans.append(
            {
                "start": m.start(1),
                "end": m.end(1),
                "url": m.group(1).decode("UTF-8"),
            }
        )
    return spans
