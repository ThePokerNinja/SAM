from __future__ import annotations

import asyncio

from sam_worker.builder_intake import run_builder_intake_turn


class _SeqClient:
    def __init__(self, sync_rows: list[dict], tool_text: str = "Next gap?") -> None:
        self._sync_rows = list(sync_rows)
        self.tools: list[str] = []
        self.tool_text = tool_text
        self._sync_idx = 0

    async def get_intake_sync(self, engagement_id: str) -> dict:
        row = self._sync_rows[min(self._sync_idx, len(self._sync_rows) - 1)]
        return {"ok": True, "engagementId": engagement_id, **row}

    async def run_tool(self, name: str, args: dict | None = None) -> dict:
        self.tools.append(name)
        if name == "proposal_apply_summary":
            self._sync_idx = min(self._sync_idx + 1, len(self._sync_rows) - 1)
            row = self._sync_rows[self._sync_idx]
            return {"ok": True, "text": "Filled.", **row}
        if name == "proposal_answer_question":
            self._sync_idx = min(self._sync_idx + 1, len(self._sync_rows) - 1)
            row = self._sync_rows[self._sync_idx]
            return {"ok": True, "text": "Saved.", **row}
        if name == "proposal_set_field":
            return {"ok": True, "text": "Set field."}
        if name == "proposal_research":
            return {"ok": True, "text": "Research attached."}
        if name == "proposal_mark_estimate_ready":
            return {
                "ok": True,
                "text": "Intake is complete. I'll put the estimate up.",
                "complete": True,
            }
        if name == "proposal_sales_advance":
            event = str((args or {}).get("event") or "")
            if event == "offer_review":
                return {
                    "ok": True,
                    "text": "I am about 90% confident on the scope. Want the draft by text or email?",
                    "sales": {"phase": "review_offered", "confidence": 90},
                }
            if event == "choose_channel":
                return {"ok": True, "text": "Got it.", "sales": {"phase": "review_sent", "confidence": 90}}
            if event == "mark_reviewed":
                return {"ok": True, "text": "Got it.", "sales": {"phase": "reviewed", "confidence": 90}}
            if event == "approve_phase1":
                return {"ok": True, "text": "Got it.", "sales": {"phase": "budget", "confidence": 90}}
            if event == "set_budget":
                return {
                    "ok": True,
                    "text": "Got it.",
                    "sales": {"phase": "budget", "confidence": 90, "budgetBand": "15000"},
                }
            if event == "approve_phase2":
                return {"ok": True, "text": "Approved.", "sales": {"phase": "phase2_approved", "confidence": 90}}
            return {"ok": False, "text": "Unknown sales event."}
        if name == "proposal_send":
            kind = str((args or {}).get("kind") or "draft")
            return {
                "ok": True,
                "text": "Sent.",
                "kind": kind,
                "body": "Harbor Izakaya — $4,125 (33 hours)\nEngagement eng-1\nOpen: https://start.michaelstewman.com/?e=eng-1",
            }
        return {"ok": True, "text": self.tool_text, "gap": {"questionId": "cms", "field": "discovery", "question": self.tool_text}}


def test_builder_intake_turn_writes_then_ask_gap() -> None:
    client = _SeqClient(
        [
            {
                "complete": False,
                "gaps": [{"field": "discovery", "questionId": "pages", "question": "How many pages?"}],
                "focus": {"questionId": "pages"},
                "answers": [],
                "questions": [{"id": "pages", "text": "How many pages?"}],
                "form_data": {"projectSummary": "Harbor"},
            },
            {
                "complete": False,
                "gaps": [{"field": "discovery", "questionId": "cms", "question": "CMS?"}],
                "focus": {"questionId": "cms"},
                "answers": [{"questionId": "pages", "value": "8"}],
                "questions": [{"id": "pages", "text": "How many pages?"}, {"id": "cms", "text": "CMS?"}],
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
                "questions": [{"id": "cms", "text": "CMS?"}],
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


def test_builder_intake_turn_research_wait_runs_research_then_asks() -> None:
    client = _SeqClient(
        [
            {
                "complete": False,
                "gaps": [{"field": "research", "question": "Hang on while I pull research."}],
                "focus": {"field": "research"},
                "answers": [],
                "form_data": {"projectSummary": "Harbor"},
            }
        ],
        tool_text="What problem is this solving?",
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="while we wait tell me more")
    )
    assert "proposal_research" in tools
    assert "proposal_ask_gap" in tools
    assert "hang on" not in spoken.lower()
    assert "problem" in spoken.lower() or "what" in spoken.lower()


def test_builder_intake_turn_dump_applies_summary() -> None:
    client = _SeqClient(
        [
            {
                "complete": False,
                "gaps": [{"field": "discovery", "questionId": "pages", "question": "How many pages?"}],
                "focus": {"questionId": "pages"},
                "answers": [],
                "questions": [{"id": "pages", "text": "How many pages?"}],
                "form_data": {"projectSummary": "Harbor"},
            },
            {
                "complete": False,
                "gaps": [{"field": "research", "question": "Hang on while I pull research."}],
                "focus": {"field": "research"},
                "answers": [],
                "form_data": {"projectSummary": "Harbor"},
            },
        ],
        tool_text="Hang on while I pull research.",
    )
    dump = (
        'I\'m a producer and we need a website for "Harbor Izakaya" this month. '
        "Reservations and a menu, no rush on extras."
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text=dump)
    )
    assert "proposal_apply_summary" in tools
    assert "proposal_answer_question" not in tools
    assert spoken


def test_builder_intake_turn_estimate_wait_marks_ready_not_what_else() -> None:
    client = _SeqClient(
        [
            {
                "complete": False,
                "gaps": [{"field": "estimate", "questionId": "_pending", "question": "One second — putting the estimate up."}],
                "focus": {"field": "estimate"},
                "answers": [{"questionId": "pages", "value": "8"}],
                "questions": [{"id": "pages", "text": "How many pages?"}],
                "form_data": {"projectSummary": "Harbor"},
            }
        ],
        tool_text="Intake is complete. I'll put the estimate up.",
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="ok go ahead")
    )
    assert "proposal_mark_estimate_ready" in tools
    assert "proposal_sales_advance" in tools
    assert "proposal_ask_gap" not in tools
    assert "what else should i know" not in spoken.lower()
    assert "confident" in spoken.lower()
    assert "text or email" in spoken.lower()


