"""Cost accounting with an optional spending threshold.

`None` disables monetary stopping while retaining the call and cost ledger.
A finite threshold stops later calls; in-flight requests can exceed it.

Extracted from `scripts/run_conjecture_demo.py`, where it was written for one
manual run, because a UI that starts agent runs on a button press needs the
same guarantee and must not carry a second, slightly different copy of it.
One implementation, one set of tests, both callers.

**Why the cap is checked before a request, not after.** OpenRouter reports the
cost of each response in `usage.cost`, so the only way to bound spend is to
refuse the *next* call once the total is reached. A budget consulted only
afterwards is not a budget; it is a receipt.

**Why an unpriced response is charged.** A response whose `usage.cost` is
missing is charged `unknown_call_cost` rather than zero. Treating an unpriced
call as free is exactly how a cap quietly stops being one — a provider that
omits the field, or a proxy that strips it, would otherwise grant an unlimited
run.

This wraps a transport rather than living inside `AttestationWorker`, because
`complete()` already accepts a `transport` seam for testing; the cap is the
same kind of thing (something interposed on the one HTTP call) and needs no
core changes to use.
"""
from __future__ import annotations

import json
import threading

from cohort.agents.openrouter import default_transport


class BudgetExceeded(RuntimeError):
    """Raised in place of making a request that would exceed the cap.

    Deliberately not a `CohortError`: this is an operator-set spending limit,
    not one of the design's own rules about evidence, and `errors.py` is
    reserved for the latter.
    """


class BudgetedTransport:
    """Totals reported costs and stops later calls at a configured threshold.

    Thread-safe: the UI runs an agent in a background thread while the request
    thread reads `spent` to report progress, so both the accumulate and the
    check happen under one lock. Without it a concurrent read could observe a
    half-updated total, and two workers sharing one budget could both pass the
    check before either recorded its spend.
    """

    def __init__(
        self, budget_usd: float | None, unknown_call_cost: float = 0.01,
        on_call=None,
    ) -> None:
        if budget_usd is not None and budget_usd <= 0:
            raise ValueError(f"budget must be positive, got {budget_usd}")
        self.budget_usd = budget_usd
        self.unknown_call_cost = unknown_call_cost
        self.spent = 0.0
        self.calls = 0
        self.unpriced_calls = 0
        self._lock = threading.Lock()
        self._on_call = on_call

    @property
    def remaining(self) -> float | None:
        with self._lock:
            return None if self.budget_usd is None else max(0.0, self.budget_usd - self.spent)

    def snapshot(self) -> dict:
        """A consistent view of all counters at once — reading them one at a
        time from another thread could mix values from either side of a
        call."""
        with self._lock:
            return {
                "budget_usd": self.budget_usd,
                "spent_usd": self.spent,
                "remaining_usd": None if self.budget_usd is None else max(0.0, self.budget_usd - self.spent),
                "calls": self.calls,
                "unpriced_calls": self.unpriced_calls,
            }

    def __call__(self, url, headers, body, timeout):
        with self._lock:
            if self.budget_usd is not None and self.spent >= self.budget_usd:
                raise BudgetExceeded(
                    f"stopping before request {self.calls + 1}: ${self.spent:.4f} of "
                    f"${self.budget_usd:.2f} budget already spent"
                )
        status, raw = default_transport(url, headers, body, timeout)
        cost = _reported_cost(raw)
        with self._lock:
            self.calls += 1
            if cost is None:
                self.unpriced_calls += 1
            self.spent += float(cost) if cost is not None else self.unknown_call_cost
            snapshot = {
                "call": self.calls,
                "charged": float(cost) if cost is not None else self.unknown_call_cost,
                "cost_reported": cost is not None,
                "spent": self.spent,
                "budget": self.budget_usd,
            }
        if self._on_call is not None:
            self._on_call(snapshot)
        return status, raw


def _reported_cost(raw: bytes) -> float | None:
    """`usage.cost` if the response carries one, else None. Never raises: a
    body that cannot be parsed here is still a body the caller must handle,
    and turning that into a budget crash would lose the response."""
    try:
        usage = json.loads(raw).get("usage") or {}
        cost = usage.get("cost")
    except (ValueError, AttributeError, TypeError):
        return None
    return None if cost is None else float(cost)
