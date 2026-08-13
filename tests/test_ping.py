from tests.base import BaseTestCase

class TestPingRoute(BaseTestCase):
    def test_ping_returns_ok_unauthenticated(self):
        # Even without logging in, /ping should return OK
        response = self.client.get('/ping')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode('utf-8'), 'OK')

    def test_ping_returns_ok_authenticated(self):
        # With logging in, /ping should still return OK
        self.login("UserTim", "password123")
        response = self.client.get('/ping')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode('utf-8'), 'OK')
