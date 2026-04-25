# Review & Improvement of Buffett-Style Valuation

The design spec accurately captures Buffett’s **owner earnings** and DCF pillars, but several gaps remain. Key issues include missing debt adjustment (EV→equity bridge), reliance on a single-year owner earnings, fragile growth assumptions, and limited use of XBRL fallbacks. Below we audit each stage, suggest fixes (with citations), and outline tests and a roadmap.

## Methodology Audit

- **Owner Earnings (Stage 1)** – The formula `OE = Net Income + D&A – Maintenance CapEx` matches Buffett’s 1986 definition【13†L319-L327】.  Note, Buffett also cautioned to include any **working-capital needs** in maintenance capex if required【13†L319-L327】.  The spec currently ignores working capital; as a fix, consider subtracting a “ΔWorking Capital” term if significant.  Also, owner earnings can be volatile year-to-year.  Using a **3–5 year average** of net income (plus D&A minus capex) smooths out cyclical swings. (Many analysts advocate multi-year smoothing to avoid overreacting to one-off profits or losses.)  In practice, compute each year’s owner earnings and use their average (or median growth rate) as the base.  

- **Maintenance CapEx Estimation** – Using the 5-year average *CapEx/Revenue* ratio is reasonable to isolate maintenance spending. To be robust, include alternative proxies.  For example, one could cap maintenance at depreciation (since Buffett suggested using depreciation as a floor) or apply industry norms.  Flagging the CapEx/Revenue ratio (as done) is good; we should ensure it’s output so users can gauge capital intensity.  If historical data is sparse, defaulting to 100% of last year’s CapEx is conservative; just document that this may overstate maintenance requirements.

- **Growth Rate (Stage 2d)** – The current **CAGR from net income** has pitfalls (negative or lumpy earnings).  The spec’s fallback to 5% if endpoints ≤0 is very conservative, but it discards history.  A better interim approach is to compute the **median of year-over-year growth rates** (ignoring zeros or one-offs) to capture a typical growth pace.  This is more robust to outliers than a single CAGR.  For volatile or cyclical businesses (e.g. automakers), even 0% long-term may be optimistic – consider a **multi-stage DCF** with a short “transition” period of 0% growth followed by recovery.  (Academics note growth can’t exceed economy-wide rates indefinitely【34†L132-L139】, justifying a low terminal growth.)  Enforce sensible caps/floors: e.g. floor 0% (as done) and cap long-term growth at the long-run nominal GDP rate (~3–5%)【34†L132-L139】.  

- **Discount Rate (Stage 2c)** – Buffett often *uses the risk-free (gov’t bond) rate* for very predictable businesses and then insists on a large margin of safety【15†L61-L69】.  However, as the spec notes, a mechanical model should use an equity return rate, not pure risk-free.  A 9% default is reasonable (reflecting a ~5–6% equity risk premium over current ~4% T-bonds), but we should allow users to adjust it.  We recommend also *flooring the discount rate by quality tier*: e.g. set **r ≥ 10%** for low-quality (score <40) firms to encode extra risk.  Any output **must** show a sensitivity table: intrinsic value at ±1–2% in r (and optionally ±1% in growth).  This aligns with best practices in DCF modeling to illustrate fragility. 

- **EV→Equity Bridge** – The spec correctly flags that we must subtract net debt to get equity value.  However, note a subtlety: if “owner earnings” are after-interest cash flows (they start from net income), then discounting at *cost of equity* actually yields equity value directly.  In that case, subtracting debt would be double-counting risk.  **Recommendation:** either (a) treat owner earnings as free cash *to equity* and use r=cost of equity, so *skip* subtracting debt; or (b) recast owner earnings to free cash *to firm* (e.g. add back interest*(1-tax)) and discount at WACC, then subtract debt.  Whichever route is chosen, be consistent.  In any case, fetch cash and debt via XBRL (`us-gaap:LongTermDebt`, `us-gaap:CashAndCashEquivalentsAtCarryingValue`) and compute `net_debt = max(0, debt - cash)`【29†L157-L164】 (or allow negative, effectively adding net cash).  Until fixed, intrinsic values for leveraged companies are overstated.

