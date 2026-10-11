import asyncio
import sys
from pathlib import Path

import pytest

from swarm.toolreg import McpServer, ToolRegistry, parse_date, t_age_on, t_calc, t_date_add, t_date_diff, t_unit_convert

HERE = Path(__file__).parent


def test_calc_exact_and_safe():
    assert t_calc("59 + 76 - 35").endswith("= 100")
    assert t_calc("(1,234 + 66) * 2").endswith("= 2600")
    assert t_calc("10 / 4").endswith("= 2.5")
    assert t_calc("2^10").endswith("= 1024")
    assert t_calc("sqrt(144) + abs(-3)").endswith("= 15")
    for bad in ("__import__('os').system('x')", "open('f')", "1 + a", "9**9**9", "[1,2]"):
        with pytest.raises(Exception):
            t_calc(bad)


def test_dates():
    assert str(parse_date("August 1, 2024")) == "2024-08-01"
    assert str(parse_date("1 Aug 2024")) == "2024-08-01"
    assert str(parse_date("1st August 2024")) == "2024-08-01"
    assert str(parse_date("2024")) == "2024-01-01"
    r = t_date_diff("1990-02-14", "2024-08-01")
    assert "34 years, 5 months, 18 days" in r and "12587 days" in r
    assert "61 years" in t_age_on("1963-01-10", "August 1, 2024")
    assert "= 2024-04-28" in t_date_add("2024-02-29", days=30, months=1)
    assert t_date_add("2024-01-31", months=1).split("=")[1].strip().startswith("2024-02-29")
    with pytest.raises(ValueError):
        parse_date("sometime soon")


def test_units():
    assert "6.2137" in t_unit_convert(10, "km", "mi")
    assert "212" in t_unit_convert(100, "c", "f")
    with pytest.raises(ValueError):
        t_unit_convert(1, "kg", "km")


@pytest.mark.asyncio
async def test_registry_returns_data_not_exceptions():
    reg = ToolRegistry(enabled=["calc", "date_diff"])
    ok = await reg.call("calc", {"expression": "2+2"})
    assert ok["ok"] and ok["result"].endswith("= 4")
    assert not (await reg.call("age_on", {"birth": "x", "on": "y"}))["ok"]          # not enabled
    assert "missing" in (await reg.call("calc", {}))["error"]
    bad = await reg.call("calc", {"expression": "import os"})
    assert not bad["ok"] and bad["error"]
    assert len(reg.log) == 4
    assert "calc(expression" in reg.menu() and "age_on" not in reg.menu()


@pytest.mark.asyncio
async def test_mcp_server_tools_and_failures():
    reg = ToolRegistry(mcp_specs={"echo": {"command": sys.executable, "args": [str(HERE / "echo_mcp_server.py")],
                                           "prefix": "echo_", "timeout": 20}})
    try:
        await reg.start()
        assert not reg.mcp["echo"].error, reg.mcp["echo"].error
        assert {"echo_shout", "echo_add", "echo_boom"} <= set(reg.names())
        r = await reg.call("echo_shout", {"text": "hi"}, timeout=20)
        assert r["ok"] and "HI" in r["result"]
        r = await reg.call("echo_add", {"a": 2, "b": 3}, timeout=20)
        assert r["ok"] and "5" in r["result"]
        r = await reg.call("echo_boom", {}, timeout=20)
        assert not r["ok"]
        # the session survives an error and a forced restart
        await reg.mcp["echo"].close()
        r = await reg.call("echo_shout", {"text": "again"}, timeout=30)
        assert r["ok"] and "AGAIN" in r["result"]
    finally:
        await reg.close()
