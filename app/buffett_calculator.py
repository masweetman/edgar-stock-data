"""
Buffett-style intrinsic value calculator.

Pure functions — no Flask, SQLAlchemy, or network imports.
All inputs are plain Python types derived from edgar_service fetch results.

Implements the four-stage model from buffett-valuation.md:
  Stage 1: Owner Earnings  (Net Income + D&A - Maintenance CapEx, 3-yr normalized)
  Stage 2: Multi-stage DCF  (10-year growth + terminal value, EV->Equity bridge)
  Stage 3: Quality Score    (ROE, debt payoff period, operating margin trend)
           + Capital Intensity, Earnings Consistency, Predictability Rating
  Stage 4: Margin of Safety (market price vs intrinsic value)
           + Sensitivity table (IV at ±1% and ±2% discount rate)
"""

import logging
import statistics
from typing import Any

logger = logging.getLogger(__name__)

# Quality score sub-weights (must total 100)
_ROE_MAX_POINTS = 40
_DEBT_MAX_POINTS = 30
_MARGIN_MAX_POINTS = 30

_ROE_THRESHOLD = 0.15          # 15% — Buffett baseline
_DEBT_PAYOFF_YEARS = 3         # long-term debt paid off in < 3 years of OE
_GROWTH_RATE_CAP = 0.15        # 15% — conservative ceiling
_TERMINAL_RATE = 0.03          # 3% — long-run GDP/inflation proxy
_MIN_CAPEX_YEARS_FOR_RATIO = 5  # use CapEx/Revenue ratio only if ≥ this many years
_OE_NORMALIZE_YEARS = 3        # years to average for normalized owner earnings

# Capital intensity thresholds (CapEx / Revenue)
_CAPEX_INTENSITY_LOW = 0.03    # < 3%: asset-light
_CAPEX_INTENSITY_HIGH = 0.08   # > 8%: capital-intensive

# Earnings consistency thresholds (coefficient of variation)
_CV_HIGH_THRESHOLD = 0.20      # CV < 0.20: high consistency
_CV_LOW_THRESHOLD = 0.50       # CV > 0.50: low consistency


# ---------------------------------------------------------------------------
# Stage 1 helpers
# ---------------------------------------------------------------------------

def estimate_maintenance_capex(
    capex_history: dict[int, float],
    revenue_history: dict[int, float],
) -> float | None:
    """Estimate the maintenance portion of CapEx.

    Strategy (per buffett-valuation.md § Stage 1):
    - If < _MIN_CAPEX_YEARS_FOR_RATIO years of data: treat 100% of latest CapEx
      as maintenance (conservative estimate).
    - If ≥ _MIN_CAPEX_YEARS_FOR_RATIO years: compute the average CapEx-to-Revenue
      ratio and apply it to the most recent revenue figure.

    Returns None if insufficient data to make any estimate.
    """
    if not capex_history:
        return None

    latest_capex = capex_history[max(capex_history)]

    common_years = sorted(set(capex_history) & set(revenue_history))

    if len(common_years) < _MIN_CAPEX_YEARS_FOR_RATIO or not revenue_history:
        # Conservative fallback: use all CapEx as maintenance
        return latest_capex

    ratios = [
        capex_history[y] / revenue_history[y]
        for y in common_years
        if revenue_history[y] != 0
    ]
    if not ratios:
        return latest_capex

    avg_ratio = sum(ratios) / len(ratios)
    latest_revenue = revenue_history[max(revenue_history)]
    return avg_ratio * latest_revenue


