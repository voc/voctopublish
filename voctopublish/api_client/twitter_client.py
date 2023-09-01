#!/bin/python3
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

from twitter import OAuth, Twitter

logging = logging.getLogger()


def send_tweet(ticket, config):
    logging.info("tweeting the release")
    target = ''
    if ticket.voctoweb_enable and ticket.profile_voctoweb_enable:
        target = config['voctoweb']['instance_name']
    if ticket.youtube_enable and ticket.profile_youtube_enable:
        if len(target) > 1:
            target += ' and '
        target += 'YouTube'

    if not target:
        logging.warning("no targets, aborting")
        return

    msg = ' has been released on ' + target
    title = ticket.title
    if len(title) >= (280 - len(msg)):
        title = title[0:len(msg)]
    message = title + msg

    # URLs on twitter are always 23 characters and we need a space as separator. If we have still enough space we add voctoweb and / or youtube url
    if ticket.voctoweb_enable and ticket.profile_voctoweb_enable and len(message) <= (280 - 24):
        message = message + ' ' + config['voctoweb']['frontend_url'] + '/v/' + ticket.slug
    if ticket.youtube_enable and ticket.profile_youtube_enable and len(message) <= (280 - 24):
        message = message + ' ' + ticket.youtube_urls['YouTube.Url0']

    try:
        t = Twitter(auth=OAuth(config['twitter']['token'], config['twitter']['token_secret'], config['twitter']['consumer_key'], config['twitter']['consumer_secret']))
        ret = t.statuses.update(status=message)
        logging.debug(ret)
    except Exception as e_:
        # we don't care if twitter fails here. We can handle this after rewriting this to oauth2
        logging.error('Twittering failed: ' + str(e_))

