"""
Unit tests for app.buffett_calculator.

All tests are pure — no Flask app, DB, or network calls.
"""

import pytest
from app.buffett_calculator import (
    calculate_intrinsic_value,
    calculate_margin_of_safety,
    calculate_operating_margins,
    calculate_owner_earnings,
    calculate_quality_score,
    calculate_roe_series,
    estimate_maintenance_capex,
    mos_signal,
    project_growth_rate,
    run_buffett_analysis,
)


# ---------------------------------------------------------------------------
# estimate_maintenance_capex
# ---------------------------------------------------------------------------

class TestEstimateMaintenanceCapex:
    def test_returns_none_when_no_capex_data(self):
        result = estimate_maintenance_capex({}, {2022: 1_000_000})
        assert result is None

    def test_uses_full_capex_when_fewer_than_5_years(self):
        capex = {2021: 100, 2022: 200}
        revenue = {2021: 1000, 2022: 2000}
        # < 5 common years → 100% of latest CapEx (200)
        result = estimate_maintenance_capex(capex, revenue)
        assert result == 200

    def test_uses_capex_revenue_ratio_when_5_plus_years(self):
        # avg ratio across 5 years:
        # 2018–2021: 100/1000 = 0.10 each; 2022: 100/1500 = 0.0667
        # avg = (0.10*4 + 0.0667) / 5 ≈ 0.0933
        # maint = 0.0933 * 1500 ≈ 140.0
        capex = {2018: 100, 2019: 100, 2020: 100, 2021: 100, 2022: 100}
        revenue = {2018: 1000, 2019: 1000, 2020: 1000, 2021: 1000, 2022: 1500}
        result = estimate_maintenance_capex(capex, revenue)
        assert result == pytest.approx(140.0, rel=1e-3)

    def test_uses_full_capex_when_no_revenue(self):
        capex = {2022: 500}
        result = estimate_maintenance_capex(capex, {})
        assert result == 500

    def test_exact_5_years_uses_ratio(self):
        capex = {yr: 50 for yr in range(2018, 2023)}
        revenue = {yr: 500 for yr in range(2018, 2023)}
        # ratio = 10%, latest revenue = 500, maint = 50
        result = estimate_maintenance_capex(capex, revenue)
        assert result == pytest.approx(50.0, rel=1e-3)


# ---------------------------------------------------------------------------
# calculate_owner_earnings
# ---------------------------------------------------------------------------

class TestCalculateOwnerEarnings:
    def test_basic_calculation(self):
        # OE = 100 + 20 - 15 = 105
        result = calculate_owner_earnings(100.0, 20.0, 15.0)
        assert result == pytest.approx(105.0)

    def test_returns_none_when_net_income_is_none(self):
        assert calculate_owner_earnings(None, 20.0, 15.0) is None

    def test_treats_missing_da_as_zero(self):
        # OE = 100 + 0 - 15 = 85
        result = calculate_owner_earnings(100.0, None, 15.0)
        assert result == pytest.approx(85.0)

    def test_treats_missing_capex_as_zero(self):
        # OE = 100 + 20 - 0 = 120
        result = calculate_owner_earnings(100.0, 20.0, None)
        assert result == pytest.approx(120.0)

    def test_negative_net_income_propagates(self):
        result = calculate_owner_earnings(-50.0, 10.0, 5.0)
        assert result == pytest.approx(-45.0)


# ---------------------------------------------------------------------------
# project_growth_rate
# ---------------------------------------------------------------------------

class TestProjectGrowthRate:
    def test_returns_default_for_single_year(self):
        assert project_growth_rate({2022: 100}) == pytest.approx(0.05)

    def test_returns_default_for_empty_history(self):
        assert project_growth_rate({}) == pytest.approx(0.05)

    def test_computes_cagr_correctly(self):
        # 100 → 121 over 2 years = CAGR 10%
        result = project_growth_rate({2020: 100, 2022: 121})
        assert result == pytest.approx(0.10, rel=1e-3)

    def test_caps_at_15_percent(self):
        # Very fast grower
        result = project_growth_rate({2015: 10, 2023: 10_000})
        assert result == pytest.approx(0.15)

    def test_floors_at_zero_for_declining_company(self):
        result = project_growth_rate({2020: 200, 2022: 100})
        assert result == 0.0

    def test_floors_at_zero_for_negative_start(self):
        result = project_growth_rate({2020: -100, 2022: 100})
        assert result == pytest.approx(0.05)  # fallback


# ---------------------------------------------------------------------------
# calculate_intrinsic_value
# ---------------------------------------------------------------------------

