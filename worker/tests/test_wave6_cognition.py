"""Wave 6 / Moderator / Pythia unit tests."""

from __future__ import annotations

import unittest

from sam_worker.agent import _session_close_summary, _session_decisions
from sam_worker.artifacts import Artifact, ArtifactStore
from sam_worker.intake import BriefItem, assemble_brief, brief_from_artifacts
from sam_worker.packs.appointment import confirm_booking
from sam_worker.packs.moderator import ModeratorRuntime, classify, is_neutral, understanding_map
from sam_worker.packs.registry import PackRegistry
from sam_worker.pythia import (
    BaselineStore,
    ForecastLedger,
    brier,
    maybe_trigger,
    predict,
    predict_threshold_event,
)
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

    def test_spoken_pack_activation_persists_until_explicit_switch(self) -> None:
        session = build_session(session_id="m1", surface="phone")
        self.assertTrue(session.activate_from_utterance("Samuel, moderate this disagreement"))
        self.assertEqual(session.kind, "moderator")
        self.assertEqual(session.pack, "moderator")
        self.assertFalse(session.activate_from_utterance("I want to explain my position"))
        self.assertEqual(session.kind, "moderator")
        self.assertTrue(session.activate_from_utterance("go back to trading mode"))
        self.assertEqual(session.kind, "trading")

    def test_calendar_question_does_not_implicitly_switch_pack(self) -> None:
        session = build_session(session_id="r1", surface="portal")
        self.assertFalse(session.activate_from_utterance("what is on my calendar today?"))
        self.assertEqual(session.kind, "trading")
        self.assertTrue(session.activate_from_utterance("switch to scheduling mode"))
        self.assertEqual(session.kind, "appointment")

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
        self.assertEqual(reg.get("skillbuilder").id, "skillbuilder")
        self.assertIn("neutrality", reg.get("moderator").safety_rules)
        self.assertIsNone(reg.tools_for("trading", ["get_pulse", "capture_note"]))
        self.assertEqual(reg.tools_for("moderator", ["capture_note", "get_pulse"]), ["capture_note"])

    def test_activate_and_unload_track_runtime_pack(self) -> None:
        reg = PackRegistry()
        reg.activate("moderator")
        self.assertEqual(reg.active_id, "moderator")
        flushed: list[str] = []
        reg.unload("moderator", flush=flushed.append)
        self.assertEqual(flushed, ["moderator"])
        self.assertEqual(reg.active_id, "trading")
        self.assertFalse(reg.is_warm("moderator"))

    def test_memory_schema_scopes_guest_away_from_owner(self) -> None:
        reg = PackRegistry()
        self.assertEqual(reg.memory_scope("trading")["profile_id"], "owner")
        self.assertTrue(reg.memory_scope("trading")["include_owner_remote"])
        intake = reg.memory_scope("intake")
        # Owner-gated proposal builder reads owner thread memory (Phase 5.0).
        self.assertEqual(intake["schema"], "owner")
        self.assertTrue(intake["include_owner_remote"])
        skill = reg.memory_scope("skillbuilder")
        self.assertEqual(skill["profile_id"], "skill_snapshot")
        self.assertFalse(skill["include_owner_remote"])


class ModeratorTests(unittest.TestCase):
    def test_spectrum_and_neutrality(self) -> None:
        self.assertEqual(classify("we agree on timing"), "agree")
        self.assertEqual(classify("I will never do that"), "absolutely_wont")
        mmap = understanding_map([("timing", "we agree"), ("money", "I won't")])
        self.assertEqual(mmap["topics"][1]["band"], "wont")
        self.assertTrue(is_neutral("Both of you want the same outcome."))
        self.assertFalse(is_neutral("that's your fault"))

    def test_runtime_preserves_speaker_attribution(self) -> None:
        runtime = ModeratorRuntime()
        runtime.observe("alex", "I agree on timing.")
        runtime.observe("jordan", "I will not change the budget.")
        artifact = runtime.understanding_artifact()
        self.assertEqual(artifact["topics"][0]["speaker_id"], "alex")
        self.assertEqual(artifact["topics"][0]["band"], "agree")
        self.assertEqual(artifact["topics"][1]["speaker_id"], "jordan")
        self.assertEqual(artifact["topics"][1]["band"], "wont")
        self.assertEqual(len(runtime.next_steps_artifact()["items"]), 1)


class SafetyTests(unittest.TestCase):
    def test_recording_off_and_pause(self) -> None:
        session = build_session(session_id="s", surface="portal")
        safety = SafetyState()
        self.assertFalse(safety.recording_allowed())
        msg = safety.request_pause(session)
        self.assertTrue(session.paused)
        self.assertIn("pause", msg.lower())
        session.resume()
        self.assertFalse(session.paused)


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

    def test_artifact_checkpoint_replaces_same_session_kind(self) -> None:
        store = ArtifactStore(":memory:")
        first_id = store.put(
            Artifact(session_id="s1", kind="summary", payload={"text": "first"})
        )
        second_id = store.put(
            Artifact(session_id="s1", kind="summary", payload={"text": "second"})
        )
        self.assertEqual(second_id, first_id)
        items = store.list_for("s1")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].payload["text"], "second")

    def test_session_close_summary_preserves_decisions(self) -> None:
        turns = [
            ("user", "We agreed to meet Tuesday."),
            ("assistant", "I will capture that."),
        ]
        self.assertIn("meet Tuesday", _session_close_summary(turns))
        self.assertEqual(_session_decisions(turns), ("We agreed to meet Tuesday.",))

    def test_prior_artifact_seeds_next_brief_with_provenance(self) -> None:
        store = ArtifactStore(":memory:")
        artifact_id = store.add(
            Artifact(session_id="prior", kind="summary", payload={"text": "Agreed Tuesday."})
        )
        store.add(Artifact(session_id="current", kind="summary", payload={"text": "Exclude me."}))
        prior = store.recent(limit=8, exclude_session_id="current")
        rendered = brief_from_artifacts(prior).as_prompt()
        self.assertIn("Agreed Tuesday", rendered)
        self.assertIn(f"artifact:{artifact_id}", rendered)
        self.assertNotIn("Exclude me", rendered)


class PythiaTests(unittest.TestCase):
    def test_predict_off_path_and_brier(self) -> None:
        store = BaselineStore()
        store.observe("mood", 1.0)
        store.observe("mood", 1.2)
        f = predict("mood", "1d", {"sleep": 0.4, "load": 0.6}, store)
        self.assertEqual(f.provenance, "pythia.rule.v0")
        self.assertIsNotNone(maybe_trigger(f, ready=False))
        self.assertGreaterEqual(brier([(0.7, 1.0), (0.2, 0.0)]), 0.0)

    def test_durable_baselines_and_calibration(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            path = Path(raw) / "pythia.db"
            baselines = BaselineStore(path)
            baselines.observe("latency", 500)
            baselines.observe("latency", 700)
            self.assertNotEqual(BaselineStore(path).zscore("latency", 900), 0.0)

            ledger = ForecastLedger(path)
            forecast = predict_threshold_event(
                "latency_over_800",
                "next_turn",
                last_value=1000,
                threshold=800,
                scale=200,
            )
            forecast_id = ledger.record(forecast)
            ledger.resolve(forecast_id, 1.0)
            count, score = ledger.calibration("latency_over_800")
            self.assertEqual(count, 1)
            self.assertIsNotNone(score)


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
