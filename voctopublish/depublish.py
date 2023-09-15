#!/usr/bin/python3
#    Copyright (C) 2022 andi
#    andi@muc.ccc.de
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

import configparser
import logging
import os
import socket
import subprocess
import sys

from api_client.c3tt_rpc_client import C3TTClient

# from api_client.voctoweb_client import VoctowebClient
from api_client.youtube_client import YoutubeAPI
from model.ticket_module import Ticket


class Depublisher:
    """
    This is the main class for the Voctopublish application
    It is meant to be used with the c3tt ticket tracker
    """

    def __init__(self):
        # load config
        if not os.path.exists('client.conf'):
            raise IOError("Error: config file not found")

        self.config = configparser.ConfigParser()
        self.config.read('client.conf')

        # set up logging
        logging.addLevelName(
            logging.WARNING,
            "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING),
        )
        logging.addLevelName(
            logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR)
        )
        logging.addLevelName(
            logging.INFO, "\033[1;32m%s\033[1;0m" % logging.getLevelName(logging.INFO)
        )
        logging.addLevelName(
            logging.DEBUG, "\033[1;85m%s\033[1;0m" % logging.getLevelName(logging.DEBUG)
        )

        self.logger = logging.getLogger()

        sh = logging.StreamHandler(sys.stdout)
        if self.config['general']['debug']:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s {%(filename)s:%(lineno)d} %(message)s'
            )
        else:
            formatter = logging.Formatter('%(asctime)s - %(message)s')

        sh.setFormatter(formatter)
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)

        level = self.config['general']['debug']
        if level == 'info':
            self.logger.setLevel(logging.INFO)
        elif level == 'warning':
            self.logger.setLevel(logging.WARNING)
        elif level == 'error':
            self.logger.setLevel(logging.ERROR)
        elif level == 'debug':
            self.logger.setLevel(logging.DEBUG)

        if self.config['C3Tracker']['host'] == "None":
            self.host = socket.getfqdn()
        else:
            self.host = self.config['C3Tracker']['host']

        self.ticket_type = self.config['C3Tracker']['ticket_type']
        self.to_state = 'removing'

        # instance variables we need later
        self.ticket = None

        logging.debug('creating C3TTClient')
        try:
            self.c3tt = C3TTClient(
                self.config['C3Tracker']['url'],
                self.config['C3Tracker']['group'],
                self.host,
                self.config['C3Tracker']['secret'],
            )
        except Exception as e_:
            raise PublisherException(
                'Config parameter missing or empty, please check config'
            ) from e_

    def depublish(self):
        """
        Decide based on the information provided by the tracker where to publish.
        """
        self.ticket = self._get_ticket_from_tracker()

        if not self.ticket:
            logging.debug('not ticket, returning')
            return

        '''
        # voctoweb
        logging.debug(f"#voctoweb {self.ticket.voctoweb_enable}")
        if self.ticket.voctoweb_enable:
            self._depublish_from_voctoweb()
        else:
            logging.debug("no voctoweb :(")
        '''
        # YouTube
        logging.debug(f"#youtube {self.ticket.youtube_enable}")
        urls = []
        if self.ticket.youtube_enable:
            if not self.ticket.has_youtube_url:
                raise DepublisherException(
                    'No YouTube URLs in ticket, can not depublish'
                )
            else:
                urls = self._depublish_from_youtube()
        else:
            logging.debug("no youtube :(")

        logging.debug('#done')
        self.c3tt.set_ticket_done(
            f'set following YouTube videos to private: {str(urls)}'
        )

    def _get_ticket_from_tracker(self):
        """
        Request the next unassigned ticket for the configured states
        :return: a ticket object or None in case no ticket is available
        """
        logging.info('requesting ticket from tracker')
        t = None
        ticket_id = self.c3tt.assign_next_unassigned_for_state(
            self.ticket_type, self.to_state
        )
        if ticket_id:
            logging.info("Ticket ID:" + str(ticket_id))
            try:
                tracker_ticket = self.c3tt.get_ticket_properties()
                logging.debug("Ticket: " + str(tracker_ticket))
            except Exception as e_:
                self.c3tt.set_ticket_failed(e_)
                raise e_
            t = Ticket(tracker_ticket, ticket_id)
        else:
            logging.info(
                'No ticket of type ' + self.ticket_type + ' for state ' + self.to_state
            )

        return t

    def _depublish_from_youtube(self):
        """
        Depublish all videos from YouTube which belong to this ticket.
        """
        logging.debug("depublishing to youtube")

        yt = YoutubeAPI(
            self.ticket,
            self.config['youtube']['client_id'],
            self.config['youtube']['secret'],
        )
        yt.setup(self.ticket.youtube_token)

        youtube_urls, props = yt.depublish()
        props['Publishing.YouTube.UrlHistory'] = (
            (self.ticket.get_raw_property('Publishing.YouTube.UrlHistory') or '')
            + ' '.join(youtube_urls)
            + ' '
        )

        self.c3tt.set_ticket_properties(props)
        return youtube_urls


class DepublisherException(Exception):
    pass


if __name__ == '__main__':
    try:
        worker = Depublisher()
    except Exception as e:
        logging.error(e)
        logging.exception(e)
        sys.exit(-1)

    try:
        worker.depublish()
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        worker.c3tt.set_ticket_failed('%s: %s' % (exc_type.__name__, e))
        logging.exception(e)
        sys.exit(-1)
