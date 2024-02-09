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
        self.acronym = self._validate_("Meta.Acronym", True) or self._validate_(
            "Project.Slug"
        )

        # general publishing properties
        self.publishing_path = ticket["Publishing.Path"]

    def _validate_(self, key, optional=False):
        value = None
        if key in self._tracker_ticket and self._tracker_ticket[key]:
            value = str(self._tracker_ticket[key]).strip()
        else:
            if optional:
                logging.warning("optional property was not in ticket: " + key)
            else:
                logging.debug(key + " is missing or empty in ticket")
                raise TicketException(key + " is missing or empty in ticket")
        return value

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

        fuse_path = self._validate_("Processing.Path.Raw", True)
        if not fuse_path:
            fuse_path = join(self._validate_("Processing.BasePath"), "fuse")

        # recording ticket properties
        self.download_url = self._validate_("Fahrplan.VideoDownloadURL")
        self.fuse_path = join(fuse_path, self._validate_("Project.Slug"))
        self.redownload_enabled = self._validate_("Record.Redownload", True) == "yes"

        download_tool = self._validate_("Record.DownloadHelper", True)
        if download_tool is None:
            download_tool = "python"
        if download_tool not in config["download"]["workers"]:
            raise TicketException(
                f'Record.DownloadHelper uses invalid value {download_tool}, must be one of {", ".join(sorted(config["download"]["workers"].keys()))}'
            )
        self.download_command = config["download"]["workers"][download_tool]

        # fahrplan properties
        self.room = self._validate_("Fahrplan.Room")
        self.fahrplan_id = self._validate_("Fahrplan.ID")
        self.language = self._get_language_from_string_(
            self._validate_("Fahrplan.Language")
        )


