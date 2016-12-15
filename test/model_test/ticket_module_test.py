'''
Created on Dec 11, 2016

@author: n-te
'''

import unittest

from model.ticket_module import Ticket, TicketException


class TestTicket(unittest.TestCase):


    def test_init_empty(self):
        with self.assertRaises(TicketException):
            t = Ticket("", 1)
        
        
if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()