- **Quality Score (Stage 3)** – The subscores (ROE, Debt, Margin Trend) map Buffett’s criteria to numbers, which is smart.  We should refine the **ROE sub-score** by using each year’s *actual* shareholder equity instead of one static denominator.  This requires fetching `us-gaap:StockholdersEquity` for each historical period.  Then count the years ROE >15% (or 20%) to score.  Also consider adding other factors: e.g. **ROIC** or **earnings stability** (low volatility) and **cash conversion ratio**.  Adding a point for consistent positive free cash flow could flag sustainable businesses.  The existing Debt score is good (years to repay debt by OE), but clarify: if net cash, score full 30 pts.  The Margin Trend metric is unusual; perhaps clarify it’s net margin or EBITDA margin.  (The notion of “first-half vs second-half” margin should be explicitly tied to annual margins over 10 years.)  Overall, high quality should mean consistently high ROE, low leverage, steady margins, strong free cash flow – all reflective of a durable moat.

- **Owner Earnings vs. Reported FCF** – The caution about *not using company-reported FCF* is valid.  Companies often report “adjusted FCF” that excludes routine costs.  Our model’s use of true maintenance capex is more conservative, which is good.  To validate, one could compare our owner earnings to simple `OCF - CapEx` from cashflow statements; large discrepancies may indicate aggressive accounting.

## EDGAR XBRL Data Mapping

To robustly retrieve inputs, expand on fallback tags and ambiguity:

- **Revenue:** Filers use various tags.  In practice, total revenue might appear as `us-gaap:Revenues`, `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`, `us-gaap:SalesRevenueNet`, or `us-gaap:SalesRevenueGoodsNet`【29†L157-L164】.  Use all as fallbacks to avoid missing data.  (XBRL forums document Microsoft using four different tags over time【29†L157-L164】.)  

- **Net Income:** `us-gaap:NetIncomeLoss` is standard (no common alternate in US filings).  

- **Depreciation & Amortization:** The tags given (`us-gaap:DepreciationDepletionAndAmortization` and `us-gaap:DepreciationAndAmortization`) cover most cases.  Some filers may report just “Amortization” or “Depreciation” separately; consider if needed.  

- **CapEx:** The primary tag `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` is correct for US GAAP.  A fallback could be `us-gaap:PropertyPlantAndEquipment` (though that’s a balance sheet item) or `us-gaap:CapitalExpenditure`.  In IFRS (foreign registrants), capex might be tagged differently, but EDGAR requires US GAAP for US companies.  

- **Cash & Debt:** `us-gaap:LongTermDebt` (with fallback `LongTermDebtNoncurrent`) and `us-gaap:CashAndCashEquivalentsAtCarryingValue` (fallback `Cash`) are good.  Also fetch **short-term debt** (if any) for net debt if needed: e.g. `us-gaap:ShortTermDebt` or `DebtCurrent`.  

- **Shares:** `us-gaap:CommonStockSharesOutstanding` often holds current share count, but check `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic`.  If filings switch between basic and diluted, you may want the latest basic or weighted average basic.  Ensure consistency year-to-year.  

For each required field, code should try the primary XBRL concept, then each fallback in order, logging any missing fields.  (XBRL inconsistencies are common【29†L157-L164】; robust parsing is needed.)

## Algorithmic & Code-Level Fixes

- **EV→Equity Bridge:** Modify `calculate_intrinsic_value()` to subtract net debt properly.  For example:  
  ```python
  net_debt = max(0, long_term_debt - cash)
  equity_value = total_pv - net_debt
  iv_per_share = equity_value / shares_outstanding
  ```  
  (Alternatively, if you use FCFE streams and r = cost of equity, skip the subtraction: equity_value = total_pv.)  Ensure you fetch `cash` and `long_term_debt` from XBRL and pass them into the DCF function.  

