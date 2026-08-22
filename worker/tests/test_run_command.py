"""run_command stays resident so any command is reachable without 31 schemas."""

from __future__ import annotations

from sam_worker.tools.select import VOICE_TOOLS, select_tools_for_utterance


def test_run_command_is_always_present_except_pricing() -> None:
    assert "run_command" in VOICE_TOOLS
    assert "run_command" in select_tools_for_utterance("tell me a joke")
    assert "run_command" in select_tools_for_utterance("hello there")
    assert "run_command" in select_tools_for_utterance("what's the pulse")
    assert select_tools_for_utterance("How much does Rainmaker cost?") == []


def test_run_command_does_not_replace_specific_tools() -> None:
    names = select_tools_for_utterance("what's the pulse looking like")
    assert names[0] == "get_pulse"
    assert names[-1] == "run_command"
