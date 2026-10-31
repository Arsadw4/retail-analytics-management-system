"""Date-range and chart-bucket helpers shared by dashboard page and API."""

from datetime import date, datetime, timedelta


def resolve_dashboard_period(period, raw_start="", raw_end="", today=None):
    """Return the selected period's dates, chart granularity, and label."""
    today = today or date.today()
    period = (period or "this_year").strip().lower()

    if period == "last_year":
        year = today.year - 1
        return period, date(year, 1, 1), date(year, 12, 31), "month", "Last Year"

    if period == "this_month":
        start = today.replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        return period, start, end, "day", "This Month"

    if period == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
        return period, start, end, "day", "Last Month"

    if period == "custom":
        try:
            start = datetime.strptime(raw_start, "%Y-%m-%d").date()
            end = datetime.strptime(raw_end, "%Y-%m-%d").date()
        except (TypeError, ValueError) as exc:
            raise ValueError("Please select a valid custom date range.") from exc
        if start > end:
            raise ValueError("Please select a valid custom date range.")
        granularity = "day" if (end - start).days <= 31 else "month"
        label = f"{start:%d %b %Y} – {end:%d %b %Y}"
        return period, start, end, granularity, label

    start = date(today.year, 1, 1)
    end = date(today.year, 12, 31)
    return "this_year", start, end, "month", "This Year"


def build_dashboard_chart_series(rows, start, end, granularity, period):
    """Fill missing date buckets with zero so the chart spans the whole range."""
    values_by_bucket = {}
    for bucket, value in rows:
        values_by_bucket[str(bucket)] = float(value or 0)

    labels = []
    values = []

    if granularity == "day":
        current = start
        while current <= end:
            key = current.isoformat()
            label = f"{current.day}" if period in ("this_month", "last_month") else current.strftime("%d %b")
            labels.append(label)
            values.append(values_by_bucket.get(key, 0.0))
            current += timedelta(days=1)
        return labels, values

    current = date(start.year, start.month, 1)
    final_month = date(end.year, end.month, 1)
    while current <= final_month:
        key = current.strftime("%Y-%m")
        labels.append(current.strftime("%b") if period in ("this_year", "last_year") else current.strftime("%b %Y"))
        values.append(values_by_bucket.get(key, 0.0))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    return labels, values
