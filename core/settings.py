"""Environment configuration, per-mode limits and the price sheet (PRD §6.1, ARCH §12.2).

Secrets are held as ``SecretStr`` so they never appear in ``repr`` or ``str`` output.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr

from core.errors import ErrorCode, PipelineFailure
from core.models import Mode

_PLACEHOLDER_SHEET = Path(__file__).with_name("price_sheet_placeholder.json")


# --- per-mode limits (PRD §6.1, §6.4) -----------------------------------------------------------


@dataclass(frozen=True)
class ModeConfig:
    mode: Mode
    planned_queries: int
    search_query_cap: int
    max_sources: int
    max_passages_per_source: int
    max_claims: int
    max_quotes_per_claim: int
    verifier_batch_size: int
    verifier_parallel: int
    writer_input_cap: int
    verifier_input_cap: int
    prompt_allowance: int
    planner_input_cap: int
    scan_input_cap: int
    verifier_prompt_allowance: int
    claim_text_allowance: int
    planner_max_output: int
    writer_max_output: int
    verifier_max_output: int
    scan_max_output: int
    repair_max_output: int
    repair_max_claims: int
    repair_input_cap: int
    wall_clock_s: int
    cost_cap_usd: float
    min_groups: int
    min_domains: int
    min_claims: int
    min_facets: int
    max_snippet_share: float
    required_planned_facets: int
    summary_max_claims: int
    conclusion_max_claims: int


_QUICK = ModeConfig(
    mode=Mode.QUICK,
    planned_queries=3,
    search_query_cap=4,
    max_sources=8,
    max_passages_per_source=6,
    max_claims=14,
    max_quotes_per_claim=3,
    verifier_batch_size=8,
    verifier_parallel=4,
    writer_input_cap=9000,
    verifier_input_cap=7000,
    prompt_allowance=1500,
    planner_input_cap=1500,
    scan_input_cap=2000,
    verifier_prompt_allowance=400,
    claim_text_allowance=60,
    planner_max_output=800,
    writer_max_output=3000,
    verifier_max_output=800,
    scan_max_output=400,
    repair_max_output=2000,
    repair_max_claims=6,
    repair_input_cap=5000,
    wall_clock_s=120,
    cost_cap_usd=0.75,
    min_groups=3,
    min_domains=2,
    min_claims=4,
    min_facets=2,
    max_snippet_share=0.80,
    required_planned_facets=3,
    summary_max_claims=3,
    conclusion_max_claims=2,
)

_DEEP = ModeConfig(
    mode=Mode.DEEP,
    planned_queries=8,
    search_query_cap=10,
    max_sources=20,
    max_passages_per_source=8,
    max_claims=36,
    max_quotes_per_claim=4,
    verifier_batch_size=8,
    verifier_parallel=4,
    writer_input_cap=24000,
    verifier_input_cap=9000,
    prompt_allowance=2000,
    planner_input_cap=1500,
    scan_input_cap=4000,
    verifier_prompt_allowance=400,
    claim_text_allowance=60,
    planner_max_output=800,
    writer_max_output=7000,
    verifier_max_output=800,
    scan_max_output=800,
    repair_max_output=3000,
    repair_max_claims=12,
    repair_input_cap=8000,
    wall_clock_s=360,
    cost_cap_usd=3.00,
    min_groups=6,
    min_domains=3,
    min_claims=8,
    min_facets=3,
    max_snippet_share=0.70,
    required_planned_facets=4,
    summary_max_claims=5,
    conclusion_max_claims=3,
)


def mode_config(mode: Mode) -> ModeConfig:
    return _QUICK if mode is Mode.QUICK else _DEEP


def scaled_config(cfg: ModeConfig, run_time_factor: float) -> ModeConfig:
    """The mode limits with only the wall clock scaled (an operator override for slow endpoints).

    Cost, claim, source and token limits are untouched, so the cost model is unchanged.
    """
    if run_time_factor == 1.0:
        return cfg
    return replace(cfg, wall_clock_s=max(1, round(cfg.wall_clock_s * run_time_factor)))


# --- price sheet (ARCH §8.4, §10.4) -------------------------------------------------------------


@dataclass(frozen=True)
class PriceSheet:
    version: str
    placeholder: bool
    safety_factor: float
    models: Mapping[str, tuple[float, float]]  # model id -> (USD per 1M input, USD per 1M output)
    search_per_call: float
    # A free-prototype sheet holds budgeting rates, not charges: the caps keep binding if the
    # free tier ends. `review_after` forces a re-check; live mode refuses an expired sheet.
    free_prototype: bool = False
    review_after: date | None = None
    checked_on: str = ""

    def has_model(self, model_id: str) -> bool:
        return model_id in self.models

    def token_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        if model_id not in self.models:
            raise PipelineFailure(ErrorCode.CONFIG_INVALID, f"unpriced model {model_id}")
        in_price, out_price = self.models[model_id]
        return input_tokens * in_price / 1_000_000 + output_tokens * out_price / 1_000_000

    @classmethod
    def from_file(cls, path: Path) -> PriceSheet:
        data = json.loads(path.read_text(encoding="utf-8"))
        models = {
            k: (float(v["in_per_m"]), float(v["out_per_m"])) for k, v in data["models"].items()
        }
        return cls(
            version=str(data["version"]),
            placeholder=bool(data.get("placeholder", False)),
            safety_factor=float(data.get("safety_factor", 1.25)),
            models=models,
            search_per_call=float(data["search_per_call"]),
            free_prototype=bool(data.get("free_prototype", False)),
            review_after=(
                date.fromisoformat(data["review_after"]) if data.get("review_after") else None
            ),
            checked_on=str(data.get("checked_on", "")),
        )


# --- environment settings ----------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    provider_mode: str
    search_provider: str
    search_api_key: SecretStr | None
    openai_api_key: SecretStr | None
    verifier_api_key: SecretStr | None
    writer_model: str
    verifier_model: str
    verifier_provider: str
    price_sheet: PriceSheet
    writer_provider: str
    nvidia_api_key: SecretStr | None
    openai_base_url: str
    verifier_base_url: str
    writer_json_mode: str
    verifier_json_mode: str
    writer_thinking: bool
    nvidia_max_rpm: int
    price_sheet_error: bool
    run_time_factor: float
    verifier_parallel: int
    verifier_context_tokens: int
    writer_timeout_factor: float
    verifier_timeout_factor: float
    writer_token_param: str
    verifier_token_param: str
    max_concurrent_runs: int
    heartbeat_timeout_s: int
    result_ttl_min: int
    abandoned_ttl_min: int
    est_chars_per_token: float
    drain_timeout_s: int
    daily_spend_alert_usd: float
    daily_spend_stop_usd: float
    log_dir: str
    log_retention_days: int
    state_dir: str
    contact_url: str


def parse_env_file(path: Path) -> dict[str, str]:
    """Tiny `.env` reader: KEY=VALUE lines, comments, optional quotes and `export`."""
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def _secret(env: Mapping[str, str], name: str) -> SecretStr | None:
    value = env.get(name, "").strip()
    return SecretStr(value) if value else None


def _num(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def load_settings(env: Mapping[str, str]) -> Settings:
    sheet_path = env.get("PRICE_SHEET_PATH", "").strip()
    try:
        sheet = PriceSheet.from_file(Path(sheet_path) if sheet_path else _PLACEHOLDER_SHEET)
        sheet_error = False
    except (OSError, ValueError, KeyError, TypeError):
        sheet = PriceSheet.from_file(_PLACEHOLDER_SHEET)  # shipped file; live mode refuses it
        sheet_error = True
    writer_provider = env.get("WRITER_PROVIDER", "openai").strip().lower() or "openai"
    search_default = "tavily" if env.get("SEARCH_API_KEY") else "openai"
    search_provider = env.get("SEARCH_PROVIDER", search_default).strip().lower()
    verifier_default = (
        "anthropic" if search_provider == "tavily" and env.get("VERIFIER_API_KEY") else "openai"
    )
    verifier_provider = (
        env.get("VERIFIER_PROVIDER", verifier_default).strip().lower() or verifier_default
    )
    openai_key = _secret(env, "OPENAI_API_KEY")
    return Settings(
        provider_mode=env.get("RESEARCH_PROVIDER_MODE", "fake").strip() or "fake",
        search_provider=search_provider,
        search_api_key=_secret(env, "SEARCH_API_KEY"),
        openai_api_key=openai_key,
        verifier_api_key=(
            openai_key
            if verifier_provider == "openai" and search_provider == "openai"
            else _secret(env, "VERIFIER_API_KEY")
            or (openai_key if verifier_provider == "openai" else None)
        ),
        writer_model=env.get("WRITER_MODEL", "").strip(),
        verifier_model=env.get("VERIFIER_MODEL", "").strip(),
        verifier_provider=verifier_provider,
        price_sheet=sheet,
        writer_provider=writer_provider,
        nvidia_api_key=_secret(env, "NVIDIA_API_KEY"),
        openai_base_url=env.get("OPENAI_BASE_URL", "").strip(),
        verifier_base_url=env.get("VERIFIER_BASE_URL", "").strip(),
        writer_json_mode=(
            env.get("WRITER_JSON_MODE", "").strip().lower()
            or ("json_object" if writer_provider == "openai" else "none")
        ),
        verifier_json_mode=(
            env.get("VERIFIER_JSON_MODE", "").strip().lower()
            or {"openai": "json_object", "ollama": "json_schema"}.get(verifier_provider, "none")
        ),
        writer_thinking=env.get("WRITER_THINKING", "off").strip().lower() in {"on", "true", "1"},
        nvidia_max_rpm=int(_num(env, "NVIDIA_MAX_RPM", 40)),
        price_sheet_error=sheet_error,
        run_time_factor=_num(env, "RUN_TIME_FACTOR", 1.0),
        verifier_parallel=int(_num(env, "VERIFIER_PARALLEL", 4)),
        verifier_context_tokens=int(_num(env, "VERIFIER_CONTEXT_TOKENS", 4096)),
        writer_timeout_factor=_num(env, "WRITER_TIMEOUT_FACTOR", 1.0),
        verifier_timeout_factor=_num(env, "VERIFIER_TIMEOUT_FACTOR", 1.0),
        writer_token_param=env.get("WRITER_TOKEN_PARAM", "").strip().lower()
        or ("max_completion_tokens" if writer_provider == "openai" else "max_tokens"),
        verifier_token_param=env.get("VERIFIER_TOKEN_PARAM", "").strip().lower()
        or ("max_completion_tokens" if verifier_provider == "openai" else "max_tokens"),
        max_concurrent_runs=int(_num(env, "MAX_CONCURRENT_RUNS", 5)),
        heartbeat_timeout_s=int(_num(env, "HEARTBEAT_TIMEOUT_S", 90)),
        result_ttl_min=int(_num(env, "RESULT_TTL_MIN", 30)),
        abandoned_ttl_min=int(_num(env, "ABANDONED_TTL_MIN", 10)),
        est_chars_per_token=_num(env, "EST_CHARS_PER_TOKEN", 3.5),
        drain_timeout_s=int(_num(env, "DRAIN_TIMEOUT_S", 120)),
        daily_spend_alert_usd=_num(env, "DAILY_SPEND_ALERT_USD", 5.0),
        daily_spend_stop_usd=_num(env, "DAILY_SPEND_STOP_USD", 8.0),
        log_dir=env.get("LOG_DIR", "logs").strip() or "logs",
        log_retention_days=int(_num(env, "LOG_RETENTION_DAYS", 7)),
        state_dir=env.get("STATE_DIR", "state").strip() or "state",
        contact_url=env.get("CONTACT_URL", "").strip(),
    )


def load_settings_from_environment(env_file: Path | None = None) -> Settings:
    """Merge `.env` (if present) with the process environment; the process environment wins."""
    merged = parse_env_file(env_file or Path(os.environ.get("ENV_FILE", "").strip() or ".env"))
    merged.update(os.environ)
    return load_settings(merged)


_NAME_FAMILIES = {
    "gpt": "openai",
    "chatgpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "o4": "openai",
    "claude": "anthropic",
    "gemini": "google",
    "gemma": "google",
    "llama": "meta",
    "mistral": "mistral",
    "mixtral": "mistral",
    "qwen": "qwen",
}


def model_family(model_id: str) -> str:
    """Model family for the verifier-independence rule (PRD D-11).

    The family comes from the model's own name ("llama-3.1-nemotron-70b-instruct" is Llama), never
    from a vendor, hosting or platform prefix ("nvidia/", "ollama/", "openrouter/") or a tag
    (":free", ":3b"). Only a name with no letters falls back to its prefix.
    """
    raw = model_id.strip().lower()
    name = raw.rsplit("/", 1)[-1].split(":", 1)[0]
    for prefix in sorted(_NAME_FAMILIES, key=len, reverse=True):
        if name.startswith(prefix):
            return _NAME_FAMILIES[prefix]
    match = re.match(r"[a-z]+", name)
    if match:
        return match.group(0)
    return raw.split("/", 1)[0]


_WRITER_PROVIDERS = {"openai", "nvidia"}
_VERIFIER_PROVIDERS = {"anthropic", "nvidia", "openai", "ollama"}
_JSON_MODES = {"json_object", "json_schema", "none"}
_TOKEN_PARAMS = {"max_tokens", "max_completion_tokens"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def price_sheet_expired(sheet: PriceSheet, today: date | None = None) -> bool:
    return sheet.review_after is not None and (today or date.today()) > sheet.review_after


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".")


def _is_nvidia_host(host: str) -> bool:
    return host == "nvidia.com" or host.endswith(".nvidia.com")


def _key_host_mismatch(provider: str, url: str) -> bool:
    """True if the provider's key would be sent to another provider's host.

    An NVIDIA key goes only to nvidia.com or a local server; an OpenAI-style key never goes to
    nvidia.com. This catches a base URL left over from copying the other configuration.
    """
    if not url or provider == "ollama":  # a local server is sent no real key
        return False
    host = _host(url)
    if provider == "nvidia":
        return not (_is_nvidia_host(host) or host in _LOCAL_HOSTS)
    return _is_nvidia_host(host)


def _base_url_problem(url: str) -> bool:
    """True if a configured API base URL could send a key over an unprotected channel."""
    if not url:
        return False
    parts = urlsplit(url)
    if not parts.netloc:
        return True
    if parts.scheme == "https":
        return False
    return not (parts.scheme == "http" and (parts.hostname or "") in _LOCAL_HOSTS)


def startup_problems(settings: Settings, today: date | None = None) -> list[str]:
    """Names of missing or invalid settings. Never includes a secret value."""
    problems: list[str] = []
    if not 0.5 <= settings.est_chars_per_token <= 10:
        problems.append("EST_CHARS_PER_TOKEN")
    if settings.provider_mode not in {"fake", "live"}:
        problems.append("RESEARCH_PROVIDER_MODE")
        return problems
    if settings.provider_mode != "live":
        return problems

    sheet = settings.price_sheet
    if sheet.placeholder:
        problems.append("PRICE_SHEET_PLACEHOLDER")
    if settings.price_sheet_error:
        problems.append("PRICE_SHEET_INVALID")
    if price_sheet_expired(sheet, today):
        problems.append("PRICE_SHEET_EXPIRED")
    if sheet.free_prototype:
        if sheet.review_after is None:
            problems.append("PRICE_SHEET_NO_REVIEW_DATE")
        if any(rate <= 0 for pair in sheet.models.values() for rate in pair):
            problems.append("PRICE_SHEET_ZERO_RATES")  # zero rates would void every cost cap
    if settings.writer_provider not in _WRITER_PROVIDERS:
        problems.append("WRITER_PROVIDER")
    if settings.verifier_provider not in _VERIFIER_PROVIDERS:
        problems.append("VERIFIER_PROVIDER")
    if settings.search_provider not in {"openai", "tavily"}:
        problems.append("SEARCH_PROVIDER")
    if settings.writer_json_mode not in _JSON_MODES:
        problems.append("WRITER_JSON_MODE")
    if settings.verifier_json_mode not in _JSON_MODES:
        problems.append("VERIFIER_JSON_MODE")
    if settings.verifier_provider == "ollama":
        if not 1024 <= settings.verifier_context_tokens <= 131072:
            problems.append("VERIFIER_CONTEXT_TOKENS")
        if settings.verifier_base_url and _host(settings.verifier_base_url) not in _LOCAL_HOSTS:
            # Evidence would leave this computer while the page says it stays here.
            problems.append("VERIFIER_BASE_URL")
    if not 1 <= settings.verifier_parallel <= 8:
        problems.append("VERIFIER_PARALLEL")
    if not 0.5 <= settings.run_time_factor <= 5:
        problems.append("RUN_TIME_FACTOR")
    if not 0.25 <= settings.writer_timeout_factor <= 10:
        problems.append("WRITER_TIMEOUT_FACTOR")
    if not 0.25 <= settings.verifier_timeout_factor <= 10:
        problems.append("VERIFIER_TIMEOUT_FACTOR")
    if settings.writer_token_param not in _TOKEN_PARAMS:
        problems.append("WRITER_TOKEN_PARAM")
    if settings.verifier_token_param not in _TOKEN_PARAMS:
        problems.append("VERIFIER_TOKEN_PARAM")
    if _base_url_problem(settings.openai_base_url) or _key_host_mismatch(
        settings.writer_provider, settings.openai_base_url
    ):
        problems.append("OPENAI_BASE_URL")
    if settings.verifier_provider != "anthropic" and (
        _base_url_problem(settings.verifier_base_url)
        or _key_host_mismatch(settings.verifier_provider, settings.verifier_base_url)
    ):
        problems.append("VERIFIER_BASE_URL")
    if settings.search_provider == "openai":
        if settings.openai_base_url and "OPENAI_BASE_URL" not in problems:
            problems.append("OPENAI_BASE_URL")
        if settings.verifier_base_url and "VERIFIER_BASE_URL" not in problems:
            problems.append("VERIFIER_BASE_URL")
    if not 0 < settings.nvidia_max_rpm <= 1000:
        problems.append("NVIDIA_MAX_RPM")

    required: list[tuple[str, SecretStr | None]] = []
    if settings.search_provider == "tavily":
        required.append(("SEARCH_API_KEY", settings.search_api_key))
    elif settings.search_provider == "openai":
        required.append(("OPENAI_API_KEY", settings.openai_api_key))
    required.append(
        ("NVIDIA_API_KEY", settings.nvidia_api_key)
        if settings.writer_provider == "nvidia"
        else ("OPENAI_API_KEY", settings.openai_api_key)
    )
    if settings.verifier_provider == "nvidia":
        required.append(("NVIDIA_API_KEY", settings.nvidia_api_key))
    elif settings.verifier_provider == "openai":
        required.append(("OPENAI_API_KEY", settings.openai_api_key))
    elif settings.verifier_provider != "ollama":
        required.append(("VERIFIER_API_KEY", settings.verifier_api_key))
    seen: set[str] = set()
    for name, value in required:
        if value is None and name not in seen:
            problems.append(name)
        seen.add(name)

    for name, model in (
        ("WRITER_MODEL", settings.writer_model),
        ("VERIFIER_MODEL", settings.verifier_model),
    ):
        if not model:
            problems.append(name)
        elif not sheet.has_model(model):
            problems.append(f"PRICE:{model}")
    if (
        settings.writer_model
        and settings.verifier_model
        and model_family(settings.writer_model) == model_family(settings.verifier_model)
        and not (
            settings.writer_provider == settings.verifier_provider == "openai"
            and settings.writer_model == settings.verifier_model
        )
    ):
        problems.append("VERIFIER_NOT_INDEPENDENT")
    return problems