- **Smoothing Owner Earnings:** Instead of using just the latest year’s NI and D&A, compute owner earnings for each of the last N years (e.g. 3 or 5) and take an average.  E.g.:  
  ```python
  owner_eps = []
  for yr in last_n_years:
      oe = NI[yr] + DA[yr] - (avg_CapEx/Revenue * Revenue[yr])
      owner_eps.append(oe)
  avg_owner_eps = sum(owner_eps) / len(owner_eps)
  ```  
  Then use `avg_owner_eps` as the DCF base.  Document this choice or let the user switch between “latest-year” vs “normalized” in code/config.  

- **Working Capital (Optional):** If adding WC adjustments, fetch `us-gaap:ChangeInOperatingAssetsAndLiabilities` or derive change in net working capital from balance sheet changes.  Subtract increases in working capital from owner earnings.  

- **Growth Projection:** Replace single CAGR with a more robust algorithm: if all historical NI values are positive, compute annual growth rates and use their median.  If any values are ≤0, remain with flat or use revenue growth as proxy.  For example:  
  ```python
  yoy_growth = [ (NI[i]/NI[i-1] - 1) for i in range(1,len(NI)) if NI[i-1]>0 ]
  if yoy_growth: g = median(yoy_growth)
  else: g = default 5%
  g = max(g, 0)  # enforce floor
  g = min(g, 0.15) # cap at 15%
  ```  
  Also consider multi-stage DCF: e.g. 2% growth for 5 years then 0–3% terminal growth.  This is more work but better for turnarounds.  

- **Discount Rate Tiers:** Implement a rule linking `UserConfig.discount_rate` to quality.  For example:  
  ```python
  if quality_score < 40 and discount_rate < 0.10:
      discount_rate = 0.10
  ```  
  This enforces a higher risk premium on low-quality firms.  

- **Sensitivity Outputs:** Code the output to include intrinsic value at discount ±1% and ±2%.  E.g. output a small table or multiple IV figures for r-2%, r-1%, r, r+1%, r+2%.  (Similarly, you could show IV at growth = g-1%, g, g+1% as an extra if desired.)  This makes clear how fragile the DCF is to input changes.  

- **Quality Score Calculation:** Fetch historical equity to compute ROE each year (`ROE_year = NI_year / Equity_year`).  Then the ROE sub-score = 40 × (fraction of years ROE>15%).  For debt, ensure you calculate “years to repay” using average owner earnings (or use latest OE) so the sub-score reflects current burden.  In Margin Trend, clarify the formula in code: e.g.  
  ```python
  margin1 = average(net_income[i]/revenue[i] for i in first_half_years)
  margin2 = average(net_income[i]/revenue[i] for i in second_half_years)
  if margin2 >= 1.02 * margin1: score_margin = 30
  elif margin2 >= 0.95 * margin1: score_margin = 18
  else: score_margin = 0
  ```  
  Consider renaming “Margin Trend” to “Net Margin Improvement” for clarity.  

- **Unit Tests:** Write tests for each piece.  For example, supply synthetic XBRL data where capex is known and verify that owner earnings subtract maintenance correctly.  Test DCF with known values (e.g. zero growth perpetuity, single cash flow, etc.).  Validate the net debt subtraction: e.g. if cash=debt, equity value should equal EV in code.  Test quality score logic: if equity had more shares in earlier years, verify ROE adjustment.  And always test edge cases: missing data (null XBRL tags), zero or negative inputs (no division by zero, handle negatives gracefully), extremely high growth, etc.

## Output & UX Enhancements

- **Presentation:** Format outputs with clear tables or charts.  For example, a table of Year | Projected OE | Discount Factor | PV could be printed to show the DCF calculation.  A summary table with IV, market price, MOS, discount rate, growth rate, and quality score is helpful.  Use Markdown tables or aligned text for readability.  

