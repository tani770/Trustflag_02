from typing import Dict

WEIGHTS = {
    "body_length": 0.25,
    "title_entropy": 0.25,
    "churn_per_file": 0.50
}

def normalize_body_length(length: float) -> float:
    # 0 chars -> 0.0, >= 200 chars -> 1.0
    return min(max(length / 200.0, 0.0), 1.0)

def normalize_title_entropy(entropy: float) -> float:
    # Typical English sentence entropy is ~3.0 - 4.5. 
    # <= 1.5 -> 0.0, >= 4.0 -> 1.0
    if entropy <= 1.5:
        return 0.0
    return min((entropy - 1.5) / 2.5, 1.0)

def normalize_churn_per_file(churn: float) -> float:
    # Single-line changes (e.g. whitespace farming) score very low.
    # Healthy churn is between 10 and 150 lines.
    if churn <= 1.0:
        return 0.1
    if churn < 10.0:
        return 0.5
    return 1.0

def calculate_quality_score(signals: Dict[str, float]) -> float:
    norm_body = normalize_body_length(signals.get("body_length", 0.0))
    norm_entropy = normalize_title_entropy(signals.get("title_entropy", 0.0))
    norm_churn = normalize_churn_per_file(signals.get("churn_per_file", 0.0))
    
    score = (
        norm_body * WEIGHTS["body_length"] +
        norm_entropy * WEIGHTS["title_entropy"] +
        norm_churn * WEIGHTS["churn_per_file"]
    )
    return round(score, 4)
