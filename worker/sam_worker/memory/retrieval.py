"""Relevance-plus-recency retrieval with a strict token budget (SAM-041)."""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass

from .episodic import EpisodicMemoryStore
from .profile import ProfileStore, embed_text


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def _tokens(text: str) -> int:
    return max(1, math.ceil(len(text.split()) * 1.3))


def _recency(timestamp: float, *, half_life_days: float = 30.0) -> float:
    age_days = max(0.0, time.time() - timestamp) / 86400.0
    return 0.5 ** (age_days / max(0.1, half_life_days))


@dataclass(frozen=True)
class RetrievedMemory:
    source: str
    text: str
    provenance: str
    score: float
    tokens: int


class MemoryRetriever:
    def __init__(self, episodes: EpisodicMemoryStore, profiles: ProfileStore) -> None:
        self.episodes = episodes
        self.profiles = profiles

    def retrieve(
        self,
        query: str,
        *,
        session_id: str,
        profile_id: str,
        token_budget: int = 600,
    ) -> list[RetrievedMemory]:
        query_vec = embed_text(query)
        candidates: list[RetrievedMemory] = []

        for fact, vector in self.profiles.facts(profile_id):
            semantic = max(0.0, _cosine(query_vec, vector))
            score = 0.70 * semantic + 0.20 * _recency(fact.updated_at) + 0.10 * fact.confidence
            text = f"{fact.key}: {fact.value}"
            candidates.append(
                RetrievedMemory("profile", text, fact.provenance, score, _tokens(text))
            )

        for episode in self.episodes.recent(session_id, limit=80):
            text = episode.summary or episode.content
            semantic = max(0.0, _cosine(query_vec, embed_text(text)))
            score = 0.72 * semantic + 0.28 * _recency(episode.created_at, half_life_days=7.0)
            candidates.append(
                RetrievedMemory("episode", text, episode.provenance, score, _tokens(text))
            )

        chosen: list[RetrievedMemory] = []
        used = 0
        for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
            if candidate.tokens + used > max(1, token_budget):
                continue
            chosen.append(candidate)
            used += candidate.tokens
        return chosen

    async def retrieve_async(
        self,
        query: str,
        *,
        session_id: str,
        profile_id: str,
        token_budget: int = 600,
    ) -> list[RetrievedMemory]:
        return await asyncio.to_thread(
            self.retrieve,
            query,
            session_id=session_id,
            profile_id=profile_id,
            token_budget=token_budget,
        )
