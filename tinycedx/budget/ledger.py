from __future__ import annotations


class BudgetExceeded(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class RecordLedger:
    def __init__(self, *, max_cost_usd: float):
        self.max_cost_usd = max_cost_usd
        self.spent_usd = 0.0
        self.steps = 0

    def would_fit(self, projected_cost_usd: float) -> bool:
        return self.spent_usd + projected_cost_usd <= self.max_cost_usd

    def record_step(self, cost_usd: float) -> None:
        self.steps += 1
        self.spent_usd += cost_usd
        if self.spent_usd > self.max_cost_usd:
            raise BudgetExceeded(
                f"spent ${self.spent_usd:.6f} exceeds MAX_COST_USD_PER_RECORD=${self.max_cost_usd:.6f}"
            )
