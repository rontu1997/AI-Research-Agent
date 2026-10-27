"""OpenAI web search supplies source snippets without another API credential."""

from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr

from adapters.live import OpenAIWebSearch


class _Responses:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="web_search_call",
                    results=[
                        {
                            "type": "text_result",
                            "title": "First",
                            "url": "https://a.example/x",
                            "snippet": "The pilot launched in March 2024 with 120 bikes.",
                        },
                        {
                            "type": "text_result",
                            "title": "Unsafe",
                            "url": "file:///secret",
                            "snippet": "This must never become a source.",
                        },
                        {"type": "text_result", "title": "No text", "url": "https://b.example/y"},
                    ],
                )
            ]
        )


def test_openai_search_uses_web_search_and_only_returns_source_text() -> None:
    responses = _Responses()
    client = SimpleNamespace(responses=responses)
    search = OpenAIWebSearch(SecretStr("sk-test"), "gpt-6-luna", client=client)

    result = search.search("bike pilot", max_results=3, want_extracted=True, timeout_s=10)

    assert responses.kwargs["model"] == "gpt-6-luna"
    assert responses.kwargs["tools"] == [{"type": "web_search"}]
    assert responses.kwargs["tool_choice"] == "required"
    assert responses.kwargs["include"] == ["web_search_call.results"]
    assert [(r.title, r.url, r.snippet) for r in result.results] == [
        ("First", "https://a.example/x", "The pilot launched in March 2024 with 120 bikes.")
    ]
    assert result.results[0].extracted_text is None
    assert "sk-test" not in repr(search)