def test_builder_intake_turn_phone_fragment_holds_then_merges() -> None:
    client = _SeqClient(
        [
            {
                "complete": False,
                "gaps": [{"field": "discovery", "questionId": "pages", "question": "How many pages?"}],
                "focus": {"questionId": "pages"},
                "answers": [],
                "questions": [{"id": "pages", "text": "How many pages?"}],
                "form_data": {"projectSummary": "Harbor"},
            },
            {
                "complete": False,
                "gaps": [{"field": "discovery", "questionId": "pages", "question": "How many pages?"}],
                "focus": {"questionId": "pages"},
                "answers": [],
                "questions": [{"id": "pages", "text": "How many pages?"}],
                "form_data": {"projectSummary": "Harbor"},
            },
            {
                "complete": False,
                "gaps": [{"field": "discovery", "questionId": "cms", "question": "CMS?"}],
                "focus": {"questionId": "cms"},
                "answers": [{"questionId": "pages", "value": "Yeah. about eight pages"}],
                "questions": [{"id": "pages", "text": "How many pages?"}, {"id": "cms", "text": "CMS?"}],
                "form_data": {"projectSummary": "Harbor"},
            },
        ],
        tool_text="Do you need a CMS?",
    )
    buffer: dict[str, str] = {}
    spoken1, tools1 = asyncio.run(
        run_builder_intake_turn(
            client,
            engagement_id="eng-1",
            text="Yeah.",
            is_phone=True,
            answer_buffer=buffer,
        )
    )
    assert tools1 == []
    assert spoken1 == ""

    spoken2, tools2 = asyncio.run(
        run_builder_intake_turn(
            client,
            engagement_id="eng-1",
            text="about eight pages",
            is_phone=True,
            answer_buffer=buffer,
        )
    )
    assert tools2 == ["proposal_answer_question", "proposal_ask_gap"]
    assert "CMS" in spoken2


def test_complete_yeah_does_not_send_proposal() -> None:
    client = _SeqClient(
        [
            {
                "complete": True,
                "gaps": [],
                "sales": {"phase": "review_offered", "confidence": 90},
                "confidence": 90,
                "form_data": {"projectSummary": "Harbor"},
            }
        ]
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="Yeah.", is_phone=True)
    )
    assert "proposal_send" not in tools
    assert "confident" in spoken.lower() or "text or email" in spoken.lower()


def test_complete_email_sends_draft_not_job_id() -> None:
    client = _SeqClient(
        [
            {
                "complete": True,
                "gaps": [],
                "sales": {"phase": "review_offered", "confidence": 90},
                "confidence": 90,
                "form_data": {"projectSummary": "Harbor"},
            }
        ]
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="email it", is_phone=True)
    )
    assert tools == ["proposal_sales_advance", "proposal_send"]
    assert "draft" in spoken.lower()
    assert "job id" not in spoken.lower()


def test_phase2_lock_sends_final() -> None:
    client = _SeqClient(
        [
            {
                "complete": True,
                "gaps": [],
                "sales": {"phase": "budget", "confidence": 90, "budgetBand": "$15,000"},
                "confidence": 90,
                "form_data": {"projectSummary": "Harbor"},
            }
        ]
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="lock it", is_phone=True)
    )
    assert "proposal_sales_advance" in tools
    assert "proposal_send" in tools
    assert "emailed" in spoken.lower()
    assert "text" in spoken.lower()
