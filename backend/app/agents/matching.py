"""Explainable heuristics; scores are product defaults, not validated predictions."""

import unicodedata

WEIGHTS = {"skills": 0.35, "location": 0.20, "availability": 0.20, "budget": 0.15, "reliability": 0.10}


def normalize(value):
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c)
    ).strip()


def score_worker(task, worker, completed=0, assigned=0, weights=None):
    weights = WEIGHTS if weights is None else weights
    if (
        set(weights) != set(WEIGHTS)
        or any(v < 0 for v in weights.values())
        or abs(sum(weights.values()) - 1) > 0.0001
    ):
        raise ValueError("Weights must use all dimensions and sum to one")
    required = {normalize(s) for s in task.get("required_skills", [])}
    offered = {normalize(s) for s in worker.get("skills", [])}
    skills = len(required & offered) / len(required) if required else 0.5
    if task.get("category") != worker.get("category"):
        skills *= 0.5
    duration = max(task.get("expected_minutes", 60), 1)
    cost = worker.get("hourly_rate", 0) * duration / 60
    same_currency = task.get("currency", "CAD") == worker.get("currency", "CAD")
    budget = min(1, max(0, task.get("budget", 0)) / cost) if cost > 0 and same_currency else 0
    values = {
        "skills": skills,
        "location": float(normalize(task.get("city", "")) == normalize(worker.get("city", ""))),
        "availability": float(worker.get("available", False)),
        "budget": budget,
        "reliability": min(1, max(0, completed) / assigned) if assigned > 0 else 0.5,
    }
    return {
        "score": round(sum(values[k] * weights[k] for k in weights) * 100, 1),
        "dimensions": values,
        "explanations": [
            f"{len(required & offered)} of {len(required)} requested skills matched"
            if required
            else "No specific skills requested",
            "Same city" if values["location"] else "Different city",
            "Available" if values["availability"] else "Currently unavailable",
            "Within budget" if budget == 1 else "Rate or currency does not fully fit the budget",
            f"{completed} completed of {assigned} assigned tasks"
            if assigned
            else "No task history; neutral reliability score",
        ],
    }
