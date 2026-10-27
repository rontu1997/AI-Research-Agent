from __future__ import annotations

import pytest

import demo


def test_demo_prints_a_completed_report_and_exits_zero(
    capsys: pytest.CaptureFixture[str], tmp_path, monkeypatch
) -> None:  # noqa: ANN001
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    code = demo.main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "Demo mode" in out and "Status: Completed" in out
    assert "Evidence appendix" in out


def test_demo_deep_flag_runs_deep_mode(
    capsys: pytest.CaptureFixture[str], tmp_path, monkeypatch
) -> None:  # noqa: ANN001
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    assert demo.main(["--deep"]) in {0, 2}
    assert "Deep mode" in capsys.readouterr().out
