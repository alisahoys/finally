"""Tests for the pure helpers and headless run of market_data_demo.py."""

import asyncio
from collections import deque

from rich.console import Console

import market_data_demo as demo


def test_sparkline_short_input_is_empty():
    assert demo.sparkline([]) == ""
    assert demo.sparkline([1.0]) == ""


def test_sparkline_flat_uses_mid_char():
    assert demo.sparkline([5, 5, 5]) == demo.SPARK_CHARS[3] * 3


def test_sparkline_rises_from_low_to_high():
    out = demo.sparkline([1, 2, 3, 4])
    assert out[0] == demo.SPARK_CHARS[0]
    assert out[-1] == demo.SPARK_CHARS[-1]


def test_format_price():
    assert demo.format_price(12.345) == "12.35" or demo.format_price(12.345) == "12.34"
    assert demo.format_price(1234.5) == "1,234.50"


def test_event_log_renders_markup_not_literal_tags():
    events = deque(["[bold green]▲ AAPL[/]  +1.20%"])
    console = Console(record=True, width=60)
    console.print(demo.build_event_log(events))
    out = console.export_text()
    assert "▲ AAPL" in out
    assert "[bold green]" not in out


async def test_headless_run_prints_summary(capsys):
    await asyncio.wait_for(demo.run(duration=1, screen=False), timeout=10)
    out = capsys.readouterr().out
    assert "Session Summary" in out
    assert "AAPL" in out
