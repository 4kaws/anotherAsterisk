"""Token counter — tracks per-step and cumulative token usage to verify O(N) cost."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Pricing per 1M tokens as of 2026-05 (Anthropic claude-sonnet-4-6 defaults)
_PRICE_INPUT = 3.00
_PRICE_OUTPUT = 15.00
_PRICE_CACHE_READ = 0.30   # ~0.1× input
_PRICE_CACHE_WRITE = 3.75  # ~1.25× input


@dataclass
class StepTokens:
    step: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens * _PRICE_INPUT / 1_000_000
            + self.output_tokens * _PRICE_OUTPUT / 1_000_000
            + self.cache_read_tokens * _PRICE_CACHE_READ / 1_000_000
            + self.cache_write_tokens * _PRICE_CACHE_WRITE / 1_000_000
        )

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class TokenCounter:
    """Accumulates token usage across all steps in one task run."""

    steps: list[StepTokens] = field(default_factory=list)

    def record(
        self,
        step: int,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> StepTokens:
        entry = StepTokens(
            step=step,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        self.steps.append(entry)
        logger.info(
            "Step %03d tokens — in: %d  out: %d  cache_read: %d  cache_write: %d  cost: $%.4f",
            step,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_write_tokens,
            entry.cost_usd,
        )
        return entry

    @property
    def total_input(self) -> int:
        return sum(s.input_tokens for s in self.steps)

    @property
    def total_output(self) -> int:
        return sum(s.output_tokens for s in self.steps)

    @property
    def total_cache_read(self) -> int:
        return sum(s.cache_read_tokens for s in self.steps)

    @property
    def total_cost_usd(self) -> float:
        return sum(s.cost_usd for s in self.steps)

    def summary(self) -> str:
        n = len(self.steps)
        naive_cost = sum(
            (s.input_tokens + s.cache_read_tokens + s.cache_write_tokens)
            * _PRICE_INPUT / 1_000_000
            + s.output_tokens * _PRICE_OUTPUT / 1_000_000
            for s in self.steps
        )
        lines = [
            f"Token summary ({n} steps):",
            f"  Total input tokens : {self.total_input:,}",
            f"  Total output tokens: {self.total_output:,}",
            f"  Cache reads        : {self.total_cache_read:,}",
            f"  Actual cost        : ${self.total_cost_usd:.4f}",
            f"  Naive cost (no cache): ${naive_cost:.4f}",
        ]
        if naive_cost > 0:
            savings = (1 - self.total_cost_usd / naive_cost) * 100
            lines.append(f"  Cache savings      : {savings:.1f}%")
        return "\n".join(lines)
