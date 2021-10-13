import unittest
import json

from model.ticket_module import Ticket
from api_client.youtube_client import YoutubeAPI
from unittest import mock


class TestYouTubeClient(unittest.TestCase):

    def setUp(self):
        self.ticket_data = {'Project.Slug': 'yt-test', 'EncodingProfile.IsMaster': 'yes', 'EncodingProfile.Extension': 'mp4', 'EncodingProfile.Slug': 'hd', 'EncodingProfile.Basename': 'yt-test-42-eng-test_hd', 'EncodingProfile.MirrorFolder': 'h264-hd', 'Fahrplan.Slug': 'yt-test', 'Fahrplan.GUID': '84b77855-e324-4a8b-88a8-6076f5203293', 'Fahrplan.ID': 42, 'Fahrplan.Title': 'Test Event', 'Fahrplan.DateTime': '2023-01-01T23:42:42+0100', 'Fahrplan.Room': 'Room 0', 'Record.Language': 'eng', 'Encoding.LanguageTemplate': 'yt-test-42-%s-test_hd', 'Publishing.Path': '/video/4release/yt-test/', 'Publishing.YouTube.EnableProfile': 'yes', 'Publishing.YouTube.Enable': 'yes', 'Publishing.YouTube.Token': 'TheToken', 'Publishing.Voctoweb.EnableProfile': 'no', 'Publishing.Voctoweb.Enable': 'no', 'Publishing.Twitter.Enable': 'no', 'Publishing.Mastodon.Enable': 'no', 'Encoding.Language': 'eng'}

    def test_init(self):
        client = YoutubeAPI(None, 'my-client', 'my-secret')

        self.assertEqual(client.client_id, 'my-client')
        self.assertEqual(client.secret, 'my-secret')

    def test_select_tags(self):
        client = self.build_client()

        tags = client._select_tags()
        self.assertEqual(tags, ['Room 0', '2023', 'yt-test ov', 'yt-test eng', 'yt-test'])

        tags = client._select_tags('rus')
        self.assertEqual(tags, ['Room 0', '2023', 'Russian (Russian (русский) translation)', 'yt-test rus', 'yt-test'])

        tags = client._select_tags('eng')
        self.assertEqual(tags, ['Room 0', '2023', 'yt-test English', 'yt-test ov', 'yt-test'])

        client = self.build_client({'Fahrplan.Day': '1'})
        tags = client._select_tags()
        self.assertEqual(tags, ['Day 1', 'Room 0', '2023', 'yt-test ov', 'yt-test eng', 'yt-test'])

    def mocked_requests_post(*args, **kwargs):
        class MockResponse:
            def __init__(self, status_code):
                self.status_code = status_code
                self.headers = {'location': 'https://www.googleapis.com/upload/youtube/v3/videos/42'}

        if args[0] == 'https://www.googleapis.com/upload/youtube/v3/videos':
            return MockResponse(200)

        return MockResponse(None, 404)

    def mocked_requests_put(*args, **kwargs):
        class MockResponse:
            def __init__(self, status_code, json_data):
                self.status_code = status_code
                self.json_data = json_data

            def json(self):
                return self.json_data

        if args[0] == 'https://www.googleapis.com/upload/youtube/v3/videos/42':
            return MockResponse(200, {'id': 'my-video-id'})

        return MockResponse(404, None)

    @mock.patch('requests.post', side_effect=mocked_requests_post)
    @mock.patch('requests.put', side_effect=mocked_requests_put)
    def test_upload(self, mock_put, mock_post):
        client = self.build_client()

        client.upload('testdata/video.mp4', None)
        post_data = json.loads(mock_post.call_args[1]['data'])
        snippet = post_data['snippet']
        self.assertEqual(snippet['defaultLanguage'], 'en')
        self.assertEqual(snippet['defaultAudioLanguage'], 'en')

        client.upload('testdata/video.mp4', 'rus')
        post_data = json.loads(mock_post.call_args[1]['data'])
        snippet = post_data['snippet']
        self.assertEqual(snippet['defaultLanguage'], 'en')
        self.assertEqual(snippet['defaultAudioLanguage'], 'ru')

        client.upload('testdata/video.mp4', 'ind')
        post_data = json.loads(mock_post.call_args[1]['data'])
        snippet = post_data['snippet']
        self.assertEqual(snippet['defaultLanguage'], 'en')
        self.assertEqual(snippet['defaultAudioLanguage'], 'id')

    def build_client(self, additional_ticket_data = {}):
        ticket_data = self.ticket_data.copy()
        ticket_data.update(additional_ticket_data)
        client = YoutubeAPI(Ticket(ticket_data, 1), 'my-client', 'my-secret')
        client.accessToken = 'my-access-token'

        return client

if __name__ == "__main__":
    unittest.main()
