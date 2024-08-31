#    Copyright (C) 2021  derpeter
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
from os.path import join
from re import sub as re_sub


class Ticket:
    """
    This class is inspired by the c3tt ticket system. It handles all information we got from the tracker
    and adds some additional information.
    """

    def __init__(self, ticket, ticket_id):
        if not ticket:
            raise TicketException("Ticket was None type")
        self._tracker_ticket = ticket
        self.id = ticket_id

        # project properties
        self.acronym = self._get_str("Meta.Acronym", True) or self._get_str(
            "Project.Slug"
        )

        # general publishing properties
        self.publishing_path = ticket["Publishing.Path"]

    def __get_property(self, key):
        key = key.lower()
        for k, v in self._tracker_ticket.items():
            if k.lower() == key:
                return v
        return None

    def _get_str(self, key, optional=False):
        value = self.__get_property(key)
        if value is not None:
            value = str(value).strip()
        else:
            if optional:
                logging.warning("optional property was not in ticket: " + key)
            else:
                logging.debug(key + " is missing or empty in ticket")
                raise TicketException(key + " is missing or empty in ticket")
        return value

    def _get_list(self, key, optional=False, split_by=","):
        value = self._get_str(key, optional)
        if value is None:
            return []
        result = []
        for v in value.split(split_by):
            v = v.strip()
            if v:
                result.append(v)
        return result

    def _get_bool(self, key, optional=False):
        value = self._get_str(key, optional)
        if value is None:
            return None
        if value.lower() in ("yes", "1"):
            return True
        return False

    @staticmethod
    def _get_language_from_string_(lang):
        # https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes
        lang_map = {
            "ar": "ara",
            "de": "deu",
            "deutsch": "deu",
            "en": "eng",
            "englisch": "eng",
            "es": "spa",
            "fr": "fra",
            "gsw": "gsw",
            "zh": "chi",
        }

        out = []
        for l in lang.split("-"):
            if l in lang_map:
                out.append(lang_map[l])
            else:
                raise TicketException("language " + l + " not in language map")
        return "-".join(out)


class RecordingTicket(Ticket):
    """
    This is ticket we use for the download worker. This ticket has less information than an encoding ticket.
    """

    def __init__(self, ticket, ticket_id, config):
        super().__init__(ticket, ticket_id)

        fuse_path = self._get_str("Processing.Path.Raw", True)
        if not fuse_path:
            fuse_path = join(self._get_str("Processing.BasePath"), "fuse")

        # recording ticket properties
        self.download_url = self._get_str("Fahrplan.VideoDownloadURL")
        self.fuse_path = join(fuse_path, self._get_str("Project.Slug"))
        self.redownload_enabled = self._get_bool("Record.Redownload", True)

        download_tool = self._get_str("Record.DownloadHelper", True)
        if download_tool is None:
            download_tool = "python"
        if download_tool not in config["download"]["workers"]:
            raise TicketException(
                f'Record.DownloadHelper uses invalid value {download_tool}, must be one of {", ".join(sorted(config["download"]["workers"].keys()))}'
            )
        self.download_command = config["download"]["workers"][download_tool]

        # fahrplan properties
        self.fuse_room = re_sub('[^a-z0-9-_]+', '_', self._get_str("Fahrplan.Room").lower())
        self.fahrplan_id = self._get_str("Fahrplan.ID")
        self.language = self._get_language_from_string_(
            self._get_str("Fahrplan.Language")
        )


