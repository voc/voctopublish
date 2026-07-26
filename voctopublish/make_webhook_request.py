#!/usr/bin/env python3

import logging
import os
import socket
from sys import argv

try:
    # python 3.11
    from tomllib import loads as toml_load
except ImportError:
    from rtoml import load as toml_load

from c3tt_rpc_client import C3TTClient
from model.ticket_module import PublishingTicket
import api_client.webhook_client as webhook

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

LOG = logging.getLogger("WebhookRequestor")

try:
    TRACKER_ID = argv[1]
except IndexError:
    print(
        f"""Usage: {argv[0]} <tracker id>

    Please make sure you use the tracker id (in the url), not the
    fahrplan id.

    This script will re-trigger the webhook (if set in ticket) for
    the specified ticket."""
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
            f"Could not find a valid config in any of these paths: {' '.join(POSSIBLE_CONFIG_PATHS)}"
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
    LOG.exception(
        "could not get ticket from tracker, are you sure you're using the *tracker id* of the encoding?"
    )
    exit(1)

if not ticket.webhook_url:
    LOG.error("ticket does not have webhook enabled")
    exit(1)

if ticket.master or not ticket.webhook_only_master:
    voctoweb_filename = None
    voctoweb_language = ticket.language
    if ticket.voctoweb_enable:
        if ticket.language_index is not None:
            voctoweb_filename = (
                ticket.language_template % ticket.languages[ticket.language_index]
                + "_"
                + ticket.profile_slug
                + "."
                + ticket.profile_extension
            )
            voctoweb_language = ticket.languages[ticket.language_index]
        else:
            voctoweb_filename = ticket.filename

    if ticket.rclone_enable:
        LOG.error("cannot re-process webhook if rclone is enabled")
        exit(1)

    result = webhook.send(
        ticket,
        config,
        voctoweb_filename,
        voctoweb_language,
        None,
    )
    if (not isinstance(result, int) or result >= 300) and ticket.webhook_fail_on_error:
        raise Exception(
            f"POSTing webhook to {ticket.webhook_url} failed with http status code {result}"
        )
    elif isinstance(result, int):
        c3tt.set_ticket_properties(
            TRACKER_ID,
            {
                "Webhook.StatusCode": result,
            },
        )
        LOG.info("success")
else:
    LOG.error(f"webhook not triggered for this ticket {TRACKER_ID}")