def calculate_capital_intensity(
    capex_history: dict[int, float],
    revenue_history: dict[int, float],
) -> float | None:
    """Return the 5-year average CapEx-to-Revenue ratio (capital intensity).

    Returns None when fewer than _MIN_CAPEX_YEARS_FOR_RATIO common years exist.
    Thresholds (informational):
      < 3%  → asset-light (software, consumer brands)
      3–8%  → moderate (consumer goods, healthcare)
      > 8%  → capital-intensive (industrials, automakers, energy)
    """
    if not capex_history or not revenue_history:
        return None
    common_years = sorted(set(capex_history) & set(revenue_history))
    if len(common_years) < _MIN_CAPEX_YEARS_FOR_RATIO:
        return None
    ratios = [
        capex_history[y] / revenue_history[y]
        for y in common_years
        if revenue_history.get(y, 0) != 0
    ]
    return round(sum(ratios) / len(ratios), 4) if ratios else None


def calculate_owner_earnings(
    net_income: float | None,
    da: float | None,
    maintenance_capex: float | None,
) -> float | None:
    """Owner Earnings = Net Income + D&A - Maintenance CapEx."""
    if net_income is None:
        return None
    da_val = da if da is not None else 0.0
    mc_val = maintenance_capex if maintenance_capex is not None else 0.0
    return net_income + da_val - mc_val


def normalize_owner_earnings(
    net_income_history: dict[int, float],
    da_history: dict[int, float],
    capex_history: dict[int, float],
    revenue_history: dict[int, float],
    years: int = _OE_NORMALIZE_YEARS,
) -> tuple[float | None, bool]:
    """Compute a normalized (multi-year average) owner earnings figure.

    Takes the most recent `years` fiscal years where all three of net income,
    D&A, and maintenance CapEx can be computed, calculates OE for each year,
    and returns the average.

    Returns:
        (normalized_oe, is_noisy) where is_noisy is True when the most
        recent single-year OE deviates by more than 25% from the average
        (signals that the single-year figure is unreliable).
    Returns (None, False) when there is insufficient data.
    """
    if not net_income_history:
        return None, False

    # Use the ratio computed from all available history for maintenance CapEx
    # but apply it year-by-year
    capex_revenue_ratio: float | None = None
    common_years = sorted(set(capex_history) & set(revenue_history))
    if len(common_years) >= _MIN_CAPEX_YEARS_FOR_RATIO:
        ratios = [
            capex_history[y] / revenue_history[y]
            for y in common_years
            if revenue_history.get(y, 0) != 0
        ]
        capex_revenue_ratio = sum(ratios) / len(ratios) if ratios else None

    recent_years = sorted(net_income_history)[-years:]
    oe_values: list[float] = []
    for yr in recent_years:
        ni = net_income_history.get(yr)
        if ni is None:
            continue
        da = da_history.get(yr, 0.0)
        # Maintenance CapEx for this year
        if capex_revenue_ratio is not None and revenue_history.get(yr):
            maint = capex_revenue_ratio * revenue_history[yr]
        elif capex_history.get(yr) is not None:
            maint = capex_history[yr]  # fallback: 100% of that year's CapEx
        else:
            maint = 0.0
        oe_values.append(ni + da - maint)

    if not oe_values:
        return None, False

    avg_oe = sum(oe_values) / len(oe_values)
    # is_noisy: most recent OE differs from avg by > 25%
    most_recent_oe = oe_values[-1]
    is_noisy = avg_oe != 0 and abs(most_recent_oe - avg_oe) / abs(avg_oe) > 0.25
    return avg_oe, is_noisy


# ---------------------------------------------------------------------------
# Stage 2 helpers
# ---------------------------------------------------------------------------

def project_growth_rate(net_income_history: dict[int, float]) -> float:
    """Estimate sustainable growth rate as the median of year-over-year changes.

    Uses the median YoY growth rate across all consecutive year pairs in the
    history. This is more robust than CAGR against outlier years and handles
    sign changes (temporary losses) without triggering the 5% default.

    Capped at _GROWTH_RATE_CAP (15%) and floored at 0.
    Returns 0.05 (5%) as a conservative default when fewer than 3 consecutive
    year pairs are available, or when all values are non-positive.
    """
    years = sorted(net_income_history)
    if len(years) < 2:
        return 0.05  # conservative default

    yoy_rates: list[float] = []
    for i in range(len(years) - 1):
        prev = net_income_history[years[i]]
        curr = net_income_history[years[i + 1]]
        if prev > 0 and curr > 0:
            yoy_rates.append(curr / prev - 1.0)
        # Skip pairs where either endpoint is non-positive

    if len(yoy_rates) < 1:
        # Not enough positive pairs — fall back to conservative default
        return 0.05

    median_rate = statistics.median(yoy_rates)
    return max(0.0, min(median_rate, _GROWTH_RATE_CAP))


