# Buffett-Style Valuation: Method & Design Documentation

> **Status:** Authoritative design spec for `app/buffett_calculator.py`.
> Incorporates lessons from `gemini-vs-claude.md` to correct methodological
> flaws identified in the Gemini/Ford analysis. Known implementation gaps
> are explicitly flagged.

---

## Core Philosophy

Warren Buffett's valuation method rests on three pillars:

1. **Owner Earnings** -- what the business *actually* produces in cash for
   shareholders, not GAAP accounting profit.
2. **Discounted Cash Flow (DCF)** -- bring those future earnings back to today's
   dollars using a rate that reflects the required return and risk.
3. **Margin of Safety** -- only buy at a significant discount to intrinsic value
   as a buffer against estimation error.

### The Gemini/Ford Cautionary Example

`gemini-vs-claude.md` documents a Gemini analysis of Ford (F, April 2026) that
produced a 79% Margin of Safety using a single-stage perpetuity at the
risk-free rate (4.31%). Claude's critique identified this as structurally
flawed in three ways:

1. The Gordon Growth Model produces **Enterprise Value**, not equity value --
   the EV->Equity bridge (net debt subtraction) was skipped entirely.
2. Using the **risk-free rate** as the discount rate for a capital-intensive,
   cyclical automaker makes the model mechanically bullish on any stock with
   positive owner earnings. With r - g = 2.31%, the denominator is paper-thin
   and the model breaks on small input changes.
3. **FCF guidance != Owner Earnings.** Company-reported "adjusted FCF" often
   excludes obligations that Buffett would count as real costs.

**Our methodology corrects all three.** Every design choice below traces back
to avoiding these failure modes.

---

## Stage 1: Owner Earnings

### Formula

```
Owner Earnings = Net Income + D&A - Maintenance CapEx
```

This is Buffett's formulation from the 1986 Berkshire Hathaway shareholder
letter. D&A is added back because it is a non-cash charge; maintenance CapEx is
subtracted because it represents cash that *must* be spent just to preserve
competitive position.

### Why Not Company-Reported FCF?

Company-reported Free Cash Flow typically uses total CapEx:

```
FCF = Operating Cash Flow - Total CapEx
```

This conflates maintenance spending (unavoidable) with growth spending
(discretionary). A company spending $10B on CapEx, $9B of which is building new
factories, looks far worse on FCF than it should from an owner-earnings
standpoint. For Ford in 2026, this distinction is critical: most of its CapEx
is effectively maintenance-level spending required to retool for EVs and stay
competitive, even if booked as "growth" investment.

### Maintenance CapEx Estimation

Companies rarely break out maintenance vs. growth CapEx in EDGAR filings. We
estimate it using the 5-year average CapEx-to-Revenue ratio applied to current
revenue:

```
Maintenance CapEx ~= avg(CapEx / Revenue, 5yr) * Revenue_current
```

**Rationale:** Revenue-normalizing smooths out lumpy one-time expansion
projects while capturing the structural CapEx burden relative to business scale.

**Fallback (< 5 years of data):** Use 100% of the latest year's CapEx as
maintenance. This is conservative -- it likely overstates the true maintenance
burden -- but prevents the model from appearing artificially generous on
companies with limited history.

**High CapEx/Revenue flag:** When the 5-year average CapEx/Revenue ratio
exceeds ~10%, this signals a capital-intensive business with a weak moat. For
automakers this ratio typically runs 5-8%; for software businesses it runs < 2%.
The ratio itself is informative and should be surfaced in output.

### Single-Year vs. Normalized Owner Earnings

**Current implementation:** Uses the most recent fiscal year's net income and
D&A. This makes the output sensitive to a single bad year.

**Known gap:** A 3-to-5-year average of owner earnings would be more
conservative and more representative. Until normalized, callers should apply
extra skepticism when the most recent year's net income is materially higher or
lower than the prior 3-year average.

---

## Stage 2: Intrinsic Value (Two-Stage DCF)

