"""Tool registry: built-in tools (exact arithmetic, dates, units) and generic MCP servers behind one interface.

Every call returns data, never raises: {"ok": bool, "result": str, "error": str, "seconds": float}.
Results are short plain text so small models can read them.
"""
from __future__ import annotations

import ast
import asyncio
import contextlib
import math
import operator
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable

MAX_RESULT_CHARS = 1200


# ---------------------------------------------------------------- built-in tools

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"abs": abs, "round": round, "min": min, "max": max, "sqrt": math.sqrt, "floor": math.floor,
          "ceil": math.ceil, "log": math.log, "log10": math.log10, "sum": lambda *a: sum(a)}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        a, b = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(b) > 1000 or abs(a) > 1e12):
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](a, b)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("only numbers, + - * / // % **, parentheses, and abs/round/min/max/sqrt/floor/ceil/log/log10/sum are allowed")


def _clean_expr(expr: str) -> str:
    s = str(expr).strip().rstrip("=").replace("×", "*").replace("÷", "/").replace("−", "-").replace("^", "**")
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)   # thousands separators
    s = re.sub(r"(\d)\s*%", r"(\1/100)", s)
    return s


def _fmt_num(x) -> str:
    if isinstance(x, float):
        if x.is_integer() and abs(x) < 1e15:
            return str(int(x))
        return f"{x:.10g}"
    return str(x)


def t_calc(expression: str) -> str:
    s = _clean_expr(expression)
    val = _eval(ast.parse(s, mode="eval"))
    return f"{expression.strip()} = {_fmt_num(val)}"


_DATE_FORMATS = ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y", "%B %d %Y", "%b %d %Y",
                 "%Y/%m/%d", "%B %Y", "%b %Y", "%Y"]


def parse_date(s: str) -> date:
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", str(s).strip().replace(".", ""))
    t = re.sub(r"\s+", " ", t)
    for f in _DATE_FORMATS:
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            continue
    try:
        from dateutil import parser as _p
        return _p.parse(t, default=datetime(2000, 1, 1)).date()
    except Exception:
        raise ValueError(f"could not read the date '{s}' (use e.g. 2024-08-01 or August 1, 2024)")


def _ymd(a: date, b: date) -> tuple[int, int, int]:
    """Whole years, months, days from a to b (a <= b)."""
    y = b.year - a.year
    m = b.month - a.month
    d = b.day - a.day
    if d < 0:
        m -= 1
        prev_month_end = b.replace(day=1) - timedelta(days=1)
        d += prev_month_end.day
    if m < 0:
        y -= 1
        m += 12
    return y, m, d


def t_date_diff(start: str, end: str) -> str:
    a, b = parse_date(start), parse_date(end)
    sign = ""
    if a > b:
        a, b, sign = b, a, "(start is after end) "
    y, m, d = _ymd(a, b)
    days = (b - a).days
    return (f"{sign}from {a.isoformat()} to {b.isoformat()}: {y} years, {m} months, {d} days; "
            f"total {days} days = {days / 7:.2f} weeks; whole months {y * 12 + m}")


def t_age_on(birth: str, on: str) -> str:
    a, b = parse_date(birth), parse_date(on)
    if a > b:
        return f"born {a.isoformat()} is after {b.isoformat()}: not born yet"
    y, m, d = _ymd(a, b)
    return f"born {a.isoformat()}, on {b.isoformat()} the age is {y} years ({y} full years, plus {m} months and {d} days)"


