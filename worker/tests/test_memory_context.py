from __future__ import annotations

import asyncio
import time

import pytest

from sam_worker.context import assemble_context
from sam_worker.memory import (
    Episode,
    EpisodicMemoryStore,
    MemoryRetriever,
    ProfileFact,
    ProfileStore,
    extract_explicit_profile_update,
)


def test_episode_persists_across_store_instances(tmp_path) -> None:
    path = tmp_path / "memory.db"
    first = EpisodicMemoryStore(path)
    row_id = first.append(
        Episode(
            session_id="room-1",
            kind="message",
            content="Michael decided to review NVDA tomorrow.",
            decisions=("review NVDA",),
            artifact_refs=("note:1",),
        )
    )
    rows = EpisodicMemoryStore(path).recent("room-1")
    assert rows[0].id == row_id
    assert rows[0].decisions == ("review NVDA",)
    assert rows[0].artifact_refs == ("note:1",)


def test_memory_writes_have_async_boundary(tmp_path) -> None:
    store = EpisodicMemoryStore(tmp_path / "memory.db")
    row_id = asyncio.run(store.append_async(Episode("room-1", "message", "Remember this")))
    assert row_id > 0


def test_profile_requires_provenance_and_owner_correction_identity(tmp_path) -> None:
    store = ProfileStore(tmp_path / "memory.db")
    store.upsert(ProfileFact("owner", "preferred_symbol", "NVDA", "session:room-1"))
    with pytest.raises(ValueError):
        store.upsert(
            ProfileFact("owner", "preferred_symbol", "AAPL", "owner_correction"),
            owner_correction=True,
        )
    store.upsert(
        ProfileFact(
            "owner",
            "preferred_symbol",
            "AAPL",
            "owner_correction",
            corrected_by="owner",
        ),
        owner_correction=True,
    )
    facts = store.facts("owner")
    assert facts[0][0].value == "AAPL"
    assert facts[0][0].corrected_by == "owner"


def test_profile_updates_require_explicit_remember_language() -> None:
    assert extract_explicit_profile_update("My favorite color is blue") is None
    update = extract_explicit_profile_update("Remember that my favorite color is blue.")
    assert update is not None
    assert update.key == "favorite_color"
    assert update.value == "blue"
    correction = extract_explicit_profile_update(
        "Actually, remember that my favorite color is green."
    )
    assert correction is not None
    assert correction.owner_correction


def test_retrieval_prefers_relevance_and_respects_budget(tmp_path) -> None:
    path = tmp_path / "memory.db"
    episodes = EpisodicMemoryStore(path)
    profiles = ProfileStore(path)
    profiles.upsert(ProfileFact("owner", "favorite_market", "semiconductor stocks", "test"))
    profiles.upsert(ProfileFact("owner", "timezone", "Pacific", "test"))
    episodes.append(Episode("room-1", "message", "We discussed NVDA semiconductor momentum."))
    result = MemoryRetriever(episodes, profiles).retrieve(
        "What semiconductor stocks did we discuss?",
        session_id="room-1",
        profile_id="owner",
        token_budget=12,
    )
    assert result
    assert sum(row.tokens for row in result) <= 12
    assert "semiconductor" in result[0].text.lower()


def test_retrieval_includes_cross_session_profile_episodes(tmp_path) -> None:
    path = tmp_path / "memory.db"
    episodes = EpisodicMemoryStore(path)
    profiles = ProfileStore(path)
    episodes.append(
        Episode(
            "room-yesterday",
            "summary",
            "We scoped a dental clinic website.",
            summary="We scoped a dental clinic website.",
            profile_id="owner",
            created_at=time.time() - 86400,
        )
    )
    episodes.append(
        Episode(
            "room-today",
            "message",
            "Let's continue the estimate.",
            profile_id="owner",
        )
    )
    result = MemoryRetriever(episodes, profiles).retrieve(
        "dental clinic website",
        session_id="room-today",
        profile_id="owner",
        token_budget=80,
    )
    sources = {row.source for row in result}
    assert "episode_cross_session" in sources


def test_context_providers_run_concurrently_and_degrade() -> None:
    async def slow(value):
        await asyncio.sleep(0.04)
        return value

    async def broken():
        await asyncio.sleep(0.01)
        raise RuntimeError("sensitive detail")

    async def run():
        started = time.perf_counter()
        snapshot = await assemble_context(
            memory=lambda: slow(["memory"]),
            profile=lambda: slow({"name": "owner"}),
            tools=lambda: slow(["get_pulse"]),
            permissions=broken,
            timeout_s=0.2,
        )
        return snapshot, time.perf_counter() - started

    snapshot, elapsed = asyncio.run(run())
    assert elapsed < 0.11
    assert snapshot.memory == ["memory"]
    assert snapshot.tools == ["get_pulse"]
    assert snapshot.errors == {"permissions": "RuntimeError"}


def test_context_timeout_returns_partial_snapshot() -> None:
    async def never():
        await asyncio.sleep(0.2)

    snapshot = asyncio.run(
        assemble_context(
            memory=lambda: ["ready"],
            profile=never,
            tools=lambda: [],
            permissions=lambda: {"owner": True},
            timeout_s=0.02,
        )
    )
    assert snapshot.memory == ["ready"]
    assert snapshot.errors["profile"] == "TimeoutError"
