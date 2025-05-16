import argparse
import configparser
import os
import socket

from api_client.c3tt_rpc_client import C3TTClient


class C3TTAdmin:
    """
    cli helper to talk to the c3tt. Api definition can be found here
    https://github.com/crs-tools/tracker/blob/master/src/Application/Controller/XMLRPC/Handler.php
    """

    def __init__(self):
        if not os.path.exists("../client.conf"):
            raise IOError("Error: config file not found")

        self.config = configparser.ConfigParser()
        self.config.read("../client.conf")

        if self.config["C3Tracker"]["host"] == "None":
            self.host = socket.getfqdn()
        else:
            self.host = self.config["C3Tracker"]["host"]

        print("creating C3TTClient")
        try:
            self.c3tt = C3TTClient(
                self.config["C3Tracker"]["url"],
                self.config["C3Tracker"]["group"],
                self.host,
                self.config["C3Tracker"]["secret"],
            )
        except Exception as e_:
            raise Exception(
                "Config parameter missing or empty, please check config"
            ) from e_

    def add_encoding_profile(self, ticket, profile, properties=None):
        print("adding profile " + str(profile) + " to ticket " + str(ticket))
        ret = self.c3tt.create_encoding_ticket(ticket, profile)
        print(ret)

    def get_version(self):
        ret = self.c3tt.get_version()
        print(ret)

    def set_ticket_properties(self, ticket, properties):
        print(properties)
        ret = self.c3tt.set_ticket_properties(ticket, properties)
        print(ret)

    def get_ticket_properties(self, ticket):
        ret = self.c3tt.get_ticket_properties(ticket)
        print(ret)

    def set_ticket_done(self, ticket):
        ret = self.c3tt.set_ticket_done(ticket)
        print(ret)

    def add_meta_ticket(self, project, title, fahrplan_id, properties=None):
        ret = self.c3tt.create_meta_ticket(project, title, fahrplan_id, properties)
        print(ret)


parser = argparse.ArgumentParser(description="Modify tickets in the ticket tracker")

parser.add_argument(
    "task", help="task to perform: add-profile, get-properties, set-done"
)
parser.add_argument("--ticket", type=int)
parser.add_argument("--profile", type=int)
parser.add_argument("--title", type=str)
parser.add_argument("--fahrplan_id", type=int)
parser.add_argument("--project", type=int)
# from https://gist.github.com/vadimkantorov/37518ff88808af840884355c845049ea
parser.add_argument(
    "--prop",
    help="each property needs to be added as an tuple like: --prop foo=bar",
    action=type(
        "",
        (argparse.Action,),
        dict(
            __call__=lambda a, p, n, v, o: getattr(n, a.dest).update(
                dict([v.split("=")])
            )
        ),
    ),
    default={},
)  # anonymously subclassing argparse.Action
args = parser.parse_args()

admin = C3TTAdmin()

print("Selected task: " + args.task)
if args.task == "task=add-profile":
    admin.add_encoding_profile(args.ticket, args.profile)
elif args.task == "task=get-properties":
    admin.get_ticket_properties(args.ticket)
elif args.task == "task=set-properties":
    admin.set_ticket_properties(args.ticket, args.prop)
elif args.task == "task=set-done":
    admin.set_ticket_done(args.ticket)
elif args.task == "task=add-ticket":
    if args.prop:
        admin.add_meta_ticket(args.project, args.title, args.fahrplan_id, args.prop)
    else:
        admin.add_meta_ticket(args.project, args.title, args.fahrplan_id)
