from unittest.mock import MagicMock, patch
import unittest
from model_guide.providers import StdlibTransport, ProviderError


class TransportTests(unittest.TestCase):
    def test_invalid_utf8_is_safe_provider_error(self):
        response = MagicMock()
        response.status = 200
        response.headers = {}
        response.read.return_value = b'\xff'
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch("model_guide.providers.urllib.request.build_opener", return_value=opener):
            with self.assertRaisesRegex(ProviderError, "provider transport failed"):
                StdlibTransport().post("https://api.openai.com/v1/responses", {}, {}, 30)
