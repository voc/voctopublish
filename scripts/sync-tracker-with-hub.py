import requests
import sys
import json
from os import getenv, path


sys.path.append(path.dirname(path.dirname(__file__)))
sys.path.append(path.dirname(__file__) + '/../voctopublish')

from voctopublish.voctopublish import Worker as TrackerClient
import voctopublish.api_client.webhook_client as webhook

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


tracker = TrackerClient()
project = '39c3'

def sync_tracker_with_hub():

    tickets = requests.get(f'https://tracker.c3voc.de/api/v1/{project}/tickets/released.json').json()
    hd_masters = [t for t in tickets if t.get('encoding_profile_name') == 'TS| HD-Master MP4']

    for row in hd_masters:
        if row['webhook_result'] != 201:
            print(row)

            forced_properties = {
                "Publishing.Voctoweb.Enable": True,
            }

            ticket = tracker.get_ticket(row['ticket_id'], 'publishing', forced_properties)


            voctoweb_url = 'https://media.ccc.de/v/' + row['fahrplan_guid']
            print(voctoweb_url)
            ticket_url = f'https://tracker.c3voc.de/{project}/ticket/{row["ticket_id"]}'
            print(ticket_url)
            #hub_api_url = f'https://api.events.ccc.de/congress/2025/event/{row["fahrplan_guid"]}/schedule'
            #hub_event = requests.get(hub_api_url).json()
            #print(hub_event['url'])
            print()

            #print(ticket)


            # preview webhook payload
            print(json.dumps(webhook._get_json(ticket), indent=2))


            exit()


            if ticket.master or not ticket.webhook_only_master:
                result = webhook.send(ticket)
                if (
                    not isinstance(result, int) or result >= 300
                ) and ticket.webhook_fail_on_error:
                    raise Exception(
                        f"POSTing webhook to {ticket.webhook_url} failed with http status code {result}"
                    )
                elif isinstance(result, int):
                    tracker.c3tt.set_ticket_properties(
                        ticket.ticket_id,
                        {
                            "Webhook.StatusCode": result,
                        },
                    )


if __name__ == "__main__":
    sync_tracker_with_hub()