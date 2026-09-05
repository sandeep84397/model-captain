import unittest
from model_guide.providers import AnthropicProvider, OpenAIProvider, ProviderError


class FakeTransport:
    def __init__(self, response): self.response = response; self.request = None
    def post(self, url, headers, body, timeout): self.request = (url, headers, body, timeout); return self.response


class ProviderTest(unittest.TestCase):
    def test_openai_contract_and_no_reference_answer(self):
        transport = FakeTransport((200, {}, {"status":"completed", "model":"gpt-x", "output":[{"type":"message", "content":[{"type":"output_text", "text":"answer"}]}], "usage":{"input_tokens":3,"output_tokens":5}}))
        result = OpenAIProvider("key", transport).evaluate({"model":"gpt-x","max_output_tokens":8,"effort":"high"}, "prompt", {"expected":"secret"})
        self.assertEqual(result.text, "answer")
        url, headers, body, _ = transport.request
        self.assertEqual(url, "https://api.openai.com/v1/responses")
        self.assertTrue(headers["Authorization"].startswith("Bearer "))
        self.assertEqual(body["reasoning"], {"effort":"high"})
        self.assertNotIn("secret", str(body))

    def test_anthropic_contract_and_refusal(self):
        transport = FakeTransport((200, {}, {"stop_reason":"end_turn", "model":"claude-x", "content":[{"type":"text", "text":"ok"}], "usage":{"input_tokens":2,"output_tokens":4}}))
        result = AnthropicProvider("key", transport).evaluate({"model":"claude-x","max_output_tokens":8,"effort":"high"}, "prompt", {})
        self.assertEqual(result.output_tokens, 4)
        self.assertEqual(transport.request[0], "https://api.anthropic.com/v1/messages")
        self.assertEqual(transport.request[2]["output_config"], {"effort":"high"})
        with self.assertRaises(ProviderError):
            OpenAIProvider("", transport)
