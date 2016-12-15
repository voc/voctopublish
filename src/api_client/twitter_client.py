#!/bin/python3
#    Copyright (C) 2014  derpeter
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

from twitter import *
import logging
logger = logging.getLogger()


def send_tweet(ticket, token, token_secret, consumer_key, consumer_secret):
    logger.info("tweeting the release")
    #FIXME we need a nicer solution for this but it is christmas
    
    if ticket['EncodingProfile.Slug'] == "hd":
        target = "media.ccc.de and youtube"
    else:
        target = "media.ccc.de"
        
    msg = " has been released as " + str(ticket['EncodingProfile.Slug']) + " on " + target
    title = str(ticket['Fahrplan.Title'])
    if len(title) >= (160 - len(msg)):
        title = title[0:len(msg)]
    message =  title + msg
    t = Twitter(auth=OAuth(token, token_secret, consumer_key, consumer_secret))
    ret = t.statuses.update(status=message)
    logger.debug(ret)