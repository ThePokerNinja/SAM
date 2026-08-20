"""Wave 6 / Moderator / Pythia unit tests."""

from __future__ import annotations

import unittest

from sam_worker.artifacts import Artifact, ArtifactStore
from sam_worker.intake import BriefItem, assemble_brief
from sam_worker.packs.appointment import confirm_booking
from sam_worker.packs.moderator import classify, is_neutral, understanding_map
from sam_worker.packs.registry import PackRegistry
from sam_worker.pythia import BaselineStore, brier, maybe_trigger, predict
from sam_worker.safety import SafetyState
from sam_worker.session import build_session, route_session_kind
from sam_worker.skillbuilder.advisory import run_advisory
from sam_worker.skillbuilder.models import (
    AlignmentInputs,
    ConfidenceInputs,
    ExpectedLift,
    RiskInputs,
    SkillCandidate,
)
from sam_worker.skillbuilder.runtime import SkillBuilderRuntime
from sam_worker.skillbuilder.states import CandidateStatus
from sam_worker.surfaces import surface_for


class SessionTests(unittest.TestCase):
    def test_default_is_trading(self) -> None:
        self.assertEqual(route_session_kind(surface="portal"), "trading")
        s = build_session(session_id="r1", surface="portal")
        self.assertEqual(s.kind, "trading")
        self.assertEqual(s.pack, "trading")

    def test_moderator_keyword(self) -> None:
        self.assertEqual(
            route_session_kind(surface="portal", keyword="moderate this"),
            "moderator",
        )

    def test_phone_surface(self) -> None:
        s = build_session(session_id="call-1", surface="phone", room_name="call-abc")
        self.assertEqual(s.surface, "phone")
        self.assertEqual(surface_for("phone").audio_hz, 8000)

    def test_add_party(self) -> None:
        s = build_session(session_id="m1", surface="portal", keyword="moderate")
        s.add_party("other", "Alex")
        self.assertEqual(len(s.participants), 2)
        self.assertEqual(s.participants[1].role, "party")


class PackTests(unittest.TestCase):
    def test_trading_prewarmed_and_moderator_present(self) -> None:
        reg = PackRegistry()
        self.assertTrue(reg.is_warm("trading"))
        self.assertEqual(reg.get("moderator").id, "moderator")
        self.assertIn("neutrality", reg.get("moderator").safety_rules)
        self.assertIsNone(reg.tools_for("trading", ["get_pulse", "capture_note"]))
        self.assertEqual(reg.tools_for("moderator", ["capture_note", "get_pulse"]), ["capture_note"])


class ModeratorTests(unittest.TestCase):
    def test_spectrum_and_neutrality(self) -> None:
        self.assertEqual(classify("we agree on timing"), "agree")
        self.assertEqual(classify("I will never do that"), "absolutely_wont")
        mmap = understanding_map([("timing", "we agree"), ("money", "I won't")])
        self.assertEqual(mmap["topics"][1]["band"], "wont")
        self.assertTrue(is_neutral("Both of you want the same outcome."))
        self.assertFalse(is_neutral("that's your fault"))


class SafetyTests(unittest.TestCase):
    def test_recording_off_and_pause(self) -> None:
        session = build_session(session_id="s", surface="portal")
        safety = SafetyState()
        self.assertFalse(safety.recording_allowed())
        msg = safety.request_pause(session)
        self.assertTrue(session.paused)
        self.assertIn("pause", msg.lower())


class IntakeArtifactTests(unittest.TestCase):
    def test_brief_skips_no_consent(self) -> None:
        brief = assemble_brief(
            (BriefItem("secret", "web", consent=False), BriefItem("ok", "sms", consent=True))
        )
        self.assertIn("ok", brief.as_prompt())
        self.assertNotIn("secret", brief.as_prompt())

    def test_artifact_roundtrip(self) -> None:
        store = ArtifactStore(":memory:")
        store.add(Artifact(session_id="s1", kind="summary", payload={"text": "hi"}))
        items = store.list_for("s1")
        self.assertEqual(items[0].payload["text"], "hi")


class PythiaTests(unittest.TestCase):
    def test_predict_off_path_and_brier(self) -> None:
        store = BaselineStore()
        store.observe("mood", 1.0)
        store.observe("mood", 1.2)
        f = predict("mood", "1d", {"sleep": 0.4, "load": 0.6}, store)
        self.assertEqual(f.provenance, "pythia.rule.v0")
        self.assertIsNotNone(maybe_trigger(f, ready=False))
        self.assertGreaterEqual(brier([(0.7, 1.0), (0.2, 0.0)]), 0.0)


class AppointmentTests(unittest.TestCase):
    def test_unconfirmed_booking_refused(self) -> None:
        self.assertFalse(confirm_booking({"when": "Tue 3pm"}, spoken_confirm=False)["ok"])
        self.assertTrue(confirm_booking({"when": "Tue 3pm"}, spoken_confirm=True)["ok"])


class AdvisoryTests(unittest.TestCase):
    def test_advisory_never_auto_adopts(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            runtime = SkillBuilderRuntime(Path(raw) / "skills.db")
            candidate = SkillCandidate(
                candidate_id="adv-1",
                skill_name="demo",
                expected_lift=ExpectedLift(0.9, 0.9, 0.9, 0.9, 0.9),
                alignment=AlignmentInputs(0.95, 0.95, 0.95, 0.95, 0.95),
                risk=RiskInputs(0.05, 0.05, 0.05, 0.05, 0.05, 0.05),
                confidence=ConfidenceInputs(0.95, 0.95, 0.95),
                static_urgency=0.9,
                fits_latency_budget=True,
            )
            out = run_advisory(runtime, candidate, reason="gap")
            self.assertEqual(out.status, CandidateStatus.UNDER_REVIEW)
            self.assertEqual(runtime.consent_status("adv-1"), "missing")


if __name__ == "__main__":
    unittest.main()
