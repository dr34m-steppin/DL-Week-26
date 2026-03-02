from dataclasses import dataclass


@dataclass
class TopicUpdate:
    attempts: int
    correct: int
    total_response_time_ms: int
    streak_wrong: int
    mastery_score: float
    struggle_score: float
    risk_level: str
    risk_reason: str


def compute_topic_state(
    attempts: int,
    correct: int,
    total_response_time_ms: int,
    streak_wrong: int,
) -> TopicUpdate:
    # Laplace smoothing keeps early-stage estimates stable.
    mastery = (correct + 1) / (attempts + 2)

    avg_response = total_response_time_ms / max(1, attempts)
    speed_penalty = min(1.0, avg_response / 90_000)
    streak_penalty = min(1.0, streak_wrong / 4)
    struggle = min(1.0, 0.55 * (1 - mastery) + 0.25 * speed_penalty + 0.20 * streak_penalty)

    if attempts < 3:
        risk = "LOW"
        reason = "Insufficient data. Continue attempts for reliable risk scoring."
    elif mastery < 0.45:
        risk = "HIGH"
        reason = "Low mastery sustained across multiple attempts."
    elif mastery < 0.60 or struggle > 0.65:
        risk = "MEDIUM"
        reason = "Emerging learning risk based on mastery or struggle indicators."
    else:
        risk = "LOW"
        reason = "Healthy performance trajectory."

    return TopicUpdate(
        attempts=attempts,
        correct=correct,
        total_response_time_ms=total_response_time_ms,
        streak_wrong=streak_wrong,
        mastery_score=round(mastery, 4),
        struggle_score=round(struggle, 4),
        risk_level=risk,
        risk_reason=reason,
    )


def grade_band(score_percent: float) -> str:
    if score_percent >= 85:
        return "A"
    if score_percent >= 75:
        return "B"
    if score_percent >= 65:
        return "C"
    if score_percent >= 50:
        return "D"
    return "F"
