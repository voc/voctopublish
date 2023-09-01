import logging

LOG = logging.getLogger("announcements")


class EmptyAnnouncementMessage(Exception):
    # raised if there is nothing to announce
    pass


def make_message(ticket, max_length=200, override_url_length=None):
    LOG.info(f"generating announcement message with max length of {max_length} chars")

    targets = []
    urls = []
    if ticket.voctoweb_enable and ticket.profile_voctoweb_enable:
        targets.append(config["voctoweb"]["instance_name"])
        urls.append(config["voctoweb"]["frontend_url"] + "/v/" + ticket.slug)
        LOG.debug("voctoweb is enabled")

    if (
        ticket.youtube_enable
        and ticket.profile_youtube_enable
        and ticket.youtube_privacy == "public"
    ):
        targets.append("YouTube")
        urls.append(ticket.youtube_urls["YouTube.Url0"])
        LOG.debug(f"youtube is enabled")

    if not targets:
        raise EmptyAnnouncementMessage()

    msg = " has been released on {}".format(" and ".join(targets))

    length_for_title = max_length - len(msg)

    title = ticket.title
    if len(title) >= length_for_title:
        title = title[0:length_for_title]

    message = title + msg

    for url in urls:
        if override_url_length:
            url_len = override_url_length
        else:
            url_len = len(url)

        if url_len <= (max_length - len(message)):
            message = message + " " + url

    LOG.info(f"{len(message)} chars: {message}")
