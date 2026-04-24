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


def fetch_data(sec_email: str, tickers: list[str], years: list[str], verify_ssl: bool = True) -> dict[str, dict[str, Any]]:
    """Fetch EPS, BVPS, and dividend data for a list of tickers from SEC EDGAR.

    Args:
        sec_email: Email address used to identify the requester to the SEC (legal requirement).
        tickers: List of stock ticker symbols (e.g. ['AAPL', 'MSFT']).
        years: List of year strings to average EPS over (e.g. ['2021', '2022', '2023']).
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
    logger.info('Fetching data for tickers: %s | years: %s', tickers, years)

    results: dict[str, dict[str, Any]] = {}

    for ticker in tickers:
        ticker = ticker.strip().upper()
        if not ticker:
            continue
        logger.info('--- Starting fetch for ticker: %s ---', ticker)
        results[ticker] = _fetch_ticker(ticker, years)
        logger.info('--- Finished fetch for ticker: %s | result: %s ---', ticker, results[ticker])

    return results


def _fetch_ticker(ticker: str, years: list[str]) -> dict[str, Any]:
    """Fetch data for a single ticker. Returns a dict with the fetched fields."""
    from edgar import Company

    entry: dict[str, Any] = {
        'cik': None,
        'eps_avg': None,
        'bvps': None,
        'div': None,
        'div_date': None,
        'error': None,
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

    # --- EPS (average diluted EPS across requested years) ---
    entry['eps_avg'] = _get_eps_avg(df, years, ticker)
    logger.info('[%s] EPS avg: %s', ticker, entry['eps_avg'])

    # --- Book Value Per Share ---
    entry['bvps'] = _get_bvps(df, ticker)
    logger.info('[%s] BVPS: %s', ticker, entry['bvps'])

    # --- Dividends ---
    div, div_date = _get_dividends(df, ticker)
    entry['div'] = div
    entry['div_date'] = div_date
    logger.info('[%s] Dividend: %s on %s', ticker, div, div_date)

    return entry


def _get_eps_avg(df, years: list[str], ticker: str = '') -> float | None:
    """Return the average annual diluted EPS over the requested years.

    Filters the facts dataframe for us-gaap:EarningsPerShareDiluted with
    fiscal_period == 'FY'. Deduplicates by taking the latest period_end
    per fiscal_year, then averages over the requested years.
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

        year_ints = [int(y) for y in years]
        matched = eps_by_year[eps_by_year['fiscal_year'].isin(year_ints)]['numeric_value'].dropna()

        if matched.empty:
            logger.info('[%s][EPS] No EPS values found for requested years: %s', ticker, years)
            return None

        avg = round(float(matched.mean()), 2)
        logger.info('[%s][EPS] Average EPS over %s: %s', ticker, years, avg)
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


def _get_dividends(df, ticker: str = '') -> tuple[float | None, str | None]:
    """Return (dividend_per_share, date) from the most recent dividend filing.

    Checks us-gaap:CommonStockDividendsPerShareDeclared then
    us-gaap:CommonStockDividendsPerShareCashPaid.
    """
    for concept in (
        _CONCEPT_DIV_DECLARED,
        _CONCEPT_DIV_PAID,
    ):
        try:
            sub = df[df['concept'] == concept].dropna(subset=['numeric_value'])
            if sub.empty:
                logger.info('[%s][DIV] Concept %s not found', ticker, concept)
                continue
            latest = sub.sort_values('period_end').iloc[-1]
            val = float(latest['numeric_value'])
            date = str(latest['period_end'])
            logger.info('[%s][DIV] Found %s: %s on %s', ticker, concept, val, date)
            return val, date
        except Exception as exc:
            logger.debug('[%s][DIV] %s failed: %s', ticker, concept, exc)

    logger.info('[%s][DIV] No dividend data found', ticker)
    return None, None


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
