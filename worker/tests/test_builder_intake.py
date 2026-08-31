from __future__ import annotations

import asyncio

from sam_worker.builder_intake import run_builder_intake_turn


class _SeqClient:
    def __init__(self, sync_rows: list[dict], tool_text: str = "Next gap?") -> None:
        self._sync_rows = list(sync_rows)
        self.tools: list[str] = []
        self.tool_text = tool_text

    async def get_intake_sync(self, engagement_id: str) -> dict:
        row = self._sync_rows[min(len(self.tools) // 2, len(self._sync_rows) - 1)]
        return {"ok": True, "engagementId": engagement_id, **row}

    async def run_tool(self, name: str, args: dict | None = None) -> dict:
        self.tools.append(name)
        if name == "proposal_answer_question":
            sync = self._sync_rows[1] if len(self._sync_rows) > 1 else self._sync_rows[0]
            return {"ok": True, "text": "Saved.", **sync}
        if name == "proposal_set_field":
            return {"ok": True, "text": "Set field."}
        return {"ok": True, "text": self.tool_text, "gap": {"questionId": "cms"}}


def test_builder_intake_turn_writes_then_ask_gap() -> None:
    client = _SeqClient(
        [
            {
                "complete": False,
                "gaps": [{"field": "discovery", "questionId": "pages", "question": "How many pages?"}],
                "focus": {"questionId": "pages"},
                "answers": [],
                "form_data": {"projectSummary": "Harbor"},
            },
            {
                "complete": False,
                "gaps": [{"field": "discovery", "questionId": "cms", "question": "CMS?"}],
                "focus": {"questionId": "cms"},
                "answers": [{"questionId": "pages", "value": "8"}],
                "form_data": {"projectSummary": "Harbor"},
            },
        ],
        tool_text="Do you need a CMS?",
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="Eight pages")
    )
    assert tools == ["proposal_answer_question", "proposal_ask_gap"]
    assert "CMS" in spoken
    assert "proposal_save_research" not in tools


def test_builder_intake_turn_skips_sync_and_leave_it_confirm() -> None:
    client = _SeqClient(
        [
            {
                "complete": False,
                "gaps": [{"field": "discovery", "questionId": "cms", "question": "CMS?"}],
                "focus": {"questionId": "pages"},
                "answers": [{"questionId": "pages", "value": "8"}],
                "form_data": {"projectSummary": "Harbor"},
            }
        ],
        tool_text="Do you need a CMS?",
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="leave it")
    )
    assert tools == ["proposal_ask_gap"]
    assert spoken == "Do you need a CMS?"


def test_builder_intake_turn_ignores_sync_prefix() -> None:
    client = _SeqClient(
        [
            {
                "complete": False,
                "gaps": [{"field": "discovery", "questionId": "pages", "question": "How many pages?"}],
                "focus": {"questionId": "pages"},
                "answers": [],
                "form_data": {},
            }
        ]
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="[SYNC] call proposal_ask_gap")
    )
    assert spoken == ""
    assert tools == []
