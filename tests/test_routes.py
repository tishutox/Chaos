import unittest

from main import app


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_home_links_to_settings(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/settings"', response.data)

    def test_settings_page_and_script_are_available(self):
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        for field in (
            b'backendUrl',
            b'apiKey',
            b'imageResolution',
            b'autoBackground',
            b'basePrompt',
            b'negativePrompt',
            b'polycount',
            b'textureResolution',
            b'pbrMaps',
            b'exportFormat',
        ):
            self.assertIn(field, response.data)
        script = self.client.get("/static/settings.js")
        self.assertEqual(script.status_code, 200)
        script.close()


if __name__ == "__main__":
    unittest.main()