class PublishingTicket(Ticket):
    """
    This is a ticket we use for Voctopublish
    """

    def __init__(self, ticket, ticket_id, config):
        super().__init__(ticket, ticket_id)

        # recording ticket properties
        self.language = self._validate_("Record.Language")
        self.languages = {
            int(k.split(".")[-1]): self._validate_(k)
            for k in self._tracker_ticket
            if k.startswith("Record.Language.")
        }
        self.language_template = self._validate_("Encoding.LanguageTemplate")

        # encoding profile properties
        if self._validate_("EncodingProfile.IsMaster") == "yes":
            self.master = True
        else:
            self.master = False
        self.profile_extension = self._validate_("EncodingProfile.Extension")
        self.profile_slug = self._validate_("EncodingProfile.Slug")
        self.filename = (
            self._validate_("EncodingProfile.Basename") + "." + self.profile_extension
        )
        self.folder = self._validate_("EncodingProfile.MirrorFolder")

        # encoding properties
        self.language_index = self._validate_("Encoding.LanguageIndex", True)

        # fahrplan properties
        self.slug = self._validate_("Fahrplan.Slug")
        self.fahrplan_id = self._validate_("Fahrplan.ID")
        self.title = self._validate_("Fahrplan.Title")
        self.subtitle = self._validate_("Fahrplan.Subtitle", True)
        self.date = self._validate_("Fahrplan.DateTime")
        self.local_filename = (
            self.fahrplan_id + "-" + self.profile_slug + "." + self.profile_extension
        )
        self.room = self._validate_("Fahrplan.Room")
        self.people = []
        if "Fahrplan.Person_list" in ticket:
            self.people = self._validate_("Fahrplan.Person_list").split(", ")
        self.links = []
        if "Fahrplan.Links" in ticket:
            self.links = self._validate_("Fahrplan.Links", True).split(" ")
        # the following are arguments that my not be present in every fahrplan
        self.track = self._validate_("Fahrplan.Track", True)
        self.day = self._validate_("Fahrplan.Day", True)
        self.url = self._validate_("Fahrplan.URL", True)

        # get abstract and description, if they are equal, ignore abstract
        self.abstract = self._validate_("Fahrplan.Abstract", True)
        self.description = self._validate_("Fahrplan.Description", True)

        if self.abstract == self.description:
            self.abstract = None

        # recording ticket properties

        # special case languages: if Encoding.Language is present, it overrides Record.Language:
        if "Encoding.Language" in ticket:
            self.language = self._validate_("Encoding.Language")
            self.languages = dict(
                enumerate(self._validate_("Encoding.Language").split("-"))
            )
        else:
            self.language = self._validate_("Record.Language")
            self.languages = {
                int(k.split(".")[-1]): self._validate_(k)
                for k in self._tracker_ticket
                if k.startswith("Record.Language.")
            }
        self.language_template = self._validate_("Encoding.LanguageTemplate")

        # general publishing properties
        self.publishing_path = self._validate_("Publishing.Path")
        self.publishing_tags = self._validate_("Publishing.Tags", True)
        self.thumbnail_file = self._validate_("Publishing.Thumbnail.PathOverride", True)

        # youtube properties
        if self._validate_("Publishing.YouTube.EnableProfile") == "yes":
            profile_youtube = True
        else:
            profile_youtube = False
        youtube = self._validate_("Publishing.YouTube.Enable", True)
        if youtube is None:
            youtube = config["youtube"]["enable_default"]
        if youtube == "yes":
            self.youtube_enable = profile_youtube
        else:
            self.youtube_enable = False

        # we will fill the following variables only if youtube is enabled
        if self.youtube_enable:
            self.youtube_update = self._validate_(
                "Publishing.YouTube.Update", optional=True
            )
            self.youtube_token = self._validate_("Publishing.YouTube.Token")
            self.youtube_category = self._validate_("Publishing.YouTube.Category", True)
            self.youtube_privacy = (
                self._validate_("Publishing.YouTube.Privacy", True) or "private"
            )
            self.youtube_tags = self._validate_("Publishing.YouTube.Tags", True)
            self.youtube_title_prefix = self._validate_(
                "Publishing.YouTube.TitlePrefix", True
            )
            self.youtube_translation_title_prefix = self._validate_(
                "Publishing.YouTube.TranslationTitlePrefix", True
            )
            self.youtube_title_prefix_speakers = self._validate_(
                "Publishing.YouTube.TitlePrefixSpeakers", True
            )
            self.youtube_title_append_speakers = self._validate_(
                "Publishing.YouTube.TitleAppendSpeakers", True
            )
            self.youtube_title_suffix = self._validate_(
                "Publishing.YouTube.TitleSuffix", True
            )
            self.youtube_translation_title_suffix = self._validate_(
                "Publishing.YouTube.TranslationTitleSuffix", True
            )
            self.youtube_publish_at = self._validate_(
                "Publishing.YouTube.PublishAt", True
            )
            self.youtube_urls = {}
            # check if this event has already been published to youtube
            if (
                "YouTube.Url0" in self._tracker_ticket
                and self._validate_("YouTube.Url0") is not None
            ):
                self.has_youtube_url = True

                for key in ticket:
                    if key.startswith("YouTube."):
                        self.youtube_urls[key] = self._validate_(key)
            else:
                self.has_youtube_url = False
            if self._validate_("Publishing.YouTube.Playlists", True) is not None:
                self.youtube_playlists = self._validate_(
                    "Publishing.YouTube.Playlists", True
                ).split(",")
            else:
                self.youtube_playlists = []

            if self.youtube_publish_at and self.youtube_privacy != "private":
                raise TicketException(
                    "Cannot use Publishing.YouTube.PublishAt when privacy is not 'private'!"
                )

        # voctoweb properties
        if self._validate_("Publishing.Voctoweb.EnableProfile") == "yes":
            profile_voctoweb = True
        else:
            profile_voctoweb = False
        voctoweb = self._validate_("Publishing.Voctoweb.Enable", True)
        if voctoweb is None:
            voctoweb = config["voctoweb"]["enable_default"]
        if voctoweb == "yes":
            self.voctoweb_enable = profile_voctoweb
        else:
            self.voctoweb_enable = False

        # we will fill the following variables only if voctoweb is enabled
        if self.voctoweb_enable:
            self.guid = self._validate_("Fahrplan.GUID")
            self.voctoweb_filename_base = self.fahrplan_id + "-" + self.guid

            self.mime_type = self._validate_("Publishing.Voctoweb.MimeType")
            self.voctoweb_thump_path = self._validate_("Publishing.Voctoweb.Thumbpath")
            self.voctoweb_path = self._validate_("Publishing.Voctoweb.Path")
            self.voctoweb_slug = self._validate_("Publishing.Voctoweb.Slug")
            self.voctoweb_tags = [
                self.acronym,
                self.fahrplan_id,
                self.date.split("-")[0],
            ]
            if self.track:
                self.voctoweb_tags.append(self.track)
            if "Publishing.Voctoweb.Tags" in ticket:
                self.voctoweb_tags += (
                    self._validate_("Publishing.Voctoweb.Tags", True)
                    .replace(" ", "")
                    .split(",")
                )
            if "Publishing.Tags" in ticket:
                self.voctoweb_tags += (
                    self._validate_("Publishing.Tags", True).replace(" ", "").split(",")
                )
            self.recording_id = self._validate_("Voctoweb.RecordingId.Master", True)
            self.voctoweb_event_id = self._validate_("Voctoweb.EventId", True)

        # rclone properties
        rclone_enabled = self._validate_("Publishing.Rclone.Enable", True)
        if rclone_enabled is None:
            rclone_enabled = "yes" if config["rclone"]["enable_default"] else "no"
        self.rclone_enabled = rclone_enabled == "yes"

        if self.rclone_enabled:
            self.rclone_destination = self._validate_("Publishing.Rclone.Destination")
            self.rclone_only_master = (
                self._validate_("Publishing.Rclone.OnlyMaster") == "yes"
            )

        # twitter properties
        twitter_enable = self._validate_("Publishing.Twitter.Enable", True) == "yes"
        if twitter_enable is None:
            twitter_enable = config["twitter"]["enable_default"]
        self.twitter_enable = twitter_enable

        # mastodon properties
        mastodon_enable = self._validate_("Publishing.Mastodon.Enable", True) == "yes"
        if mastodon_enable is None:
            mastodon_enable = config["mastodon"]["enable_default"]
        self.mastodon_enable = mastodon_enable

        # bluesky properties
        bluesky_enable = self._validate_("Publishing.Bluesky.Enable", True) == "yes"
        if bluesky_enable is None:
            bluesky_enable = config["bluesky"]["enable_default"]
        self.bluesky_enable = bluesky_enable

        # googlechat properties
        self.googlechat_webhook_url = self._validate_(
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
