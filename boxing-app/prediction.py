"""Fightbase illustrative probability models; not calibrated boxing odds."""

def calculate_score(boxer):
    wins = max(0, int(boxer["wins"]))
    losses = max(0, int(boxer["losses"]))
    score = 50 + (20 if wins > 10 else 10 if wins > 5 else 0)
    score -= min(20, 2 * losses)
    age = boxer.get("age")
    if age is not None and (int(age) < 22 or int(age) > 35):
        score -= 10
    return max(5, score)


def calculate_probability(boxer_a, boxer_b):
    """Retains the legacy two-outcome manual comparison."""
    sa, sb = calculate_score(boxer_a), calculate_score(boxer_b)
    prob_a = round(sa / (sa + sb) * 100, 1)
    return {
        "name_a": boxer_a["name"],
        "name_b": boxer_b["name"],
        "probability_a": prob_a,
        "probability_b": round(100.0 - prob_a, 1),
    }


def calculate_three_way(boxer_a, boxer_b):
    """A+B+draw exactly 100%, *not* a trained or calibrated model."""
    if any(boxer.get(field) is None for boxer in (boxer_a,boxer_b)
           for field in ("wins","losses")):
        return None
    sa, sb = calculate_score(boxer_a), calculate_score(boxer_b)
    draw = 4.0  # model assumption only, not a claimed measured draw rate
    pa = round(96.0 * sa / (sa + sb), 1)
    pb = round(100.0 - draw - pa, 1)
    return {"name_a":boxer_a["name"],"name_b":boxer_b["name"],
            "probability_a":pa,"probability_draw":draw,"probability_b":pb,
            "method":"Heuristisches Demonstrationsmodell (nicht kalibriert)"}