def t_date_add(date_: str, days: int = 0, months: int = 0, years: int = 0) -> str:
    d0 = parse_date(date_)
    total_m = d0.month - 1 + int(months) + 12 * int(years)
    y, m = d0.year + total_m // 12, total_m % 12 + 1
    day = min(d0.day, [31, 29 if (y % 4 == 0 and (y % 100 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    d1 = date(y, m, day) + timedelta(days=int(days))
    return f"{d0.isoformat()} + {years} years, {months} months, {days} days = {d1.isoformat()} ({d1.strftime('%A')})"


def t_weekday(date_: str) -> str:
    d0 = parse_date(date_)
    return f"{d0.isoformat()} is a {d0.strftime('%A')}"


_UNITS = {  # to a base unit per kind
    "length": {"m": 1.0, "meter": 1.0, "meters": 1.0, "km": 1000.0, "kilometer": 1000.0, "kilometers": 1000.0,
               "cm": 0.01, "mm": 0.001, "mi": 1609.344, "mile": 1609.344, "miles": 1609.344, "ft": 0.3048,
               "foot": 0.3048, "feet": 0.3048, "in": 0.0254, "inch": 0.0254, "inches": 0.0254, "yd": 0.9144,
               "yard": 0.9144, "yards": 0.9144, "nmi": 1852.0},
    "mass": {"kg": 1.0, "g": 0.001, "mg": 1e-6, "lb": 0.45359237, "lbs": 0.45359237, "pound": 0.45359237,
             "pounds": 0.45359237, "oz": 0.028349523125, "ounce": 0.028349523125, "tonne": 1000.0, "ton": 907.18474},
    "volume": {"l": 1.0, "liter": 1.0, "liters": 1.0, "ml": 0.001, "gal": 3.785411784, "gallon": 3.785411784,
               "gallons": 3.785411784, "qt": 0.946352946, "pt": 0.473176473, "cup": 0.2365882365,
               "floz": 0.0295735295625},
    "time": {"s": 1.0, "sec": 1.0, "min": 60.0, "h": 3600.0, "hr": 3600.0, "hour": 3600.0, "hours": 3600.0,
             "day": 86400.0, "days": 86400.0, "week": 604800.0, "weeks": 604800.0, "year": 31557600.0,
             "years": 31557600.0},
    "speed": {"mps": 1.0, "kph": 1 / 3.6, "kmh": 1 / 3.6, "mph": 0.44704, "knot": 0.514444, "knots": 0.514444},
}


def t_unit_convert(value: float, from_unit: str, to_unit: str) -> str:
    v = float(value)
    f, t = from_unit.strip().lower(), to_unit.strip().lower()
    temps = {"c": "c", "celsius": "c", "f": "f", "fahrenheit": "f", "k": "k", "kelvin": "k"}
    if f in temps and t in temps:
        a, b = temps[f], temps[t]
        c = v if a == "c" else (v - 32) * 5 / 9 if a == "f" else v - 273.15
        out = c if b == "c" else c * 9 / 5 + 32 if b == "f" else c + 273.15
        return f"{_fmt_num(v)} {from_unit} = {out:.6g} {to_unit}"
    for kind, table in _UNITS.items():
        if f in table and t in table:
            out = v * table[f] / table[t]
            return f"{_fmt_num(v)} {from_unit} = {out:.8g} {to_unit}"
    raise ValueError(f"cannot convert {from_unit} to {to_unit} (same kind of unit needed)")


# ---------------------------------------------------------------- registry

@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, str]              # arg name -> short type/help, e.g. {"expression": "string"}
    required: list[str]
    fn: Callable[..., Any]
    kind: str = "builtin"               # builtin | mcp
    schema: dict = field(default_factory=dict)   # full JSON schema for MCP tools (validation)

    def line(self) -> str:
        args = ", ".join(f"{k}: {v}" for k, v in self.params.items())
        return f"{self.name}({args}) - {self.description}"


def builtin_tools() -> dict[str, Tool]:
    T = [
        Tool("calc", "exact arithmetic; only numbers and + - * / // % ** ( ) abs round min max sqrt",
             {"expression": "string, e.g. 59 + 76 - 35"}, ["expression"], t_calc),
        Tool("date_diff", "years, months, days and total days between two dates",
             {"start": "date, e.g. 1988-04-02", "end": "date, e.g. 'August 1, 2024'"}, ["start", "end"], t_date_diff),
        Tool("age_on", "a person's age on a given date",
             {"birth": "date", "on": "date"}, ["birth", "on"], t_age_on),
        Tool("date_add", "a date plus some years, months and days",
             {"date_": "date", "days": "int", "months": "int", "years": "int"}, ["date_"], t_date_add),
        Tool("weekday", "the weekday of a date", {"date_": "date"}, ["date_"], t_weekday),
        Tool("unit_convert", "convert length, mass, volume, time, speed or temperature units",
             {"value": "number", "from_unit": "string, e.g. km", "to_unit": "string, e.g. mi"},
             ["value", "from_unit", "to_unit"], t_unit_convert),
    ]
    return {t.name: t for t in T}


def _trim(s: str) -> str:
    s = str(s)
    return s if len(s) <= MAX_RESULT_CHARS else s[:MAX_RESULT_CHARS] + " ...(cut)"


class ToolRegistry:
    """Built-in tools plus optional MCP servers. `enabled` limits which tools a model may see."""

    def __init__(self, enabled: list[str] | None = None, mcp_specs: dict | None = None):
        self.tools: dict[str, Tool] = builtin_tools()
        self.mcp: dict[str, McpServer] = {}
        for name, spec in (mcp_specs or {}).items():
            self.mcp[name] = McpServer(name, **spec)
        self.enabled = enabled
        self.log: list[dict] = []

    async def start(self) -> None:
        """Start MCP servers and add their tools. A server that fails to start is reported, not fatal."""
        for name, srv in self.mcp.items():
            try:
                for t in await srv.start():
                    self.tools[t.name] = t
            except Exception as e:
                srv.error = f"{type(e).__name__}: {e}"

    async def close(self) -> None:
        for srv in self.mcp.values():
            with contextlib.suppress(Exception):
                await srv.close()

    def names(self) -> list[str]:
        return [n for n in self.tools if self.enabled is None or n in self.enabled]

    def menu(self) -> str:
        return "\n".join(f"- {self.tools[n].line()}" for n in self.names())

    async def call(self, name: str, args: dict | None, timeout: float = 20.0) -> dict:
        t0 = time.time()
        args = args if isinstance(args, dict) else {}
        out: dict
        tool = self.tools.get(name)
        if tool is None or name not in self.names():
            out = {"ok": False, "result": "", "error": f"unknown tool '{name}'. Tools: {', '.join(self.names())}"}
        else:
            missing = [r for r in tool.required if r not in args or args[r] in (None, "")]
            if missing:
                out = {"ok": False, "result": "", "error": f"missing argument(s): {', '.join(missing)}"}
            else:
                try:
                    clean = {k: v for k, v in args.items() if k in tool.params or tool.kind == "mcp"}
                    if tool.kind == "builtin":
                        res = tool.fn(**{k: _coerce(tool.params.get(k, ""), v) for k, v in clean.items()})
                        if asyncio.iscoroutine(res):
                            res = await res
                    else:
                        res = await asyncio.wait_for(tool.fn(clean), timeout)
                    out = {"ok": True, "result": _trim(res), "error": ""}
                except asyncio.TimeoutError:
                    out = {"ok": False, "result": "", "error": f"timed out after {timeout:.0f}s"}
                except Exception as e:
                    out = {"ok": False, "result": "", "error": _trim(f"{type(e).__name__}: {e}")}
        out["seconds"] = round(time.time() - t0, 3)
        out["tool"], out["args"] = name, args
        self.log.append(out)
        return out


def _coerce(hint: str, v):
    if hint.startswith("int"):
        return int(float(v))
    if hint.startswith("number"):
        return float(v)
    return v if not isinstance(v, (int, float)) else str(v)


# ---------------------------------------------------------------- generic MCP client

class McpServer:
    """One stdio MCP server. Starts lazily on first use, restarts once if its session dies."""

    def __init__(self, name: str, command: str | None = None, args: list[str] | None = None, cwd: str | None = None,
                 env: dict | None = None, tools: list[str] | None = None, prefix: str = "", timeout: float = 30.0):
        self.name, self.command, self.args, self.cwd = name, command or sys.executable, args or [], cwd
        self.env, self.only, self.prefix, self.timeout = env or {}, tools, prefix, timeout
        self.error = ""
        self._stack: contextlib.AsyncExitStack | None = None
        self._session = None
        self._lock = asyncio.Lock()
        self._specs: list[Tool] = []

    async def _open(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import get_default_environment, stdio_client
        env = get_default_environment()
        env.update({"PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1", **self.env})
        params = StdioServerParameters(command=self.command, args=self.args, cwd=self.cwd, env=env)
        self._stack = contextlib.AsyncExitStack()
        try:
            read, write = await self._stack.enter_async_context(stdio_client(params))
            self._session = await self._stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(self._session.initialize(), 60)
        except BaseException:
            await self.close()
            raise

    async def start(self) -> list[Tool]:
        await self._open()
        listed = await asyncio.wait_for(self._session.list_tools(), 30)
        out = []
        for t in listed.tools:
            if self.only is not None and t.name not in self.only:
                continue
            props = (t.inputSchema or {}).get("properties", {}) or {}
            params = {k: str(v.get("type", "any")) for k, v in props.items()}
            req = list((t.inputSchema or {}).get("required", []) or [])
            name = self.prefix + t.name
            out.append(Tool(name, (t.description or "").strip().split("\n")[0][:160], params, req,
                            self._caller(t.name), kind="mcp", schema=t.inputSchema or {}))
        self._specs = out
        return out

    def _caller(self, tool_name: str):
        async def call(args: dict):
            async with self._lock:
                for attempt in (0, 1):
                    try:
                        if self._session is None:
                            await self._open()
                        res = await self._session.call_tool(tool_name, args)
                        break
                    except Exception:
                        await self.close()
                        if attempt:
                            raise
                if getattr(res, "isError", False):
                    raise RuntimeError(_text(res) or "tool error")
                sc = getattr(res, "structuredContent", None)
                if sc:
                    import json
                    return json.dumps(sc.get("result", sc) if isinstance(sc, dict) else sc, ensure_ascii=False)
                return _text(res)
        return call

    async def close(self) -> None:
        stack, self._stack, self._session = self._stack, None, None
        if stack is not None:
            with contextlib.suppress(BaseException):
                await stack.aclose()


def _text(res) -> str:
    parts = []
    for c in getattr(res, "content", []) or []:
        t = getattr(c, "text", None)
        if t:
            parts.append(t)
    return "\n".join(parts)
