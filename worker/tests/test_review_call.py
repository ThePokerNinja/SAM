"""Proposal Studio review: Sam reads Charles's staging area, drafts decisions, never commits."""

from __future__ import annotations

import asyncio
import inspect
import unittest
from typing import Any

from sam_worker.outbound import encode_outbound_metadata, decode_outbound_metadata, take_pending_script
from sam_worker.review_call import (
    REVIEW_OPENING_EMPTY,
    REVIEW_OPENING_TAIL,
    is_review_call,
    resolve_outbound_spoken,
    review_opening,
)
from sam_worker.tools.handlers import (
    artifact_kind_from_words,
    handle_draft_decision,
    handle_finish_review,
    handle_get_proposal_artifact,
    handle_list_proposals,
    handle_review_digest,
    handle_review_note,
)
from sam_worker.tools.rainmaker import MockRainmakerClient
from sam_worker.tools.rainmaker_registry import register_rainmaker_tools
from sam_worker.tools.registry import ToolRegistry
from sam_worker.tools.select import REVIEW_TOOLS, is_review_utterance, select_tools_for_utterance


def _identity_decorator(fn):
    return fn


class SpyReviewClient:
    """Records calls and returns rm_api-shaped payloads for the review routes."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.lanes: dict[str, list[dict]] = {
            "staging": [
                {"id": "ab2cd", "title": "Slippage dashboard", "built": 9, "total": 9},
                {"id": "ef3gh", "title": "Night-shift cost cap", "built": 4, "total": 9},
            ],
            "inbox": [],
            "paused": [],
            "accepted": [],
        }
        self.pending: list[dict] = []
        self.finish_payload: dict = {
            "ok": True,
            "changed": True,
            "code": "k7m2p",
            "summary": "Accepted: Slippage dashboard. Rejected: none. Paused: Night-shift cost cap.",
            "smsResult": {"sent": True},
        }

    async def review_digest(self) -> dict:
        self.calls.append(("review_digest", ()))
        return {"ok": True, "text": "Overnight Charles finished the package for Slippage dashboard; it is in staging for you.", "stagedCount": 1}

    async def list_proposals(self, lane: str = "staging") -> dict:
        self.calls.append(("list_proposals", (lane,)))
        return {"ok": True, "proposals": list(self.lanes.get(lane, [])), "counts": {k: len(v) for k, v in self.lanes.items()}}

    async def get_proposal_artifact(self, proposal_id: str, kind: str) -> dict:
        self.calls.append(("get_proposal_artifact", (proposal_id, kind)))
        if kind == "user_feedback":
            return {"ok": False, "error": "http 404"}
        body = "# PRD\n\n## Acceptance criteria\n- Fills show against quotes.\n- **Slippage** per trade is logged.\n\n## KPIs\n1. Median slippage under 5 bps.\n"
        return {"ok": True, "artifact": {"kind": kind, "label": "PRD", "body_md": body}}

    async def review_draft(self, session_id: str, proposal_id: str, decision: str, note: str = "") -> dict:
        self.calls.append(("review_draft", (session_id, proposal_id, decision, note)))
        self.pending.append({"id": proposal_id, "decision": decision})
        return {"ok": True, "drafted": {"id": proposal_id, "decision": decision}, "pending": list(self.pending)}

    async def review_note(self, session_id: str, text: str, proposal_id: str = "") -> dict:
        self.calls.append(("review_note", (session_id, text, proposal_id)))
        return {"ok": True, "notes": 1}

    async def review_finish(self, session_id: str) -> dict:
        self.calls.append(("review_finish", (session_id,)))
        return dict(self.finish_payload)


class ReviewHandlerTests(unittest.TestCase):
    def test_digest_reads_the_text_verbatim(self) -> None:
        spy = SpyReviewClient()
        out = asyncio.run(handle_review_digest(spy))
        self.assertIn("Slippage dashboard", out)
        self.assertEqual(spy.calls, [("review_digest", ())])

    def test_list_names_progress_only_when_incomplete(self) -> None:
        out = asyncio.run(handle_list_proposals(SpyReviewClient(), "staging"))
        self.assertTrue(out.startswith("2 ideas in staging: "))
        self.assertIn("Slippage dashboard;", out)
        self.assertIn("Night-shift cost cap (4 of 9 artifacts)", out)
        self.assertNotIn("9 of 9", out)

    def test_list_empty_lane_points_elsewhere(self) -> None:
        out = asyncio.run(handle_list_proposals(SpyReviewClient(), "inbox"))
        self.assertTrue(out.startswith("Nothing in inbox."))
        self.assertIn("staging 2", out)

    def test_artifact_resolves_title_words_and_flattens_markdown(self) -> None:
        spy = SpyReviewClient()
        out = asyncio.run(handle_get_proposal_artifact(spy, "slippage", "the PRD"))
        self.assertEqual(spy.calls[-1], ("get_proposal_artifact", ("ab2cd", "prd")))
        self.assertTrue(out.startswith("PRD for Slippage dashboard: "))
        self.assertNotIn("#", out)
        self.assertNotIn("**", out)
        self.assertNotIn("- ", out)
        self.assertIn("Acceptance criteria: Fills show against quotes.", out)
        self.assertIn("KPIs: Median slippage under 5 bps.", out)

    def test_artifact_missing_says_not_written_yet(self) -> None:
        out = asyncio.run(handle_get_proposal_artifact(SpyReviewClient(), "cost cap", "user feedback"))
        self.assertEqual(out, "Charles has not written the user feedback for Night-shift cost cap yet.")

    def test_artifact_unknown_proposal(self) -> None:
        out = asyncio.run(handle_get_proposal_artifact(SpyReviewClient(), "unicorn", "brief"))
        self.assertEqual(out, "I couldn't find a proposal matching unicorn.")

    def test_kind_aliases(self) -> None:
        self.assertEqual(artifact_kind_from_words("the PRD"), "prd")
        self.assertEqual(artifact_kind_from_words("Personas"), "personas")
        self.assertEqual(artifact_kind_from_words("competitive analysis"), "competitive_analysis")
        self.assertEqual(artifact_kind_from_words("heuristics"), "heuristic_assessment")
        self.assertEqual(artifact_kind_from_words("acceptance criteria"), "prd")
        self.assertEqual(artifact_kind_from_words("problem statement"), "problem_statement")
        self.assertEqual(artifact_kind_from_words("ux_recommendations"), "ux_recommendations")

    def test_draft_decision_repeats_back_and_says_nothing_moves(self) -> None:
        spy = SpyReviewClient()
        out = asyncio.run(handle_draft_decision(spy, "samuel-dial-1", "slippage", "Accept", note="ship it"))
        self.assertEqual(spy.calls[-1], ("review_draft", ("samuel-dial-1", "ab2cd", "accept", "ship it")))
        self.assertTrue(out.startswith("Noted: accept Slippage dashboard."))
        self.assertIn("Nothing moves until you text YES after the call.", out)
        out2 = asyncio.run(handle_draft_decision(spy, "samuel-dial-1", "cost cap", "pause"))
        self.assertIn("That makes 2 so far.", out2)

    def test_draft_decision_rejects_unknown_verb(self) -> None:
        spy = SpyReviewClient()
        out = asyncio.run(handle_draft_decision(spy, "s", "slippage", "maybe"))
        self.assertEqual(out, "Say accept, reject, pause, or resume.")
        self.assertEqual(spy.calls, [])

    def test_review_note_attaches_to_proposal_when_named(self) -> None:
        spy = SpyReviewClient()
        out = asyncio.run(handle_review_note(spy, "s1", "ask about data retention", proposal="slippage"))
        self.assertEqual(out, "Got it, noted.")
        self.assertEqual(spy.calls[-1], ("review_note", ("s1", "ask about data retention", "ab2cd")))
        out2 = asyncio.run(handle_review_note(spy, "s1", "general thought"))
        self.assertEqual(spy.calls[-1], ("review_note", ("s1", "general thought", "")))
        self.assertEqual(out2, "Got it, noted.")

    def test_finish_review_points_to_the_text(self) -> None:
        spy = SpyReviewClient()
        out = asyncio.run(handle_finish_review(spy, "samuel-dial-1"))
        self.assertIn("Accepted: Slippage dashboard.", out)
        self.assertIn("reply YES with the code to commit it", out)
        self.assertNotIn("k7m2p", out)  # the code travels by SMS, not voice

    def test_finish_review_with_no_decisions(self) -> None:
        spy = SpyReviewClient()
        spy.finish_payload = {"ok": True, "changed": True, "summary": "No decisions were drafted on this call."}
        out = asyncio.run(handle_finish_review(spy, "s"))
        self.assertEqual(out, "No decisions this time, so nothing to confirm. Your notes are saved.")

    def test_mock_client_round_trip(self) -> None:
        client = MockRainmakerClient()
        self.assertIn("staging", asyncio.run(handle_review_digest(client)))
        self.assertIn("Slippage dashboard", asyncio.run(handle_list_proposals(client)))
        self.assertIn("Noted: accept", asyncio.run(handle_draft_decision(client, "s", "ab2cd", "accept")))
        self.assertIn("YES", asyncio.run(handle_finish_review(client, "s")))


class ReviewRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        register_rainmaker_tools(self.registry)

    def test_review_tools_are_owner_gated(self) -> None:
        for name in REVIEW_TOOLS:
            tools = self.registry.build_livekit_tools(
                client=SpyReviewClient(),
                is_owner=lambda: False,
                function_tool=_identity_decorator,
                owner_refusal="owner only",
                only=[name],
            )
            params = list(inspect.signature(tools[0]).parameters)[1:]
            args = ["x"] * sum(1 for p in params if p in {"proposal", "decision", "text"})
            self.assertEqual(asyncio.run(tools[0](None, *args)), "owner only", name)

    def test_draft_decision_uses_room_name_as_review_session(self) -> None:
        spy = SpyReviewClient()
        tools = self.registry.build_livekit_tools(
            client=spy,
            is_owner=lambda: True,
            function_tool=_identity_decorator,
            owner_refusal="owner only",
            deps={"room_name": "samuel-dial-77", "session_id": "ignored"},
            only=["draft_decision", "finish_review"],
        )
        asyncio.run(tools[0](None, "slippage", "reject"))
        asyncio.run(tools[1](None))
        self.assertEqual(spy.calls[-2][1][0], "samuel-dial-77")
        self.assertEqual(spy.calls[-1], ("review_finish", ("samuel-dial-77",)))


class ReviewSelectTests(unittest.TestCase):
    def test_review_words_load_the_pack(self) -> None:
        for utterance in (
            "review",
            "what's Charles working on",
            "read me the PRD for the slippage one",
            "accept that one",
            "let's review his proposals",
            "wrap up",
        ):
            selected = select_tools_for_utterance(utterance)
            for name in REVIEW_TOOLS:
                self.assertIn(name, selected, utterance)

    def test_client_proposal_words_do_not_load_the_pack(self) -> None:
        self.assertFalse(is_review_utterance("draft a proposal for the website job"))
        self.assertFalse(is_review_utterance("send this proposal to Cathy"))
        selected = select_tools_for_utterance("what's the pulse")
        self.assertNotIn("draft_decision", selected)


class DialDryRunTests(unittest.TestCase):
    """The lab proof: a dry run passes the allow-list and trunk checks without a room or a ring."""

    def _env(self, trunk: str) -> dict[str, str]:
        return {
            "SAM_SIP_OUTBOUND_ALLOWED": "+15551212",
            "SAM_SIP_OUTBOUND_TRUNK_ID": trunk,
            "LIVEKIT_URL": "wss://x",
            "LIVEKIT_API_KEY": "k",
            "LIVEKIT_API_SECRET": "s",
        }

    def test_dry_run_reports_configured_without_dialing(self) -> None:
        import os
        from unittest import mock

        from sam_worker.outbound import dial_from_text

        with mock.patch.dict(os.environ, self._env("ST_abc"), clear=False):
            out = asyncio.run(dial_from_text("+15551212", brief="review: lab", spoken="review", dry_run=True))
        self.assertEqual(out, {"ok": True, "dryRun": True, "number": "+15551212", "configured": True})

    def test_dry_run_still_fails_closed(self) -> None:
        import os
        from unittest import mock

        from sam_worker.outbound import dial_from_text

        with mock.patch.dict(os.environ, self._env(""), clear=False):
            out = asyncio.run(dial_from_text("+15551212", dry_run=True))
            self.assertEqual(out, {"ok": False, "error": "outbound_not_configured"})
            out = asyncio.run(dial_from_text("+19995551212", dry_run=True))
            self.assertEqual(out, {"ok": False, "error": "number_not_allowlisted"})


class ReviewLegTests(unittest.TestCase):
    def test_rm_api_dial_metadata_marks_the_leg(self) -> None:
        raw = encode_outbound_metadata(brief="review: Charles finished two packages", spoken="review", notify_owner=False)
        meta = decode_outbound_metadata(raw)
        self.assertTrue(is_review_call(meta))
        self.assertFalse(is_review_call({"brief": "call Cathy about the deck", "spoken": "Hi Cathy"}))
        self.assertFalse(is_review_call(None))

    def test_opening_is_digest_plus_one_question(self) -> None:
        meta = {"brief": "review: Charles finished the package for Slippage dashboard", "spoken": "review"}
        self.assertEqual(
            review_opening(meta),
            f"Charles finished the package for Slippage dashboard. {REVIEW_OPENING_TAIL}",
        )
        self.assertEqual(review_opening({"brief": "review:", "spoken": "review"}), REVIEW_OPENING_EMPTY)

    def test_guest_scripts_pass_through_unchanged(self) -> None:
        self.assertEqual(resolve_outbound_spoken({"brief": "x", "spoken": "Hi Cathy, it's Samuel."}), "Hi Cathy, it's Samuel.")

    def test_opening_is_delivered_on_first_human_speech(self) -> None:
        meta = {"brief": "review: Two packages landed", "spoken": "review"}
        state = {"spoken": resolve_outbound_spoken(meta), "delivered": False}
        self.assertEqual(take_pending_script(state, "Hello?"), f"Two packages landed. {REVIEW_OPENING_TAIL}")
        self.assertIsNone(take_pending_script(state, "ok"))


if __name__ == "__main__":
    unittest.main()