def calculate_intrinsic_value(
    owner_earnings: float,
    growth_rate: float,
    discount_rate: float,
    shares: float,
    net_debt: float = 0.0,
    terminal_rate: float = _TERMINAL_RATE,
    years: int = 10,
) -> float | None:
    """Multi-stage DCF intrinsic value per share with EV->Equity bridge.

    Stage 1: Project owner earnings for `years` at `growth_rate`, discount
             each at `discount_rate` to get PV of growth period cash flows.
    Stage 2: Terminal value using Gordon Growth Model on year-N earnings,
             discounted back to present.
    Bridge:  Subtract net_debt (long_term_debt - cash) from total enterprise
             value to get equity value before dividing by shares.

    Returns None if inputs are invalid (e.g. discount_rate ≤ terminal_rate,
    zero shares, negative owner_earnings — which would imply a negative IV).
    net_debt defaults to 0.0 so debt-free companies are unaffected.
    """
    if shares is None or shares <= 0:
        return None
    if discount_rate <= terminal_rate:
        return None
    if owner_earnings is None or owner_earnings <= 0:
        return None

    pv_sum = 0.0
    cf = owner_earnings
    for n in range(1, years + 1):
        cf *= (1.0 + growth_rate)
        pv_sum += cf / (1.0 + discount_rate) ** n

    # Terminal value: perpetuity of the final projected CF growing at terminal_rate
    terminal_cf = cf * (1.0 + terminal_rate)
    terminal_value = terminal_cf / (discount_rate - terminal_rate)
    pv_terminal = terminal_value / (1.0 + discount_rate) ** years

    # Enterprise Value -> Equity Value (EV bridge)
    enterprise_value = pv_sum + pv_terminal
    equity_value = max(0.0, enterprise_value - net_debt)
    return round(equity_value / shares, 2)


def calculate_iv_sensitivity(
    owner_earnings: float,
    growth_rate: float,
    discount_rate: float,
    shares: float,
    net_debt: float = 0.0,
    terminal_rate: float = _TERMINAL_RATE,
) -> dict[str, float | None]:
    """Return intrinsic value at five discount rate variants around the base.

    Keys: 'r_minus_2', 'r_minus_1', 'base', 'r_plus_1', 'r_plus_2'
    Each value is the IV/share (or None if discount_rate <= terminal_rate).
    """
    offsets = {
        'r_minus_2': -0.02,
        'r_minus_1': -0.01,
        'base': 0.0,
        'r_plus_1': 0.01,
        'r_plus_2': 0.02,
    }
    return {
        key: calculate_intrinsic_value(
            owner_earnings=owner_earnings,
            growth_rate=growth_rate,
            discount_rate=discount_rate + delta,
            shares=shares,
            net_debt=net_debt,
            terminal_rate=terminal_rate,
        )
        for key, delta in offsets.items()
    }


# ---------------------------------------------------------------------------
# Stage 3 helpers
# ---------------------------------------------------------------------------

def calculate_roe_series(
    net_income_history: dict[int, float],
    equity: float | None,
) -> dict[int, float]:
    """Return {year: ROE} using a constant equity denominator (most recent equity).

    A simplification — historical equity per year is not available from EDGAR
    entity facts without per-year balance-sheet reconstruction, so we use the
    most recent equity as the denominator across all years.
    Returns an empty dict if equity is None or ≤ 0.
    """
    if not net_income_history or not equity or equity <= 0:
        return {}
    return {yr: ni / equity for yr, ni in net_income_history.items()}