### Why Not the Gordon Growth Model Alone

The single-stage perpetuity used by Gemini:

```
IV = OE / (r - g)
```

...has two problems. First, it produces **Enterprise Value** (whole-business
value), not shareholder equity value. Second, the result is dominated by the
denominator: at r = 4.31% and g = 2%, a half-point error in either variable
swings the outcome by 15-25%. This is mathematically fragile by construction,
not conservative.

### Two-Stage DCF Structure

**Stage 2a -- Growth Period (Years 1-10)**

Project owner earnings forward at the estimated growth rate, discount each
year's cash flow back to the present:

```
PV_growth = sum over n=1..10 of: OE * (1+g)^n / (1+r)^n
```

**Stage 2b -- Terminal Value**

After year 10, assume a perpetual growth rate gT (default 3%, roughly matching
long-run nominal GDP/inflation). Computed on year-10 earnings and discounted back:

```
TV          = CF_10 * (1 + gT) / (r - gT)
PV_terminal = TV / (1 + r)^10
```

### The EV -> Equity Bridge (Critical -- Currently Incomplete)

The sum `PV_growth + PV_terminal` represents **Enterprise Value** -- the value
of the entire business, debt included. Shareholders own only the equity portion.
Net debt must be subtracted:

```
Equity Value = EV - Net Debt
Net Debt     = Long-Term Debt - Cash & Equivalents
IV per share = Equity Value / Shares Outstanding
```

**Current implementation gap:** `calculate_intrinsic_value()` divides total PV
directly by shares without subtracting net debt. This overstates intrinsic
value for any leveraged company. For a debt-free company it is exact; for a
company like Ford (automotive net debt ~$10B) it materially inflates the
per-share result.

**The fix requires:**
1. Fetching cash/cash equivalents from EDGAR
   (`us-gaap:CashAndCashEquivalentsAtCarryingValue`)
2. Passing `long_term_debt` and `cash` into `calculate_intrinsic_value()`
3. Computing `equity_value = total_pv - max(0, long_term_debt - cash)`

Until this is implemented, the tool systematically overstates intrinsic value
for leveraged companies. The quality score's debt sub-score partially
compensates by penalizing high-debt firms, but it is not a substitute for the
bridge.

---

## Stage 2c: Discount Rate

### The Most Important Input

The discount rate is the single biggest lever in any DCF. A 2% difference in r
can change intrinsic value by 40-60% for a company with moderate growth.

The sensitivity table from the Gemini/Ford critique illustrates this:

| Discount Rate | Ford IV/Share |
|:---|:---|
| 4.31% (Treasury yield -- Gemini) | $59.38 |
| 7.00% | $27.35 |
| 9.00% | $18.18 |
| 10.00% | $14.53 |

At 10%, the Margin of Safety for Ford nearly vanishes. The model's conclusion is
almost entirely a function of this one input.

### Why Not the Risk-Free Rate?

