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

from model.ticket_module import Ticket


def send_toot(ticket, config):
    logging.info("toot the release")

    target = ''
    if ticket.voctoweb_enable and ticket.profile_voctoweb_enable:
        target = 'media.ccc.de'  # todo this should be generic but voctoweb is also not usefull here
    if ticket.youtube_enable and ticket.profile_youtube_enable:
        if len(target) > 1:
            target += ' and '
        target += 'YouTube'

    msg = ' has been released on ' + target
    title = ticket.title
    if len(title) >= (500 - len(msg)):
        title = title[0:len(msg)]
    message = title + msg

    voctoweb_url = 'https://media.ccc.de/v/' + ticket.voctoweb_slug
    if len(voctoweb_url) >= (500 - len(message)):
        message = message + voctoweb_url

    try:
        Mastodon.create_app(
            'pytooterapp',
            api_base_url=config['api_base_url'],
            to_file='pytooter_clientcred.secret'
        )

        mastodon = Mastodon(
            client_id='pytooter_clientcred.secret',
            api_base_url='https://chaos.social'
        )
        mastodon.log_in(
            config['email'],
            config['password'],
            to_file='pytooter_usercred.secret'
        )

        # Create actual API instance
        mastodon = Mastodon(
            access_token='pytooter_usercred.secret',
            api_base_url=config['api_base_url']
        )
        mastodon.toot(message)
    except Exception as e_:
        # we don't care if tooting fails here.
        logging.error('Tooting failed: ' + str(e_))
