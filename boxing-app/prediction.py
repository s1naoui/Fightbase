def calculate_score(boxer):
    score = 50

    if boxer["wins"] > 10:
        score += 20
    elif boxer["wins"] > 5:
        score += 10

    if boxer["age"] < 22 or boxer["age"] > 35:
        score -= 20

    return score


def calculate_probability(boxer_a, boxer_b):
    score_a = calculate_score(boxer_a)
    score_b = calculate_score(boxer_b)

    total = score_a + score_b

    probability_a = (score_a / total) * 100
    probability_b = (score_b / total) * 100

    return {
        "name_a": boxer_a["name"],
        "name_b": boxer_b["name"],
        "probability_a": round(probability_a, 1),
        "probability_b": round(probability_b, 1)
    }