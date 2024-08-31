import logging
from re import sub

LOG = logging.getLogger("announcements")


class EmptyAnnouncementMessage(Exception):
    # raised if there is nothing to announce
    pass


def make_message(ticket, config, max_length=None, override_url_length=None):
    if max_length is None:
        # if max_length is not set, set it to something very big here.
        # saves us a bunch of isinstance() calls below
        max_length = 1_000_000

    LOG.info(f"generating announcement message with max length of {max_length} chars")

    targets = []
    urls = []
    if ticket.voctoweb_enable:
        targets.append(config["voctoweb"]["instance_name"])
        urls.append(config["voctoweb"]["frontend_url"] + "/v/" + ticket.slug)
        LOG.debug("voctoweb is enabled")

    if ticket.youtube_enable and ticket.youtube_privacy == "public":
        targets.append("YouTube")
        urls.append(ticket.youtube_urls["YouTube.Url0"])
        LOG.debug(f"youtube is enabled")

    if not targets:
        raise EmptyAnnouncementMessage()

    msg = " has been released on {}".format(" and ".join(targets))

    length_for_title = max_length - len(msg)

    title = ticket.title
    if len(title) >= length_for_title:
        title = title[0 : length_for_title - 3] + "..."

    message = title + msg

    for tag in ticket.publishing_tags:
        tag = sub(r"[^A-Za-z0-9]+", "", tag)
        if tag.isdigit():
            continue
        if len(message) < (max_length - 2 - len(tag)):
            message += " #" + tag

    for url in urls:
        if override_url_length:
            url_len = override_url_length
        else:
            url_len = len(url)

        if url_len <= (max_length - len(message)):
            message = message + " " + url

    LOG.info(f"{len(message)} chars: {message}")
    return message
