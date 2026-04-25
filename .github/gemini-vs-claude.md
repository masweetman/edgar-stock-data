I asked Gemini to calculate the MOS for Ford (F) to help train you. Here is what it said:

To calculate the **Margin of Safety (MOS)** for Ford (F), we apply the Buffett logic using current 2026 financial data. 

Buffett’s method is notoriously conservative, particularly for capital-intensive industries like automotive. While Ford’s "Free Cash Flow" (FCF) looks healthy, Buffett would scrutinize how much of that cash is truly "owner earnings" versus money that *must* be reinvested just to stay competitive.

---

### 1. The Inputs (April 2026 Data)
* **Current Stock Price:** **$12.35**
* **Shares Outstanding:** **4.01 Billion**
* **2026 Projected Owner Earnings (FCF Guidance):** **$5.5 Billion** (Mid-point of $5B–$6B range)
* **Discount Rate ($r$):** **4.31%** (Current 10-Year Treasury Yield)
* **Perpetual Growth Rate ($g$):** **2%** (Conservative estimate for a mature industry)

---

### 2. The Calculation (Simplified DCF)
To find the Intrinsic Value per share, we first find the **Terminal Value** (the value of all future cash flows) and then discount it back to today.

$$Intrinsic\ Value = \frac{Owner\ Earnings}{r - g}$$

$$Intrinsic\ Value = \frac{\$5.5B}{0.0431 - 0.02} = \frac{\$5.5B}{0.0231} \approx \$238.1\ Billion$$

Now, we divide by the total number of shares to get the value per share:
$$\$238.1B \div 4.01B\ shares = \mathbf{\$59.38\ per\ share}$$

---

### 3. The Margin of Safety (MOS) Result
The MOS is the difference between what the company is "worth" ($59.38) and what you pay ($12.35).

$$MOS = 1 - \left( \frac{\$12.35}{\$59.38} \right) = \mathbf{79.2\%}$$

---

### 4. The "Buffett" Reality Check
While a **79% Margin of Safety** looks like an incredible "Buy" signal, the AI model would add a **Predictability Score** that might lower the enthusiasm. Here is why:

* **The "Lumpiness" Factor:** Ford’s net income is highly volatile (it reported a significant net loss in 2025 despite high revenue). Buffett prefers the "boring" predictability of a See's Candies or a Coca-Cola.
* **Capital Intensity:** Ford is spending **$10 Billion a year** on CapEx. In Buffett's view, a company that has to spend that much just to keep its market share has a "weak moat" compared to a software company with low CapEx.
* **Debt:** Ford has a massive debt load (largely due to Ford Credit). A strict Buffett AI would penalize the score because the interest payments eat into the "safety" of those earnings.

**Final Verdict:** Quantitatively, the MOS is huge (**79%**). Qualitatively, the AI would likely flag Ford as a **Medium-Risk Value Play** rather than a "Buffett Sure Thing" because of the inconsistent earnings history and high debt.

Then, I asked Claude to review and challenge Gemini's calculations. Here is what it said:

This is a good starting point but has some significant methodological flaws worth flagging before you build this into a tool. Let me break them down from most critical to stylistic.Good timing — Ford is currently trading around $12.48, so the price input is roughly accurate. But there are several serious problems with the analysis, ranging from a fatal math error to flawed assumptions. Here's the full breakdown:

---

## 🔴 Critical Errors

### 1. The EV → Equity Bridge is Missing (The Biggest Flaw)

This is the most consequential mistake. The Gordon Growth Model formula produces **Enterprise Value** — the value of the whole business — not equity value for shareholders. You must subtract net debt to arrive at equity value.

Ford is not a normal industrial company. Ford Credit is essentially an embedded bank. Ford Motor Credit carried approximately $134 billion in debt as of early 2025. Even if you treat Ford Credit as a self-funding financial subsidiary and only deduct the automotive segment's net debt (roughly $5–10B), the omission still meaningfully distorts the per-share result. Treating $238B of enterprise value as if it were directly divisible into equity value per share is a fundamental DCF error.

**The corrected math, even being generous:** $238B − ~$10B (automotive net debt) ÷ 4.01B shares = ~$57/share — still a large MOS, but the principle matters enormously for companies with heavier leverage.

---

### 2. The Discount Rate is Dangerously Low

