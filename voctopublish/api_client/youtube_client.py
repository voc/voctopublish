#!/usr/bin/python3
#    Copyright (C) 2017  andi, derpeter
#    andi@muc.ccc.de
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

import json
import logging
import mimetypes
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import langcodes
import requests
from model.ticket_module import Ticket
from tools.thumbnails import ThumbnailGenerator

logging = logging.getLogger()


class YoutubeAPI:
    """
    This class implements the YouTube API v3
    https://developers.google.com/youtube/v3/docs
    """

    def __init__(
        self, t: Ticket, thumb: ThumbnailGenerator, config, client_id: str, secret: str
    ):
        self.t = t
        self.thumbnail = thumb
        self.client_id = client_id
        self.secret = secret
        self.config = config

        self.lang_map = {
            "deu": "German",
            "eng": "English",
            "spa": "Spanish",
            "gsw": "Schweizerdeutsch",
            "fra": "French",
            "rus": "Russian",
            "fas": "Farsi",
            "chi": "Chinese",
            "ara": "Arabic",
            "hrv": "Croatian",
            "pol": "Polish",
            "por": "Portuguese",
            "ind": "Bahasa Indonesia",
            "ben": "Bengali",
            "ita": "Italian",
            "swe": "Swedish",
        }

        self.translation_strings = {
            "deu": "deutsche Übersetzung",
            "eng": "english translation",
            "spa": "La traducción española",
            "gsw": "Schwizerdüütschi Übersetzig",
            "fra": "traduction française",
            "rus": "Russian (русский) translation",
            "chi": "中文翻译",
            "ara": "الترجمة العربية",
            "hrv": "Hrvatski prijevod",
            "pol": "Prijevod s poljskog",
            "por": "Tradução portuguesa",
            "ind": "Terjemahan bahasa Indonesia",
            "ben": "Bengali translation",
            "ita": "Traduzione italiana",
            "swe": "Svensk översättning",
        }

        self.youtube_urls = []
        self.channelId = None
        self.accessToken = None

    def setup(self, token):
        """
        fetch access token and channel if form youtube
        :param token: youtube token to be used
        """
        self.accessToken = self.get_fresh_token(token, self.client_id, self.secret)
        self.channelId = self.get_channel_id(self.accessToken)

    def publish(self):
        """
        publish a file on youtube
        :return: returns a list containing a youtube url for each released file
        """
        logging.info(
            "publishing Ticket %s (%s) to youtube" % (self.t.fahrplan_id, self.t.title)
        )

        # handle multi language events
        if len(self.t.languages) > 1:
            logging.debug("Languages: " + str(self.t.languages))

            i = 0
            for lang in self.t.languages:
                video_url = self.t.get_raw_property("YouTube.Url{}".format(i))
                if video_url and self.t.youtube_update != "force":
                    logging.info(
                        "Video track {} is already on youtube, returning previous URL {}".format(
                            i, video_url
                        )
                    )
                else:
                    out_filename = (
                        self.t.fahrplan_id
                        + "-"
                        + self.t.profile_slug
                        + "-audio"
                        + str(lang)
                        + "."
                        + self.t.profile_extension
                    )
                    out_path = os.path.join(self.t.publishing_path, out_filename)

                    logging.info(
                        "remuxing " + self.t.local_filename + " to " + out_path
                    )

                    try:
                        subprocess.check_output(
                            "ffmpeg -y -v warning -nostdin -i "
                            + os.path.join(
                                self.t.publishing_path, self.t.local_filename
                            )
                            + " -map 0:0 -map 0:a:"
                            + str(lang)
                            + " -c copy "
                            + out_path,
                            shell=True,
                        )
                    except Exception as e_:
                        raise YouTubeException(
                            "error remuxing "
                            + self.t.local_filename
                            + " to "
                            + out_path
                        ) from e_

                    if int(lang) == 0:
                        lang = None
                    else:
                        lang = self.t.languages[lang]

                    video_id = self.upload(out_path, lang)
                    video_url = "https://www.youtube.com/watch?v=" + video_id
                    logging.info("published %s video track to %s" % (lang, video_url))

                self.youtube_urls.append(video_url)
                i += 1
        else:
            video_id = self.upload(
                os.path.join(self.t.publishing_path, self.t.local_filename), None
            )

            video_url = "https://www.youtube.com/watch?v=" + video_id
            logging.info("published Ticket to %s" % video_url)
            self.youtube_urls.append(video_url)

        return self.youtube_urls

    def upload(self, file, lang):
        """
        Call the youtube API and push the file to youtube
        :param file: file to upload
        :param lang: language of the file
        :return:
        """
        # todo split up event creation and upload
        # todo change function name
        # todo add the license properly

        title = self._build_title(lang)
        if self.t.subtitle:
            subtitle = self.t.subtitle
        else:
            subtitle = ""
        if self.t.abstract:
            abstract = self.strip_tags(self.t.abstract)
        else:
            abstract = ""

        if self.t.description:
            description = self.strip_tags(self.t.description)
        else:
            description = ""

        if self.t.url:
            if self.t.url.startswith("//"):
                url = "https:" + self.t.url
            else:
                url = self.t.url
        else:
            url = ""

        topline = [
            "#" + re.sub("[^A-Za-z0-9]+", "", x)
            for x in [self.t.acronym, self.t.track]
            if x
        ]
        if self.t.acronym and lang and lang != self.t.languages[0]:
            topline.append(topline[0] + "_" + lang)

        description = "\n\n".join(
            [
                subtitle,
                abstract,
                description,
                " ".join(self.t.people),
                url,
                " ".join(topline),
            ]
        )
        description = self.strip_tags(description)

        if self.t.voctoweb_enable:
            description = (
                self.config["voctoweb"]["frontend_url"]
                + "/v/"
                + self.t.slug
                + "\n\n"
                + description
            )

        license = self.t.get_raw_property("Meta.License")
        if license and "https://creativecommons.org/licenses/by" in license:
            license = "creativeCommon"
        else:
            license = "youtube"

        metadata = {
            "snippet": {
                "title": title,
                # YouTube does not allow <> in description -> escape them
                "description": description.replace("<", "&lt").replace(">", "&gt"),
                "channelId": self.channelId,
                "tags": self._select_tags(lang),
                "defaultLanguage": langcodes.get(self.t.languages[0]).language,
                "defaultAudioLanguage": langcodes.get(
                    lang or self.t.languages[0]
                ).language,
            },
            "status": {
                "privacyStatus": self.t.youtube_privacy,
                "embeddable": True,
                "publicStatsViewable": True,
                "license": license,
            },
            "recordingDetails": {
                "recordingDate": self.t.date,
            },
        }

        if self.t.youtube_publish_at:
            metadata["status"]["publishAt"] = self.t.youtube_publish_at.isoformat(timespec="seconds")

        # limit title length to 100 (YouTube api conformity)
        metadata["snippet"]["title"] = metadata["snippet"]["title"][:100]
        # limit Description length to 5000 (YouTube api conformity)
        metadata["snippet"]["description"] = metadata["snippet"]["description"][:5000]

        if self.t.youtube_category:
            metadata["snippet"]["categoryId"] = int(self.t.youtube_category)

        (mimetype, encoding) = mimetypes.guess_type(file)
        size = os.stat(file).st_size

        logging.debug(
            "guessed mime type for file %s as %s and its size as %u bytes"
            % (file, mimetype, size)
        )

        # https://developers.google.com/youtube/v3/docs/videos#resource
        r = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos",
            params={
                "uploadType": "resumable",
                "part": "snippet,status,recordingDetails",
            },
            headers={
                "Authorization": "Bearer " + self.accessToken,
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": mimetype,
                "X-Upload-Content-Length": str(size),
            },
            data=json.dumps(metadata),
        )
        logging.info(json.dumps(metadata, indent=2))

        if 200 != r.status_code:
            if 400 == r.status_code:
                raise YouTubeException(
                    r.json()["error"]["message"]
                    + "\n"
                    + r.text
                    + "\n\n"
                    + json.dumps(metadata, indent=2)
                )
            else:
                raise YouTubeException(
                    "Video creation failed with error-code %u: %s"
                    % (r.status_code, r.text)
                )

        if "location" not in r.headers:
            raise YouTubeException(
                "Video creation did not return a location-header to upload to: %s"
                % (r.headers,)
            )

        logging.info(
            "successfully created video and received upload-url from %s"
            % (r.headers["server"] if "server" in r.headers else "-")
        )
        logging.debug("uploading video-data to %s" % r.headers["location"])

        with open(file, "rb") as fp:
            upload = requests.put(
                r.headers["location"],
                headers={
                    "Authorization": "Bearer " + self.accessToken,
                    "Content-Type": mimetype,
                },
                data=fp,
            )

            if 200 != upload.status_code and 201 != upload.status_code:
                raise YouTubeException(
                    "uploading video failed with error-code %u: %s"
                    % (r.status_code, r.text)
                )

        video = upload.json()

        outjpg = os.path.join(
            self.t.publishing_path, self.t.fahrplan_id + "_youtube.jpg"
        )

        try:
            r = subprocess.check_output(
                "ffmpeg -loglevel error -i "
                + self.thumbnail.path
                + " -f image2 -vcodec mjpeg -pix_fmt yuv420p -q:v 0 -y "
                + outjpg,
                shell=True,
            )
            logging.info("thumbnails reformatted for youtube")
        except Exception as e_:
            raise YouTubeException(
                "Could not scale thumbnail: " + r.decode("utf-8")
            ) from e_

        YoutubeAPI.update_thumbnail(self.accessToken, video["id"], outjpg)

        youtube_url = "https://www.youtube.com/watch?v=" + video["id"]
        logging.info("successfully uploaded video as %s", youtube_url)

        return video["id"]

    def _build_title(self, lang=None):
        """
        Build the title
        :param lang: if present the language will be added to the title
        :return: Returns the title string
        """
        title = self.t.title
        language = lang if lang else self.t.languages[0]

        title_prefix = (
            self.t.youtube_translation_title_prefix
            if lang and self.t.youtube_translation_title_prefix
            else self.t.youtube_title_prefix
        )
        # if localized title exits, overwrite original title
        if lang and self.t.has_property(f"Fahrplan.Title.{lang}"):
            title = self.t.get_raw_property(f"Fahrplan.Title.{lang}")

        if title_prefix:
            title_prefix = self._replace_language_placeholders(title_prefix, language)
            title = title_prefix + " " + title
            logging.debug("adding " + str(title_prefix) + " as title prefix")

        # when self.t.youtube_title_prefix_speakers is set, prepend up to x people to title,
        # where x is defined by the integer in self.t.youtube_title_prefix_speakers
        if self.t.youtube_title_prefix_speakers and len(self.t.people) <= int(
            self.t.youtube_title_prefix_speakers
        ):
            title = (", ".join(self.t.people)) + ": " + title
            logging.debug("adding speaker names as title prefix: " + title)
        elif self.t.youtube_title_append_speakers and len(self.t.people) <= int(
            self.t.youtube_title_append_speakers
        ):
            title += " (" + (", ".join(self.t.people)) + ")"
            logging.debug("appending speaker names to title: " + title)

        title_suffix = (
            self.t.youtube_translation_title_suffix
            if lang and self.t.youtube_translation_title_suffix
            else self.t.youtube_title_suffix
        )
        if title_suffix:
            title_suffix = self._replace_language_placeholders(title_suffix, language)
            title = title + " " + title_suffix
            logging.debug(f"adding '{title_suffix}' as title suffix, new title: {title}")

        if (
            lang
            and not self.t.youtube_translation_title_prefix
            and not self.t.youtube_translation_title_suffix
        ):
            title += self._replace_language_placeholders(" - ${translation}", lang)

        # YouTube does not allow <> in titles – even not as &gt;&lt;
        title = title.replace("<", "(").replace(">", ")")
        logging.debug(f"final title: {title}")
        return title

    def _replace_language_placeholders(self, string, lang):
        """
        Replace language related placeholders in a string
        :param string: string where the placeholders should be replaced
        :param lang: the language
        :return: Returns the string with applied replacements
        """
        translation = ""
        language_name = ""
        if lang:
            if lang in self.translation_strings.keys() and lang in self.lang_map:
                translation = self.translation_strings[lang]
                language_name = self.lang_map[lang]
            else:
                raise YouTubeException("language not defined in translation strings")

        return (
            string.replace("${translation}", translation)
            .replace("${language_code}", lang)
            .replace("${language_name}", language_name)
        )

    def _select_tags(self, lang=None):
        """
        Build the tag list
        :param lang: if present the language will be added to the tags
        :return: Returns an array of tag strings
        """
        tags = []

        # if tags are set - copy them into the metadata dict
        if self.t.youtube_tags:
            tags.extend(self.t.youtube_tags)

        if lang:
            if lang in self.lang_map.keys():
                if self.t.languages[0] == lang:
                    tags.append(self.t.acronym + " " + self.lang_map[lang])
                    tags.append(self.t.acronym + " ov")
                else:
                    tags.append(
                        self.lang_map[lang]
                        + " ("
                        + self.translation_strings[lang]
                        + ")"
                    )
                    tags.append(self.t.acronym + " " + lang)
            else:
                raise YouTubeException("language not in lang map")
        else:
            tags.append(self.t.acronym + " ov")
            tags.append(self.t.acronym + " " + self.t.languages[0])

        tags.extend(self.t.people)

        logging.debug("YouTube Tags: " + str(tags))

        return tags

    def depublish(self):
        """
        depublish videos on youtube
        :return:
        """
        logging.info(
            "depublishing Ticket %s (%s) to youtube"
            % (self.t.fahrplan_id, self.t.title)
        )

        # second YoutubeAPI instance for playlist management at youtube.com, if the playlist is on a different channel that the video
        # if 'playlist_token' in self.config['youtube'] and self.ticket.youtube_token != self.config['youtube']['playlist_token']:
        #    yt = YoutubeAPI(self.ticket, self.config['youtube']['client_id'], self.config['youtube']['secret'])
        #    yt.setup(self.config['youtube']['playlist_token'])
        # else:
        #    logging.debug('using same token for publishing and playlist management')
        yt = self

        i = 0
        depublished_urls = []
        props = {}
        for lang in self.t.languages:
            video_url = self.t.get_raw_property(f"YouTube.Url{i}")
            if video_url:
                try:
                    video_id = video_url.split("=", 2)[1]
                    self.update_metadata(
                        video_id,
                        {"id": video_id, "status": {"privacyStatus": "private"}},
                    )
                    logging.info(
                        "depublished %s video track from %s" % (lang, video_url)
                    )
                    depublished_urls.append(video_url)
                    props[f"YouTube.Url{i}"] = ""

                    if self.t.youtube_playlists:
                        yt.remove_from_playlists(video_id, self.t.youtube_playlists)
                except Exception as e:
                    logging.error(f"debublishing of {video_url} failed with {e}")

                i += 1
            return depublished_urls, props

    def update_metadata(self, video_id, metadata):
        # https://developers.google.com/youtube/v3/docs/videos#resource
        r = requests.put(
            "https://youtube.googleapis.com/youtube/v3/videos",
            params={
                "part": "status"  # TODO extract keys from ','.join(metadata.keys())
            },
            headers={
                "Authorization": "Bearer " + self.accessToken,
                "Content-Type": "application/json; charset=UTF-8",
            },
            data=json.dumps(metadata),
        )

        if 200 != r.status_code:
            logging.debug(metadata)
            if 400 == r.status_code:
                raise YouTubeException(
                    r.json()["error"]["message"]
                    + "\n"
                    + r.text
                    + "\n\n"
                    + json.dumps(metadata, indent=2)
                )
            else:
                raise YouTubeException(
                    "Video update failed with error-code %u: %s"
                    % (r.status_code, r.text)
                )
        return r

    def add_to_playlists(self, video_id: str, playlist_ids):
        for p in playlist_ids:
            YoutubeAPI.add_to_playlist(self, video_id, p)

    def add_to_playlist(self, video_id: str, playlist_id: str):
        """
        documentation: https://developers.google.com/youtube/v3/docs/playlistItems/insert
        :param access_token:
        :param video_id:
        :param playlist_id:
        """
        r = requests.post(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "snippet"},
            headers={
                "Authorization": "Bearer " + self.accessToken,
                "Content-Type": "application/json; charset=UTF-8",
            },
            data=json.dumps(
                {
                    "snippet": {
                        "playlistId": playlist_id,  # required
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },  # required
                    },
                }
            ),
        )

        if 200 != r.status_code:
            raise YouTubeException(
                "Adding video to playlist failed with error-code %u: %s"
                % (r.status_code, r.text)
            )

        logging.info("video added to playlist: " + playlist_id)

    def remove_from_playlists(self, video_id: str, ids):
        """
        documentation: https://developers.google.com/youtube/v3/docs/playlistItems/list
        :param video_id:
        :param ids: list or string of playlist ids
        """
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={
                "part": "id",
                "id": ",".join(ids),
                "videoId": video_id,
            },
            headers={
                "Authorization": "Bearer " + self.accessToken,
                "Content-Type": "application/json; charset=UTF-8",
            },
        )

        if 200 != r.status_code:
            raise YouTubeException(
                "Could not lookup playlist item ids, failed with error-code %u: %s"
                % (r.status_code, r.text)
            )

        for item in r.json()["items"]:
            remove_playlist_item(item["id"])

    def remove_playlist_item(self, item_id: str):
        """
        documentation: https://developers.google.com/youtube/v3/docs/playlistItems/delete
        :param item_id:
        """
        r = requests.delete(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "id"},
            headers={
                "Authorization": "Bearer " + self.accessToken,
                "Content-Type": "application/json; charset=UTF-8",
            },
            data=json.dumps(
                {
                    "id": item_id,
                }
            ),
        )

        if 204 != r.status_code:
            raise YouTubeException(
                "Removing video from playlist failed with error-code %u: %s"
                % (r.status_code, r.text)
            )

        logging.info("video removed from playlist ")

    @staticmethod
    def update_thumbnail(access_token: str, video_id: str, thumbnail: str):
        """
        https://developers.google.com/youtube/v3/docs/thumbnails/set
        :param access_token:
        :param video_id:
        :param thumbnail:
        """
        fp = open(thumbnail, "rb")

        r = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
            params={"videoId": video_id},
            headers={
                "Authorization": "Bearer " + access_token,
                "Content-Type": "image/png",
            },
            data=fp.read(),
        )

        if 200 != r.status_code:
            raise YouTubeException(
                "Video update failed with error-code %u: %s" % (r.status_code, r.text)
            )

        logging.info(f"Thumbnails for {video_id} updated")

    @staticmethod
    def get_playlist(access_token: str, playlist_id: str):
        """
        currently a method to help with debugging --Andi, August 2016
        :param access_token:
        :param playlist_id:
        :return:
        """
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "snippet", "playlistId": playlist_id},
            headers={
                "Authorization": "Bearer " + access_token,
                "Content-Type": "application/json; charset=UTF-8",
            },
        )

        if 200 != r.status_code:
            raise YouTubeException(
                "Video add to playlist failed with error-code %u: %s"
                % (r.status_code, r.text)
            )

        logging.debug(json.dumps(r.json(), indent=4))

    @staticmethod
    def get_fresh_token(refresh_token: str, client_id: str, client_secret: str):
        """
        request a 'fresh' youtube token
        :param refresh_token:
        :param client_id:
        :param client_secret:
        :return: YouTube access token
        """
        logging.debug(
            "fetching fresh Access-Token on behalf of the refreshToken %s"
            % refresh_token
        )
        r = requests.post(
            "https://accounts.google.com/o/oauth2/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )

        if 200 != r.status_code:
            raise YouTubeException(
                "fetching a fresh authToken failed with error-code %u: %s"
                % (r.status_code, r.text)
            )

        data = r.json()
        if "access_token" not in data:
            raise YouTubeException(
                "fetching a fresh authToken did not return a access_token: %s" % r.text
            )

        logging.info("successfully fetched Access-Token %s" % data["access_token"])
        return data["access_token"]

    @staticmethod
    def get_channel_id(access_token: str):
        """
        request the channel id associated with the access token
        :param access_token: Youtube access token
        :return: YouTube channel id
        """
        logging.debug(
            "fetching Channel-Info on behalf of the accessToken %s" % access_token
        )
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            headers={
                "Authorization": "Bearer " + access_token,
            },
            params={
                "part": "id,brandingSettings",
                "mine": "true",
            },
        )

        if 200 != r.status_code:
            raise YouTubeException(
                "fetching channelID failed with error-code %u: %s"
                % (r.status_code, r.text)
            )

        data = r.json()
        channel = data["items"][0]

        logging.info("successfully fetched Channel-ID %s " % (channel["id"]))
        return channel["id"]

    @staticmethod
    def strip_tags(html):
        """
        wrapper around MLStripper to clean html input
        :return: stripped input
        """
        s = MLStripper()
        s.feed(html)
        return s.get_data()


class MLStripper(HTMLParser):
    """ """

    def error(self, message):
        pass

    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return "".join(self.fed)


class YouTubeException(Exception):
    pass
