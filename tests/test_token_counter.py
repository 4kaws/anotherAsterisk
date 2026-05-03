"""Unit tests for StepTokens and TokenCounter."""
from __future__ import annotations

import pytest

from asterisk.token_counter import StepTokens, TokenCounter


class TestStepTokens:
    def test_cost_usd_no_cache(self):
        s = StepTokens(step=1, input_tokens=1_000_000, output_tokens=1_000_000)
        # $3.00 input + $15.00 output = $18.00
        assert abs(s.cost_usd - 18.00) < 0.001

    def test_cost_usd_with_cache(self):
        s = StepTokens(
            step=1,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=1_000_000,
            cache_write_tokens=1_000_000,
        )
        # $0.30 cache_read + $3.75 cache_write = $4.05
        assert abs(s.cost_usd - 4.05) < 0.001

    def test_total_tokens(self):
        s = StepTokens(step=1, input_tokens=100, output_tokens=50)
        assert s.total_tokens == 150


class TestTokenCounter:
    def test_empty_counter(self):
        c = TokenCounter()
        assert c.total_input == 0
        assert c.total_output == 0
        assert c.total_cost_usd == 0.0
        assert len(c.steps) == 0

    def test_record_returns_step_tokens(self):
        c = TokenCounter()
        entry = c.record(step=1, input_tokens=100, output_tokens=50)
        assert isinstance(entry, StepTokens)
        assert entry.step == 1
        assert entry.input_tokens == 100

    def test_accumulates_across_steps(self):
        c = TokenCounter()
        c.record(step=1, input_tokens=100, output_tokens=50)
        c.record(step=2, input_tokens=200, output_tokens=80)
        assert c.total_input == 300
        assert c.total_output == 130

    def test_summary_format(self):
        c = TokenCounter()
        c.record(step=1, input_tokens=1000, output_tokens=500, cache_read_tokens=2000)
        text = c.summary()
        assert "1 steps" in text
        assert "Cache savings" in text

    def test_summary_no_division_by_zero_on_empty(self):
        c = TokenCounter()
        text = c.summary()
        assert "0 steps" in text
        assert "Cache savings" not in text  # no savings line when naive_cost == 0

    def test_total_cache_read(self):
        c = TokenCounter()
        c.record(step=1, input_tokens=0, output_tokens=0, cache_read_tokens=500)
        c.record(step=2, input_tokens=0, output_tokens=0, cache_read_tokens=300)
        assert c.total_cache_read == 800