def calculate_operating_margins(
    op_income_history: dict[int, float],
    revenue_history: dict[int, float],
) -> dict[int, float]:
    """Return {year: operating_margin} for years present in both histories."""
    if not op_income_history or not revenue_history:
        return {}
    result: dict[int, float] = {}
    for yr in sorted(set(op_income_history) & set(revenue_history)):
        rev = revenue_history[yr]
        if rev and rev != 0:
            result[yr] = op_income_history[yr] / rev
    return result


def calculate_quality_score(
    roe_series: dict[int, float],
    long_term_debt: float | None,
    owner_earnings: float | None,
    margin_series: dict[int, float],
) -> int | None:
    """0–100 quality score based on three Buffett criteria.

    ROE sub-score  (0–40): fraction of years where ROE > 15%, scaled to 40 pts.
    Debt sub-score (0–30): full 30 pts if OE pays off LT debt in < 3 years;
                           partial credit for up to 6 years.
    Margin sub-score (0–30): full 30 pts if margins are stable or widening;
                              partial if flat; 0 if declining.

    Returns None if there is insufficient data to score any sub-category
    (all three would return 0 with no data, which is misleading).
    """
    if not roe_series and long_term_debt is None and not margin_series:
        return None

    # --- ROE sub-score ---
    if roe_series:
        roe_vals = list(roe_series.values())
        passing = sum(1 for r in roe_vals if r >= _ROE_THRESHOLD)
        roe_score = int(round(_ROE_MAX_POINTS * passing / len(roe_vals)))
    else:
        roe_score = 0

    # --- Debt sub-score ---
    if long_term_debt is not None and owner_earnings and owner_earnings > 0:
        payoff_years = long_term_debt / owner_earnings
        if payoff_years <= _DEBT_PAYOFF_YEARS:
            debt_score = _DEBT_MAX_POINTS
        elif payoff_years <= _DEBT_PAYOFF_YEARS * 2:
            # Linear interpolation between 3 and 6 years → 0–30 pts
            fraction = 1.0 - (payoff_years - _DEBT_PAYOFF_YEARS) / _DEBT_PAYOFF_YEARS
            debt_score = int(round(_DEBT_MAX_POINTS * fraction))
        else:
            debt_score = 0
    elif long_term_debt == 0 or long_term_debt is None and owner_earnings:
        # No debt → full debt score
        debt_score = _DEBT_MAX_POINTS if long_term_debt == 0 else 0
    else:
        debt_score = 0

    # --- Margin trend sub-score ---
    if len(margin_series) >= 2:
        margins = [margin_series[yr] for yr in sorted(margin_series)]
        # Compare average of first half vs second half
        mid = len(margins) // 2
        first_half_avg = sum(margins[:mid]) / mid if mid else 0.0
        second_half_avg = sum(margins[mid:]) / (len(margins) - mid)

        if second_half_avg >= first_half_avg * 1.02:
            # Widening margins
            margin_score = _MARGIN_MAX_POINTS
        elif second_half_avg >= first_half_avg * 0.95:
            # Essentially flat (within 5%)
            margin_score = int(_MARGIN_MAX_POINTS * 0.6)
        else:
            # Declining margins
            margin_score = 0
    else:
        margin_score = 0

    return roe_score + debt_score + margin_score


def calculate_earnings_consistency(
    net_income_history: dict[int, float],
) -> tuple[float | None, str]:
    """Return (coefficient_of_variation, label) for net income history.

    CV = std_dev / mean over all available years.
    Only positive-income years are included in the calculation so that a single
    loss year does not make the mean near-zero and inflate the CV artificially.

    Labels:
      CV < 0.20 -> 'High'   (Coca-Cola territory)
      0.20-0.50 -> 'Medium'
      > 0.50   -> 'Low'   (Ford / cyclical territory)

    Returns (None, 'Unknown') when fewer than 3 positive-income years exist.
    """
    positive_values = [v for v in net_income_history.values() if v > 0]
    if len(positive_values) < 3:
        return None, 'Unknown'

    mean = statistics.mean(positive_values)
    stdev = statistics.stdev(positive_values)
    if mean == 0:
        return None, 'Unknown'

    cv = round(stdev / mean, 4)
    if cv < _CV_HIGH_THRESHOLD:
        label = 'High'
    elif cv <= _CV_LOW_THRESHOLD:
        label = 'Medium'
    else:
        label = 'Low'
    return cv, label


