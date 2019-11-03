#    Copyright (C) 2019  derpeter
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
    This class is inspired by the c3tt ticket system. It handles all information we got from the tracker
    and adds some additional information.
    """
    def __init__(self, ticket, ticket_id):
        if not ticket:
            raise TicketException('Ticket was None type')
        self.__tracker_ticket = ticket
        self.ticket_id = ticket_id

        # project properties
        self.acronym = self.__validate('Project.Slug')

        # fahrplan properties
        self.slug = self.__validate('Fahrplan.Slug')
        self.guid = self.__validate('Fahrplan.GUID')
        self.fahrplan_id = self.__validate('Fahrplan.ID')
        self.title = self.__validate('Fahrplan.Title')
        self.date = self.__validate('Fahrplan.Date')
        self.room = self.__validate('Fahrplan.Room')

        # the following are arguments that my not be present in every fahrplan
        self.people = []
        if 'Fahrplan.Person_list' in self.__tracker_ticket:
            self.people = self.__validate('Fahrplan.Person_list').split(', ')
        self.links = []
        if 'Fahrplan.Links' in self.__tracker_ticket:
            self.links = self.__validate('Fahrplan.Links', True).split(' ')

        self.subtitle = self.__validate('Fahrplan.Subtitle', True)
        self.abstract = self.__validate('Fahrplan.Abstract', True)
        self.description = self.__validate('Fahrplan.Description', True)
        self.track = self.__validate('Fahrplan.Track', True)
        self.day = self.__validate('Fahrplan.Day', True)
        self.url = self.__validate('Fahrplan.URL', True)

        # general publishing properties
        self.publishing_path = self.__validate('Publishing.Path')
        self.publishing_tags = self.__validate('Publishing.Tags', True)

        # encoding (profile) properties
        if self.__validate('EncodingProfile.IsMaster') == 'yes':
            self.master = True
        else:
            self.master = False
        self.profile_slug = self.__validate('EncodingProfile.Slug')
        if self.profile_slug == 'relive':
            # TODO: map two char language codes to three char ones in a more proper way...
            lang_map = {'en': 'eng', 'de': 'deu'}   # WORKAROUND
            self.language = lang_map[self.__validate('Fahrplan.Language')]
            self.languages = {0: self.language}
        else:
            self.profile_extension = self.__validate('EncodingProfile.Extension', optional=True)
            self.filename = self.__validate('EncodingProfile.Basename') + "." + self.profile_extension
            self.folder = self.__validate('EncodingProfile.MirrorFolder')
            self.language_index = self.__validate('Encoding.LanguageIndex', True)
            self.local_filename = self.fahrplan_id + "-" + self.profile_slug + "." + self.profile_extension
            self.local_filename_base = self.fahrplan_id + "-" + self.profile_slug

            # special case languages: if Encoding.Language is present, it overrides Record.Language:
            if 'Encoding.Language' in self.__tracker_ticket:
                self.language = self.__validate('Encoding.Language')
                self.languages = dict(enumerate(self.__validate('Encoding.Language').split('-')))
            else:
                self.language = self.__validate('Record.Language')
                self.languages = {int(k.split('.')[-1]): self.__validate(k) for k in self.__tracker_ticket.keys()
                                  if k.startswith('Record.Language.')}
            self.language_template = self.__validate('Encoding.LanguageTemplate')

            # youtube properties
            if self.__validate('Publishing.YouTube.EnableProfile') == 'yes':
                self.profile_youtube_enable = True
            else:
                self.profile_youtube_enable = False
            if self.__validate('Publishing.YouTube.Enable') == 'yes':
                self.youtube_enable = True
            else:
                self.youtube_enable = False
            # we will fill the following variables only if youtube is enabled
            if self.profile_youtube_enable and self.youtube_enable:
                self.youtube_token = self.__validate('Publishing.YouTube.Token')
                self.youtube_category = self.__validate('Publishing.YouTube.Category', True)
                self.youtube_privacy = self.__validate('Publishing.YouTube.Privacy', True)
                self.youtube_tags = self.__validate('Publishing.YouTube.Tags', True)
                self.youtube_title_prefix = self.__validate('Publishing.YouTube.TitlePrefix', True)
                self.youtube_title_prefix_speakers = self.__validate('Publishing.YouTube.TitlePrefixSpeakers', True)
                self.youtube_title_suffix = self.__validate('Publishing.YouTube.TitleSuffix', True)
                # check if this event has already been published to youtube
                if 'YouTube.Url0' in self.__tracker_ticket and self.__validate('YouTube.Url0') is not None:
                    self.has_youtube_url = True
                else:
                    self.has_youtube_url = False
                if self.__validate('Publishing.YouTube.Playlists', True) is not None:
                    self.youtube_playlists = self.__validate('Publishing.YouTube.Playlists', True).split(',')
                else:
                    self.youtube_playlists = []
                self.youtube_urls = ''

        # voctoweb properties
        if self.__validate('Publishing.Voctoweb.EnableProfile') == 'yes':
            self.profile_voctoweb_enable = True
        else:
            self.profile_voctoweb_enable = False
        if self.__validate('Publishing.Voctoweb.Enable') == 'yes':
            self.voctoweb_enable = True
        else:
            self.voctoweb_enable = False

        self.voctoweb_url = self.__validate('Publishing.Voctoweb.Url', True)
        # we will fill the following variables only if voctoweb is enabled
        if self.profile_voctoweb_enable and self.voctoweb_enable:
            self.mime_type = self.__validate('Publishing.Voctoweb.MimeType')
            self.voctoweb_thump_path = self.__validate('Publishing.Voctoweb.Thumbpath')
            self.voctoweb_path = self.__validate('Publishing.Voctoweb.Path')
            self.voctoweb_slug = self.__validate('Publishing.Voctoweb.Slug')
            self.voctoweb_tags = [self.acronym, self.fahrplan_id, self.date.split('-')[0]]
            if self.track:
                self.voctoweb_tags.append(self.track)
            if 'Publishing.Voctoweb.Tags' in self.__tracker_ticket:
                self.voctoweb_tags += self.__validate('Publishing.Voctoweb.Tags').replace(' ', '').split(',')
            if 'Publishing.Tags' in self.__tracker_ticket:
                self.voctoweb_tags += self.__validate('Publishing.Tags').replace(' ', '').split(',')

            # properties present in rerelease / update tickets
            self.voctoweb_event_id = self.__validate('Voctoweb.EventId', True)
            if self.voctoweb_event_id:
                self.recording_id_master = self.__validate('Voctoweb.RecordingId.Master', True)
                if len(self.languages) > 1:
                    self.translation_recordings = {}
                    for index in self.languages.keys():
                        self.translation_recordings.update(
                            {self.languages[index]: self.__validate('Voctoweb.RecordingId.' + self.languages[index])})

        # twitter properties
        if self.__validate('Publishing.Twitter.Enable') == 'yes':
            self.twitter_enable = True
        else:
            self.twitter_enable = False

        # mastodon properties
        if self.__validate('Publishing.Mastodon.Enable') == 'yes':
            self.mastodon_enable = True
        else:
            self.mastodon_enable = False

    def __validate(self, key, optional=False):
        """
        check for the presence of an property in the ticket.
        :param key: key of the property to be looked up in the ticket
        :param optional: Define if a property can be absent or not
        :return: The value of the property casted to str.
        """
        value = None
        if key in self.__tracker_ticket:
            value = self.__tracker_ticket[key]
            if not value and not optional:
                logging.debug(key + ' is empty in ticket')
                raise TicketException(key + ' is empty in ticket')
            else:
                value = str(value)
        else:
            if optional:
                logging.debug("optional property was not in ticket: " + key)
            else:
                logging.debug(key + ' is missing in ticket')
                raise TicketException(key + ' is missing in ticket')
        return value


class TicketException(Exception):
    pass
