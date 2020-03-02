import argparse

import configparser
import os
import socket

from api_client.c3tt_rpc_client import C3TTClient

class C3TT_Admin:
    def __init__(self):
        if not os.path.exists('client.conf'):
            raise IOError("Error: config file not found")

        self.config = configparser.ConfigParser()
        self.config.read('client.conf')

        if self.config['C3Tracker']['host'] == "None":
            self.host = socket.getfqdn()
        else:
            self.host = self.config['C3Tracker']['host']

        print('creating C3TTClient')
        try:
            self.c3tt = C3TTClient(self.config['C3Tracker']['url'],
                                   self.config['C3Tracker']['group'],
                                   self.host,
                                   self.config['C3Tracker']['secret'])
        except Exception as e_:
            raise Exception('Config parameter missing or empty, please check config') from e_

    def add_encoding_profile(self, ticket, profile, properties=[]):
        print("adding profile " + str(profile) + " to ticket " + str(ticket))
        ret = self.c3tt.create_encoding_ticket(ticket, profile)
        print(ret)


parser = argparse.ArgumentParser(description="Modify tickets in the ticket tracker")

parser.add_argument("task", help="task to perform: add-profile, tbd")
parser.add_argument("--ticket", type=int)
parser.add_argument("--profile", type=int)
args = parser.parse_args()

admin = C3TT_Admin()

print("Selected task: " + args.task)
if args.task == "task=add-profile":
    admin.add_encoding_profile(args.ticket, args.profile)


