import unittest
from datetime import date

from core.dashboard_period import build_dashboard_chart_series, resolve_dashboard_period


class DashboardPeriodTests(unittest.TestCase):
    def test_this_year_covers_the_full_calendar_year(self):
        period = resolve_dashboard_period("this_year", today=date(2026, 6, 4))

        self.assertEqual(period, ("this_year", date(2026, 1, 1), date(2026, 12, 31), "month", "This Year"))

    def test_month_ranges_handle_leap_year_and_year_boundary(self):
        this_month = resolve_dashboard_period("this_month", today=date(2024, 2, 12))
        last_month = resolve_dashboard_period("last_month", today=date(2026, 1, 12))

        self.assertEqual(this_month[1:3], (date(2024, 2, 1), date(2024, 2, 29)))
        self.assertEqual(last_month[1:3], (date(2025, 12, 1), date(2025, 12, 31)))

    def test_custom_daily_chart_keeps_zero_sales_days(self):
        labels, values = build_dashboard_chart_series(
            [("2026-10-10", 125.5)],
            date(2026, 10, 9),
            date(2026, 10, 11),
            "day",
            "custom",
        )

        self.assertEqual(labels, ["09 Oct", "10 Oct", "11 Oct"])
        self.assertEqual(values, [0.0, 125.5, 0.0])

    def test_custom_monthly_chart_fills_missing_months(self):
        labels, values = build_dashboard_chart_series(
            [("2026-01", 10), ("2026-03", 30)],
            date(2026, 1, 15),
            date(2026, 3, 2),
            "month",
            "custom",
        )

        self.assertEqual(labels, ["Jan 2026", "Feb 2026", "Mar 2026"])
        self.assertEqual(values, [10.0, 0.0, 30.0])

    def test_invalid_or_reversed_custom_ranges_are_rejected(self):
        for start, end in (("2026-02-30", "2026-03-01"), ("2026-03-02", "2026-03-01")):
            with self.subTest(start=start, end=end):
                with self.assertRaises(ValueError):
                    resolve_dashboard_period("custom", start, end, today=date(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
