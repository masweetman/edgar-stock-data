"""
EDGAR data fetching service using the edgartools package.

All SEC EDGAR access is performed via edgartools, which handles HTTP,
rate limiting, and identity headers internally.

Data is extracted from EntityFacts.to_dataframe(), which returns all XBRL
facts with columns: concept, label, value, numeric_value, unit, period_type,
period_start, period_end, fiscal_year, fiscal_period.
Annual facts are identified by fiscal_period == 'FY'.
"""

import logging
import statistics
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# US-GAAP XBRL concept identifiers used for data extraction
_CONCEPT_EPS_DILUTED = 'us-gaap:EarningsPerShareDiluted'
_CONCEPT_ASSETS = 'us-gaap:Assets'
_CONCEPT_LIABILITIES = 'us-gaap:Liabilities'
_CONCEPT_LIABILITIES_CURRENT = 'us-gaap:LiabilitiesCurrent'
_CONCEPT_LIABILITIES_NONCURRENT = 'us-gaap:LiabilitiesNoncurrent'
_CONCEPT_SHARES_BASIC = 'us-gaap:WeightedAverageNumberOfSharesOutstandingBasic'
_CONCEPT_SHARES_OUTSTANDING = 'us-gaap:CommonStockSharesOutstanding'
_CONCEPT_DIV_DECLARED = 'us-gaap:CommonStockDividendsPerShareDeclared'
_CONCEPT_DIV_PAID = 'us-gaap:CommonStockDividendsPerShareCashPaid'

# Buffett-analysis XBRL concepts
_CONCEPT_NET_INCOME = 'us-gaap:NetIncomeLoss'
_CONCEPT_DA = 'us-gaap:DepreciationDepletionAndAmortization'
_CONCEPT_DA_ALT = 'us-gaap:DepreciationAndAmortization'
_CONCEPT_CAPEX = 'us-gaap:PaymentsToAcquirePropertyPlantAndEquipment'
_CONCEPT_CAPEX_ALT = 'us-gaap:CapitalExpenditure'
_CONCEPT_REVENUE = 'us-gaap:Revenues'
_CONCEPT_REVENUE_ALT = 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax'
_CONCEPT_REVENUE_ALT2 = 'us-gaap:SalesRevenueNet'
_CONCEPT_REVENUE_ALT3 = 'us-gaap:SalesRevenueGoodsNet'
_CONCEPT_OP_INCOME = 'us-gaap:OperatingIncomeLoss'
_CONCEPT_LT_DEBT = 'us-gaap:LongTermDebt'
_CONCEPT_LT_DEBT_ALT = 'us-gaap:LongTermDebtNoncurrent'
_CONCEPT_LT_DEBT_ALT2 = 'us-gaap:LongTermDebtAndCapitalLeaseObligations'
_CONCEPT_LT_DEBT_ALT3 = 'us-gaap:NotesPayable'
_CONCEPT_LT_DEBT_ALT4 = 'us-gaap:DebtAndCapitalLeaseObligations'
_CONCEPT_ST_DEBT = 'us-gaap:ShortTermBorrowings'
_CONCEPT_ST_DEBT_ALT = 'us-gaap:DebtCurrent'
_CONCEPT_EQUITY = 'us-gaap:StockholdersEquity'
# Additional concepts for EV-→Equity bridge and cross-checks
_CONCEPT_CASH = 'us-gaap:CashAndCashEquivalentsAtCarryingValue'
_CONCEPT_CASH_ALT = 'us-gaap:Cash'
_CONCEPT_OP_CASHFLOW = 'us-gaap:NetCashProvidedByUsedInOperatingActivities'


def fetch_data(sec_email: str, tickers: list[str], verify_ssl: bool = True) -> dict[str, dict[str, Any]]:
    """Fetch EPS, BVPS, and dividend data for a list of tickers from SEC EDGAR.

    Args:
        sec_email: Email address used to identify the requester to the SEC (legal requirement).
        tickers: List of stock ticker symbols (e.g. ['AAPL', 'MSFT']).
        verify_ssl: Whether to verify SSL certificates. Should be True in production.

    Returns:
        Dict keyed by ticker, each value containing:
            cik, eps_avg, bvps, div, div_date, error (on failure)
    """
    from edgar import Company, set_identity, configure_http

    if not verify_ssl:
        logger.warning('SSL verification is DISABLED — only use this in development')
        configure_http(verify_ssl=False)

    logger.info('Setting SEC identity to: %s', sec_email)
    set_identity(sec_email)
    logger.info('Fetching data for tickers: %s', tickers)

    results: dict[str, dict[str, Any]] = {}

    for ticker in tickers:
        ticker = ticker.strip().upper()
        if not ticker:
            continue
        logger.info('--- Starting fetch for ticker: %s ---', ticker)
        results[ticker] = _fetch_ticker(ticker)
        logger.info('--- Finished fetch for ticker: %s | result: %s ---', ticker, results[ticker])

    return results