def calculate_predictability_rating(
    quality_score: int | None,
    earnings_consistency_label: str,
    capital_intensity: float | None,
) -> str:
    """Composite High / Medium / Low predictability label.

    Combines the three main signals into a single user-facing assessment of
    how much to trust the intrinsic value estimate.

    High:   quality_score >= 70 AND consistency == 'High' AND intensity < 8%
    Low:    quality_score < 40  OR  consistency == 'Low'
    Medium: everything else
    """
    qs = quality_score if quality_score is not None else 0
    ci = capital_intensity if capital_intensity is not None else 0.0

    if (
        qs >= 70
        and earnings_consistency_label == 'High'
        and ci < _CAPEX_INTENSITY_HIGH
    ):
        return 'High'
    if qs < 40 or earnings_consistency_label == 'Low':
        return 'Low'
    return 'Medium'


# ---------------------------------------------------------------------------
# Stage 4 helper
# ---------------------------------------------------------------------------

def calculate_margin_of_safety(
    market_price: float | None,
    intrinsic_value: float | None,
) -> float | None:
    """MOS = 1 - (Market Price / Intrinsic Value).

    Returns None if either value is missing or intrinsic_value ≤ 0.
    A positive MOS means the stock is trading below intrinsic value (cheap).
    A negative MOS means the stock is above intrinsic value (expensive).
    """
    if market_price is None or intrinsic_value is None or intrinsic_value <= 0:
        return None
    return round(1.0 - (market_price / intrinsic_value), 4)


