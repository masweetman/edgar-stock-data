"""
SEC EDGAR filing service — downloads the most-recent 10-K and 10-Q for a
given company as PDFs using Playwright + real Chrome.

Why real Chrome (channel='chrome')?
  SEC.gov returns 403 Forbidden to headless Chromium. Launching with
  channel='chrome' (the user-installed browser) bypasses this restriction.

Rate limit: SEC EDGAR enforces 10 requests/second.
User-Agent: required by SEC fair-access policy.
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SUBMISSIONS_URL = 'https://data.sec.gov/submissions/CIK{cik10}.json'
_FILING_BASE_URL = 'https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}'
_TARGET_FORMS = ('10-K', '10-Q')


def _sec_headers(sec_email: str) -> dict:
    """Build SEC-compliant request headers.

    SEC policy requires the User-Agent to identify the requester:
      Format: "<Company or App Name> <contact-email>"
    See: https://www.sec.gov/os/accessing-edgar-data
    """
    return {
        'User-Agent': f'edgar-stock-data {sec_email}',
        'Accept-Encoding': 'gzip, deflate',
    }


def fetch_latest_filings(
    ticker: str,
    cik: str,
    storage_path: str,
    sec_email: str = '',
) -> list[dict[str, Any]]:
    """Fetch and PDF-render the most-recent 10-K and 10-Q for *ticker*.

    Args:
        ticker: Stock ticker symbol (used for directory naming).
        cik: SEC CIK number (raw, no leading zeros required).
        storage_path: Base directory where PDFs are stored.
                      PDFs land at <storage_path>/<TICKER>/<form>_<report_date>.pdf
        sec_email: User's registered SEC contact email (required by SEC fair-access
                   policy — used in the User-Agent header).

    Returns:
        List of dicts, one per successfully downloaded filing:
          {filing_type, filing_date, report_date, accession_number, filing_path}
        filing_path is relative to the *storage_path* root (i.e. TICKER/filename.pdf).
    """
    import requests

    ticker = ticker.upper()
    cik_str = str(cik).lstrip('0') or '0'
    cik10 = cik_str.zfill(10)

    headers = _sec_headers(sec_email)
    submissions_url = _SUBMISSIONS_URL.format(cik10=cik10)
    logger.info('[%s] Fetching SEC submissions metadata: %s', ticker, submissions_url)

    try:
        resp = requests.get(submissions_url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning('[%s] Could not fetch submissions: %s', ticker, exc)
        return []

    recent = data.get('filings', {}).get('recent', {})
    forms = recent.get('form', [])
    filing_dates = recent.get('filingDate', [])
    report_dates = recent.get('reportDate', [])
    accession_numbers = recent.get('accessionNumber', [])
    primary_docs = recent.get('primaryDocument', [])

    # Find the most-recent of each target form type by sorting all candidates
    latest_by_form: dict[str, dict] = {}
    for i, form in enumerate(forms):
        if form not in _TARGET_FORMS:
            continue
        entry = {
            'filing_type': form,
            'filing_date': filing_dates[i] if i < len(filing_dates) else '',
            'report_date': report_dates[i] if i < len(report_dates) else '',
            'accession_number': accession_numbers[i] if i < len(accession_numbers) else '',
            'primary_document': primary_docs[i] if i < len(primary_docs) else '',
        }
        existing = latest_by_form.get(form)
        if existing is None or entry['filing_date'] > existing['filing_date']:
            latest_by_form[form] = entry

    if not latest_by_form:
        logger.info('[%s] No 10-K or 10-Q filings found in submissions', ticker)
        return []

    results: list[dict[str, Any]] = []

    for form, meta in latest_by_form.items():
        accession_nodash = meta['accession_number'].replace('-', '')
        filing_url = _FILING_BASE_URL.format(
            cik=cik_str,
            accession=accession_nodash,
            document=meta['primary_document'],
        )

        report_date = meta['report_date'] or meta['filing_date']
        filename = f"{form.replace('-', '')}_{report_date}.pdf"
        ticker_dir = Path(storage_path) / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)
        abs_pdf_path = ticker_dir / filename

        logger.info('[%s] Downloading %s → %s', ticker, form, abs_pdf_path)
        success = _html_to_pdf(filing_url, str(abs_pdf_path), ticker, headers)

        if success:
            # Store path relative to storage_path so it's portable
            rel_path = str(Path(ticker) / filename)
            results.append({
                'filing_type': form,
                'filing_date': meta['filing_date'],
                'report_date': report_date,
                'accession_number': meta['accession_number'],
                'filing_path': rel_path,
            })
        else:
            logger.warning('[%s] PDF generation failed for %s', ticker, form)

    return results


def _html_to_pdf(url: str, output_path: str, ticker: str = '', headers: dict | None = None) -> bool:
    """Render *url* to PDF using Playwright + real Chrome.

    Returns True on success, False on any error.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error(
            '[%s] playwright is not installed. Run: pip install playwright && playwright install chrome',
            ticker,
        )
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel='chrome',   # use real Chrome — avoids SEC.gov 403
                headless=True,
            )
            context = browser.new_context(
                extra_http_headers=headers or {},
            )
            page = context.new_page()
            page.goto(url, wait_until='networkidle', timeout=90_000)
            page.pdf(
                path=output_path,
                format='A4',
                print_background=True,
            )
            context.close()
            browser.close()
        logger.info('[%s] PDF saved: %s', ticker, output_path)
        return True
    except Exception as exc:
        logger.warning('[%s] Playwright PDF generation error: %s', ticker, exc)
        return False
