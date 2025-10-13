import logging
from re import sub

LOG = logging.getLogger("announcements")


class EmptyAnnouncementMessage(Exception):
    # raised if there is nothing to announce
    pass


def _replace_special_chars(maybe_string):
    string = str(maybe_string)
    for search, replace in {
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
        "ß": "ss",
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ẞ": "Ss",
    }.items():
        string = string.replace(search, replace)
    string = unicodedata.normalize("NFD", string).encode("ascii", "ignore").decode("utf-8")
    return sub(r"[^A-Za-z0-9]+", "", string)


def make_message(ticket, config, max_length=None):
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

    if ticket.url:
        urls.append(ticket.url)

    msg = " has been released on {}".format(" and ".join(targets))

    length_for_title = max_length - len(msg)

    title = ticket.title
    if len(title) >= length_for_title:
        title = title[0 : length_for_title - 3] + "..."

    message = title + msg

    for tag in ticket.publishing_tags:
        if tag is None:
            continue
        tag = _replace_special_chars(tag)
        if tag.isdigit():
            continue
        if len(message) < (max_length - 2 - len(tag)):
            message += " #" + tag

    for url in urls:
        if len(url) <= (max_length - len(message)):
            message = message + " " + url

    LOG.info(f"{len(message)} chars: {message}")
    return message