def mos_signal(mos: float | None) -> str:
    """Human-readable buy/hold/avoid signal from a MOS fraction."""
    if mos is None:
        return 'Unknown'
    if mos >= 0.35:
        return 'Strong Buy'
    if mos >= 0.20:
        return 'Buy'
    if mos >= 0.0:
        return 'Hold'
    return 'Overvalued'


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_buffett_analysis(
    ticker_data: dict[str, Any],
    discount_rate: float,
) -> dict[str, Any]:
    """Run full Buffett-style analysis on a single ticker's fetch result.

    Args:
        ticker_data: Dict returned by edgar_service._fetch_ticker() for one ticker.
        discount_rate: User's preferred discount rate (e.g. 0.09 for 9%).

    Returns:
        Dict with keys: intrinsic_value, owner_earnings, normalized_owner_earnings,
        oe_is_noisy, quality_score, growth_rate_used, net_debt, capital_intensity,
        earnings_consistency_cv, earnings_consistency_label, predictability_rating,
        sensitivity (dict), error (None on success).
    """
    result: dict[str, Any] = {
        'intrinsic_value': None,
        'owner_earnings': None,
        'normalized_owner_earnings': None,
        'oe_is_noisy': False,
        'quality_score': None,
        'growth_rate_used': None,
        'net_debt': None,
        'capital_intensity': None,
        'earnings_consistency_cv': None,
        'earnings_consistency_label': 'Unknown',
        'predictability_rating': 'Unknown',
        'sensitivity': None,
        'error': None,
    }

    try:
        net_income_history: dict[int, float] = ticker_data.get('net_income_history') or {}
        da_history: dict[int, float] = ticker_data.get('da_history') or {}
        capex_history: dict[int, float] = ticker_data.get('capex_history') or {}
        revenue_history: dict[int, float] = ticker_data.get('revenue_history') or {}
        op_income_history: dict[int, float] = ticker_data.get('operating_income_history') or {}
        long_term_debt: float | None = ticker_data.get('long_term_debt')
        equity: float | None = ticker_data.get('equity')
        shares: float | None = ticker_data.get('shares_outstanding')
        net_debt: float = ticker_data.get('net_debt') or 0.0

        result['net_debt'] = net_debt

        # --- Capital Intensity (informational, independent of DCF) ---
        capital_intensity = calculate_capital_intensity(capex_history, revenue_history)
        result['capital_intensity'] = capital_intensity

        # --- Earnings Consistency ---
        cv, ec_label = calculate_earnings_consistency(net_income_history)
        result['earnings_consistency_cv'] = cv
        result['earnings_consistency_label'] = ec_label

        # Stage 1: Normalized Owner Earnings (3-yr average, primary input to DCF)
        normalized_oe, is_noisy = normalize_owner_earnings(
            net_income_history, da_history, capex_history, revenue_history,
        )
        result['normalized_owner_earnings'] = (
            round(normalized_oe, 0) if normalized_oe is not None else None
        )
        result['oe_is_noisy'] = is_noisy

        # Single-year OE for transparency
        latest_net_income = (
            net_income_history[max(net_income_history)] if net_income_history else None
        )
        latest_da = da_history[max(da_history)] if da_history else None
        maintenance_capex = estimate_maintenance_capex(capex_history, revenue_history)
        single_year_oe = calculate_owner_earnings(latest_net_income, latest_da, maintenance_capex)
        result['owner_earnings'] = (
            round(single_year_oe, 0) if single_year_oe is not None else None
        )

        # Use normalized OE for DCF; fall back to single-year if normalization unavailable
        oe_for_dcf = normalized_oe if normalized_oe is not None else single_year_oe

        if oe_for_dcf is None or shares is None or shares <= 0:
            result['error'] = 'Insufficient data for DCF (missing net income or shares).'
            # Still attempt quality score and supplemental metrics
        else:
            # Stage 2: Growth Rate + Intrinsic Value
            growth_rate = project_growth_rate(net_income_history)
            result['growth_rate_used'] = round(growth_rate, 4)

            intrinsic_value = calculate_intrinsic_value(
                owner_earnings=oe_for_dcf,
                growth_rate=growth_rate,
                discount_rate=discount_rate,
                shares=shares,
                net_debt=net_debt,
            )
            result['intrinsic_value'] = intrinsic_value

            # Sensitivity table (only when base IV is computable)
            if oe_for_dcf > 0:
                result['sensitivity'] = calculate_iv_sensitivity(
                    owner_earnings=oe_for_dcf,
                    growth_rate=growth_rate,
                    discount_rate=discount_rate,
                    shares=shares,
                    net_debt=net_debt,
                )

        # Stage 3: Quality Score
        roe_series = calculate_roe_series(net_income_history, equity)
        margin_series = calculate_operating_margins(op_income_history, revenue_history)
        quality_score = calculate_quality_score(
            roe_series=roe_series,
            long_term_debt=long_term_debt,
            owner_earnings=oe_for_dcf if oe_for_dcf is not None else single_year_oe,
            margin_series=margin_series,
        )
        result['quality_score'] = quality_score

        # Predictability Rating (composite)
        result['predictability_rating'] = calculate_predictability_rating(
            quality_score=quality_score,
            earnings_consistency_label=ec_label,
            capital_intensity=capital_intensity,
        )

        logger.info(
            'Buffett analysis complete: IV=%s norm_OE=%s QS=%s growth=%.1f%% '
            'net_debt=%s capex_intensity=%s consistency=%s predictability=%s',
            result['intrinsic_value'],
            result['normalized_owner_earnings'],
            result['quality_score'],
            (result['growth_rate_used'] or 0) * 100,
            result['net_debt'],
            result['capital_intensity'],
            result['earnings_consistency_label'],
            result['predictability_rating'],
        )

    except Exception as exc:
        logger.warning('Buffett analysis failed: %s', exc)
        result['error'] = f'Analysis error: {exc}'

    return result
