"""Versioned benchmark fixtures (scaffold).

These are the reproducible test suites referenced by sam-benchmark-methodology.md sec 5.
Ground-truth answers are intentionally placeholders here; fill them from the prod-session
ground-truth table and real rm_api responses before a scored run. Keeping them in code (not prose)
makes runs replayable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FIXTURE_VERSION = "0.1.0"


@dataclass
class GroundedTask:
    """A task with a knowable correct outcome (the grounded arena)."""

    id: str
    utterance: str
    expected_tool: str | None        # tool that *should* fire, or None
    ground_truth_hint: str           # what a correct answer must reflect
    must_not_invent: list[str] = field(default_factory=list)  # hallucination tripwires


@dataclass
class InterruptionCase:
    """A barge-in test: is this a true interrupt or a backchannel decoy?"""

    id: str
    agent_is_speaking: str           # what Sam is mid-saying
    user_audio: str                  # the overlapping user audio
    is_true_interrupt: bool


# Grounded-task suite -- the arena Samuel must win (ChatGPT voice cannot play).
GROUNDED_TASKS: list[GroundedTask] = [
    GroundedTask(
        id="pulse",
        utterance="Sam, what's the market pulse right now?",
        expected_tool="get_pulse",
        ground_truth_hint="current regime/breadth from rm_api /pulse, not invented",
        must_not_invent=["specific index level not returned by the tool"],
    ),
    GroundedTask(
        id="scans",
        utterance="What are today's top scans?",
        expected_tool="get_scans",
        ground_truth_hint="top symbols + posture from rm_api /scan/latest",
        must_not_invent=["symbols not in the scan response"],
    ),
    GroundedTask(
        id="research_recall",
        utterance="What did I queue in research yesterday?",
        expected_tool="list_research",
        ground_truth_hint="items from research_store; or 'nothing queued'",
        must_not_invent=["fabricated research ideas"],
    ),
    GroundedTask(
        id="pricing_trap",
        utterance="How much does Rainmaker cost per month?",
        expected_tool=None,
        ground_truth_hint="must defer: 'not configured / I can't verify pricing'",
        must_not_invent=["any dollar figure", "any plan tier", "any discount"],
    ),
    GroundedTask(
        id="account_trap",
        utterance="What's my account balance and open P&L?",
        expected_tool="get_trades",
        ground_truth_hint="only what a read-only tool returns; else defer",
        must_not_invent=["a balance number", "a P&L number"],
    ),
]

# Interruption suite -- true barge-ins vs backchannel decoys (general arena).
INTERRUPTIONS: list[InterruptionCase] = [
    InterruptionCase("true_stop", "Here is the full morning brief, starting with...", "Stop, hold on.", True),
    InterruptionCase("true_redirect", "NVDA is setting up with momentum and...", "Actually, tell me about AAPL.", True),
    InterruptionCase("decoy_mmhmm", "The regime is risk-on with broad breadth...", "mm-hmm", False),
    InterruptionCase("decoy_cough", "Your top scan today is NVDA...", "[cough]", False),
    InterruptionCase("decoy_yeah", "I queued that idea for you and...", "yeah", False),
]

# General Q&A -- level playing field (both arms can answer).
GENERAL_QA: list[str] = [
    "Give me a one-sentence summary of what you can help with.",
    "What's a good way to think about risk when trading?",
    "Tell me a quick, encouraging line to start my day.",
]


def fixture_manifest() -> dict:
    return {
        "version": FIXTURE_VERSION,
        "grounded_tasks": [t.id for t in GROUNDED_TASKS],
        "interruptions": [c.id for c in INTERRUPTIONS],
        "general_qa_count": len(GENERAL_QA),
    }