def _fetch_ticker(ticker: str) -> dict[str, Any]:
    """Fetch data for a single ticker. Returns a dict with the fetched fields."""
    from edgar import Company

    entry: dict[str, Any] = {
        'cik': None,
        'eps_avg': None,
        'eps_history': {},
        'bvps': None,
        'div': None,
        'div_date': None,
        'dividend_history': [],
        'error': None,
        # Buffett-analysis fields
        'net_income_history': {},
        'da_history': {},
        'capex_history': {},
        'revenue_history': {},
        'operating_income_history': {},
        'op_cashflow_history': {},
        'long_term_debt': None,
        'short_term_debt': None,
        'cash': None,
        'net_debt': None,
        'debt_unreliable': False,
        'equity': None,
        'equity_history': {},
        'shares_outstanding': None,
    }

    logger.info('[%s] Looking up company via edgartools...', ticker)
    try:
        company = Company(ticker)
        logger.info('[%s] Company found: %s', ticker, company)
    except Exception as exc:
        logger.warning('[%s] Could not find company: %s', ticker, exc)
        entry['error'] = f'Ticker not found: {exc}'
        return entry

    try:
        entry['cik'] = str(company.cik)
        logger.info('[%s] CIK: %s', ticker, entry['cik'])
    except Exception:
        logger.warning('[%s] Could not retrieve CIK', ticker)

    # Fetch all facts once and reuse for all metrics
    logger.info('[%s] Loading entity facts...', ticker)
    try:
        facts = company.get_facts()
        df = facts.to_dataframe() if facts is not None else None
    except Exception as exc:
        logger.warning('[%s] Could not load facts: %s', ticker, exc)
        entry['error'] = f'Facts unavailable: {exc}'
        return entry

    if df is None or df.empty:
        logger.warning('[%s] Facts dataframe is empty', ticker)
        entry['error'] = 'No facts available'
        return entry

    logger.info('[%s] Facts loaded: %d rows', ticker, len(df))

    # --- EPS (average diluted EPS across the 6 most recent calendar years) ---
    entry['eps_avg'] = _get_eps_avg(df, ticker)
    logger.info('[%s] EPS avg: %s', ticker, entry['eps_avg'])
    entry['eps_history'] = _get_annual_series(df, _CONCEPT_EPS_DILUTED, ticker)
    logger.info('[%s] EPS history: %s', ticker, entry['eps_history'])

    # --- Book Value Per Share ---
    entry['bvps'] = _get_bvps(df, ticker)
    logger.info('[%s] BVPS: %s', ticker, entry['bvps'])

    # --- Dividends ---
    div, div_date = _get_dividends(df, ticker)
    entry['div'] = div
    entry['div_date'] = div_date
    logger.info('[%s] Dividend: %s on %s', ticker, div, div_date)
    entry['dividend_history'] = _get_dividend_history(df, ticker)

    # --- Buffett-analysis data (10-year history series) ---
    entry['net_income_history'] = _get_annual_series(df, _CONCEPT_NET_INCOME, ticker)
    entry['da_history'] = _get_annual_series_with_fallback(
        df, _CONCEPT_DA, _CONCEPT_DA_ALT, ticker)
    entry['capex_history'] = _get_annual_series_with_fallback(
        df, _CONCEPT_CAPEX, _CONCEPT_CAPEX_ALT, ticker)
    entry['revenue_history'] = _get_annual_series_with_fallbacks(
        df,
        # ASC 606 concept first — used by most post-2018 filers and more consistently
        # scoped to operating revenues only. us-gaap:Revenues is kept as fallback because
        # some older filers never adopted the 606 taxonomy.
        [_CONCEPT_REVENUE_ALT, _CONCEPT_REVENUE, _CONCEPT_REVENUE_ALT2, _CONCEPT_REVENUE_ALT3],
        ticker,
    )
    _warn_if_sparse_revenue(entry['revenue_history'], ticker)
    entry['operating_income_history'] = _get_annual_series(df, _CONCEPT_OP_INCOME, ticker)
    entry['long_term_debt'] = _latest_annual_value_with_fallbacks(
        df,
        [
            _CONCEPT_LT_DEBT,
            _CONCEPT_LT_DEBT_ALT,
            _CONCEPT_LT_DEBT_ALT2,
            _CONCEPT_LT_DEBT_ALT3,
            _CONCEPT_LT_DEBT_ALT4,  # combined total debt+leases — for captive-finance filers like Ford
        ],
        ticker,
    )
    entry['short_term_debt'] = _latest_annual_value_with_fallback(
        df, _CONCEPT_ST_DEBT, _CONCEPT_ST_DEBT_ALT, ticker)
    entry['cash'] = _latest_annual_value_with_fallback(
        df, _CONCEPT_CASH, _CONCEPT_CASH_ALT, ticker)
    entry['op_cashflow_history'] = _get_annual_series(df, _CONCEPT_OP_CASHFLOW, ticker)
    entry['equity'] = _latest_annual_value(df, _CONCEPT_EQUITY, ticker)
    entry['equity_history'] = _get_annual_series(df, _CONCEPT_EQUITY, ticker)
    entry['shares_outstanding'] = (
        _latest_annual_value(df, _CONCEPT_SHARES_BASIC, ticker)
        or _latest_annual_value(df, _CONCEPT_SHARES_OUTSTANDING, ticker)
    )
    # Derive net debt for the EV→Equity bridge.
    # Negative means net-cash (cash exceeds total debt) — this is meaningful and preserved.
    lt_debt = entry['long_term_debt'] or 0.0
    st_debt = entry['short_term_debt'] or 0.0
    cash = entry['cash'] or 0.0
    entry['net_debt'] = lt_debt + st_debt - cash

    # Flag when captured debt looks implausibly small relative to total liabilities.
    # This catches companies with large financing subsidiaries (e.g. Ford Motor Credit)
    # whose debt is filed under non-standard XBRL concepts not yet in our fallback chain.
    total_liabilities = _latest_annual_value(df, _CONCEPT_LIABILITIES, ticker) or 0.0
    captured_debt = lt_debt + st_debt
    entry['debt_unreliable'] = (
        total_liabilities > 0
        and captured_debt < 0.15 * total_liabilities
    )
    if entry['debt_unreliable']:
        logger.warning(
            '[%s] debt_unreliable=True: captured debt %.0f is <15%% of total liabilities %.0f',
            ticker, captured_debt, total_liabilities,
        )

    logger.info(
        '[%s] Buffett data: net_income years=%s, da years=%s, capex years=%s, '
        'revenue years=%s, equity=%s, shares=%s, cash=%s, st_debt=%s, net_debt=%s',
        ticker,
        list(entry['net_income_history'].keys()),
        list(entry['da_history'].keys()),
        list(entry['capex_history'].keys()),
        list(entry['revenue_history'].keys()),
        entry['equity'],
        entry['shares_outstanding'],
        entry['cash'],
        entry['short_term_debt'],
        entry['net_debt'],
    )

    return entry