Buffett discounts at the long-term Treasury rate -- but *only* for businesses
with near-certain, bond-like predictability (Coca-Cola, See's Candies). For
these businesses, the risk-free rate is appropriate, and he uses a large MOS as
his risk buffer rather than adding an explicit risk premium to r.

**A tool cannot replicate this judgment.** Without Buffett's qualitative
assessment of "predictability," using the risk-free rate produces inflated
intrinsic values for every company with positive earnings.

### Our Approach

- **Default discount rate: 9%** -- a reasonable long-run nominal required return
  for public equity investors, reflecting the historical equity risk premium.
- **User-configurable:** Stored in `UserConfig.discount_rate`. Users who
  understand the model can adjust it.
- **Minimum floor by risk tier (future improvement):** The quality score should
  eventually set a floor on the discount rate -- low-quality companies (score
  < 40) should use >= 10%, even if the user sets a lower rate.

### Sensitivity Table Requirement

Any valuation output should include the intrinsic value at +/-1% and +/-2% on
the discount rate. This shows the user how much to trust the point estimate and
is more informative than the estimate itself for fragile models.

---

## Stage 2d: Growth Rate Projection

### Formula

CAGR of historical net income, used as a proxy for sustainable growth:

```
g = (NI_last / NI_first) ^ (1 / years) - 1
```

### Caps and Floors

| Constraint | Value | Rationale |
|:---|:---|:---|
| Floor | 0% | Avoid negative perpetuity distortion for temporarily loss-making companies |
| Cap | 15% | Very few businesses sustain > 15% long-term; projecting higher overstates value |
| Default (< 2 years data) | 5% | Conservative median when history is insufficient |

### Known Fragility: CAGR on Volatile Earners

CAGR breaks down when:
- The starting net income is negative or near zero
- The company had a one-off loss or gain in either endpoint year
- Earnings are highly cyclical (automakers, airlines, commodities)

Current code returns the 5% default when `first_val <= 0` or `last_val <= 0`.
This is a safe fallback but loses all historical information.

**Better approach (future improvement):** Use the median of year-over-year
growth rates across all consecutive year pairs. This is more robust to outlier
years and handles sign changes more gracefully.

For companies in a loss-to-profit transition (EV startups, turnarounds), even
0% is optimistic as a near-term assumption. A three-stage DCF -- stress period,
growth period, terminal -- would handle this more accurately.

---

## Stage 3: Quality Score (0-100)

The quality score converts qualitative Buffett criteria into a quantitative
signal. It does **not** alter the intrinsic value calculation -- it is a
separate indicator of how much to trust the IV estimate.

**High MOS + High Quality Score = Strong signal.**
**High MOS + Low Quality Score = Model uncertainty, not a guaranteed bargain.**

### Sub-Scores

| Component | Max Points | Criterion |
|:---|:---|:---|
| ROE | 40 | Fraction of years where ROE > 15%, scaled to 40 pts |
| Debt | 30 | Full 30 pts if LT debt repayable in < 3 years of owner earnings; linear decay to 0 at 6 years |
| Margin Trend | 30 | Full 30 pts if second-half avg margin >= 102% of first-half; 18 pts if within 5%; 0 if declining |

### Interpretation

| Score | Meaning |
|:---|:---|
| 70-100 | High predictability -- IV estimate is likely reliable |
| 40-69 | Medium predictability -- apply additional MOS conservatism |
| 0-39 | Low predictability -- IV estimate is unreliable; do not act on it alone |

### ROE Sub-Score Limitation: Static Equity Denominator

Current implementation uses the most recent equity as the denominator across
all historical years:

```
ROE_year = net_income_year / equity_current   # simplification
```

Ideally, each year's ROE would use that year's equity. The simplification
overstates ROE in earlier years (when equity was lower) and understates it in
later years (when equity may have grown). For companies with significant
buybacks or equity issuance, this can meaningfully distort the score.

---

## Stage 4: Margin of Safety

```
MOS = 1 - (Market Price / Intrinsic Value)
```

### Signal Thresholds

| MOS | Signal | Interpretation |
|:---|:---|:---|
| >= 35% | Strong Buy | Stock trades at >= 35% discount to IV |
| 20-34% | Buy | Meaningful discount with reasonable upside |
| 0-19% | Hold | Near fair value |
| < 0% | Overvalued | Market price exceeds estimated IV |

### MOS Is Only as Good as the IV Estimate

The Gemini/Ford case produced a 79% MOS from a structurally flawed IV
calculation. **MOS alone is not a buy signal.** It must be read alongside:

1. **Quality score** -- low score = low confidence in the IV
2. **Discount rate used** -- a 5% discount rate will almost always produce a
   high MOS; that is a model artifact, not investment alpha
3. **Growth rate used** -- if the projected growth rate exceeds the company's
   recent trend, the IV is optimistic
4. **Whether net debt was subtracted** -- until the EV->Equity bridge is
   implemented, the MOS for leveraged companies is overstated

---

## Worked Example: Ford (F) -- Correcting Gemini

Using April 2026 data to demonstrate correct vs. naive methodology.

### Inputs

| Input | Value |
|:---|:---|
| Owner Earnings | $5.5B |
| Shares Outstanding | 4.01B |
| Near-term growth rate | 2% (mature/declining automaker) |
| Terminal growth rate | 3% |
| Discount rate | 9% (risk-adjusted; Gemini used 4.31%) |
| Automotive net debt | ~$10B |

### Two-Stage DCF at 9%

```
Years 1-10 PV (2% OE growth, 9% discount):  PV_growth ~= $39.4B
Year-10 CF (2% growth for 10 years):         CF_10 ~= $6.7B
Terminal Value:  TV = $6.7B * 1.03 / 0.06 ~= $115B
PV_terminal = $115B / 1.09^10 ~= $48.5B

Enterprise Value  = $39.4B + $48.5B = $87.9B
Equity Value      = $87.9B - $10B   = $77.9B
IV per share      = $77.9B / 4.01B  = $19.43
MOS at $12.35     = 1 - (12.35/19.43) = 36.4%
```

### Comparison

| Approach | Discount Rate | IV/Share | MOS |
|:---|:---|:---|:---|
| Gemini (Gordon Growth, risk-free rate, no bridge) | 4.31% | $59.38 | 79.2% |
| Corrected (two-stage DCF, 9%, net debt deducted) | 9.00% | $19.43 | 36.4% |

The 3x difference in intrinsic value is almost entirely explained by the
discount rate choice and the missing EV->Equity bridge -- not any difference
in underlying business assumptions.

**Quality score for Ford would be ~20-35 (low):** volatile earnings, high
capital intensity, large debt load, declining automotive margins. This tells
the user that even the corrected 36% MOS should be treated with caution.

---

## Known Deficiencies and Roadmap

| # | Issue | Impact | Priority |
|:---|:---|:---|:---|
| 1 | EV->Equity bridge missing -- net debt not subtracted from total PV | Overstates IV for any leveraged company | High |
| 2 | Single-year owner earnings -- sensitive to one bad year | Overstates/understates depending on year | High |
| 3 | No sensitivity table output -- user cannot see model fragility | Silent model risk | High |
| 4 | CAGR growth rate breaks on volatile/negative earners | Loses historical signal; returns 5% default | Medium |
| 5 | ROE uses static equity denominator | Minor score distortion for buyback-heavy companies | Medium |
| 6 | No multi-stage DCF for transitional businesses | Misvalues EV transitions, turnarounds | Medium |
| 7 | Discount rate not tiered by quality score | Under-penalizes risky companies | Low |
| 8 | No third-party benchmark | No sanity check against analyst consensus | Low |

---

## Data Inputs Reference

### EDGAR XBRL Concepts Used

| Field | Primary Concept | Fallback |
|:---|:---|:---|
| Net Income | `us-gaap:NetIncomeLoss` | -- |
| D&A | `us-gaap:DepreciationDepletionAndAmortization` | `us-gaap:DepreciationAndAmortization` |
| CapEx | `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` | -- |
| Revenue | `us-gaap:Revenues` | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` |
| Operating Income | `us-gaap:OperatingIncomeLoss` | -- |
| Long-Term Debt | `us-gaap:LongTermDebt` | `us-gaap:LongTermDebtNoncurrent` |
| Equity | `us-gaap:StockholdersEquity` | -- |
| Shares Outstanding | `us-gaap:CommonStockSharesOutstanding` | `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic` |
| Cash (needed for EV bridge) | `us-gaap:CashAndCashEquivalentsAtCarryingValue` | `us-gaap:Cash` |

### Macro Inputs

| Field | Source | Notes |
|:---|:---|:---|
| Discount Rate | User config | Default 9%; should not be set below 7% for cyclical companies |
| Terminal Growth Rate | Hardcoded constant | 3% -- long-run nominal GDP proxy; not user-configurable |
| Market Price | User-provided | Not fetched from EDGAR; entered at analysis time |
