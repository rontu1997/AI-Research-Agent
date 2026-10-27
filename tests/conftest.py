import pytest  # noqa: E402

from tests.pipeline.conftest import make_ctx  # noqa: F401  (shared fixture for root-level tests)


@pytest.fixture(autouse=True)
def _hermetic_env_file(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests never read the developer's own `.env` (it may hold live keys and live mode)."""
    monkeypatch.setenv("ENV_FILE", str(tmp_path_factory.getbasetemp() / "no-such.env"))
