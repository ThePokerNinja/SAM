from __future__ import annotations

import asyncio

from sam_worker.builder_intake import (
    _closer_discovery_line,
    _reflect_answer,
    classify_close_turn,
    run_builder_intake_turn,
)


class _SeqClient:
    def __init__(self, sync_rows: list[dict], tool_text: str = "Next gap?") -> None:
        self._sync_rows = list(sync_rows)
        self.tools: list[str] = []
        self.last_args: dict = {}
        self.send_args: dict = {}
        self.tool_text = tool_text
        self._sync_idx = 0
        self.pending: dict[str, str] = {}

    async def get_intake_sync(self, engagement_id: str) -> dict:
        row = self._sync_rows[min(self._sync_idx, len(self._sync_rows) - 1)]
        sales = dict(row.get("sales") or {})
        if self.pending:
            sales.update(self.pending)
        return {"ok": True, "engagementId": engagement_id, **row, "sales": sales}

    async def run_tool(self, name: str, args: dict | None = None) -> dict:
        self.tools.append(name)
        self.last_args = dict(args or {})
        if name == "proposal_send":
            self.send_args = dict(args or {})
        if name == "proposal_sales_set_pending":
            self.pending["pendingOffer"] = str((args or {}).get("pendingOffer") or "")
            self.pending["pendingPrompt"] = str((args or {}).get("pendingPrompt") or "")
            return {"ok": True, "sales": self.pending}
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
                    "text": (
                        "I am about 90% confident on the scope. "
                        "I can send the draft by email or text — which do you want?"
                    ),
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
        if name == "proposal_resume":
            row = self._sync_rows[0]
            sales = row.get("sales") or {}
            name = str((row.get("form_data") or {}).get("projectName") or "the job")
            prompt = str(sales.get("pendingPrompt") or "I can send the draft by email or text — which do you want?")
            return {"ok": True, "text": f"We're back on {name}. {prompt}", "sales": sales}
        if name == "proposal_send":
            kind = str((args or {}).get("kind") or "draft")
            return {
                "ok": True,
                "text": "Sent.",
                "kind": kind,
                "body": "Harbor Izakaya — $4,125 (33 hours)\nEngagement eng-1\nOpen: https://start.michaelstewman.com/?e=eng-1",
            }
        return {"ok": True, "text": self.tool_text, "gap": {"questionId": "cms", "field": "discovery", "question": self.tool_text}}


def test_reflect_answer_skips_short_fragments() -> None:
    assert _reflect_answer("Yeah.") == ""
    assert _reflect_answer("Eight pages with menu and reservations").startswith("Got it")


def test_closer_discovery_line_reflects_then_asks() -> None:
    line = _closer_discovery_line("Eight pages with menu", "Do you need a CMS?")
    assert line.startswith("Got it")
    assert "CMS" in line


def test_cost_question_during_discovery_deflects() -> None:
    client = _SeqClient(
        [
            {
                "complete": False,
                "gaps": [{"field": "discovery", "questionId": "pages", "question": "How many pages?"}],
                "focus": {"questionId": "pages"},
                "answers": [],
                "questions": [{"id": "pages", "text": "How many pages?"}],
                "form_data": {"projectSummary": "Harbor"},
            }
        ]
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="How much will this cost?")
    )
    assert tools == []
    assert "real number" in spoken.lower()
    assert "pages" in spoken.lower()


def test_silent_sync_writes_without_speaking() -> None:
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
                "answers": [{"questionId": "pages", "value": "Eight pages with menu"}],
                "questions": [{"id": "pages", "text": "How many pages?"}, {"id": "cms", "text": "CMS?"}],
                "form_data": {"projectSummary": "Harbor"},
            },
        ],
        tool_text="Do you need a CMS?",
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(
            client,
            engagement_id="eng-1",
            text="Eight pages with menu",
            speak=False,
        )
    )
    assert spoken == ""
    assert "proposal_answer_question" in tools


