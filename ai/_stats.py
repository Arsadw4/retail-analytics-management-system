"""
ai/_stats.py
Small, dependency-free statistics helpers shared by the AI modules.
Deliberately pure Python (no numpy/pandas/scikit-learn) -- the data
volumes a single retail location generates don't need them, and it
keeps this module deployable anywhere Flask itself runs. See
AI_SETUP_GUIDE.md for how to swap in a real ML library later if your
data volume grows enough to benefit from one.
"""


def linear_regression(x, y):
    """
    Ordinary least-squares fit of y = slope*x + intercept.
    x, y: same-length lists of numbers (x is typically 0..n-1, one
    point per day/week/month of history).
    Returns (slope, intercept). (0, mean(y)) if fewer than 2 points.
    """
    n = len(x)
    if n < 2:
        return 0.0, (y[0] if y else 0.0)

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

    if denominator == 0:
        return 0.0, mean_y

    slope = numerator / denominator
    intercept = mean_y - slope * mean_x
    return slope, intercept


def forecast_next(x, y, steps_ahead):
    """Project `steps_ahead` points past the end of x using a linear fit."""
    slope, intercept = linear_regression(x, y)
    last_x = x[-1] if x else 0
    return [slope * (last_x + i) + intercept for i in range(1, steps_ahead + 1)]


def moving_average(values, window):
    if not values:
        return 0.0
    tail = values[-window:] if len(values) >= window else values
    return sum(tail) / len(tail)


def mean(values):
    return sum(values) / len(values) if values else 0.0


def stdev(values):
    if len(values) < 2:
        return 0.0
    m = mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return variance ** 0.5
