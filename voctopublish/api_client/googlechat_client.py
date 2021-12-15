#!/bin/python3
#    Copyright (C) 2021 kunsi
#    voc@kunsmann.eu
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

from requests import post


def send_chat_message(ticket, config):
    logging.info("posting message to google chat")

    buttons = []
    if ticket.voctoweb_enable and ticket.profile_voctoweb_enable:
        buttons.append(
            {
                "textButton": {
                    "text": config["voctoweb"]["instance_name"],
                    "onClick": {
                        "openLink": {
                            "url": config["voctoweb"]["frontend_url"]
                            + "/v/"
                            + ticket.slug
                        },
                    },
                }
            }
        )

    if ticket.youtube_enable and ticket.profile_youtube_enable:
        if len(ticket.youtube_urls) == 1:
            buttons.append(
                {
                    "textButton": {
                        "text": "YouTube",
                        "onClick": {
                            "openLink": {
                                "url": ticket.youtube_urls["YouTube.Url0"],
                            },
                        },
                    }
                }
            )
        else:
            for count, url in enumerate(sorted(ticket.youtube_urls.values()), start=1):
                buttons.append(
                    {
                        "textButton": {
                            "text": "YouTube " + str(count),
                            "onClick": {
                                "openLink": {
                                    "url": url,
                                },
                            },
                        }
                    }
                )

    if not buttons:
        logging.warning("GoogleChat: No buttons for videos :(")
        return

    if ticket.url:
        buttons.append(
            {
                "textButton": {
                    "text": "Talk URL",
                    "onClick": {
                        "openLink": {
                            "url": ticket.url,
                        },
                    },
                }
            }
        )

    key_value = [
        {
            "keyValue": {
                "topLabel": "Room",
                "content": ticket.room,
            },
        }
    ]

    if ticket.people:
        key_value.append(
            {
                "keyValue": {
                    "topLabel": "Speakers",
                    "content": ", ".join(ticket.people),
                },
            }
        )

    if ticket.track:
        key_value.append(
            {
                "keyValue": {
                    "topLabel": "Track",
                    "content": ticket.track,
                },
            }
        )

    try:
        r = post(
            ticket.googlechat_webhook_url,
            json={
                "cards": [
                    {
                        "header": {
                            "title": ticket.title,
                            "subtitle": ticket.acronym,
                        },
                        "sections": [
                            {
                                "widgets": [
                                    {
                                        "textParagraph": {
                                            "text": ticket.abstract,
                                        },
                                    },
                                ],
                            },
                            {
                                "widgets": key_value,
                            },
                            {
                                "widgets": [
                                    {
                                        "buttons": buttons,
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
        )
        r.raise_for_status()
        logging.debug("Google said: " + repr(r.json()))
    except Exception as e_:
        logging.error("GoogleChat failed: " + repr(e_))
