#!/bin/python3
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

from mastodon import Mastodon
import logging
from pathlib import Path


def send_toot(ticket, config):
    logging.info("toot the release")

    target = ''
    youtube = False
    if ticket.voctoweb_enable and ticket.profile_voctoweb_enable:
        target = config['voctoweb']['instance_name']
    if ticket.youtube_enable and ticket.profile_youtube_enable and ticket.youtube_privacy == 'public':
        youtube = True
        if len(target) > 1:
            target += ' and '
        target += 'YouTube'

    if not target:
        logging.warning("no targets, abort")
        return

    msg = ' has been released on ' + target
    title = ticket.title
    if len(title) >= (500 - len(msg)):
        title = title[0:len(msg)]
    message = title + msg

    if ticket.voctoweb_enable and ticket.profile_voctoweb_enable:
        voctoweb_url = ' ' + config['voctoweb']['frontend_url'] + '/v/' + ticket.slug
        if len(voctoweb_url) <= (500 - len(message)):
            message = message + voctoweb_url
    if youtube and len(ticket.youtube_urls['YouTube.Url0']) <= (500 - len(message)):
        message = message + ' ' + ticket.youtube_urls['YouTube.Url0']

    try:
        # check if we already have our client token and secret and if not get a new one
        if not Path('./mastodon_clientcred.secret').exists():
            logging.debug('no mastodon client credentials found, get fresh ones')
            Mastodon.create_app(
                'voctopublish',
                api_base_url=config['mastodon']['api_base_url'],
                to_file='mastodon_clientcred.secret'
            )
        else:
            logging.debug('Using exisiting Mastodon client credentials')

        mastodon = Mastodon(
            client_id='mastodon_clientcred.secret',
            api_base_url=config['mastodon']['api_base_url']
        )

        # check if we already have an access token, if not get a fresh one
        if not Path('./mastodon_usercred.secret').exists():
            logging.debug('no mastodon user credentials found, getting a fresh token')
            mastodon.log_in(
                config['mastodon']['email'],
                config['mastodon']['password'],
                to_file='mastodon_usercred.secret'
            )
        else:
            logging.debug('Using existing Mastodon user token')

        # Create actual API instance
        mastodon = Mastodon(
            access_token='mastodon_usercred.secret',
            api_base_url=config['mastodon']['api_base_url']
        )
        mastodon.toot(message)
    except Exception as e_:
        # we don't care if tooting fails here.
        logging.error('Tooting failed: ' + str(e_))
