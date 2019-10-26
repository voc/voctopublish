'''
Created on Dec 11, 2016

@author: n-te
'''

import unittest

from model.ticket_module import Ticket, TicketException


class TestTicket(unittest.TestCase):

    def setUp(self):
        self.ticket_json = {
            'EncodingProfile.IsMaster': 'yes',
            'EncodingProfile.Basename': 'rel-test-2342-deu-eng-spa-gsw-testi_mc_testface_hd',
            'EncodingProfile.Extension': 'mp4',
            'Encoding.LanguageIndex': '1',
            'Encoding.Basename': 'rel-test-2342-deu-eng-spa-gsw-testi_mc_testface',
            'Encoding.LanguageTemplate': 'rel-test-2342-%s-testi_mc_testface',
            'EncodingProfile.MirrorFolder': 'h264-hd',
            'EncodingProfile.Slug': 'hd',

            'Fahrplan.Abstract': 'lorem und so weiter',
            'Fahrplan.Date': '23-42-12',
            'Fahrplan.GUID': '123456',
            'Fahrplan.Room': 'HS1',
            'Fahrplan.ID': 2342,
            'Fahrplan.Slug': 'supercon2023',
            'Fahrplan.Subtitle': 'subitdidup',
            'Fahrplan.Title': 'testi mc testface',

            'Meta.Album': 'Album',
            'Meta.License': '(C) All rights reserved.',
            'Meta.Year': '2020',

            'Processing.Path.Output': '/video/encoded/rel-test/',
            'Processing.Video.AspectRatio': '16:9',
            'Processing.Auphonic.Enable': 'no',
            'Processing.Path.Tmp': '/video/tmp/rel-test/',

            'Publishing.Media.Host': '192.168.23.42',
            'Publishing.Media.EnableProfile': 'yes',
            'Publishing.Path': '/video/4release/rel-test/',
            'Publishing.YouTube.Privacy': 'private FIXME',
            'Publishing.Media.User': 'ubuntu',
            'Publishing.YouTube.Tags': 'test,script,python',
            'Publishing.Media.Thumbpath': '/tmp/',
            'Publishing.Media.Url': 'https://media.ccc.de/v/fasel',
            'Publishing.Media.Slug': 'supercon2023',
            'Publishing.YouTube.Category': '27',
            'Publishing.Media.Path': '/tmp/',
            'Publishing.YouTube.Enable': 'no',
            'Publishing.YouTube.EnableProfile': 'yes',
            'Publishing.YouTube.Token': 'FIXME',
            'Publishing.Media.Enable': 'yes',
            'Publishing.Media.MimeType': 'video/mp4',

            'Project.Slug': 'rel-test',

            'Record.Container': 'TS',
            'Record.Language': 'deu-eng-spa-gsw',
            'Record.Language.0': 'deu',
            'Record.Language.1': 'eng',
            'Record.Language.2': 'spa',
            'Record.Language.3': 'gsw',
            }

        self.update_ticket_json = self.ticket_json
        self.update_ticket_json.update(
            {'Voctoweb.EventId': 7359,
             'Voctoweb.RecordingId.Master': 37162,
             'Voctoweb.RecordingId.deu': 37161,
             'Voctoweb.RecordingId.eng': 33242,
             'Voctoweb.RecordingId.spa': 34234,
             'Voctoweb.RecordingId.gsw': 43543,
             'YouTube.Url0': 'https://www.youtube.com/watch?v=JKxxGausFXo',
             'YouTube.Url1': 'https://www.youtube.com/watch?v=JKxxGausFXo',
             'YouTube.Url2': 'https://www.youtube.com/watch?v=JKxxGausFXo',
             'YouTube.Url3': 'https://www.youtube.com/watch?v=JKxxGausFXo'
             })

    def test_init_success(self):
        t = Ticket(self.ticket_json, 1)
        self.assertIsNotNone(t, "Ticket not successfully created")

    def test_init_ticket_empty(self):
        with self.assertRaises(TicketException):
            Ticket("", 1)

    def test_init_ticket_none(self):
        with self.assertRaises(TicketException):
            Ticket(None, 1)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