def _get_eps_avg(df, ticker: str = '') -> float | None:
    """Return the average annual diluted EPS over the 6 most recent calendar years.

    Filters the facts dataframe for us-gaap:EarningsPerShareDiluted with
    fiscal_period == 'FY'. Deduplicates by taking the latest period_end
    per fiscal_year, then averages over the 6 most recent calendar years
    (current year inclusive).
    """
    try:
        eps_df = df[
            (df['concept'] == _CONCEPT_EPS_DILUTED) &
            (df['fiscal_period'] == 'FY')
        ].copy()

        if eps_df.empty:
            logger.info('[%s][EPS] No annual EPS facts found', ticker)
            return None

        # Deduplicate: keep latest period_end per fiscal_year
        eps_by_year = (
            eps_df.sort_values('period_end')
            .groupby('fiscal_year', as_index=False)
            .last()
        )
        logger.info('[%s][EPS] Annual EPS by year:\n%s', ticker,
                    eps_by_year[['fiscal_year', 'numeric_value']].to_string(index=False))

        current_year = date.today().year
        year_ints = list(range(current_year - 5, current_year + 1))
        matched = eps_by_year[eps_by_year['fiscal_year'].isin(year_ints)]['numeric_value'].dropna()

        if matched.empty:
            logger.info('[%s][EPS] No EPS values found for years: %s', ticker, year_ints)
            return None

        avg = round(float(matched.mean()), 2)
        logger.info('[%s][EPS] Average EPS over %s: %s', ticker, year_ints, avg)
        return avg
    except Exception as exc:
        logger.warning('[%s][EPS] Failed: %s: %s', ticker, type(exc).__name__, exc)
        return None


