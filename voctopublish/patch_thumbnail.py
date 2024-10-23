#!/usr/bin/env python3

import logging
import os
import re
from sys import argv

try:
    # python 3.11
    from tomllib import loads as toml_load
except ImportError:
    from rtoml import load as toml_load

from c3tt_rpc_client import C3TTClient
from c3tt_rpc_client.exceptions import C3TTException

from api_client.voctoweb_client import VoctowebClient
from api_client.youtube_client import YoutubeAPI
from model.ticket_module import PublishingTicket
from tools.thumbnails import ThumbnailGenerator

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

LOG = logging.getLogger("ThumbnailPatcher")

try:
    TRACKER_ID = argv[1]
except IndexError:
    print(
        f"""Usage: {argv[0]} <tracker id>

    Please make sure you use the tracker id (in the url), not the
    fahrplan id.

    This script will upload the pre-existing thumbnails for the named
    ticket to voctoweb and/or youtube, whichever is enabled via tracker
    properties. You will have to make sure the thumbnail is placed
    correctly in the file system."""
    )
    exit(1)

try:
    MY_PATH = os.path.abspath(os.path.dirname(__file__))
    POSSIBLE_CONFIG_PATHS = [
        os.getenv("VOCTOPUBLISH_CONFIG", ""),
        os.path.expanduser("~/voctopublish.conf"),
        os.path.join(MY_PATH, "voctopublish.conf"),
        os.path.join(MY_PATH, "client.conf"),
    ]

    for path in POSSIBLE_CONFIG_PATHS:
        if path:
            if os.path.isfile(path):
                my_config_path = path
                break
    else:
        raise FileNotFoundError(
            f'Could not find a valid config in any of these paths: {" ".join(POSSIBLE_CONFIG_PATHS)}'
        )

    with open(my_config_path) as f:
        config = toml_load(f.read())
except Exception:
    LOG.exception("Could not load config")
    exit(1)

try:
    HOST = config["C3Tracker"].get("host", "").strip()
    if not HOST:
        HOST = socket.getfqdn()

    c3tt = C3TTClient(
        config["C3Tracker"]["url"],
        config["C3Tracker"]["group"],
        HOST,
        config["C3Tracker"]["secret"],
    )

    properties = c3tt.get_ticket_properties(TRACKER_ID)
    ticket = PublishingTicket(properties, TRACKER_ID, config)
except Exception:
    LOG.exception("could not get ticket from tracker")
    exit(1)

if not ticket.master:
    LOG.error("this ticket is not a master ticket, aborting!")
    exit(1)

thumbs = ThumbnailGenerator(ticket, config)
if not thumbs.exists:
    LOG.error(
        f"thumbnail file {thumbs.path} does not exist, please ensure file is located correctly"
    )
    exit(1)

had_error = False
if ticket.voctoweb_enable:
    try:
        LOG.info("updating thumbnail on voctoweb")
        vw = VoctowebClient(
            ticket,
            thumbs,
            config["voctoweb"]["api_key"],
            config["voctoweb"]["api_url"],
            config["voctoweb"]["ssh_host"],
            config["voctoweb"]["ssh_port"],
            config["voctoweb"]["ssh_user"],
        )
        LOG.info("generating voctoweb compatible thumbnails")
        vw.generate_thumbs()
        LOG.info("uploading thumbnails to voctoweb")
        vw.upload_thumbs()
        LOG.info("replaced thumbnails on voctoweb")
    except Exception:
        LOG.exception("could not replace thumbnail on voctoweb")
        had_error = True

if ticket.youtube_enable:
    try:
        LOG.info("updating thumbnail on youtube")
        yt = YoutubeAPI(
            ticket,
            thumbs,
            config,
            config["youtube"]["client_id"],
            config["youtube"]["secret"],
        )
        yt.setup(ticket.youtube_token)

        for url in ticket.youtube_urls.values():
            try:
                LOG.info(f"replacing thumbnail for youtube url {url}")
                m = re.search(r"watch\?v=(.+)$", url)
                if not m:
                    LOG.error(f"{url} is not a youtube url")
                    continue
                yt.generate_and_upload_thumbnail(m.groups()[0])
                LOG.info(f"replaced thumbnail for youtube url {url}")
            except Exception:
                LOG.exception(f"could not replace thumbnail on youtube for {url}")
                had_error = True
    except Exception:
        LOG.exception(f"could not replace thumbnail on youtube")
        had_error = True

if had_error:
    LOG.error("had errors, check above")
    exit(1)
