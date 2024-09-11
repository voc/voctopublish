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
import re
from os.path import join


class Ticket:
    """
    This class is inspired by the c3tt ticket system. It handles all information we got from the tracker
    and adds some additional information.
    """

    def __init__(self, ticket, ticket_id, config):
        if not ticket:
            raise TicketException("Ticket was None type")
        self._tracker_ticket = ticket
        self.id = ticket_id
        self.config = config

        # project properties
        self.acronym = self._get_str("Meta.Acronym", True) or self._get_str(
            "Project.Slug"
        )

    def __get_default(self, key):
        key = key.lower()
        for k, v in self.config.get("defaults", {}).items():
            if k.lower() == key:
                if isinstance(v, bool):
                    return v
                return str(v).strip()
        return None

    def __get_property(self, key):
        key = key.lower()
        for k, v in self._tracker_ticket.items():
            if k.lower() == key:
                return str(v).strip()
        return None

    def _get_str(self, key, optional=False, try_default=False):
        value = self.__get_property(key)
        if not value:
            if try_default:
                logging.warning(
                    f"optional property '{key}' was not in ticket, trying default"
                )
                value = self.__get_default(key)
            elif optional:
                logging.warning(f"optional property '{key}' was not in ticket")
            if not optional and value in (None, ""):
                raise TicketException(f"Property '{key}' is missing or empty in ticket")
        return value

    def _get_list(self, key, optional=False, try_default=False, split_by=","):
        value = self._get_str(key, optional=optional, try_default=try_default)
        if value is None:
            return []
        result = []
        for v in value.split(split_by):
            v = v.strip()
            if v:
                result.append(v)
        return result

    def _get_bool(self, key, optional=False, try_default=False):
        value = self._get_str(key, optional=optional, try_default=try_default)
        if value is None:
            return None
        if isinstance(value, bool):
            return value
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
        super().__init__(ticket, ticket_id, config)

        fuse_path = self._get_str("Processing.Path.Raw", optional=True)
        if not fuse_path:
            fuse_path = join(self._get_str("Processing.BasePath"), "fuse")

        # recording ticket properties
        self.download_url = self._get_str("Fahrplan.VideoDownloadURL")
        self.fuse_path = join(fuse_path, self._get_str("Project.Slug"))
        self.redownload_enabled = self._get_bool("Record.Redownload", try_default=True)

        download_tool = self._get_str("Record.DownloadHelper", try_default=True)
        if download_tool not in config["download"]["workers"]:
            raise TicketException(
                f'Record.DownloadHelper uses invalid value {download_tool}, must be one of {", ".join(sorted(config["download"]["workers"].keys()))}'
            )
        self.download_command = config["download"]["workers"][download_tool]

        # fahrplan properties
        self.fuse_room = re.sub(
            "[^a-z0-9-_]+", "_", self._get_str("Fahrplan.Room").lower()
        )
        self.fahrplan_id = self._get_str("Fahrplan.ID")
        self.language = self._get_language_from_string_(
            self._get_str("Fahrplan.Language")
        )


