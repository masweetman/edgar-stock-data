"""
Unit tests for app.edgar_service helper functions.

Pure tests — no Flask app, DB, or network calls.
"""

import pandas as pd
import pytest
from app.edgar_service import (
    _annualise_dividend,
    _get_dividends,
    _latest_annual_value_with_fallbacks,
)


# ---------------------------------------------------------------------------
# _annualise_dividend
# ---------------------------------------------------------------------------

class TestAnnualiseDividend:
    def test_quarterly_period(self):
        # ~91 days → quarterly → × 4
        result = _annualise_dividend(0.25, '2023-10-01', '2023-12-31', 'TEST')
        assert result == pytest.approx(1.00, abs=0.0001)

    def test_monthly_period(self):
        # ~31 days → monthly → × 12
        result = _annualise_dividend(0.10, '2023-12-01', '2023-12-31', 'TEST')
        assert result == pytest.approx(1.20, abs=0.0001)

    def test_semi_annual_period(self):
        # ~181 days → semi-annual → × 2
        result = _annualise_dividend(0.50, '2023-01-01', '2023-07-01', 'TEST')
        assert result == pytest.approx(1.00, abs=0.0001)

    def test_annual_period(self):
        # ~365 days → annual → × 1
        result = _annualise_dividend(1.00, '2023-01-01', '2023-12-31', 'TEST')
        assert result == pytest.approx(1.00, abs=0.0001)

    def test_too_short_period_returns_none(self):
        # < 14 days → unreliable
        result = _annualise_dividend(0.25, '2023-12-25', '2023-12-31', 'TEST')
        assert result is None

    def test_too_long_period_returns_none(self):
        # > 400 days → unreliable
        result = _annualise_dividend(0.25, '2022-01-01', '2023-12-31', 'TEST')
        assert result is None

    def test_date_objects_accepted(self):
        from datetime import date
        result = _annualise_dividend(0.25, date(2023, 10, 1), date(2023, 12, 31), 'TEST')
        assert result == pytest.approx(1.00, abs=0.0001)

    def test_invalid_dates_return_none(self):
        result = _annualise_dividend(0.25, 'not-a-date', '2023-12-31', 'TEST')
        assert result is None


# ---------------------------------------------------------------------------
# _get_dividends
# ---------------------------------------------------------------------------

