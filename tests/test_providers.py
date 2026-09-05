import unittest

from model_guide.providers import AnthropicProvider, OpenAIProvider, ProviderError


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.request = None

    def post(self, url, headers, body, timeout):
        self.request = (url, headers, body, timeout)
        return self.response


def openai_response(**overrides):
    value = {
        "id": "resp_123",
        "object": "response",
        "status": "completed",
        "model": "gpt-x-2026-01-01",
        "output": [
            {
                "id": "msg_123",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": '{"answer":true}',
                        "annotations": [],
                        "logprobs": [],
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 3,
            "input_tokens_details": {"cached_tokens": 1},
            "output_tokens": 5,
            "output_tokens_details": {"reasoning_tokens": 4},
            "total_tokens": 8,
        },
    }
    value.update(overrides)
    return value


def anthropic_response(**overrides):
    value = {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "model": "claude-x-20260101",
        "content": [{"type": "text", "text": '{"answer":true}'}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 2,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 4,
        },
    }
    value.update(overrides)
    return value


class ProviderTest(unittest.TestCase):
    def test_openai_contract_omits_reference_answer_and_does_not_double_count_reasoning(self):
        transport = FakeTransport((200, {}, openai_response()))
        result = OpenAIProvider("key", transport).evaluate(
            {
                "model": "gpt-x-2026-01-01",
                "max_output_tokens": 8,
                "effort": "high",
            },
            "prompt",
            {"expected": "secret"},
        )
        self.assertEqual(result.text, '{"answer":true}')
        self.assertEqual(result.input_tokens, 3)
        self.assertEqual(result.output_tokens, 5)
        self.assertEqual(result.model, "gpt-x-2026-01-01")
        url, headers, body, timeout = transport.request
        self.assertEqual(url, "https://api.openai.com/v1/responses")
        self.assertEqual(timeout, 30)
        self.assertTrue(headers["Authorization"].startswith("Bearer "))
        self.assertEqual(body["reasoning"], {"effort": "high"})
        self.assertNotIn("secret", str(body))

    def test_anthropic_contract_uses_native_effort_and_provider_usage(self):
        transport = FakeTransport((200, {}, anthropic_response()))
        result = AnthropicProvider("key", transport).evaluate(
            {
                "model": "claude-x-20260101",
                "max_output_tokens": 8,
                "effort": "high",
            },
            "prompt",
            {},
        )
        self.assertEqual(result.text, '{"answer":true}')
        self.assertEqual(result.input_tokens, 2)
        self.assertEqual(result.output_tokens, 4)
        self.assertEqual(transport.request[0], "https://api.anthropic.com/v1/messages")
        self.assertEqual(transport.request[2]["output_config"], {"effort": "high"})

    def test_completed_responses_allow_unknown_usage_without_crashing(self):
        openai = OpenAIProvider(
            "key", FakeTransport((200, {}, openai_response(usage=None)))
        ).evaluate({"model": "gpt-x-2026-01-01"}, "prompt", {})
        anthropic = AnthropicProvider(
            "key", FakeTransport((200, {}, anthropic_response(usage=None)))
        ).evaluate({"model": "claude-x-20260101"}, "prompt", {})
        self.assertIsNone(openai.input_tokens)
        self.assertIsNone(openai.output_tokens)
        self.assertIsNone(anthropic.input_tokens)
        self.assertIsNone(anthropic.output_tokens)

    def test_openai_refusal_and_truncation_fail_and_preserve_safe_metadata(self):
        refusal = openai_response(
            output=[
                {
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": '{"answer":true}'},
                        {"type": "refusal", "refusal": "private refusal detail"},
                    ],
                }
            ]
        )
        incomplete = openai_response(status="incomplete", output=[])
        for body, message in (
            (refusal, "provider response refused"),
            (incomplete, "provider response incomplete"),
        ):
            with self.subTest(message=message):
                provider = OpenAIProvider("sk-DO-NOT-LEAK", FakeTransport((200, {}, body)))
                with self.assertRaisesRegex(ProviderError, f"^{message}$") as raised:
                    provider.evaluate({"model": "gpt-x-2026-01-01"}, "prompt", {})
                error = raised.exception
                self.assertEqual(error.returned_model, "gpt-x-2026-01-01")
                self.assertEqual(error.model, "gpt-x-2026-01-01")
                self.assertEqual(error.input_tokens, 3)
                self.assertEqual(error.output_tokens, 5)
                self.assertNotIn("private refusal detail", str(error))
                self.assertNotIn("sk-DO-NOT-LEAK", str(error))

    def test_anthropic_refusal_and_token_limit_fail_and_preserve_safe_metadata(self):
        for stop_reason, message in (
            ("refusal", "provider response refused"),
            ("max_tokens", "provider response incomplete"),
        ):
            with self.subTest(stop_reason=stop_reason):
                body = anthropic_response(
                    stop_reason=stop_reason,
                    content=[{"type": "text", "text": '{"answer":true}'}],
                )
                provider = AnthropicProvider(
                    "anthropic-secret", FakeTransport((200, {}, body))
                )
                with self.assertRaisesRegex(ProviderError, f"^{message}$") as raised:
                    provider.evaluate({"model": "claude-x-20260101"}, "prompt", {})
                error = raised.exception
                self.assertEqual(error.returned_model, "claude-x-20260101")
                self.assertEqual(error.input_tokens, 2)
                self.assertEqual(error.output_tokens, 4)
                self.assertNotIn("anthropic-secret", str(error))

    def test_malformed_shapes_and_invalid_usage_become_sanitized_provider_errors(self):
        cases = [
            (OpenAIProvider, [], "gpt-x-2026-01-01"),
            (OpenAIProvider, openai_response(output=[]), "gpt-x-2026-01-01"),
            (OpenAIProvider, openai_response(model="unsafe\nmodel"), "gpt-x-2026-01-01"),
            (OpenAIProvider, openai_response(output=[{"type": "message", "content": None}]), "gpt-x-2026-01-01"),
            (OpenAIProvider, openai_response(usage={"input_tokens": True, "output_tokens": 5}), "gpt-x-2026-01-01"),
            (OpenAIProvider, openai_response(usage={"input_tokens": 3, "output_tokens": -1}), "gpt-x-2026-01-01"),
            (AnthropicProvider, [], "claude-x-20260101"),
            (AnthropicProvider, anthropic_response(content=None), "claude-x-20260101"),
            (AnthropicProvider, anthropic_response(content=[{"type": "text"}]), "claude-x-20260101"),
            (AnthropicProvider, anthropic_response(usage={"input_tokens": 2.5, "output_tokens": 4}), "claude-x-20260101"),
        ]
        for provider_type, body, model in cases:
            with self.subTest(provider=provider_type.__name__, body=body):
                provider = provider_type("credential-value", FakeTransport((200, {}, body)))
                with self.assertRaisesRegex(ProviderError, "^invalid provider response$") as raised:
                    provider.evaluate({"model": model}, "prompt", {})
                self.assertNotIn("credential-value", str(raised.exception))
                self.assertNotIn(str(body), str(raised.exception))

    def test_redirect_http_and_malformed_transport_responses_are_sanitized(self):
        cases = [
            ((302, {"location": "https://evil.example"}, {"secret": "body"}), "redirect refused"),
            ((429, {}, {"error": {"message": "account secret"}}), "provider HTTP error 429"),
            ((200,), "invalid provider response"),
            (("200", {}, {}), "invalid provider response"),
        ]
        for response, message in cases:
            with self.subTest(response=response):
                provider = OpenAIProvider("credential-value", FakeTransport(response))
                with self.assertRaisesRegex(ProviderError, f"^{message}$") as raised:
                    provider.evaluate({"model": "gpt-x-2026-01-01"}, "prompt", {})
                self.assertNotIn("account secret", str(raised.exception))
                self.assertNotIn("credential-value", str(raised.exception))

    def test_unsafe_returned_model_is_not_preserved(self):
        body = openai_response(model="unsafe\nmodel")
        provider = OpenAIProvider("key", FakeTransport((200, {}, body)))
        with self.assertRaisesRegex(ProviderError, "^invalid provider response$") as raised:
            provider.evaluate({"model": "gpt-x-2026-01-01"}, "prompt", {})
        self.assertIsNone(raised.exception.model)
        self.assertIsNone(raised.exception.input_tokens)
        self.assertIsNone(raised.exception.output_tokens)

    def test_missing_credentials_raise_safe_errors(self):
        transport = FakeTransport((200, {}, openai_response()))
        with self.assertRaisesRegex(ProviderError, "^OPENAI_API_KEY is required$"):
            OpenAIProvider("", transport)
        with self.assertRaisesRegex(ProviderError, "^ANTHROPIC_API_KEY is required$"):
            AnthropicProvider("", transport)


if __name__ == "__main__":
    unittest.main()