def test_classify_close_turn_paraphrases() -> None:
    assert classify_close_turn("sure", pending_offer="send_final", phase="budget") == "affirm"
    assert classify_close_turn("yeah", pending_offer="", phase="review_offered") == "affirm_no_offer"
    assert classify_close_turn("send it to my inbox", pending_offer="", phase="review_offered") == "choose_email"
    assert classify_close_turn("just text me", pending_offer="", phase="review_offered") == "choose_text"
    assert classify_close_turn("I looked", pending_offer="mark_reviewed", phase="review_sent") == "reviewed"
    assert classify_close_turn("fifteen thousand", pending_offer="", phase="budget") == "budget"
    assert classify_close_turn("what's this cost?", pending_offer="", phase="review_offered") == "cost_question"
    assert classify_close_turn("Continue. Email it.", pending_offer="choose_channel", phase="review_offered") == "choose_email"
    assert classify_close_turn("Continue.", pending_offer="choose_channel", phase="review_offered") == "continue"


def test_silent_complete_continue_returns_pickup() -> None:
    client = _SeqClient(
        [
            {
                "complete": True,
                "gaps": [],
                "sales": {
                    "phase": "review_offered",
                    "pendingOffer": "choose_channel",
                    "pendingPrompt": "I can send the draft by email or text — which do you want?",
                    "confidence": 100,
                },
                "form_data": {"projectName": "Harbor Izakaya"},
            }
        ]
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(
            client,
            engagement_id="eng-1",
            text="Continue.",
            speak=False,
        )
    )
    assert "proposal_resume" in tools
    assert "Harbor" in spoken
    assert "email" in spoken.lower()


def test_choose_text_sends_draft_with_text_channel() -> None:
    client = _SeqClient(
        [
            {
                "complete": True,
                "gaps": [],
                "sales": {
                    "phase": "review_offered",
                    "pendingOffer": "choose_channel",
                    "confidence": 100,
                },
                "form_data": {"projectName": "Harbor Izakaya"},
            }
        ]
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(
            client,
            engagement_id="eng-1",
            text="Just text me.",
            speak=False,
        )
    )
    assert "proposal_sales_advance" in tools
    assert "proposal_send" in tools
    assert client.send_args.get("channel") == "text"
    assert "text" in spoken.lower()


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
    assert "proposal_sales_set_pending" in tools
    assert "proposal_ask_gap" not in tools
    assert "what else should i know" not in spoken.lower()
    assert "email or text" in spoken.lower()


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
                "sales": {
                    "phase": "review_offered",
                    "confidence": 90,
                    "pendingOffer": "choose_channel",
                    "pendingPrompt": "I can send the draft by email or text — which do you want?",
                },
                "confidence": 90,
                "form_data": {"projectSummary": "Harbor"},
            }
        ]
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="Yeah.", is_phone=True)
    )
    assert "proposal_send" not in tools
    assert "email or text" in spoken.lower()


def test_complete_inbox_sends_draft_not_job_id() -> None:
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
        run_builder_intake_turn(
            client, engagement_id="eng-1", text="send it to my inbox", is_phone=True
        )
    )
    assert "proposal_sales_advance" in tools
    assert "proposal_send" in tools
    assert "proposal_sales_set_pending" in tools
    assert "draft" in spoken.lower()
    assert "job id" not in spoken.lower()


def test_complete_sure_after_email_offer_sends_draft() -> None:
    client = _SeqClient(
        [
            {
                "complete": True,
                "gaps": [],
                "sales": {
                    "phase": "review_offered",
                    "confidence": 90,
                    "pendingOffer": "choose_email",
                    "pendingPrompt": "Want me to send the draft by email?",
                },
                "confidence": 90,
                "form_data": {"projectSummary": "Harbor"},
            }
        ]
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="sure", is_phone=True)
    )
    assert "proposal_send" in tools
    assert "draft" in spoken.lower()


def test_phase2_go_ahead_sends_final() -> None:
    client = _SeqClient(
        [
            {
                "complete": True,
                "gaps": [],
                "sales": {
                    "phase": "budget",
                    "confidence": 90,
                    "budgetBand": "$15,000",
                    "pendingOffer": "send_final",
                    "pendingPrompt": "Want me to send the final estimate and text the link?",
                },
                "confidence": 90,
                "form_data": {"projectSummary": "Harbor"},
            }
        ]
    )
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-1", text="go ahead", is_phone=True)
    )
    assert "proposal_sales_advance" in tools
    assert "proposal_send" in tools
    assert "inbox" in spoken.lower()
    assert "text" in spoken.lower()
