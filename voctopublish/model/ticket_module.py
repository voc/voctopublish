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


class Ticket:
    """
    This class is inspired by the c3tt ticket system. If handles all information we got from the tracker
    and adds some additional information.
    """
    def __init__(self, ticket, ticket_id):
        if not ticket:
            raise TicketException('Ticket was None type')
        self.__tracker_ticket = ticket
        self.ticket_id = ticket_id

        # project properties
        self.acronym = self._validate_('Project.Slug')

        # general publishing properties
        self.publishing_path = self._validate_('Publishing.Path')

    def _validate_(self, key, optional=False):
        value = None
        if key in self.__tracker_ticket:
            value = self.__tracker_ticket[key]
            if not value:
                logging.debug(key + ' is empty in ticket')
                raise TicketException(key + ' is empty in ticket')
            else:
                value = str(value)
        else:
            if optional:
                logging.warning("optional property was not in ticket: " + key)
            else:
                logging.debug(key + ' is missing in ticket')
                raise TicketException(key + ' is missing in ticket')
        return value


class RecordingTicket(Ticket):
    '''
    This is ticket we use for the download worker. This ticket has less information than an encoding ticket.
    '''

    def __init__(self, ticket, ticket_id):
        Ticket.__init__(self, ticket, ticket_id)

        # recording ticket properties
        self.download_url = self._validate_('Fahrplan.VideoDownloadURL')
        self.fuse_path = self._validate_('Processing.Path.Raw') + self._validate_('Project.Slug')

        # fahrplan properties
        self.room = self._validate_('Fahrplan.Room')
        self.fahrplan_id = self._validate_('Fahrplan.ID')
        lang_in = self._validate_('Fahrplan.Language')
        # todo make a lookup table which can be used app wide
        if lang_in == 'de' or lang_in == 'deutsch':
            self.language = 'deu'
        elif lang_in == 'en' or lang_in == 'englisch':
            self.language = 'eng'



class PublishingTicket(Ticket):
    '''
    This is a ticket we use for Voctopublish
    '''

    def __init__(self, ticket, ticket_id):
        Ticket.__init__(self, ticket, ticket_id)

        # recording ticket properties
        self.language = self._validate_('Record.Language')
        self.languages = {int(k.split('.')[-1]): self._validate_(k) for k in self.__tracker_ticket.keys()
                          if k.startswith('Record.Language.')}
        self.language_template = self._validate_('Encoding.LanguageTemplate')

        # encoding profile properties
        if self._validate_('EncodingProfile.IsMaster') == 'yes':
            self.master = True
        else:
            self.master = False
        self.profile_extension = self._validate_('EncodingProfile.Extension')
        self.profile_slug = self._validate_('EncodingProfile.Slug')
        self.filename = self._validate_('EncodingProfile.Basename') + "." + self.profile_extension
        self.folder = self._validate_('EncodingProfile.MirrorFolder')

        # encoding properties
        self.language_index = self._validate_('Encoding.LanguageIndex', True)

        # fahrplan properties
        self.slug = self._validate_('Fahrplan.Slug')
        self.guid = self._validate_('Fahrplan.GUID')
        self.fahrplan_id = self._validate_('Fahrplan.ID')
        self.title = self._validate_('Fahrplan.Title')
        self.subtitle = self._validate_('Fahrplan.Subtitle', True)
        self.abstract = self._validate_('Fahrplan.Abstract', True)
        self.description = self._validate_('Fahrplan.Description', True)
        self.date = self._validate_('Fahrplan.Date')
        self.local_filename = self.fahrplan_id + "-" + self.profile_slug + "." + self.profile_extension
        self.local_filename_base = self.fahrplan_id + "-" + self.profile_slug
        self.room = self._validate_('Fahrplan.Room')
        self.people = []
        if 'Fahrplan.Person_list' in ticket:
            self.people = self._validate_('Fahrplan.Person_list').split(', ')
        # the following are arguments that my not be present in every fahrplan
        self.track = self._validate_('Fahrplan.Track', True)
        self.day = self._validate_('Fahrplan.Day', True)

        # youtube properties
        self.profile_youtube_enable = self._validate_('Publishing.YouTube.EnableProfile')
        self.youtube_enable = self._validate_('Publishing.YouTube.Enable')
        # we will fill the following variables only if youtube is enabled
        if self.profile_youtube_enable == 'yes' and self.youtube_enable == 'yes':
            self.youtube_token = self._validate_('Publishing.YouTube.Token')
            self.youtube_category = self._validate_('Publishing.YouTube.Category', True)
            self.youtube_privacy = self._validate_('Publishing.YouTube.Privacy', True)
            self.youtube_tags = self._validate_('Publishing.YouTube.Tags', True)
            if self.track:
                self.youtube_tags += self.track
            self.youtube_title_prefix = self._validate_('Publishing.YouTube.TitlePrefix', True)
            self.youtube_title_suffix = self._validate_('Publishing.YouTube.TitleSuffix', True)
            # check if this event has already been published to youtube
            if 'YouTube.Url0' in ticket and self._validate_('YouTube.Url0') is not None:
                self.has_youtube_url = True
            else:
                self.has_youtube_url = False

        # voctoweb properties
        self.profile_media_enable = self._validate_('Publishing.Media.EnableProfile')
        self.media_enable = self._validate_('Publishing.Media.Enable')
        # we will fill the following variables only if voctoweb is enabled
        if self.profile_media_enable == 'yes' and self.media_enable == 'yes':
            self.mime_type = self._validate_('Publishing.Media.MimeType')
            self.media_thump_path = self._validate_('Publishing.Media.Thumbpath')
            self.media_host = self._validate_('Publishing.Media.Host')
            self.media_user = self._validate_('Publishing.Media.User')
            self.media_path = self._validate_('Publishing.Media.Path')
            self.media_slug = self._validate_('Publishing.Media.Slug')
            self.media_url = self._validate_('Publishing.Media.Url', True)
            self.tags = [self.acronym, self.fahrplan_id]
            if self.track:
                self.tags.append(self.track)
            if 'Media.Tags' in ticket:
                self.tags += self._validate_('Media.Tags').replace(' ', '').split(',')
            self.recording_id = self._validate_('Voctoweb.RecordingId.Master', True)

        # twitter properties
        self.twitter_enable = self._validate_('Publishing.Twitter.Enable')


class TicketException(Exception):
    pass