- **Narrative Explanation:** In addition to raw numbers, provide a brief interpretation.  E.g. “At r=9% and g=2%, the intrinsic value is $X. A 36% margin of safety suggests caution given the 25% quality score. If discount rate is raised to 10%, IV falls to $Y【15†L61-L69】【34†L132-L139】.”  This ties the math to intuition.  

- **Scenarios:** Optionally include a “bear case/base case/bull case” summary by varying growth.  For instance, show IV if growth = 0%, 2%, 4% (with same discount) to illustrate the effect of growth assumptions.  Similarly, chart how IV moves with the discount rate (as suggested).  

- **UX Inputs:** Allow the user to override default assumptions easily.  Document each parameter (e.g. what if discount rate = 8% vs 9%).  If building a UI, sliders or input boxes for r and g can be provided, with IV updating.  If CLI, ensure prompts or config files are clear.  

- **Data Verification:** After fetching EDGAR data, display key inputs (e.g. last 3 years of net income, D&A, CapEx, Debt, Cash) so users can verify the inputs.  Highlight any interpolations or defaults used.  

- **Alert Flags:** If quality score is low or MOS is extreme, output a flag or warning (e.g. **“Low quality (score 20) – intrinsic value is highly uncertain”**).  Similarly, if net debt is large, note it explicitly.  Users should not miss that a 30% discount at 4% r (like Gemini’s Ford case) is likely a quirk, not a sure buy.

## Prioritized Implementation Roadmap

1. **EV→Equity Bridge (High, ~4 days):** Fetch cash from XBRL and subtract net debt in `calculate_intrinsic_value()`. This corrects intrinsic value for leverage.  
2. **Owner Earnings Averaging (High, ~2 days):** Compute 3–5 year average owner earnings or median growth, instead of single year. Flag this in docs.  
3. **Sensitivity Output (High, ~2 days):** Extend output to include IV at r±1–2% (and optionally at g±1%). This reveals model risk.  
4. **Expanded Tag Handling (High, ~3 days):** Update data-extraction code with additional XBRL fallbacks (e.g. add `SalesRevenueNet`, `SalesRevenueGoodsNet` for Revenue【29†L157-L164】). Ensure shares, equity, and debt have robust alternatives.  
5. **Quality Score Improvements (Medium, ~3 days):** Recalculate ROE per year using annual equity; refine Debt and Margin scoring as described. Optionally add one more metric (e.g. cash flow stability).  
6. **Growth Projection Robustness (Medium, ~4 days):** Implement median YoY growth and multi-stage DCF framework (e.g. different 5-year vs terminal growth). Clamp terminal growth ≤ GDP (≈3%). Provide option for user input of a growth path.  
7. **Discount Rate by Risk (Low, ~2 days):** Enforce a floor on discount rate for low-quality firms. Possibly tie the default r to a CAPM or historical market return.  
8. **Working Capital Adjustment (Low, ~3 days):** (Optional) Add change in net working capital to owner earnings if material. Requires pulling current and prior assets/liabilities from XBRL.  
9. **Consensus Benchmark (Low, ~3 days):** Integrate a third-party price target or analyst consensus as a reality check. (Could pull from Yahoo Finance or an API, if allowed.)  
10. **Testing Suite (Ongoing):** Throughout development, write unit tests. Include test cases for extreme values (e.g. negative earnings, zero growth) and for each new feature.  

Each task’s effort is rough – some can be parallelized.  High-priority fixes (debt bridge, owner earnings smoothing, sensitivities) should come first, as they materially affect valuations. Lower-priority items (additional ratios, benchmarks) enhance but aren’t urgent.  

By addressing these gaps and rigorously testing, the calculator will better reflect Buffett’s principles (emphasizing cash flow and safety) and avoid the pitfalls shown in the Gemini/Ford example【15†L61-L69】【13†L319-L327】.

**Sources:** The improvements above follow Buffett’s teachings and valuation best practices【13†L319-L327】【15†L61-L69】【29†L157-L164】【34†L132-L139】, SEC XBRL conventions, and common financial modeling guidelines. Each suggestion is grounded in these authoritative references.