from dataclasses import dataclass
import json
import urllib.error
import urllib.request

class ProviderError(RuntimeError): pass

class StdlibTransport:
    """Fixed-endpoint JSON transport. Redirects are refused before credentials leak."""
    def post(self, url, headers, body, timeout):
        request=urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
        opener=urllib.request.build_opener(_NoRedirect())
        try:
            with opener.open(request, timeout=timeout) as response:
                return response.status, dict(response.headers), json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, {}, {}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderError("provider transport failed") from exc

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

@dataclass
class ProviderResult:
    text: str; model: str; input_tokens: int|None; output_tokens: int|None

def _result(response, parser):
    status, headers, body = response
    if 300 <= status < 400: raise ProviderError("redirect refused")
    if status < 200 or status >= 300: raise ProviderError(f"provider HTTP error {status}")
    try: return parser(body)
    except (KeyError, TypeError, ValueError) as exc: raise ProviderError("invalid provider response") from exc

class OpenAIProvider:
    def __init__(self, key, transport):
        if not key: raise ProviderError("OPENAI_API_KEY is required")
        self.key,self.transport=key,transport
    def evaluate(self, candidate, prompt, task):
        body={"model":candidate["model"],"input":prompt,"max_output_tokens":candidate.get("max_output_tokens",1024),"store":False}
        if candidate.get("effort"): body["reasoning"]={"effort":candidate["effort"]}
        def parse(data):
            if data.get("status") != "completed": raise ValueError("incomplete")
            content=next(x["content"] for x in data["output"] if x.get("type")=="message")
            text="".join(x["text"] for x in content if x.get("type")=="output_text")
            if not text: raise ValueError("empty")
            u=data.get("usage",{}); return ProviderResult(text,data["model"],u.get("input_tokens"),u.get("output_tokens"))
        return _result(self.transport.post("https://api.openai.com/v1/responses", {"Authorization":"Bearer "+self.key,"Content-Type":"application/json"}, body, 30),parse)

class AnthropicProvider:
    def __init__(self, key, transport):
        if not key: raise ProviderError("ANTHROPIC_API_KEY is required")
        self.key,self.transport=key,transport
    def evaluate(self, candidate, prompt, task):
        body={"model":candidate["model"],"max_tokens":candidate.get("max_output_tokens",1024),"messages":[{"role":"user","content":prompt}]}
        if candidate.get("effort"): body["output_config"]={"effort":candidate["effort"]}
        def parse(data):
            if data.get("stop_reason") not in ("end_turn","stop_sequence"): raise ValueError("incomplete")
            text="".join(x["text"] for x in data["content"] if x.get("type")=="text")
            if not text: raise ValueError("empty")
            u=data.get("usage",{}); return ProviderResult(text,data["model"],u.get("input_tokens"),u.get("output_tokens"))
        headers={"x-api-key":self.key,"anthropic-version":"2023-06-01","Content-Type":"application/json"}
        return _result(self.transport.post("https://api.anthropic.com/v1/messages",headers,body,30),parse)
