import argparse
import requests
import sys
import json
from os import getenv, path


sys.path.append(path.dirname(path.dirname(__file__)))
sys.path.append(path.dirname(__file__) + '/../voctopublish')

from voctopublish.api_client.youtube_client import YoutubeAPI
from voctopublish.voctopublish import Worker as TrackerClient
import voctopublish.api_client.webhook_client as webhook

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


tracker = TrackerClient()

def sync_tracker_with_hub(project, args):

    tickets = requests.get(f'https://tracker.c3voc.de/api/v1/{project}/tickets/released.json').json()
    hd_masters = [t for t in tickets if t.get('encoding_profile_name') == 'TS| HD-Master MP4']

    for row in hd_masters:
        if int(row['webhook_result']) != 201:
            print('---')
            print()

            print(row)

            forced_properties = {
                "Publishing.Voctoweb.Enable": True,
            }

            ticket = tracker.get_ticket(row['ticket_id'], 'publishing', forced_properties)


            voctoweb_url = 'https://media.ccc.de/v/' + row['fahrplan_guid']
            print(voctoweb_url)
            ticket_url = f'https://tracker.c3voc.de/{project}/ticket/{row["ticket_id"]}'
            print(ticket_url)

            print()

            #print(ticket)
            changed_properties = {}

            if ticket.master or not ticket.webhook_only_master:
                
                for key, url in ticket.youtube_urls.items():

                    youtube_metadata = YoutubeAPI.get_oembed_json(url)

                    # when privacy is private and we got a 200 status, change to public in ticket model so webhook can update hub
                    if ticket.youtube_privacy == 'private' and key == 'YouTube.Url0' and youtube_metadata['status'] == 200:
                        ticket.youtube_privacy = 'public'

                    if ticket[key + '.status'] != youtube_metadata['status']:
                        changed_properties[f'{key}.status'] = youtube_metadata['status']
                    
                    #if 'title' in youtube_metadata and ticket[key + '.Title'] != youtube_metadata['title']:
                    #    changed_properties[f'{key}.Title'] = youtube_metadata['title']

                print(changed_properties)

                if args.debug:
                    # preview webhook payload
                    print(json.dumps(webhook._get_json(ticket), indent=2))

                if not args.dry_run:
                    result = webhook.send(ticket)
                    if (
                        not isinstance(result, int) or result >= 300
                    ):
                        logger.error(
                            f"POSTing webhook to {ticket.webhook_url} failed with http status code {result}"
                        )
                    elif isinstance(result, int):
                        changed_properties['Webhook.StatusCode'] = result

                    if changed_properties.__len__() > 0:
                        tracker.c3tt.set_ticket_properties(ticket.id, changed_properties)
                        pass



            print()
            print(ticket['Fahrplan.URL'])



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('project', action="store", help="Tracker project slug, e.g. `39C3`")
    #parser.add_argument('year', action="store", help="Year, e.g. `2025`")
    parser.add_argument('--debug', action="store_true", default=False)
    parser.add_argument('--dry-run', action="store_true", default=False)
    args = parser.parse_args()

    sync_tracker_with_hub(args.project, args)