def _get_bvps(df, ticker: str = '') -> float | None:
    """Calculate Book Value Per Share from the most recent annual facts.

    Uses us-gaap:Assets, us-gaap:Liabilities, and shares outstanding.
    BVPS = (Assets - Liabilities) / Shares
    """
    try:
        assets = _latest_annual_value(df, _CONCEPT_ASSETS, ticker)
        liabilities = _latest_annual_value(df, _CONCEPT_LIABILITIES, ticker)

        if liabilities is None:
            # Fallback: sum current + noncurrent liabilities
            curr = _latest_annual_value(df, _CONCEPT_LIABILITIES_CURRENT, ticker)
            noncurr = _latest_annual_value(df, _CONCEPT_LIABILITIES_NONCURRENT, ticker)
            if curr is not None:
                liabilities = curr + (noncurr or 0.0)

        shares = _latest_annual_value(df, _CONCEPT_SHARES_BASIC, ticker)
        if shares is None:
            shares = _latest_annual_value(df, _CONCEPT_SHARES_OUTSTANDING, ticker)

        logger.info('[%s][BVPS] Assets: %s | Liabilities: %s | Shares: %s',
                    ticker, assets, liabilities, shares)

        if assets is not None and liabilities is not None and shares and shares > 0:
            bvps = round((assets - liabilities) / shares, 2)
            logger.info('[%s][BVPS] Calculated BVPS: %s', ticker, bvps)
            return bvps

        logger.info('[%s][BVPS] Cannot calculate BVPS — missing component(s)', ticker)
    except Exception as exc:
        logger.warning('[%s][BVPS] Failed: %s: %s', ticker, type(exc).__name__, exc)

    return None


def _annualise_dividend(val: float, period_start, period_end, ticker: str = '') -> float | None:
    """Return the estimated annual dividend given a per-period value and its date range.

    Computes the period duration in days and scales accordingly:
        14–59 days  → monthly  (× 12)
        60–120 days → quarterly (× 4)
        121–270 days → semi-annual (× 2)
        271–400 days → annual (× 1)
    Periods outside these bands are considered unreliable and return None.
    """
    try:
        def _to_date(d) -> date:
            if isinstance(d, date):
                return d
            return date.fromisoformat(str(d)[:10])

        start = _to_date(period_start)
        end = _to_date(period_end)
        days = (end - start).days

        if 14 <= days <= 59:
            multiplier = 12
            period_label = 'monthly'
        elif 60 <= days <= 120:
            multiplier = 4
            period_label = 'quarterly'
        elif 121 <= days <= 270:
            multiplier = 2
            period_label = 'semi-annual'
        elif 271 <= days <= 400:
            multiplier = 1
            period_label = 'annual'
        else:
            logger.warning(
                '[%s][DIV] Period duration %d days is outside expected bands '
                '(start=%s, end=%s) — skipping this row',
                ticker, days, start, end,
            )
            return None

        annualised = round(val * multiplier, 4)
        logger.info(
            '[%s][DIV] Annualised: %.4f (%.4f × %d, %s, %d-day period)',
            ticker, annualised, val, multiplier, period_label, days,
        )
        return annualised
    except Exception as exc:
        logger.warning('[%s][DIV] Could not annualise dividend: %s', ticker, exc)
        return None