class PublishingTicket(Ticket):
    """
    This is a ticket we use for Voctopublish
    """

    def __init__(self, ticket, ticket_id, config):
        super().__init__(ticket, ticket_id)

        # recording ticket properties
        self.language = self._get_str("Record.Language", True)
        if self.language is None:
            self.language = self._validate("Fahrplan.Language")
        self.languages = {
            int(k.split(".")[-1]): self._get_str(k)
            for k in self._tracker_ticket
            if k.startswith("Record.Language.")
        }
        self.language_template = self._get_str("Encoding.LanguageTemplate")

        # encoding profile properties
        if self._get_bool("EncodingProfile.IsMaster"):
            self.master = True
        else:
            self.master = False
        self.profile_extension = self._get_str("EncodingProfile.Extension")
        self.profile_slug = self._get_str("EncodingProfile.Slug")
        self.filename = (
            self._get_str("EncodingProfile.Basename") + "." + self.profile_extension
        )
        self.folder = self._get_str("EncodingProfile.MirrorFolder")

        # encoding properties
        self.language_index = self._get_str("Encoding.LanguageIndex", True)

        # fahrplan properties
        self.slug = self._get_str("Fahrplan.Slug")
        self.fahrplan_id = self._get_str("Fahrplan.ID")
        self.title = self._get_str("Fahrplan.Title")
        self.subtitle = self._get_str("Fahrplan.Subtitle", True)
        self.date = self._get_str("Fahrplan.DateTime")
        self.local_filename = (
            self.fahrplan_id + "-" + self.profile_slug + "." + self.profile_extension
        )
        self.room = self._get_str("Fahrplan.Room")
        self.people = self._get_list("Fahrplan.Person_list")
        self.links = self._get_list("Fahrplan.Links", optional=True, split_by=" ")
        # the following are arguments that my not be present in every fahrplan
        self.track = self._get_str("Fahrplan.Track", True)
        self.day = self._get_str("Fahrplan.Day", True)
        self.url = self._get_str("Fahrplan.URL", True)

        # get abstract and description, if they are equal, ignore abstract
        self.abstract = self._get_str("Fahrplan.Abstract", True)
        self.description = self._get_str("Fahrplan.Description", True)

        if self.abstract == self.description:
            self.abstract = None

        # recording ticket properties

        # special case languages: if Encoding.Language is present, it overrides Record.Language:
        if "Encoding.Language" in ticket:
            self.language = self._get_str("Encoding.Language")
            self.languages = dict(
                enumerate(self._get_list("Encoding.Language", split_by="-"))
            )
        self.language_template = self._get_str("Encoding.LanguageTemplate")

        # general publishing properties
        self.publishing_path = self._get_str("Publishing.Path")
        self.thumbnail_file = self._get_str("Publishing.Thumbnail.PathOverride", True)

        self.publishing_tags = [
            self.acronym,
            self.track,
            self.room,
            self.date.split("-")[0],
            *self._get_list("Publishing.Tags", True),
        ]

        # youtube properties
        if self._get_bool("Publishing.YouTube.EnableProfile"):
            profile_youtube = True
        else:
            profile_youtube = False
        youtube = self._get_bool("Publishing.YouTube.Enable", True)
        if youtube is None:
            youtube = config["youtube"]["enable_default"]
        if youtube:
            self.youtube_enable = profile_youtube
        else:
            self.youtube_enable = False

        # we will fill the following variables only if youtube is enabled
        if self.youtube_enable:
            self.youtube_update = self._get_str(
                "Publishing.YouTube.Update", optional=True
            )
            self.youtube_token = self._get_str("Publishing.YouTube.Token")
            self.youtube_category = self._get_str("Publishing.YouTube.Category", True)
            self.youtube_privacy = (
                self._get_str("Publishing.YouTube.Privacy", True) or "private"
            )
            self.youtube_title_prefix = self._get_str(
                "Publishing.YouTube.TitlePrefix", True
            )
            self.youtube_translation_title_prefix = self._get_str(
                "Publishing.YouTube.TranslationTitlePrefix", True
            )
            self.youtube_title_prefix_speakers = self._get_bool(
                "Publishing.YouTube.TitlePrefixSpeakers", True
            )
            self.youtube_title_append_speakers = self._get_bool(
                "Publishing.YouTube.TitleAppendSpeakers", True
            )
            self.youtube_title_suffix = self._get_str(
                "Publishing.YouTube.TitleSuffix", True
            )
            self.youtube_translation_title_suffix = self._get_str(
                "Publishing.YouTube.TranslationTitleSuffix", True
            )
            self.youtube_publish_at = self._get_str(
                "Publishing.YouTube.PublishAt", True
            )

            self.youtube_urls = {}
            # check if this event has already been published to youtube
            for key in ticket:
                if key.lower().startswith('youtube.'):
                    self.has_youtube_url = True
                    self.youtube_urls[key] = self._get_str(key)
            else:
                self.has_youtube_url = False

            self.youtube_playlists = self._get_list(
                "Publishing.YouTube.Playlists", True
            )

            self.youtube_tags = [
                *self._get_list("Publishing.YouTube.Tags", True),
                *self.publishing_tags,
            ]
            if self.day:
                self.youtube_tags.append(f"Day {self.day}")

            if self.youtube_publish_at and self.youtube_privacy != "private":
                raise TicketException(
                    "Cannot use Publishing.YouTube.PublishAt when privacy is not 'private'!"
                )

        # voctoweb properties
        if self._get_bool("Publishing.Voctoweb.EnableProfile"):
            profile_voctoweb = True
        else:
            profile_voctoweb = False
        voctoweb = self._get_bool("Publishing.Voctoweb.Enable", True)
        if voctoweb is None:
            voctoweb = config["voctoweb"]["enable_default"]
        if voctoweb:
            self.voctoweb_enable = profile_voctoweb
        else:
            self.voctoweb_enable = False

        # we will fill the following variables only if voctoweb is enabled
        if self.voctoweb_enable:
            self.guid = self._get_str("Fahrplan.GUID")
            self.voctoweb_filename_base = self.fahrplan_id + "-" + self.guid

            self.mime_type = self._get_str("Publishing.Voctoweb.MimeType")
            self.voctoweb_thumb_path = self._get_str("Publishing.Voctoweb.Thumbpath")
            self.voctoweb_path = self._get_str("Publishing.Voctoweb.Path")
            self.voctoweb_slug = self._get_str("Publishing.Voctoweb.Slug")
            self.recording_id = self._get_str("Voctoweb.RecordingId.Master", True)
            self.voctoweb_event_id = self._get_str("Voctoweb.EventId", True)
            self.voctoweb_tags = [
                self.fahrplan_id,
                *self._get_list("Publishing.Voctoweb.Tags", True),
                *self.publishing_tags,
            ]
            if self.day:
                self.voctoweb_tags.append(f"Day {self.day}")

        # rclone properties
        self.rclone_enabled = self._get_bool("Publishing.Rclone.Enable", True)
        if self.rclone_enabled is None:
            self.rclone_enabled = config["rclone"]["enable_default"]

        if self.rclone_enabled:
            self.rclone_destination = self._get_str("Publishing.Rclone.Destination")
            self.rclone_only_master = self._get_bool("Publishing.Rclone.OnlyMaster")

        # twitter properties
        self.witter_enable = self._get_bool("Publishing.Twitter.Enable", True)
        if self.twitter_enable is None:
            self.twitter_enable = config["twitter"]["enable_default"]

        # mastodon properties
        self.mastodon_enable = self._get_bool("Publishing.Mastodon.Enable", True)
        if self.mastodon_enable is None:
            self.mastodon_enable = config["mastodon"]["enable_default"]

        # bluesky properties
        self.bluesky_enable = self._get_bool("Publishing.Bluesky.Enable", True)
        if self.bluesky_enable is None:
            self.bluesky_enable = config["bluesky"]["enable_default"]

        # googlechat properties
        self.googlechat_webhook_url = self._get_str(
            "Publishing.Googlechat.Webhook", True
        )

    def has_property(self, key):
        return key in self.__tracker_ticket

    def get_raw_property(self, key, optional=True):
        value = None
        if key in self._tracker_ticket:
            value = self._tracker_ticket[key]
        else:
            if not optional:
                logging.debug(key + " is missing in ticket")
                raise TicketException(key + " is missing in ticket")
        return value


class TicketException(Exception):
    pass