Using the 10-year Treasury yield (4.31%) as the discount rate for Ford produces a near-magical valuation because the denominator (r − g = 2.31%) is paper-thin. **This is a misapplication of how Buffett actually uses the risk-free rate.**

Buffett discounts at the risk-free rate *only* for businesses with near-certain, highly predictable cash flows — think Coca-Cola or See's Candies. He then demands a large MOS as his additional risk buffer. For a cyclical, capital-intensive automaker undergoing a costly EV transition, a practitioner would typically require 8–12% as a required return.

**Sensitivity test — the model breaks under scrutiny:**

| Discount Rate | Intrinsic Value/Share |
|---|---|
| 4.31% (used) | $59.38 |
| 7.00% | $27.35 |
| 9.00% | $18.18 |
| 10.00% | $14.53 |

At 10%, the MOS nearly vanishes entirely. The model's conclusion is almost entirely a function of this one aggressive input.

---

### 3. FCF Guidance ≠ Owner Earnings

The analysis conflates Ford's own adjusted FCF guidance with Buffett's concept of "owner earnings." These are not the same thing.

Buffett's formula: **Owner Earnings = Net Income + D&A − Maintenance CapEx**

The critical question is: of Ford's ~$8–10B annual CapEx, how much is *maintenance* (just to stay competitive) versus *growth* (genuinely discretionary)? For an automaker facing EV platform retooling, UAW obligations, and platform upgrades, the vast majority is likely maintenance in nature. Gemini acknowledges this concern qualitatively but then ignores it quantitatively by using the full $5.5B figure unchallenged.

Additionally, Ford's FCF guidance had already become unreliable. Ford's adjusted operating margin was only 3.6% in 2025, compared to 6.8% in 2015 — using peak-ish guidance as the perpetuity base is optimistic.

---

## 🟡 Methodological Issues

### 4. Single-Stage Perpetuity Is Inappropriate Here

The Gordon Growth Model assumes Ford grows at exactly 2% forever, *starting today*. But Ford is actively losing money on EVs, faces significant tariff headwinds, and saw an 8.8% year-over-year decline in Q1 2026 US deliveries, with F-Series pickup sales down 16%. A proper model would use a two- or three-stage DCF: lower or negative near-term free cash flow growth, transitioning to a terminal growth rate after stabilization.

### 5. Model Sensitivity Is Never Disclosed

With r − g = 2.31%, the model is extraordinarily fragile. A 0.5% change in either variable swings intrinsic value by 15–25%. Any AI valuation tool should automatically surface a sensitivity table — this is arguably more useful than the point estimate itself.

### 6. The Morningstar Sanity Check Is Missing

Morningstar's analyst fair value estimate for Ford is $32/share, with a 5-star (strong buy) price of $76.30. The $59.38 figure from Gemini sits near the top of Morningstar's range — not impossible, but it signals that the assumptions used are on the optimistic end, not the conservative end. A credible tool should benchmark against third-party estimates.

---

## ✅ What Gemini Got Right

- The qualitative caveats (lumpiness, capital intensity, debt) are legitimate and well-framed
- The "Predictability Score" concept is the right instinct — it acknowledges the model's limits
- The conservative growth rate (2%) is reasonable
- The stock price input (~$12.35) is accurate

---

## Recommended Improvements for Your Tool

For a rigorous AI valuation tool, here's what should be added:

1. **Enforce the EV → Equity bridge**: Subtract net debt (and flag Ford Credit separately)
2. **Use a risk-adjusted discount rate**: Either WACC, or a tiered rate based on earnings predictability (e.g., 5% for Coca-Cola, 10% for Ford)
3. **Separate maintenance from growth CapEx**: Use normalized owner earnings, not company-guided FCF
4. **Multi-stage DCF**: Near-term stress period → terminal value
5. **Auto-generate sensitivity tables**: Show the valuation at ±1% on both r and g
6. **Third-party benchmark**: Pull Morningstar/analyst consensus fair value as a sanity check
7. **Flag withdrawn or revised guidance**: Ford's 2026 guidance is materially uncertain due to tariff exposure — the tool should note when inputs are unreliable

The 79% MOS conclusion isn't necessarily wrong directionally, but it's built on assumptions that happen to point in the same favorable direction. A tool meant to replicate Buffett's *conservatism* should stress-test assumptions, not cherry-pick them.