class TestCalculateIntrinsicValue:
    def test_returns_none_for_zero_shares(self):
        assert calculate_intrinsic_value(1000, 0.10, 0.09, 0) is None

    def test_returns_none_for_zero_owner_earnings(self):
        assert calculate_intrinsic_value(0, 0.10, 0.09, 1_000_000) is None

    def test_returns_none_for_negative_owner_earnings(self):
        assert calculate_intrinsic_value(-500, 0.10, 0.09, 1_000_000) is None

    def test_returns_none_when_discount_le_terminal(self):
        assert calculate_intrinsic_value(1000, 0.05, 0.03, 100, terminal_rate=0.03) is None

    def test_positive_result_for_valid_inputs(self):
        iv = calculate_intrinsic_value(
            owner_earnings=1_000_000,
            growth_rate=0.10,
            discount_rate=0.09,
            shares=1_000_000,
        )
        assert iv is not None
        assert iv > 0

    def test_higher_growth_rate_produces_higher_iv(self):
        kwargs = dict(owner_earnings=1_000_000, discount_rate=0.09, shares=1_000_000)
        iv_low = calculate_intrinsic_value(growth_rate=0.05, **kwargs)
        iv_high = calculate_intrinsic_value(growth_rate=0.12, **kwargs)
        assert iv_high > iv_low

    def test_higher_discount_rate_produces_lower_iv(self):
        kwargs = dict(owner_earnings=1_000_000, growth_rate=0.10, shares=1_000_000)
        iv_cheap = calculate_intrinsic_value(discount_rate=0.07, **kwargs)
        iv_expensive = calculate_intrinsic_value(discount_rate=0.12, **kwargs)
        assert iv_cheap > iv_expensive

    def test_per_share_scaling(self):
        iv_1m = calculate_intrinsic_value(1_000_000, 0.10, 0.09, 1_000_000)
        iv_2m = calculate_intrinsic_value(1_000_000, 0.10, 0.09, 2_000_000)
        # Doubling shares should halve per-share IV
        assert iv_1m == pytest.approx(iv_2m * 2, rel=1e-3)


# ---------------------------------------------------------------------------
# calculate_roe_series
# ---------------------------------------------------------------------------

class TestCalculateRoeSeries:
    def test_basic_roe_calculation(self):
        ni = {2021: 100, 2022: 120}
        result = calculate_roe_series(ni, equity=1000)
        assert result == {2021: 0.10, 2022: 0.12}

    def test_returns_empty_for_none_equity(self):
        assert calculate_roe_series({2021: 100}, None) == {}

    def test_returns_empty_for_zero_equity(self):
        assert calculate_roe_series({2021: 100}, 0) == {}

    def test_returns_empty_for_empty_history(self):
        assert calculate_roe_series({}, 1000) == {}


# ---------------------------------------------------------------------------
# calculate_operating_margins
# ---------------------------------------------------------------------------

class TestCalculateOperatingMargins:
    def test_basic_margin_calculation(self):
        op = {2021: 200, 2022: 300}
        rev = {2021: 1000, 2022: 1500}
        result = calculate_operating_margins(op, rev)
        assert result == {2021: pytest.approx(0.20), 2022: pytest.approx(0.20)}

    def test_skips_years_with_zero_revenue(self):
        op = {2021: 100, 2022: 200}
        rev = {2021: 0, 2022: 1000}
        result = calculate_operating_margins(op, rev)
        assert 2021 not in result
        assert result[2022] == pytest.approx(0.20)

    def test_returns_empty_for_empty_inputs(self):
        assert calculate_operating_margins({}, {2021: 100}) == {}
        assert calculate_operating_margins({2021: 100}, {}) == {}


# ---------------------------------------------------------------------------
# calculate_quality_score
# ---------------------------------------------------------------------------

class TestCalculateQualityScore:
    def test_returns_none_when_no_data(self):
        result = calculate_quality_score({}, None, None, {})
        assert result is None

    def test_perfect_company_scores_100(self):
        # ROE > 15% every year, debt < 3yr OE, clearly widening margins
        roe = {yr: 0.25 for yr in range(2015, 2024)}  # all years > 15%
        # Margins double from 0.20 to 0.40 — well above the 2% half-avg threshold
        margins = {yr: 0.20 + (yr - 2015) * 0.025 for yr in range(2015, 2024)}
        score = calculate_quality_score(
            roe_series=roe,
            long_term_debt=0,   # no debt → full debt score
            owner_earnings=1_000_000,
            margin_series=margins,
        )
        assert score == 100

    def test_terrible_company_scores_near_zero(self):
        roe = {yr: 0.05 for yr in range(2015, 2024)}  # all years < 15% → 0 pts
        # Positive but clearly declining margins: 0.30 → 0.10 over 9 years
        margins = {yr: 0.30 - (yr - 2015) * 0.025 for yr in range(2015, 2024)}
        score = calculate_quality_score(
            roe_series=roe,
            long_term_debt=1_000_000_000,
            owner_earnings=100,  # would take 10M years to pay off debt → 0 pts
            margin_series=margins,
        )
        assert score == 0

    def test_debt_payoff_within_3_years_gives_full_debt_points(self):
        score = calculate_quality_score(
            roe_series={},
            long_term_debt=300,
            owner_earnings=100,  # 3 year payoff exactly
            margin_series={},
        )
        assert score == 30  # only debt sub-score (ROE and margin both 0)

    def test_debt_payoff_4_years_gives_partial_debt_points(self):
        score = calculate_quality_score(
            roe_series={},
            long_term_debt=400,
            owner_earnings=100,  # 4 year payoff (between 3 and 6)
            margin_series={},
        )
        assert 0 < score < 30


