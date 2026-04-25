"""
Buffett-style intrinsic value calculator.

Pure functions — no Flask, SQLAlchemy, or network imports.
All inputs are plain Python types derived from edgar_service fetch results.

Implements the four-stage model from buffet-calculator.md:
  Stage 1: Owner Earnings  (Net Income + D&A - Maintenance CapEx)
  Stage 2: Multi-stage DCF  (10-year growth + terminal value)
  Stage 3: Quality Score    (ROE, debt payoff period, operating margin trend)
  Stage 4: Margin of Safety (market price vs intrinsic value)
"""

import logging
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


# ---------------------------------------------------------------------------
# Stage 1 helpers
# ---------------------------------------------------------------------------

def estimate_maintenance_capex(
    capex_history: dict[int, float],
    revenue_history: dict[int, float],
) -> float | None:
    """Estimate the maintenance portion of CapEx.

    Strategy (per buffet-calculator.md §2 Stage 1):
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


# ---------------------------------------------------------------------------
# Stage 2 helpers
# ---------------------------------------------------------------------------

def project_growth_rate(net_income_history: dict[int, float]) -> float:
    """Estimate sustainable growth rate as CAGR of net income history.

    Capped at _GROWTH_RATE_CAP (15%) and floored at 0 to avoid negative
    discount distortion for temporarily loss-making companies.
    Returns 0.05 (5%) as a conservative default when fewer than 2 years
    of history are available.
    """
    years = sorted(net_income_history)
    if len(years) < 2:
        return 0.05  # conservative default

    first_val = net_income_history[years[0]]
    last_val = net_income_history[years[-1]]
    n = years[-1] - years[0]

    if n <= 0 or first_val <= 0 or last_val <= 0:
        return 0.05

    try:
        cagr = (last_val / first_val) ** (1.0 / n) - 1.0
    except (ZeroDivisionError, ValueError):
        return 0.05

    return max(0.0, min(cagr, _GROWTH_RATE_CAP))


def calculate_intrinsic_value(
    owner_earnings: float,
    growth_rate: float,
    discount_rate: float,
    shares: float,
    terminal_rate: float = _TERMINAL_RATE,
    years: int = 10,
) -> float | None:
    """Multi-stage DCF intrinsic value per share.

    Stage 1: Project owner earnings for `years` at `growth_rate`, discount
             each at `discount_rate`.
    Stage 2: Terminal value using Gordon Growth Model on year-N earnings,
             discounted back to present.
    Divide total PV by shares to arrive at intrinsic value per share.

    Returns None if inputs are invalid (e.g. discount_rate ≤ terminal_rate,
    zero shares, negative owner_earnings — which would imply a negative IV).
    """
    if shares is None or shares <= 0:
        return None
    if discount_rate <= terminal_rate:
        return None
    if owner_earnings is None or owner_earnings <= 0:
        # Negative or zero OE → IV is not meaningful
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

    total_pv = pv_sum + pv_terminal
    return round(total_pv / shares, 2)


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
        Dict with keys: intrinsic_value, owner_earnings, quality_score,
        growth_rate_used, error (None on success).
    """
    result: dict[str, Any] = {
        'intrinsic_value': None,
        'owner_earnings': None,
        'quality_score': None,
        'growth_rate_used': None,
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

        # Stage 1: Owner Earnings
        latest_net_income = (
            net_income_history[max(net_income_history)]
            if net_income_history else None
        )
        latest_da = (
            da_history[max(da_history)]
            if da_history else None
        )
        maintenance_capex = estimate_maintenance_capex(capex_history, revenue_history)
        owner_earnings = calculate_owner_earnings(latest_net_income, latest_da, maintenance_capex)
        result['owner_earnings'] = round(owner_earnings, 0) if owner_earnings is not None else None

        if owner_earnings is None or shares is None or shares <= 0:
            result['error'] = 'Insufficient data for DCF (missing net income or shares).'
            # Still attempt quality score even without DCF
        else:
            # Stage 2: Intrinsic Value
            growth_rate = project_growth_rate(net_income_history)
            result['growth_rate_used'] = round(growth_rate, 4)
            intrinsic_value = calculate_intrinsic_value(
                owner_earnings=owner_earnings,
                growth_rate=growth_rate,
                discount_rate=discount_rate,
                shares=shares,
            )
            result['intrinsic_value'] = intrinsic_value

        # Stage 3: Quality Score
        roe_series = calculate_roe_series(net_income_history, equity)
        margin_series = calculate_operating_margins(op_income_history, revenue_history)
        result['quality_score'] = calculate_quality_score(
            roe_series=roe_series,
            long_term_debt=long_term_debt,
            owner_earnings=owner_earnings,
            margin_series=margin_series,
        )

        logger.info(
            'Buffett analysis complete: IV=%s OE=%s QS=%s growth=%.1f%%',
            result['intrinsic_value'],
            result['owner_earnings'],
            result['quality_score'],
            (result['growth_rate_used'] or 0) * 100,
        )

    except Exception as exc:
        logger.warning('Buffett analysis failed: %s', exc)
        result['error'] = f'Analysis error: {exc}'

    return result