class PublishingTicket(Ticket):
    """
    This is a ticket we use for Voctopublish
    """

    def __init__(self, ticket, ticket_id, config):
        super().__init__(ticket, ticket_id, config)

        # recording ticket properties
        self.language = self._get_str("Record.Language", optional=True)
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
        self.language_index = self._get_str("Encoding.LanguageIndex", optional=True)

        # fahrplan properties
        self.slug = self._get_str("Fahrplan.Slug")
        self.fahrplan_id = self._get_str("Fahrplan.ID")
        self.title = self._get_str("Fahrplan.Title")
        self.subtitle = self._get_str("Fahrplan.Subtitle", optional=True)
        self.date = self._get_str("Fahrplan.DateTime")
        self.local_filename = (
            self.fahrplan_id + "-" + self.profile_slug + "." + self.profile_extension
        )
        self.room = self._get_str("Fahrplan.Room")
        self.people = self._get_list("Fahrplan.Person_list")
        self.links = self._get_list("Fahrplan.Links", optional=True, split_by=" ")
        # the following are arguments that my not be present in every fahrplan
        self.track = self._get_str("Fahrplan.Track", optional=True)
        self.day = self._get_str("Fahrplan.Day", optional=True)
        self.url = self._get_str("Fahrplan.URL", optional=True)

        # get abstract and description, if they are equal, ignore abstract
        self.abstract = self._get_str("Fahrplan.Abstract", optional=True)
        self.description = self._get_str("Fahrplan.Description", optional=True)

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
        self.publishing_path = self._get_str("Publishing.Path", optional=True)
        if not self.publishing_path:
            self.publishing_path = join(
                self._get_str("Processing.BasePath"),
                "encoded",
                self._get_str("Project.Slug"),
            )

        self.thumbnail_file = self._get_str(
            "Publishing.Thumbnail.PathOverride", optional=True
        )

        self.publishing_tags = [
            self.acronym,
            self.track,
            self.room,
            self.date.split("-")[0],
            *self._get_list("Publishing.Tags", optional=True),
        ]

        # youtube properties
        if self._get_bool(
            "Publishing.YouTube.Enable", try_default=True
        ) and self._get_bool("Publishing.YouTube.EnableProfile", optional=True):
            self.youtube_enable = True
        else:
            self.youtube_enable = False

        # we will fill the following variables only if youtube is enabled
        if self.youtube_enable:
            self.youtube_update = self._get_str(
                "Publishing.YouTube.Update", try_default=True
            )
            self.youtube_token = self._get_str("Publishing.YouTube.Token")
            self.youtube_category = self._get_str(
                "Publishing.YouTube.Category", try_default=True
            )
            self.youtube_privacy = self._get_str(
                "Publishing.YouTube.Privacy", try_default=True
            )
            self.youtube_title_prefix = self._get_str(
                "Publishing.YouTube.TitlePrefix", optional=True
            )
            self.youtube_translation_title_prefix = self._get_str(
                "Publishing.YouTube.TranslationTitlePrefix", optional=True
            )
            self.youtube_title_prefix_speakers = self._get_bool(
                "Publishing.YouTube.TitlePrefixSpeakers", optional=True
            )
            self.youtube_title_append_speakers = self._get_bool(
                "Publishing.YouTube.TitleAppendSpeakers", optional=True
            )
            self.youtube_title_suffix = self._get_str(
                "Publishing.YouTube.TitleSuffix", optional=True
            )
            self.youtube_translation_title_suffix = self._get_str(
                "Publishing.YouTube.TranslationTitleSuffix", optional=True
            )

            self.youtube_urls = {}
            # check if this event has already been published to youtube
            for key in ticket:
                if key.lower().startswith("youtube."):
                    self.has_youtube_url = True
                    self.youtube_urls[key] = self._get_str(key)
            else:
                self.has_youtube_url = False

            self.youtube_playlists = self._get_list(
                "Publishing.YouTube.Playlists", optional=True
            )

            self.youtube_tags = [
                *self._get_list("Publishing.YouTube.Tags", optional=True),
                *self.publishing_tags,
            ]
            if self.day:
                self.youtube_tags.append(f"Day {self.day}")

            youtube_publish_at = self._get_str(
                "Publishing.YouTube.PublishAt", try_default=True
            )
            self.youtube_publish_at = None
            if youtube_publish_at:
                if self.youtube_privacy != "private":
                    raise TicketException(
                        "Cannot use Publishing.YouTube.PublishAt when privacy is not 'private'!"
                    )
                try:
                    self.youtube_publish_at = datetime.strptime(
                        youtube_publish_at, "%Y-%m-%d %H:%M"
                    )
                except ValueError:
                    result = re.findall(r"(\d+[wdh])", youtube_publish_at)
                    if not result:
                        raise TicketException(
                            "Invalid value for Publishing.YouTube.PublishAt, either use 'YYYY-MM-DD HH:MM' or relative values like '7d 2h' (*w*eeks, *d*ays and *h*ours supported)"
                        )
                    else:
                        kwargs = {}
                        for k, keyword in {
                            "w": "weeks",
                            "d": "days",
                            "h": "hours",
                        }:
                            for v in result:
                                if v.endswith(k):
                                    kwargs[keyword] = int(v[:-1])
                        self.youtube_publish_at = datetime.now(
                            timezone.utc
                        ) + timedelta(**kwargs)

        # voctoweb properties
        if self._get_bool(
            "Publishing.Voctoweb.Enable", try_default=True
        ) and self._get_bool("Publishing.Voctoweb.EnableProfile", optional=True):
            self.voctoweb_enable = True
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
            self.recording_id = self._get_str(
                "Voctoweb.RecordingId.Master", optional=True
            )
            self.voctoweb_event_id = self._get_str("Voctoweb.EventId", optional=True)
            self.voctoweb_tags = [
                self.fahrplan_id,
                *self._get_list("Publishing.Voctoweb.Tags", optional=True),
                *self.publishing_tags,
            ]
            if self.day:
                self.voctoweb_tags.append(f"Day {self.day}")

        # rclone properties
        self.rclone_enable = self._get_bool(
            "Publishing.Rclone.Enable", try_default=True
        )
        if self.rclone_enable:
            self.rclone_destination = self._get_str(
                "Publishing.Rclone.Destination", try_default=True
            )
            self.rclone_only_master = self._get_bool(
                "Publishing.Rclone.OnlyMaster", try_default=True
            )

        # generic webhook that gets called on release
        self.webhook_url = self._get_str("Publishing.Webhook.Url", try_default=True)
        if self.webhook_url:
            self.webhook_user = self._get_str(
                "Publishing.Webhook.User", try_default=True
            )
            self.webhook_pass = self._get_str(
                "Publishing.Webhook.Password", try_default=True
            )
            self.webhook_only_master = self._get_bool(
                "Publishing.Webhook.OnlyMaster", try_default=True
            )
            self.webhook_fail_on_error = self._get_bool(
                "Publishing.Webhook.FailOnError", try_default=True
            )

        # various announcement bots
        self.twitter_enable = self._get_bool(
            "Publishing.Twitter.Enable", try_default=True
        )
        self.mastodon_enable = self._get_bool(
            "Publishing.Mastodon.Enable", try_default=True
        )
        self.bluesky_enable = self._get_bool(
            "Publishing.Bluesky.Enable", try_default=True
        )
        self.googlechat_webhook_url = self._get_str(
            "Publishing.Googlechat.Webhook", try_default=True
        )


class TicketException(Exception):
    pass