# ---------------------------------------------------------------------------
# calculate_margin_of_safety
# ---------------------------------------------------------------------------

class TestCalculateMarginOfSafety:
    def test_stock_at_50_percent_discount(self):
        mos = calculate_margin_of_safety(market_price=50, intrinsic_value=100)
        assert mos == pytest.approx(0.50)

    def test_stock_at_premium(self):
        mos = calculate_margin_of_safety(market_price=120, intrinsic_value=100)
        assert mos == pytest.approx(-0.20)

    def test_returns_none_for_none_price(self):
        assert calculate_margin_of_safety(None, 100) is None

    def test_returns_none_for_none_iv(self):
        assert calculate_margin_of_safety(100, None) is None

    def test_returns_none_for_zero_iv(self):
        assert calculate_margin_of_safety(100, 0) is None


# ---------------------------------------------------------------------------
# mos_signal
# ---------------------------------------------------------------------------

class TestMosSignal:
    def test_strong_buy_at_35_percent_or_more(self):
        assert mos_signal(0.35) == 'Strong Buy'
        assert mos_signal(0.60) == 'Strong Buy'

    def test_buy_between_20_and_35(self):
        assert mos_signal(0.20) == 'Buy'
        assert mos_signal(0.34) == 'Buy'

    def test_hold_between_0_and_20(self):
        assert mos_signal(0.0) == 'Hold'
        assert mos_signal(0.19) == 'Hold'

    def test_overvalued_when_negative(self):
        assert mos_signal(-0.01) == 'Overvalued'
        assert mos_signal(-0.50) == 'Overvalued'

    def test_unknown_when_none(self):
        assert mos_signal(None) == 'Unknown'


# ---------------------------------------------------------------------------
# run_buffett_analysis (integration of all stages)
# ---------------------------------------------------------------------------

class TestRunBuffettAnalysis:
    _complete_data = {
        'net_income_history': {2019: 55_256e6, 2020: 57_411e6, 2021: 94_680e6,
                               2022: 99_803e6, 2023: 96_995e6},
        'da_history': {2019: 12_547e6, 2020: 11_056e6, 2021: 11_284e6,
                       2022: 11_104e6, 2023: 11_519e6},
        'capex_history': {2019: 10_495e6, 2020: 7_309e6, 2021: 11_085e6,
                          2022: 10_708e6, 2023: 10_959e6},
        'revenue_history': {2019: 260_174e6, 2020: 274_515e6, 2021: 365_817e6,
                            2022: 394_328e6, 2023: 383_285e6},
        'operating_income_history': {2019: 63_930e6, 2020: 66_288e6, 2021: 108_949e6,
                                     2022: 119_437e6, 2023: 114_301e6},
        'long_term_debt': 95_281e6,
        'equity': 62_146e6,
        'shares_outstanding': 15_550_000_000,
    }

    def test_complete_data_returns_all_fields(self):
        result = run_buffett_analysis(self._complete_data, discount_rate=0.09)
        assert result['intrinsic_value'] is not None
        assert result['owner_earnings'] is not None
        assert result['quality_score'] is not None
        assert result['growth_rate_used'] is not None
        assert result['error'] is None

    def test_intrinsic_value_is_positive_for_profitable_company(self):
        result = run_buffett_analysis(self._complete_data, discount_rate=0.09)
        assert result['intrinsic_value'] > 0

    def test_quality_score_in_valid_range(self):
        result = run_buffett_analysis(self._complete_data, discount_rate=0.09)
        assert 0 <= result['quality_score'] <= 100

    def test_empty_data_returns_error_gracefully(self):
        result = run_buffett_analysis({}, discount_rate=0.09)
        assert result['intrinsic_value'] is None
        assert result['error'] is not None

    def test_missing_shares_sets_error_but_still_scores_quality(self):
        data = {**self._complete_data, 'shares_outstanding': None}
        result = run_buffett_analysis(data, discount_rate=0.09)
        assert result['intrinsic_value'] is None
        assert result['error'] is not None
        # Quality score should still be computed
        assert result['quality_score'] is not None

    def test_missing_net_income_returns_none_iv(self):
        data = {**self._complete_data, 'net_income_history': {}}
        result = run_buffett_analysis(data, discount_rate=0.09)
        assert result['intrinsic_value'] is None

    def test_higher_discount_rate_lowers_iv(self):
        iv_low = run_buffett_analysis(self._complete_data, 0.07)['intrinsic_value']
        iv_high = run_buffett_analysis(self._complete_data, 0.12)['intrinsic_value']
        assert iv_low > iv_high
