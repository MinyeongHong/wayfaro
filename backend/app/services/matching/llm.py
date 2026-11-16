"""Gemini generateContent REST adapter; never expose keys or document text."""
import copy
import json
import re

import httpx
from pydantic import ValidationError

from app.config import settings
from app.services.ingestion.greenhouse import _retry_after


def _gemini_schema(schema):
    """Omit array maxItems for generation only; preserve the local validation schema."""
    result = copy.deepcopy(schema.model_json_schema())

    def remove_max_items(value):
        if not isinstance(value, dict):
            return
        value.pop("maxItems", None)
        # These maps contain named subschemas: their keys are data names, not keywords.
        for key in ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas", "dependencies"):
            children = value.get(key)
            if isinstance(children, dict):
                for child in children.values():
                    remove_max_items(child)
        for key in ("items", "additionalItems", "additionalProperties", "unevaluatedItems", "unevaluatedProperties",
                    "contains", "propertyNames", "not", "if", "then", "else", "contentSchema",
                    "allOf", "anyOf", "oneOf", "prefixItems"):
            child = value.get(key)
            if isinstance(child, list):
                for item in child:
                    remove_max_items(item)
            else:
                remove_max_items(child)
        # Defaults, examples, enum/const values and other annotations are data, not schemas.

    remove_max_items(result)
    return result


def http_error_type(status):
    """Classify the numeric status only; never inspect provider response bodies."""
    explicit = {400: "HTTP_BAD_REQUEST", 401: "HTTP_UNAUTHENTICATED",
                403: "HTTP_PERMISSION_DENIED", 404: "HTTP_NOT_FOUND",
                408: "HTTP_REQUEST_TIMEOUT", 409: "HTTP_CONFLICT", 429: "HTTP_RATE_LIMITED"}
    if status in explicit:
        return explicit[status]
    if 500 <= status <= 599:
        return "HTTP_SERVER_ERROR"
    if 300 <= status <= 399:
        return "HTTP_REDIRECT"
    return "HTTP_OTHER_ERROR"


class MatchError(Exception):
    def __init__(self, code, *, retryable=False, retry_after=None, http_status=None):
        super().__init__(code)
        self.code, self.retryable, self.retry_after = code, retryable, retry_after
        self.http_status = http_status
        self.stage = None

    def diagnostics(self):
        details = {"code": self.code}
        if self.http_status is not None:
            details.update(http_status=str(self.http_status), error_type=http_error_type(self.http_status))
        else:
            details["error_type"] = {"LLM_READ_TIMEOUT": "READ_TIMEOUT", "LLM_TIMEOUT": "TIMEOUT",
                                     "LLM_NETWORK_ERROR": "NETWORK_ERROR"}.get(self.code, self.code)
        if self.stage in ("extraction", "comparison"):
            details["stage"] = self.stage
        return details

    def __str__(self):
        # Only locally defined codes, numeric status and fixed pipeline stage are shown.
        return " ".join(f"{key}={value}" for key, value in self.diagnostics().items())


class GeminiMatchLLM:
    def __init__(self, client=None):
        self.client = client
        self.model = settings.gemini_model.strip().removeprefix("models/")

    def generate(self, schema, instruction, document):
        key = settings.gemini_api_key
        if key is None or not key.get_secret_value().strip() or not self.model:
            raise MatchError("LLM_NOT_CONFIGURED")
        # Model is a path segment, never an arbitrary URL, query string or resource path.
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.model):
            raise MatchError("LLM_INVALID_MODEL")
        body = {
            "systemInstruction": {"parts": [{"text": instruction}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(document, ensure_ascii=False)}]}],
            "generationConfig": {"maxOutputTokens": 12000,
                                 "responseMimeType": "application/json",
                                 "responseJsonSchema": _gemini_schema(schema)}}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": key.get_secret_value()}
        try:
            if self.client is None:
                with httpx.Client(timeout=httpx.Timeout(120, connect=10), follow_redirects=False) as client:
                    response = client.post(url, json=body, headers=headers)
            else:
                response = self.client.post(url, json=body, headers=headers, timeout=120, follow_redirects=False)
        except httpx.ReadTimeout:
            raise MatchError("LLM_READ_TIMEOUT", retryable=True) from None
        except httpx.TimeoutException:
            raise MatchError("LLM_TIMEOUT", retryable=True) from None
        except httpx.RequestError:
            raise MatchError("LLM_NETWORK_ERROR", retryable=True) from None
        if not response.is_success:
            retryable = response.status_code in (408, 409, 429, 500, 502, 503, 504)
            raise MatchError("LLM_HTTP_ERROR", retryable=retryable, http_status=response.status_code,
                             retry_after=_retry_after(response.headers.get("Retry-After")))
        try:
            data = response.json()
            blocked = data.get("promptFeedback", {}).get("blockReason")
            if blocked and blocked != "BLOCK_REASON_UNSPECIFIED":
                raise MatchError("LLM_REFUSED")
            candidates = data.get("candidates", [])
            if len(candidates) != 1:
                raise MatchError("LLM_INVALID_OUTPUT", retryable=True)
            candidate = candidates[0]
            reason = candidate.get("finishReason")
            if reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII",
                          "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT", "MODEL_ARMOR"}:
                raise MatchError("LLM_REFUSED")
            if reason == "MAX_TOKENS":
                raise MatchError("LLM_INCOMPLETE", retryable=True)
            if reason != "STOP":
                raise MatchError("LLM_INVALID_OUTPUT", retryable=True)
            parts = candidate.get("content", {}).get("parts", [])
            # Thinking text is not the final JSON and must not be parsed or persisted.
            if any(not part.get("thought", False) and "text" not in part for part in parts):
                raise MatchError("LLM_INVALID_OUTPUT", retryable=True)
            output = "".join(part["text"] for part in parts if not part.get("thought", False))
            return schema.model_validate_json(output)
        except (ValueError, TypeError, KeyError, AttributeError, ValidationError):
            raise MatchError("LLM_INVALID_OUTPUT", retryable=True) from None
