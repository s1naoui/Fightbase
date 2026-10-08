import unittest
from unittest.mock import patch
import boxing_feed as feed

class FreeFeedMappingTests(unittest.TestCase):
    def test_only_boxing_events_are_accepted(self):
        self.assertTrue(feed._is_boxing({'strSport':'Fighting','strLeague':'World Boxing Championship'}))
        self.assertFalse(feed._is_boxing({'strSport':'Fighting','strLeague':'UFC MMA'}))
        self.assertFalse(feed._is_boxing({'strSport':'Soccer','strLeague':'Boxing League'}))

    def test_fighter_names(self):
        a,b=feed._split_match({'strEvent':'Tyson Fury vs Oleksandr Usyk'})
        self.assertEqual((a,b),('Tyson Fury','Oleksandr Usyk'))

    def test_no_paid_api_calls(self):
        with self.assertRaises(ValueError):
            feed.get('/v2/fighters/',{})
        self.assertEqual(feed.rankings(1),[])

    def test_free_api_public_key(self):
        self.assertTrue(feed.API.endswith('/123'))
        self.assertEqual(feed.status()['configured'],True)

if __name__ == '__main__':
    unittest.main()
