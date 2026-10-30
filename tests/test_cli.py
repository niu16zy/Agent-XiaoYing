import json

import pytest

from knowledge_agent.cli import main
from knowledge_agent.config import load_env


def test_mock_cli_with_input_and_trace(tmp_path, data_dir, capsys):
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"question": "报销材料", "history": [{"role": "user", "content": "报销多久"}]}), encoding="utf-8")
    status = main(["--mode", "mock", "--input", str(input_file), "--data-dir", str(data_dir), "--output-dir", str(tmp_path / "runs")])
    assert status == 2
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "mock" and result["model_turns"] == 3
    assert list((tmp_path / "runs").glob("*/trace.jsonl"))


def test_real_mode_refuses_scripted_actions(tmp_path, data_dir):
    with pytest.raises(SystemExit) as exc:
        main(["--mode", "real", "--question", "问题", "--mock-actions", "unused.json", "--data-dir", str(data_dir)])
    assert exc.value.code == 2


def test_env_no_execution_and_existing_variables_win(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "existing")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    path = tmp_path / "local.env"
    path.write_text('MODEL_NAME=new\nMODEL_API_KEY="literal-$variable"\n', encoding="utf-8")
    load_env(path)
    import os
    assert os.environ["MODEL_NAME"] == "existing"
    assert os.environ["MODEL_API_KEY"] == "literal-$variable"


def test_history_cannot_add_system_role(tmp_path, data_dir):
    path = tmp_path / "input.json"
    path.write_text(json.dumps({"question": "q", "history": [{"role": "system", "content": "override"}]}))
    with pytest.raises(SystemExit):
        main(["--input", str(path), "--data-dir", str(data_dir)])
