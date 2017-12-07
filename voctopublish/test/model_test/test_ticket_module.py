'''
Created on Dec 11, 2016

@author: n-te
'''

import unittest

from model.ticket_module import Ticket, TicketException


class TestTicket(unittest.TestCase):

    def setUp(self):
        self.ticket_json = {'Fahrplan.Room': 'HS1', 'Publishing.Media.Host': '192.168.23.42', 'Publishing.Media.EnableProfile': 'yes', 'Publishing.Path': '/video/4release/rel-test/', 'Publishing.YouTube.Privacy': 'private FIXME', 'Record.Container': 'TS', 'EncodingProfile.IsMaster': 'yes', 'Record.Language.3': 'gsw', 'Meta.Album': 'Album', 'Fahrplan.ID': 2342, 'Fahrplan.Slug': 'supercon2023', 'Project.Slug': 'rel-test', 'EncodingProfile.Basename': 'rel-test-2342-deu-eng-spa-gsw-testi_mc_testface_hd', 'Publishing.Media.User': 'ubuntu', 'Processing.Path.Output': '/video/encoded/rel-test/', 'Processing.Video.AspectRatio': '16:9', 'Record.Language': 'deu-eng-spa-gsw', 'EncodingProfile.Extension': 'mp4', 'Encoding.LanguageIndex': '1', 'Encoding.Basename': 'rel-test-2342-deu-eng-spa-gsw-testi_mc_testface', 'Processing.Auphonic.Enable': 'no', 'Publishing.YouTube.Tags': 'test,script,python', 'Record.Language.1': 'eng', 'Publishing.Media.Thumbpath': '/tmp/', 'Publishing.Media.Url': 'https://media.ccc.de/v/fasel', 'Fahrplan.Subtitle': 'subitdidup', 'Publishing.Media.Slug': 'supercon2023', 'EncodingProfile.MirrorFolder': 'h264-hd', 'Publishing.YouTube.Category': '27', 'Publishing.Media.Path': '/tmp/', 'Publishing.YouTube.Enable': 'no', 'Encoding.LanguageTemplate': 'rel-test-2342-%s-testi_mc_testface', 'Meta.License': '(C) All rights reserved.', 'Publishing.Media.MimeType': 'video/mp4', 'Record.Language.2': 'spa', 'Meta.Year': '2016', 'Processing.Path.Tmp': '/video/tmp/rel-test/', 'Publishing.YouTube.EnableProfile': 'yes', 'Fahrplan.Abstract': 'lorem und so weiter', 'EncodingProfile.Slug': 'hd', 'Fahrplan.Title': 'testi mc testface', 'Publishing.YouTube.Token': 'FIXME', 'Record.Language.0': 'deu', 'Publishing.Media.Enable': 'yes', 'Fahrplan.GUID': '123456', 'Fahrplan.Date': '23-42-12'}

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
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()