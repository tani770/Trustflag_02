from typing import Dict

WEIGHTS = {
    "churn_per_file": 0.25,
    "title_entropy": 0.20,
    "body_length": 0.15,
    "efficiency": 0.40  # 40% weight on algorithmic efficiency
}

def normalize_body_length(length: float) -> float:
    return min(max(length / 200.0, 0.0), 1.0)

def normalize_title_entropy(entropy: float) -> float:
    if entropy <= 1.5:
        return 0.0
    return min((entropy - 1.5) / 2.5, 1.0)

def normalize_churn_per_file(churn: float) -> float:
    if churn <= 1.0:
        return 0.1
    if churn < 10.0:
        return 0.5
    return 1.0

def normalize_efficiency(time_order: float) -> float:
    # O(1) or O(N) -> 1.0 (Optimal)
    # O(N^2) or Hidden O(N^2) -> 0.2 (Heavy Penalty)
    # O(N^3+) or Sleep stall -> 0.0 (Zero score)
    if time_order <= 1.0:
        return 1.0
    elif time_order == 2.0:
        return 0.2
    return 0.0

def calculate_quality_score(signals: Dict[str, float]) -> float:
    norm_body = normalize_body_length(signals.get("body_length", 0.0))
    norm_entropy = normalize_title_entropy(signals.get("title_entropy", 0.0))
    norm_churn = normalize_churn_per_file(signals.get("churn_per_file", 0.0))
    norm_eff = normalize_efficiency(signals.get("time_complexity", 0.0))

    score = (
        norm_body * WEIGHTS["body_length"] +
        norm_entropy * WEIGHTS["title_entropy"] +
        norm_churn * WEIGHTS["churn_per_file"] +
        norm_eff * WEIGHTS["efficiency"]
    )
    return round(score, 4)
