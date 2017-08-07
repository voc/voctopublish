#!/bin/python3
#    Copyright (C) 2016  derpeter
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

from twitter import Twitter, OAuth
import logging
logging = logging.getLogger()


def send_tweet(ticket, config):
    logging.info("tweeting the release")
    # todo add more logic here. Also we should only tweet the master releases
    # only tweet master releases
    target = ''
    if ticket.master:
        if ticket.media_enable and ticket.profile_media_enable:
            target = 'media.ccc.de'  # todo this should be generic but voctoweb is also not usefull here
        if ticket.youtube_enable and ticket.profile_youtube_enable:
            if len(target) > 1:
                target += ' and '
            target += 'YouTube'

        msg = " has been released on " + target
        title = ticket.title
        if len(title) >= (160 - len(msg)):
            title = title[0:len(msg)]
        message = title + msg
        # todo switch to oauth2

        t = Twitter(auth=OAuth(config['token'], config['token_secret'], config['consumer_key'], config['consumer_secret']))
        ret = t.statuses.update(status=message)
        logging.debug(ret)
    else:
        logging.info('this is not a master => no twitter')