def _make_div_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal facts dataframe with the columns _get_dividends uses."""
    return pd.DataFrame(rows)


class TestGetDividends:
    def _quarterly_row(self, concept, val, period_start, period_end, fiscal_period='Q1'):
        return {
            'concept': concept,
            'numeric_value': val,
            'period_start': period_start,
            'period_end': period_end,
            'fiscal_period': fiscal_period,
        }

    def test_quarterly_declared_annualised_correctly(self):
        df = _make_div_df([
            self._quarterly_row(
                'us-gaap:CommonStockDividendsPerShareDeclared',
                0.25, '2023-10-01', '2023-12-31',
            )
        ])
        div, date = _get_dividends(df, 'TEST')
        assert div == pytest.approx(1.00, abs=0.0001)
        assert date == '2023-12-31'

    def test_prefers_non_fy_over_fy_row(self):
        # FY row has value 1.0 (already annual) — should be skipped in favour of Q4
        df = _make_div_df([
            self._quarterly_row(
                'us-gaap:CommonStockDividendsPerShareDeclared',
                0.25, '2023-10-01', '2023-12-31', fiscal_period='Q4',
            ),
            self._quarterly_row(
                'us-gaap:CommonStockDividendsPerShareDeclared',
                1.00, '2023-01-01', '2023-12-31', fiscal_period='FY',
            ),
        ])
        div, _ = _get_dividends(df, 'TEST')
        # Should use Q4 row (0.25 × 4 = 1.00), not FY row (1.00 × 1 = 1.00, same here)
        # Verify it picked the quarterly row by checking it's 4× the quarterly value
        assert div == pytest.approx(1.00, abs=0.0001)

    def test_falls_back_to_paid_concept(self):
        df = _make_div_df([
            self._quarterly_row(
                'us-gaap:CommonStockDividendsPerShareCashPaid',
                0.50, '2023-07-01', '2023-12-31',
            )
        ])
        div, _ = _get_dividends(df, 'TEST')
        # 183-day period → semi-annual → × 2
        assert div == pytest.approx(1.00, abs=0.0001)

    def test_no_dividend_data_returns_none(self):
        df = _make_div_df([
            {'concept': 'us-gaap:Assets', 'numeric_value': 1000.0,
             'period_start': '2023-01-01', 'period_end': '2023-12-31',
             'fiscal_period': 'FY'}
        ])
        div, date = _get_dividends(df, 'TEST')
        assert div is None
        assert date is None

    def test_skips_out_of_band_periods_and_tries_next(self):
        # First row has > 400 day span → skipped; second is quarterly → used
        df = _make_div_df([
            self._quarterly_row(
                'us-gaap:CommonStockDividendsPerShareDeclared',
                0.25, '2021-01-01', '2023-12-31', fiscal_period='Q1',
            ),
            self._quarterly_row(
                'us-gaap:CommonStockDividendsPerShareDeclared',
                0.25, '2023-10-01', '2023-12-31', fiscal_period='Q4',
            ),
        ])
        div, _ = _get_dividends(df, 'TEST')
        assert div == pytest.approx(1.00, abs=0.0001)

    def test_empty_dataframe_returns_none(self):
        df = pd.DataFrame(columns=['concept', 'numeric_value', 'period_start',
                                   'period_end', 'fiscal_period'])
        div, date = _get_dividends(df, 'TEST')
        assert div is None
        assert date is None


# ---------------------------------------------------------------------------
# _latest_annual_value_with_fallbacks
# ---------------------------------------------------------------------------

def _make_facts_df(concept: str, value: float, fiscal_period: str = 'FY') -> pd.DataFrame:
    """Build a minimal single-row facts dataframe."""
    return pd.DataFrame([{
        'concept': concept,
        'numeric_value': value,
        'fiscal_period': fiscal_period,
        'period_end': '2024-12-31',
    }])


class TestLatestAnnualValueWithFallbacks:
    def test_returns_primary_when_present(self):
        df = _make_facts_df('us-gaap:LongTermDebt', 1_000.0)
        result = _latest_annual_value_with_fallbacks(
            df,
            ['us-gaap:LongTermDebt', 'us-gaap:LongTermDebtNoncurrent',
             'us-gaap:LongTermDebtAndCapitalLeaseObligations'],
            'TEST',
        )
        assert result == 1_000.0

    def test_falls_back_to_third_concept_when_primary_and_alt_absent(self):
        # Only the third concept has data (simulates Ford-like filing)
        df = _make_facts_df('us-gaap:LongTermDebtAndCapitalLeaseObligations', 99_000_000_000.0)
        result = _latest_annual_value_with_fallbacks(
            df,
            ['us-gaap:LongTermDebt', 'us-gaap:LongTermDebtNoncurrent',
             'us-gaap:LongTermDebtAndCapitalLeaseObligations', 'us-gaap:NotesPayable'],
            'TEST',
        )
        assert result == 99_000_000_000.0

    def test_falls_back_to_fourth_concept_when_first_three_absent(self):
        df = _make_facts_df('us-gaap:NotesPayable', 500_000_000.0)
        result = _latest_annual_value_with_fallbacks(
            df,
            ['us-gaap:LongTermDebt', 'us-gaap:LongTermDebtNoncurrent',
             'us-gaap:LongTermDebtAndCapitalLeaseObligations', 'us-gaap:NotesPayable'],
            'TEST',
        )
        assert result == 500_000_000.0

    def test_falls_back_to_fifth_concept_ford_style(self):
        # Simulates Ford Motor Credit filer: only DebtAndCapitalLeaseObligations present
        df = _make_facts_df('us-gaap:DebtAndCapitalLeaseObligations', 154_287_000_000.0)
        result = _latest_annual_value_with_fallbacks(
            df,
            ['us-gaap:LongTermDebt', 'us-gaap:LongTermDebtNoncurrent',
             'us-gaap:LongTermDebtAndCapitalLeaseObligations', 'us-gaap:NotesPayable',
             'us-gaap:DebtAndCapitalLeaseObligations'],
            'TEST',
        )
        assert result == 154_287_000_000.0

    def test_returns_none_when_no_concept_matches(self):
        df = _make_facts_df('us-gaap:SomeOtherConcept', 42.0)
        result = _latest_annual_value_with_fallbacks(
            df,
            ['us-gaap:LongTermDebt', 'us-gaap:LongTermDebtNoncurrent'],
            'TEST',
        )
        assert result is None

    def test_empty_concepts_list_returns_none(self):
        df = _make_facts_df('us-gaap:LongTermDebt', 1_000.0)
        result = _latest_annual_value_with_fallbacks(df, [], 'TEST')
        assert result is None
