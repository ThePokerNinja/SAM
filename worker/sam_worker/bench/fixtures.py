"""Versioned benchmark fixtures.

These are the reproducible test suites referenced by sam-benchmark-methodology.md sec 5.
Dynamic Rainmaker answers are grounded by the named tool and its captured rm_api response; static
refusal cases carry their exact non-invention requirement. Keeping those contracts in code makes
runs replayable without freezing market data into the fixture.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FIXTURE_VERSION = "1.1.0"


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
    expect_context_reset: bool = False  # after true interrupt, must not assume unheard tail


@dataclass
class DuplexCase:
    """Full-duplex conversational behavior (ChatGPT / GPT-Live style)."""

    id: str
    scenario: str                    # human-readable label
    agent_is_speaking: str           # Samuel mid-utterance (if any)
    user_behavior: str               # pause, backchannel, barge-in, side speech
    must_not_interrupt: bool         # True = agent should keep floor (thinking pause / backchannel)
    must_recover_context: bool = False
    participate_hint: str = ""       # rubric hint for MOS / manual scoring


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
    InterruptionCase(
        "true_redirect",
        "NVDA is setting up with momentum and...",
        "Actually, tell me about AAPL.",
        True,
        expect_context_reset=True,
    ),
    InterruptionCase("decoy_mmhmm", "The regime is risk-on with broad breadth...", "mm-hmm", False),
    InterruptionCase("decoy_cough", "Your top scan today is NVDA...", "[cough]", False),
    InterruptionCase("decoy_yeah", "I queued that idea for you and...", "yeah", False),
    InterruptionCase("decoy_uh_huh", "So breadth is expanding and...", "uh-huh", False),
    InterruptionCase("decoy_right", "The open drive setup looks like...", "right", False),
]

# Duplex arena — thinking pauses, backchannels, side speech, resume tone (GPT-Live / Full Duplex Bench).
DUPLEX_CASES: list[DuplexCase] = [
    DuplexCase(
        "thinking_pause_1_5s",
        "User trails off mid-thought for 1.5s",
        "Take your time — I'm listening.",
        "[1.5s silence while user thinks]",
        must_not_interrupt=True,
        participate_hint="Waits through a short thinking pause without filling silence",
    ),
    DuplexCase(
        "thinking_pause_3s",
        "User trails off mid-thought for 3s",
        "No rush.",
        "[3s silence while user thinks]",
        must_not_interrupt=True,
        participate_hint="Does not jump in during a longer pause",
    ),
    DuplexCase(
        "backchannel_yeah",
        "User says yeah while Samuel speaks",
        "The regime is risk-on with broad participation...",
        "yeah",
        must_not_interrupt=True,
        participate_hint="Treats yeah as backchannel, not a new question",
    ),
    DuplexCase(
        "backchannel_uh_huh",
        "User says uh-huh while Samuel speaks",
        "Your top scan today is setting up with momentum...",
        "uh-huh",
        must_not_interrupt=True,
    ),
    DuplexCase(
        "barge_in_truncate",
        "User redirects mid-brief; Samuel must not assume unheard tail",
        "Starting with NVDA, then AAPL, then MSFT in the brief...",
        "Stop — just NVDA.",
        must_not_interrupt=False,
        must_recover_context=True,
        participate_hint="Next reply addresses NVDA only; no recap of unheard symbols",
    ),
    DuplexCase(
        "side_speech_decoy",
        "User talks to someone else briefly",
        "Pulse is risk-on this morning...",
        "[talking to someone else] one sec honey",
        must_not_interrupt=True,
        participate_hint="Does not treat background side speech as a full turn",
    ),
    DuplexCase(
        "resume_tone",
        "After pause/resume, tone continues prior thread",
        "We were talking about your calendar for Saturday...",
        "resume the conversation",
        must_not_interrupt=False,
        must_recover_context=True,
        participate_hint="Picks up Saturday thread without generic reset greeting",
    ),
    DuplexCase(
        "participate_not_faq",
        "Open-ended chat — participate, do not FAQ-dump",
        "",
        "Tell me something interesting — not about Rainmaker.",
        must_not_interrupt=False,
        participate_hint="Answers with banter/story; not capability brochure",
    ),
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
        "duplex_cases": [c.id for c in DUPLEX_CASES],
        "general_qa_count": len(GENERAL_QA),
    }
