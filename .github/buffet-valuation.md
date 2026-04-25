Teaching an AI to perform a Buffett-style valuation requires moving beyond simple arithmetic to **pattern recognition**. The goal is for the AI to not just "do the math," but to assess the **predictability** of the company, which is the cornerstone of Buffett’s philosophy.

Below is a structured plan to build an AI scoring model based on Owner Earnings and Intrinsic Value.

---

## 1. The Data Ingestion Layer (Inputs)
To calculate a Buffett score, the AI needs three categories of data. It should pull these from 10-K filings, quarterly reports (10-Q), and market data APIs.

### A. Core Financial Inputs (Quantitative)
* **Net Income:** The starting point for earnings.
* **Non-Cash Charges:** Depreciation, Amortization, and Depletion.
* **Capital Expenditures (CapEx):** Split into **Maintenance CapEx** (keeping the lights on) and **Growth CapEx** (expanding).
* **Long-term Debt:** To ensure the company isn't fueling growth with "junk" debt.
* **Shareholder Equity:** To calculate Return on Equity (ROE).
* **Shares Outstanding:** To convert total value into a per-share price.

### B. Historical Trend Inputs (Consistency)
* **10-Year History:** Revenue, net income, and free cash flow over a decade.
* **Operating Margins:** To check for "pricing power" (high, stable margins are key).

### C. Macro Inputs (The Discounting Factor)
* **Risk-Free Rate:** Usually the 10-year or 30-year Treasury Bond yield.
* **Market Price:** The current trading price to compare against the intrinsic value.

---

## 2. The Logic Engine (Calculations & Outputs)
The AI should process the inputs through four distinct logical stages to arrive at a final score.

### Stage 1: The "Owner Earnings" Filter
The AI calculates true cash flow rather than GAAP accounting profit.
$$Owner\ Earnings = Net\ Income + (Depreciation + Amortization) - Maintenance\ CapEx$$
*Note: If a company doesn't report maintenance CapEx separately, the AI can estimate it by looking at the 5-year average of CapEx vs. Sales.*

### Stage 2: The Multi-Stage DCF Model
The AI projects the future value of those earnings.
* **Years 1–10:** Apply a "Growth Rate" based on historical ROE and retained earnings.
* **Terminal Value:** A "forever" growth rate (usually 2–3%, roughly matching inflation/GDP).
* **Present Value ($PV$):** All these future dollars are brought back to today's value using the Discount Rate ($r$):
$$PV = \frac{CF}{(1+r)^n}$$

### Stage 3: The "Buffett Quality" Score
The AI assigns a 0–100 score based on qualitative-turned-quantitative metrics:
* **ROE Check:** Is ROE > 15% consistently?
* **Debt Check:** Can the company pay off its long-term debt with < 3 years of owner earnings?
* **Moat Check:** Are operating margins widening or stable over 10 years?

### Stage 4: Margin of Safety (MOS)
The AI calculates the final "Buy/Wait/Avoid" signal.
$$MOS = 1 - \left( \frac{\text{Market Price}}{\text{Intrinsic Value}} \right)$$

---

## 3. AI Training & Execution Plan

| Step | Action | Objective |
| :--- | :--- | :--- |
| **1. Data Labeling** | Feed the AI historical data of Berkshire Hathaway's actual buys (e.g., Coke in 1988, Apple in 2016). | Teach the AI what a "Buffett-style" financial profile looks like before a big run. |
| **2. Regression Analysis** | Train the model to correlate historical owner earnings with future stock performance. | Improve the accuracy of the "Growth Rate Projection." |
| **3. Sentiment Analysis** | Use NLP to scan CEO letters and earnings calls for mentions of "competitive advantage" or "pricing power." | Add a qualitative "Moat" score to the quantitative DCF. |
| **4. Stress Testing** | Run the model through different discount rates (e.g., 5% vs 10%). | Determine how sensitive the "Intrinsic Value" is to interest rate changes. |

### Final Output: The "Buffett Dashboard"
The AI should output a report for any ticker containing:
1.  **Intrinsic Value:** e.g., "$150.00"
2.  **Current Price:** e.g., "$100.00"
3.  **MOS Percentage:** "33% (Strong Buy)"
4.  **Quality Score:** "88/100 (High Predictability)"

**Would you like to see a Python code snippet demonstrating how the AI would calculate the Maintenance CapEx portion specifically?**