def _get_dividends(df, ticker: str = '') -> tuple[float | None, str | None]:
    """Return (estimated_annual_dividend_per_share, date) from the most recent dividend filing.

    Checks us-gaap:CommonStockDividendsPerShareDeclared then
    us-gaap:CommonStockDividendsPerShareCashPaid.

    The returned dividend value is an estimated *annual* figure, derived by
    scaling the per-period declared/paid amount by the number of periods per year,
    inferred from the filing's period_start / period_end duration.

    Annual filings (fiscal_period == 'FY') are used only as a last resort because
    they are already full-year totals — using them with any multiplier would
    over-count. Non-FY rows (quarterly declarations etc.) are preferred.
    """
    for concept in (_CONCEPT_DIV_DECLARED, _CONCEPT_DIV_PAID):
        try:
            sub = df[df['concept'] == concept].dropna(subset=['numeric_value'])
            if sub.empty:
                logger.info('[%s][DIV] Concept %s not found', ticker, concept)
                continue

            # Prefer non-FY rows (per-declaration/quarterly) over FY aggregates
            non_fy = sub[sub['fiscal_period'] != 'FY'] if 'fiscal_period' in sub.columns else sub
            candidates = non_fy if not non_fy.empty else sub

            # Try each candidate from most-recent to least-recent
            for _, row in candidates.sort_values('period_end', ascending=False).iterrows():
                val = float(row['numeric_value'])
                period_start = row.get('period_start')
                period_end = row.get('period_end')
                div_date = str(period_end)

                if period_start is None or period_end is None:
                    # No date range — assume quarterly as a conservative default
                    logger.warning(
                        '[%s][DIV] Missing period_start/period_end for %s — assuming quarterly',
                        ticker, concept,
                    )
                    annualised = round(val * 4, 4)
                    logger.info('[%s][DIV] Annualised (assumed quarterly): %.4f', ticker, annualised)
                    return annualised, div_date

                annualised = _annualise_dividend(val, period_start, period_end, ticker)
                if annualised is not None:
                    return annualised, div_date

            logger.info('[%s][DIV] No usable rows found for %s', ticker, concept)
        except Exception as exc:
            logger.debug('[%s][DIV] %s failed: %s', ticker, concept, exc)

    logger.info('[%s][DIV] No dividend data found', ticker)
    return None, None


def _get_dividend_history(df, ticker: str = '') -> list[dict]:
    """Return a list of raw per-period dividend records for all available filings.

    Tries us-gaap:CommonStockDividendsPerShareDeclared first, then
    us-gaap:CommonStockDividendsPerShareCashPaid. Prefers declared over paid
    when both have a record for the same period_end date.

    Returns a list of dicts with keys:
        dividend_date (str), dividend_period (str), value (float)
    sorted by dividend_date descending.
    """
    def _period_label(period_start, period_end) -> str:
        try:
            from datetime import date as _date
            def _to_date(d):
                if isinstance(d, _date):
                    return d
                return _date.fromisoformat(str(d)[:10])
            days = (_to_date(period_end) - _to_date(period_start)).days
            if 14 <= days <= 59:
                return 'monthly'
            elif 60 <= days <= 120:
                return 'quarterly'
            elif 121 <= days <= 270:
                return 'semi-annual'
            elif 271 <= days <= 400:
                return 'annual'
        except Exception:
            pass
        return 'unknown'

    # keyed by dividend_date string; declared wins over paid
    records: dict[str, dict] = {}

    for concept in (_CONCEPT_DIV_DECLARED, _CONCEPT_DIV_PAID):
        try:
            sub = df[df['concept'] == concept].dropna(subset=['numeric_value'])
            if sub.empty:
                continue
            non_fy = sub[sub['fiscal_period'] != 'FY'] if 'fiscal_period' in sub.columns else sub
            candidates = non_fy if not non_fy.empty else sub

            for _, row in candidates.iterrows():
                period_end = row.get('period_end')
                if period_end is None:
                    continue
                div_date = str(period_end)[:10]
                # Don't overwrite a record already set by the preferred concept
                if div_date in records:
                    continue
                period_start = row.get('period_start')
                period = _period_label(period_start, period_end) if period_start is not None else 'unknown'
                records[div_date] = {
                    'dividend_date': div_date,
                    'dividend_period': period,
                    'value': round(float(row['numeric_value']), 4),
                }
        except Exception as exc:
            logger.debug('[%s][DIV_HIST] %s failed: %s', ticker, concept, exc)

    result = sorted(records.values(), key=lambda r: r['dividend_date'], reverse=True)
    logger.info('[%s][DIV_HIST] %d dividend records found', ticker, len(result))
    return result


