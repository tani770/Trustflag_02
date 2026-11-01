from typing import Dict

def calculate_quality_score(signals: Dict[str, float]) -> float:
    """
    Score is based 100% on functional accuracy.
    No padding from title length, diff churn, or body descriptions.
    """
    accuracy = signals.get("accuracy", 0.0)
    # Strict clamp [0.0, 1.0]
    return round(float(min(max(accuracy, 0.0), 1.0)), 4)
