'''
Created on Dec 15, 2016

@author: n-te
'''
import unittest

from voctopublish.api_client.c3tt_rpc_client import C3TTClient


class TestC3TTClient(unittest.TestCase):
    def setUp(self):
        self._client = C3TTClient("<server>", "group", "host", "secret")

    def test_init(self):
        assert self._client.url == "<server>rpc"  # todo shouldn't this be an _url join?
        assert self._client.ticket_id is None

    def test_gen_signature_args_empty(self):
        hash_ = self._client._gen_signature("test", [])
        assert hash_ == "35cea736060974b7e67f95d7c07a2cecdc8fff882632cb73121a3b3a77a2625a"


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
