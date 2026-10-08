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
    """Heuristic 100-point comparison. Not empirically calibrated odds.

    40 win rate (draws count as half-points)
    20 experience (capped at 30 bouts)
    15 knockout efficiency (neutral if unavailable)
    15 low-loss consistency
    10 prime age (neutral if unknown)
    """
    from math import exp

    def rating(boxer):
        if any(boxer.get(field) is None for field in ("wins","losses")):
            return None
        wins=max(0,int(boxer["wins"]))
        losses=max(0,int(boxer["losses"]))
        draws_raw=boxer.get("draws")
        draws=max(0,int(draws_raw)) if draws_raw is not None else 0
        total=wins+losses+draws
        if total==0:
            return None
        win_rate=(wins+0.5*draws)/total
        ko=boxer.get("ko_wins")
        ko_rate=min(wins,max(0,int(ko)))/wins if wins and ko is not None else None
        age=boxer.get("age")
        if age is None:
            prime=7.0
        elif 25<=int(age)<=34:
            prime=10.0
        elif 21<=int(age)<=38:
            prime=8.0
        else:
            prime=5.0
        value=(40.0*win_rate
              +20.0*min(total/30.0,1.0)
              +(15.0*ko_rate if ko_rate is not None else 7.5)
              +15.0*(1-losses/total)
              +prime)
        return max(0.0,min(100.0,value)),total,draws

    a,b=rating(boxer_a),rating(boxer_b)
    if a is None or b is None:
        return None
    score_a,total_a,draws_a=a
    score_b,total_b,draws_b=b
    draw=round(max(2.0,min(9.0,
         4.0 + 11.0*((draws_a+draws_b)/(total_a+total_b))-1.0)),1)
    share_a=1.0/(1.0+exp(-(score_a-score_b)/20.0))
    probability_a=round((100.0-draw)*share_a,1)
    probability_b=round(100.0-draw-probability_a,1)
    return {
        "name_a":boxer_a["name"],
        "name_b":boxer_b["name"],
        "probability_a":probability_a,
        "probability_draw":draw,
        "probability_b":probability_b,
        "score_a":round(score_a,1),
        "score_b":round(score_b,1),
        "method":"Fightbase-100-Punkte-Demomodell – statistisch nicht kalibriert",
    }
