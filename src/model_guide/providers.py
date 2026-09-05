from dataclasses import dataclass
import json
import re
import urllib.error
import urllib.request


_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")


class ProviderError(RuntimeError):
    """Safe provider failure plus any trustworthy billing metadata."""

    def __init__(
        self,
        message,
        *,
        returned_model=None,
        input_tokens=None,
        output_tokens=None,
    ):
        super().__init__(message)
        self.returned_model = returned_model
        self.model = returned_model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class StdlibTransport:
    """Fixed-endpoint JSON transport. Redirects are refused before credentials leak."""

    def post(self, url, headers, body, timeout):
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            with opener.open(request, timeout=timeout) as response:
                return response.status, dict(response.headers), json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, {}, {}
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            raise ProviderError("provider transport failed") from exc


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class ProviderResult:
    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None


def _token_count(value):
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError("invalid token count")
    return value


def _metadata(data):
    if not isinstance(data, dict):
        raise ValueError("response body must be an object")
    model = data.get("model")
    if not isinstance(model, str) or not _MODEL_ID.fullmatch(model):
        raise ValueError("invalid returned model")
    usage = data.get("usage")
    if usage is None:
        return model, None, None
    if not isinstance(usage, dict):
        raise ValueError("invalid usage")
    return (
        model,
        _token_count(usage.get("input_tokens")),
        _token_count(usage.get("output_tokens")),
    )


def _state_error(message, model, input_tokens, output_tokens):
    return ProviderError(
        message,
        returned_model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _result(response, parser):
    if not isinstance(response, (tuple, list)) or len(response) != 3:
        raise ProviderError("invalid provider response")
    status, headers, body = response
    if type(status) is not int or not isinstance(headers, dict):
        raise ProviderError("invalid provider response")
    if 300 <= status < 400:
        raise ProviderError("redirect refused")
    if status < 200 or status >= 300:
        raise ProviderError(f"provider HTTP error {status}")
    try:
        return parser(body)
    except ProviderError:
        raise
    except (AttributeError, KeyError, StopIteration, TypeError, ValueError) as exc:
        raise ProviderError("invalid provider response") from exc


class OpenAIProvider:
    def __init__(self, key, transport):
        if not key:
            raise ProviderError("OPENAI_API_KEY is required")
        self.key = key
        self.transport = transport

    def evaluate(self, candidate, prompt, task):
        body = {
            "model": candidate["model"],
            "input": prompt,
            "max_output_tokens": candidate.get("max_output_tokens", 1024),
            "store": False,
        }
        if candidate.get("effort"):
            body["reasoning"] = {"effort": candidate["effort"]}

        def parse(data):
            model, input_tokens, output_tokens = _metadata(data)
            status = data.get("status")
            if status in ("incomplete", "failed", "cancelled", "in_progress", "queued"):
                raise _state_error(
                    "provider response incomplete", model, input_tokens, output_tokens
                )
            if status != "completed":
                raise ValueError("invalid response status")
            output = data.get("output")
            if not isinstance(output, list) or not output:
                raise ValueError("invalid output")

            text_parts = []
            saw_message = False
            refused = False
            for item in output:
                if not isinstance(item, dict):
                    raise ValueError("invalid output item")
                if item.get("type") != "message":
                    continue
                saw_message = True
                message_status = item.get("status")
                if message_status is not None and message_status != "completed":
                    raise _state_error(
                        "provider response incomplete",
                        model,
                        input_tokens,
                        output_tokens,
                    )
                content = item.get("content")
                if not isinstance(content, list):
                    raise ValueError("invalid message content")
                for block in content:
                    if not isinstance(block, dict):
                        raise ValueError("invalid content block")
                    block_type = block.get("type")
                    if block_type == "refusal":
                        refused = True
                    elif block_type == "output_text":
                        text = block.get("text")
                        if not isinstance(text, str):
                            raise ValueError("invalid output text")
                        text_parts.append(text)
                    else:
                        raise ValueError("invalid content block type")
            if refused:
                raise _state_error(
                    "provider response refused", model, input_tokens, output_tokens
                )
            text = "".join(text_parts)
            if not saw_message or not text.strip():
                raise ValueError("empty output")
            return ProviderResult(text, model, input_tokens, output_tokens)

        response = self.transport.post(
            "https://api.openai.com/v1/responses",
            {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
            body,
            30,
        )
        return _result(response, parse)


class AnthropicProvider:
    def __init__(self, key, transport):
        if not key:
            raise ProviderError("ANTHROPIC_API_KEY is required")
        self.key = key
        self.transport = transport

    def evaluate(self, candidate, prompt, task):
        body = {
            "model": candidate["model"],
            "max_tokens": candidate.get("max_output_tokens", 1024),
            "messages": [{"role": "user", "content": prompt}],
        }
        if candidate.get("effort"):
            body["output_config"] = {"effort": candidate["effort"]}

        def parse(data):
            model, input_tokens, output_tokens = _metadata(data)
            stop_reason = data.get("stop_reason")
            if stop_reason == "refusal":
                raise _state_error(
                    "provider response refused", model, input_tokens, output_tokens
                )
            if stop_reason in (
                "max_tokens",
                "model_context_window_exceeded",
                "tool_use",
                "pause_turn",
            ):
                raise _state_error(
                    "provider response incomplete", model, input_tokens, output_tokens
                )
            if stop_reason not in ("end_turn", "stop_sequence"):
                raise ValueError("invalid stop reason")
            content = data.get("content")
            if not isinstance(content, list) or not content:
                raise ValueError("invalid content")

            text_parts = []
            refused = False
            for block in content:
                if not isinstance(block, dict) or not isinstance(block.get("type"), str):
                    raise ValueError("invalid content block")
                if block["type"] == "refusal":
                    refused = True
                elif block["type"] == "text":
                    text = block.get("text")
                    if not isinstance(text, str):
                        raise ValueError("invalid text block")
                    text_parts.append(text)
            if refused:
                raise _state_error(
                    "provider response refused", model, input_tokens, output_tokens
                )
            text = "".join(text_parts)
            if not text.strip():
                raise ValueError("empty output")
            return ProviderResult(text, model, input_tokens, output_tokens)

        headers = {
            "x-api-key": self.key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        response = self.transport.post(
            "https://api.anthropic.com/v1/messages", headers, body, 30
        )
        return _result(response, parse)