def _latest_annual_value(df, concept: str, ticker: str = '') -> float | None:
    """Return the most recent annual (FY) numeric value for a given US-GAAP concept."""
    sub = df[
        (df['concept'] == concept) &
        (df['fiscal_period'] == 'FY')
    ].dropna(subset=['numeric_value'])

    if sub.empty:
        # Fallback: take any period if no FY entries
        sub = df[df['concept'] == concept].dropna(subset=['numeric_value'])

    if sub.empty:
        return None

    val = float(sub.sort_values('period_end').iloc[-1]['numeric_value'])
    logger.debug('[%s] %s = %s', ticker, concept, val)
    return val


def _latest_annual_value_with_fallback(
    df, concept: str, fallback_concept: str, ticker: str = ''
) -> float | None:
    """Return the most recent annual value, trying fallback concept if primary is empty."""
    val = _latest_annual_value(df, concept, ticker)
    if val is None:
        val = _latest_annual_value(df, fallback_concept, ticker)
    return val


def _get_annual_series(df, concept: str, ticker: str = '', years_back: int = 10) -> dict[int, float]:
    """Return a {fiscal_year: value} dict for up to `years_back` most recent annual FY facts.

    Uses the latest period_end per fiscal_year to deduplicate restated filings.
    Returns an empty dict if the concept is not present.
    """
    try:
        sub = df[
            (df['concept'] == concept) &
            (df['fiscal_period'] == 'FY')
        ].dropna(subset=['numeric_value']).copy()

        if sub.empty:
            logger.debug('[%s] _get_annual_series: no FY data for %s', ticker, concept)
            return {}

        # Deduplicate: keep row with the latest period_end per fiscal_year
        deduped = (
            sub.sort_values('period_end')
            .groupby('fiscal_year', as_index=False)
            .last()
        )

        # Keep only the most recent N years
        deduped = deduped.sort_values('fiscal_year').tail(years_back)

        result = {
            int(row['fiscal_year']): float(row['numeric_value'])
            for _, row in deduped.iterrows()
        }
        logger.debug('[%s] _get_annual_series %s: %s', ticker, concept, result)
        return result
    except Exception as exc:
        logger.warning('[%s] _get_annual_series failed for %s: %s', ticker, concept, exc)
        return {}


def _get_annual_series_with_fallback(
    df, concept: str, fallback_concept: str, ticker: str = '', years_back: int = 10
) -> dict[int, float]:
    """Return annual series for concept, falling back to fallback_concept if empty."""
    result = _get_annual_series(df, concept, ticker, years_back)
    if not result:
        result = _get_annual_series(df, fallback_concept, ticker, years_back)
    return result


def _get_annual_series_with_fallbacks(
    df, concepts: list[str], ticker: str = '', years_back: int = 10
) -> dict[int, float]:
    """Return annual series for the first concept in *concepts* that has data.

    Tries each concept in order; returns the first non-empty result.
    Returns an empty dict if none of the concepts has annual data.
    """
    for concept in concepts:
        result = _get_annual_series(df, concept, ticker, years_back)
        if result:
            return result
    return {}


def _latest_annual_value_with_fallbacks(
    df, concepts: list[str], ticker: str = ''
) -> float | None:
    """Return the most recent annual value for the first concept in *concepts* that has data.

    Tries each concept in order; returns the first non-None result.
    Returns None if none of the concepts has annual data.
    """
    for concept in concepts:
        val = _latest_annual_value(df, concept, ticker)
        if val is not None:
            return val
    return None


def _warn_if_sparse_revenue(revenue_history: dict[int, float], ticker: str) -> None:
    """Warn when revenue history has fewer than 5 entries in the last 5 fiscal years.

    Sparse revenue coverage means the CapEx-to-Revenue ratio will be computed from
    too few years, making maintenance CapEx estimates unreliable.
    """
    if not revenue_history:
        logger.warning('[%s] Revenue history is empty — maintenance CapEx will use raw CapEx fallback', ticker)
        return
    latest_year = max(revenue_history)
    recent_years_present = sum(1 for y in revenue_history if y >= latest_year - 4)
    if recent_years_present < 5:
        logger.warning(
            '[%s] Revenue history has only %d of the last 5 fiscal years (%s) — '
            'CapEx/Revenue ratio may be unreliable',
            ticker, recent_years_present, sorted(revenue_history),
        )
