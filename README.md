# 13F Holdings Sentiment Analysis and Backtesting Pipeline

## Overview

This project implements a Python-based pipeline to analyze 13F filings from the SEC EDGAR database. The primary goal is to derive sentiment signals for various stocks based on the holdings of selected "Smart Money" institutional investors and then backtest trading strategies based on these signals. The pipeline automates data acquisition, processing, signal generation, historical price fetching, and strategy backtesting.

## Pipeline Stages

The project follows a sequential data processing and analysis flow:

1.  **Data Acquisition (13F Filings):** `edgar_scraper.py` fetches 13F filing documents (primary document and information table) from the SEC EDGAR database for specified CIKs or filing URLs.
2.  **Data Processing & Cleaning:** `process_13f_data.py` parses the downloaded filings (HTML primary documents and XML/HTML information tables) to extract detailed holdings data (issuer name, CUSIP, value, quantity) and the crucial reporting date for each filing.
3.  **Smart Money Filtering:** `filter_smart_money.py` filters the consolidated holdings data to include only records from a predefined list of "Smart Money" investor CIKs.
4.  **Sentiment Signal Construction:** `construct_sentiment_signal.py` aggregates the Smart Money holdings per stock (CUSIP) and reporting period, calculates changes in these holdings (e.g., change in total value, number of investors), and computes a sentiment score.
5.  **Historical Price Acquisition:** `get_price_history.py` fetches historical OHLCV (Open, High, Low, Close, Volume) price data for the CUSIPs identified in the sentiment signals, using a CUSIP-to-Ticker mapping.
6.  **Backtesting & Iteration:** `backtest_strategy.py` simulates a trading strategy based on the generated sentiment scores and historical price data, calculating various performance metrics. Strategy parameters can be iterated upon to observe different outcomes.

## Scripts Description

The pipeline consists of the following Python scripts:

*   **`edgar_scraper.py`**
    *   **Purpose:** Downloads 13F filing documents (primary document and information table) from the SEC EDGAR database.
    *   **Key Inputs:** Can be configured to run based on a list of CIKs and number of recent quarters, or a direct list of SEC filing page URLs.
    *   **Key Outputs:** Saves downloaded files (e.g., `CIK_ACCESSION_primary.xml`, `CIK_ACCESSION_infotable.xml`) into the `13f_filings/` directory.

*   **`process_13f_data.py`**
    *   **Purpose:** Parses the downloaded filing documents to extract detailed holdings information and the reporting date for each filing.
    *   **Key Inputs:** Reads files from the `13f_filings/` directory.
    *   **Key Outputs:** Produces `processed_13f_data/consolidated_13f_holdings.csv` containing all extracted holdings data.

*   **`filter_smart_money.py`**
    *   **Purpose:** Filters the consolidated holdings data to retain only records from a specified list of "Smart Money" CIKs.
    *   **Key Inputs:** `processed_13f_data/consolidated_13f_holdings.csv`, a predefined list of `SMART_MONEY_CIKS` within the script.
    *   **Key Outputs:** `processed_13f_data/smart_money_holdings.csv`.

*   **`construct_sentiment_signal.py`**
    *   **Purpose:** Calculates sentiment scores for each stock (CUSIP) based on changes in Smart Money holdings over different reporting periods.
    *   **Key Inputs:** `processed_13f_data/smart_money_holdings.csv`.
    *   **Key Outputs:** `processed_13f_data/sentiment_signals.csv`, including CUSIP, reporting date, aggregate holding metrics, changes in these metrics, and the calculated sentiment score.

*   **`get_price_history.py`**
    *   **Purpose:** Downloads historical OHLCV stock price data for CUSIPs identified in the sentiment signals.
    *   **Key Inputs:** `processed_13f_data/sentiment_signals.csv` (to get unique CUSIPs and date ranges), a CUSIP-to-Ticker map within the script.
    *   **Key Outputs:** Individual CSV files for each ticker (e.g., `AAPL.csv`) in the `price_data/` directory.

*   **`backtest_strategy.py`**
    *   **Purpose:** Simulates a trading strategy based on the generated sentiment signals and historical price data. The strategy implements quarterly rebalancing:
        *   Trading decisions are made on a quarterly basis, aligned with 13F reporting dates (with a configurable `SIGNAL_LAG_DAYS`).
        *   On these rebalancing days, all existing positions in the portfolio are liquidated.
        *   New positions are then established based on the latest quarterly sentiment signals.
    *   **Capital Allocation:** For new buy positions, capital is allocated using a **score-weighted** approach:
        *   Stocks with higher positive sentiment scores (those meeting the `BUY_THRESHOLD`) receive a proportionally larger share of the available cash.
        *   If the sum of positive scores for eligible stocks is zero or negative, the allocation falls back to an equal-weight distribution among eligible stocks.
    *   **Key Inputs:** `processed_13f_data/sentiment_signals.csv`, price data from `price_data/`, strategy parameters (e.g., `BUY_THRESHOLD`, `INITIAL_CAPITAL`, `SIGNAL_LAG_DAYS`).
    *   **Key Outputs:**
        *   Console output of performance metrics (Total Return, Sharpe Ratio, etc.).
        *   `backtest_results/portfolio_daily_performance.csv` (daily portfolio value).
        *   `backtest_results/trades_log.csv` (log of executed trades).
        *   `backtest_results/quarterly_portfolio_composition.csv` (detailed portfolio holdings after each rebalance).

*   **`rl_optimizer_concept.py`**
    *   **Purpose:** A conceptual script outlining how Reinforcement Learning could be applied to optimize parameters (like buy/sell thresholds) of the `backtest_strategy.py`.
    *   **Note:** This script is for illustration and does not implement a working RL algorithm.

## Setup and Dependencies

*   **Python:** Python 3.8+ is recommended.
*   **Libraries:** The main libraries used are:
    *   `requests` (for HTTP requests to SEC EDGAR)
    *   `BeautifulSoup4` (for parsing HTML/XML content)
    *   `lxml` (as a parser for BeautifulSoup, install separately if needed)
    *   `pandas` (for data manipulation and CSV handling)
    *   `numpy` (for numerical operations, often a dependency of pandas)
    *   `yfinance` (for downloading historical stock price data)
*   **`requirements.txt`:** It is recommended to create a `requirements.txt` file:
    ```
    requests
    beautifulsoup4
    lxml
    pandas
    numpy
    yfinance
    ```
    Install dependencies using: `pip install -r requirements.txt`

## Running the Pipeline (Step-by-Step Guide)

### 1. Configuration

Before running the pipeline, configure the following in the respective scripts:

*   **`edgar_scraper.py`**:
    *   **User-Agent:** Ensure the `HEADERS['User-Agent']` is set to a compliant string (e.g., `'MyCompanyName MyContactEmail@example.com'`) as per SEC guidelines.
    *   **Data Collection Mode:**
        *   **By CIKs & Quarters:** Modify the `main()` function's call (in the `if __name__ == "__main__":` block) to specify `ciks_to_fetch` (list of CIK strings) and `num_quarters_to_fetch`.
            ```python
            # Example for CIKs and number of quarters
            main(ciks_to_fetch=['CIK1', 'CIK2'], num_quarters_to_fetch=8)
            ```
        *   **By Specific URLs:** Modify the `main()` function's call to pass a list of direct `target_urls`.
            ```python
            # Example for specific URLs
            target_urls = ["url1", "url2"]
            main(target_urls=target_urls)
            ```
*   **`filter_smart_money.py`**:
    *   Update the `SMART_MONEY_CIKS` list with the CIKs you consider "Smart Money" and for which you've downloaded data.
        ```python
        SMART_MONEY_CIKS = ['0001067983', '0001037389', ...]
        ```
*   **`get_price_history.py`**:
    *   The `cusip_to_ticker_map` dictionary needs to be updated with mappings for any CUSIPs you expect to process for which price data is needed. `yfinance` primarily uses ticker symbols.
        ```python
        cusip_to_ticker_map = {
            "037833100": "AAPL", # Apple
            "025816109": "AXP",  # American Express
            # Add other CUSIP:Ticker pairs
        }
        ```
*   **`backtest_strategy.py`**:
    *   Review and set `INITIAL_CAPITAL`.
    *   Adjust `BUY_THRESHOLD` and `SELL_THRESHOLD` to define your strategy's sensitivity.
    *   `SIGNAL_LAG_DAYS` can be adjusted to simulate delays in signal availability.

### 2. Data Acquisition (Scraping)

*   Run `edgar_scraper.py`:
    ```bash
    python edgar_scraper.py
    ```
*   **CRUCIAL CAVEAT:** SEC EDGAR may block frequent, automated requests (often resulting in 503 errors). The script includes delays and retries, but persistent blocking can occur.
    *   Execute cautiously, especially for large data pulls.
    *   Consider running from an environment with a fresh IP address if blocking is persistent.
    *   For the development and demonstration of this pipeline, pre-downloaded or simulated data (as created in one of the subtasks) was ultimately used to ensure subsequent scripts could run without being blocked during development iterations.

### 3. Data Processing

Execute the scripts in the following order:

1.  **Process Downloaded Filings:**
    ```bash
    python process_13f_data.py
    ```
    This parses the raw files in `13f_filings/` and creates `processed_13f_data/consolidated_13f_holdings.csv`.

2.  **Filter for Smart Money:**
    ```bash
    python filter_smart_money.py
    ```
    This filters the consolidated holdings and creates `processed_13f_data/smart_money_holdings.csv`.

3.  **Construct Sentiment Signals:**
    ```bash
    python construct_sentiment_signal.py
    ```
    This calculates sentiment scores and creates `processed_13f_data/sentiment_signals.csv`.

### 4. Price Data Acquisition

*   Run `get_price_history.py`:
    ```bash
    python get_price_history.py
    ```
    This downloads price data for CUSIPs found in `sentiment_signals.csv` (using the internal CUSIP-ticker map) and saves them into the `price_data/` directory.

### 5. Backtesting

*   Run `backtest_strategy.py`:
    ```bash
    python backtest_strategy.py
    ```
    This simulates the trading strategy and outputs performance metrics to the console and CSV files in `backtest_results/`.

## Output Files Description

*   **`13f_filings/`**:
    *   Contains the downloaded raw filing documents.
    *   `CIK_ACCESSION_primary.xml` (or `.txt`): The primary filing document (often an HTML view of the 13F-HR form). Used to extract the reporting date.
    *   `CIK_ACCESSION_infotable.xml` (or `.txt`): The information table containing the holdings data (can be raw XML or an HTML view).

*   **`processed_13f_data/consolidated_13f_holdings.csv`**:
    *   **Columns:** `filer_cik`, `reporting_date`, `name_of_issuer`, `cusip`, `value_usd`, `quantity`, `security_type`, `source_file`.
    *   **Purpose:** Contains all holdings data extracted and cleaned from all downloaded 13F filings. `value_usd` is the full dollar amount.

*   **`processed_13f_data/smart_money_holdings.csv`**:
    *   **Columns:** Same as `consolidated_13f_holdings.csv`.
    *   **Purpose:** Contains holdings data filtered to include only those from the CIKs defined in the `SMART_MONEY_CIKS` list.

*   **`processed_13f_data/sentiment_signals.csv`**:
    *   **Columns:** `cusip`, `reporting_date`, `total_sm_value`, `total_sm_shares`, `num_sm_investors`, `change_in_total_sm_value`, `change_in_total_sm_shares`, `change_in_num_sm_investors`, `pct_change_in_total_sm_value`, `pct_change_in_total_sm_shares`, `sentiment_score`.
    *   **Purpose:** Provides the calculated sentiment score and supporting metrics for each CUSIP per reporting period, based on "Smart Money" activity.

*   **`price_data/`**:
    *   Contains individual CSV files for each stock ticker (e.g., `AAPL.csv`).
    *   Each file has columns: `Date`, `Open`, `High`, `Low`, `Close`, `Adj Close`, `Volume`, `Ticker`.

*   **`backtest_results/portfolio_daily_performance.csv`**:
    *   **Columns:** `Date` (index), `total_value`.
    *   **Purpose:** Logs the total market value of the simulated portfolio on each trading day.

*   **`backtest_results/trades_log.csv`**:
    *   **Columns:** `Date`, `Ticker`, `Action` (Buy/Sell), `Price`, `Shares`, `SentimentScoreAtTrade`, `PortfolioCashBeforeTrade`, `PortfolioValueBeforeTrade`.
    *   **Purpose:** Records details of each simulated trade executed by the backtester.

*   **`backtest_results/quarterly_portfolio_composition.csv`**:
    *   **Columns:** `RebalanceDate`, `AssetType` (Stock/Cash), `Ticker`, `Shares`, `PriceAtRebalance`, `MarketValue`, `WeightInPortfolio`, `CashAfterRebalance`, `TotalPortfolioValueAfterRebalance`.
    *   **Purpose:** Logs the detailed composition of the portfolio (all stock holdings and cash) immediately after each quarterly rebalancing event, including weights and values at the time of rebalancing.

## Example Iteration

During development, an example iteration involved:
1.  Simulating 3 quarters of 13F data for Berkshire Hathaway (CIK `0001067983`).
2.  Processing this data through the pipeline. `sentiment_signals.csv` showed dynamic scores for stocks like AAPL, AXP, BAC. For example, AXP had a sentiment score of ~0.086 for 2023-12-31, while AAPL had ~0.051.
3.  Running `backtest_strategy.py` with `BUY_THRESHOLD = 0.05`. This resulted in "Buy" trades for AAPL (score ~0.051) and AXP (score ~0.086). Capital was allocated based on their relative scores (AXP receiving more due to its higher score).
4.  Changing `BUY_THRESHOLD` to `0.07`.
5.  Re-running `backtest_strategy.py`. This time, only AXP (score ~0.086) was bought, as AAPL's score (~0.051) no longer met the more stringent threshold. AXP would receive 100% of the cash allocated for buys in this scenario. This demonstrated how parameter changes directly impact strategy behavior and performance outcomes.

## Known Limitations

*   **SEC EDGAR Scraping Reliability:** Access to SEC EDGAR can be inconsistent due to rate limiting or blocking, making large-scale, frequent scraping challenging without more advanced techniques (e.g., distributed IPs, robust error handling beyond simple retries).
*   **Basic Sentiment Model:** The current sentiment score is based on simple changes in reported holdings (value, shares, number of investors). It does not incorporate more nuanced factors like the type of investor, concentration, or NLP on filing text.
*   **Backtester Simplifications:**
    *   No transaction costs (brokerage fees) or market slippage are modeled.
    *   Capital allocation is score-weighted based on sentiment signals. While more advanced than simple equal division, further refinements (e.g., risk parity, maximum position size constraints) are not yet implemented.
    *   Assumes trades execute at the next day's Open price based on signals active from the prior day's effective date (controlled by `SIGNAL_LAG_DAYS`).
*   **CUSIP-to-Ticker Mapping:** Relies on a manual, hardcoded dictionary. This is not scalable and requires constant updates for new CUSIPs. A dedicated mapping API or database would be needed for broader coverage.
*   **Simulated Data for Demo:** Due to scraping challenges during development, the final demonstrations used a manually curated set of simulated 13F data to ensure the pipeline's functionality could be tested end-to-end.

## Potential Future Enhancements

*   **Robust Scraping:** Implement more sophisticated scraping techniques, potentially using official bulk data feeds if available, or more resilient request strategies.
*   **Advanced Sentiment Models:** Incorporate NLP on management discussion, analyze changes in portfolio concentration, differentiate by investor type, or use machine learning to derive sentiment.
*   **Sophisticated Backtester:** Add support for transaction costs, slippage models, various portfolio allocation strategies (e.g., Kelly criterion, risk parity), stop-loss/take-profit orders, and more detailed performance attribution.
*   **Automated CUSIP/Identifier Mapping:** Integrate with financial data APIs (e.g., OpenFIGI, Refinitiv, Bloomberg if available) for robust CUSIP-to-Ticker and other identifier mapping.
*   **User Interface:** Develop a GUI or web interface for easier configuration, execution monitoring, and visualization of results (e.g., equity curves, sentiment trends).
*   **RL Optimization:** Fully implement the RL agent and environment outlined in `rl_optimizer_concept.py` to automatically tune strategy parameters.
*   **Database Integration:** Store downloaded filings, processed data, and signals in a database for more efficient querying and analysis.
*   **Expanded Data Sources:** Incorporate other data sources like news sentiment, macroeconomic indicators, or alternative data to enrich trading signals.
*   **Refined Signal Timing:** More accurately model the delay between the actual quarter end (`reportingDate` from the 13F primary document), the filing date of the 13F, and when this information would realistically be processed and actionable.
*   **Handling of Amendments:** The current scraper logic for selecting unique quarters might pick an amendment over an original filing or vice-versa based purely on filing date. A more robust approach would identify original (13F-HR) and amended (13F-HR/A) filings for the same reporting period and decide how to use them (e.g., always use the latest amendment, or consolidate data).


## Generating a 5-Year Dataset for Comprehensive Backtesting

To perform robust backtesting over a longer period (e.g., 5 years) and with a diversified set of "Smart Money" managers, follow these data generation steps. This involves configuring the EDGAR scraper, processing the downloaded data, and fetching extensive historical price data.

**Assumptions:**
*   You have a list of CIKs for the "Smart Money" managers you wish to track.
*   The Python environment is set up with all necessary libraries (see "Setup and Dependencies" section).

**Step 1: Configure and Run `edgar_scraper.py`**

1.  **Edit `edgar_scraper.py`:**
    *   **User-Agent:** Ensure `HEADERS['User-Agent']` is set to a compliant string (e.g., `'YourCompanyName YourContactEmail@example.com'`) as per SEC guidelines to avoid being blocked.
    *   **Target CIKs and Quarters:** Modify the `main()` function call within the `if __name__ == "__main__":` block.
        *   `ciks_to_fetch`: Provide a list of CIK strings for your chosen "Smart Money" managers. For a diversified analysis, aim for 10-20 reputable managers known for long-term investments.
            ```python
            # Example for CIKs and number of quarters
            ciks_to_fetch = ['CIK1', 'CIK2', '...', 'CIK20'] # Replace with actual CIKs
            num_quarters_to_fetch = 20 # For 5 years (4 quarters/year * 5 years)
            main(ciks_to_fetch=ciks_to_fetch, num_quarters_to_fetch=num_quarters_to_fetch)
            ```
        *   Alternatively, if you have specific filing URLs spanning the desired period for your selected managers, you can use the `target_urls` parameter.

2.  **Run the Scraper:**
    ```bash
    python edgar_scraper.py
    ```
    *   **Important Considerations:**
        *   This step can take a significant amount of time, especially for many CIKs and quarters. Plan accordingly.
        *   SEC EDGAR may rate-limit or block frequent, automated requests. The script includes some delays, but persistent issues may require running the script in smaller batches (e.g., fewer CIKs or quarters at a time) or from different IP addresses if possible.
        *   Ensure sufficient disk space for downloaded filings in the `13f_filings/` directory. A 5-year dataset for 20 managers can result in hundreds of filings.

**Step 2: Process Downloaded 13F Filings**

1.  **Run `process_13f_data.py`:** This script parses the raw filings from `13f_filings/` and creates the `processed_13f_data/consolidated_13f_holdings.csv` file. This step can also be time-consuming if many filings were downloaded.
    ```bash
    python process_13f_data.py
    ```

**Step 3: Filter for Smart Money Holdings**

1.  **Edit `filter_smart_money.py`:**
    *   Update the `SMART_MONEY_CIKS` list in this script to match *exactly* the CIKs you used in `edgar_scraper.py` in Step 1. This ensures consistency in your dataset.
        ```python
        SMART_MONEY_CIKS = ['CIK1', 'CIK2', '...', 'CIK20'] # Must match CIKs from Step 1
        ```

2.  **Run `filter_smart_money.py`:** This filters the consolidated data and creates `processed_13f_data/smart_money_holdings.csv`.
    ```bash
    python filter_smart_money.py
    ```

**Step 4: Construct Sentiment Signals**

1.  **Run `construct_sentiment_signal.py`:** This script uses `smart_money_holdings.csv` to calculate sentiment scores based on changes in holdings and generates `processed_13f_data/sentiment_signals.csv`.
    ```bash
    python construct_sentiment_signal.py
    ```
    *   For initial data generation, the default `WEIGHT_` parameters within this script can be used. You might experiment with these weights later for comparative strategy analysis by regenerating this signals file with different settings.

**Step 5: Acquire Historical Price Data**

1.  **Edit `get_price_history.py`:**
    *   **CUSIP-to-Ticker Mapping (`cusip_to_ticker_map`):** This is a critical and potentially laborious step. The script needs to map CUSIPs (from `sentiment_signals.csv`) to ticker symbols that `yfinance` can use.
        *   You will likely need to significantly expand the `cusip_to_ticker_map` dictionary to cover all unique CUSIPs present in your 5-year `sentiment_signals.csv`. This map is essential for fetching the correct price data.
        *   For CUSIPs that `yfinance` cannot find (e.g., delisted stocks, different ticker symbol conventions), you may need to find alternative ticker symbols or accept that price data might not be available for all CUSIPs.
        *   Consider using external data sources or APIs for more robust CUSIP-to-Ticker mapping if dealing with a very large and diverse set of CUSIPs. This script currently relies on a manual map.
    *   **Date Range:** The script automatically determines the required date range from the earliest `reporting_date` in your `sentiment_signals.csv`. `yfinance` will attempt to fetch data for this entire period.

2.  **Run `get_price_history.py`:**
    ```bash
    python get_price_history.py
    ```
    *   This will download historical price data for all successfully mapped tickers and save them as individual CSV files in the `price_data/` directory.
    *   This step can also be very time-consuming, depending on the number of unique tickers and the length of the historical period. It requires a stable internet connection.
    *   Monitor for any errors from `yfinance` regarding missing tickers.

**Step 6: Verify Data and Prepare for Backtesting**

*   **Review Output Files:**
    *   Inspect `processed_13f_data/sentiment_signals.csv`: Check the number of unique CUSIPs, the range of `reporting_date`s, and the distribution of sentiment scores.
    *   Inspect the `price_data/` directory: Verify that CSV files have been created for the majority of your expected tickers. Check a few files for correct OHLCV data and date ranges.
*   **Consistency Checks:**
    *   Ensure the date ranges in your price data align with the dates in your sentiment signals.
    *   Note any CUSIPs for which price data could not be fetched; these cannot be included in backtests that require daily pricing.
*   **Backup Your Dataset:** Once generated, consider backing up the `processed_13f_data/` and `price_data/` directories, especially if the generation process was lengthy.

You are now ready to run `backtest_strategy.py` using this comprehensive 5-year dataset. Remember to use the command-line arguments to point the backtester to your generated files if they differ from default paths, and to experiment with different strategy parameters (e.g., `--buy_threshold`, `--signal_lag_days`, `--run_name_suffix`).

This detailed data generation process, while intensive, is crucial for conducting meaningful long-term backtests and deriving more reliable insights from your strategy analysis.


## Strategy for Comparative Analysis and Iteration

After generating a comprehensive dataset (e.g., 5 years) and refactoring `backtest_strategy.py` for parameterized runs, you can perform comparative analysis to find optimal strategy configurations. The goal is to improve risk-adjusted returns while meeting diversification objectives.

**1. Baseline Backtest Run**

*   Start with a baseline run using the default or initial set of parameters on your full dataset.
    ```bash
    python backtest_strategy.py --signals_file "processed_13f_data/sentiment_signals.csv" --price_dir "price_data/" --output_dir "backtest_results/" --initial_capital 100000.0 --buy_threshold 0.07 --signal_lag_days 1 --run_name_suffix "_baseline"
    ```
*   Carefully record the performance metrics and analyze the output CSVs (`portfolio_daily_performance_baseline.csv`, `trades_log_baseline.csv`, `quarterly_portfolio_composition_baseline.csv`). This is your benchmark.

**2. Iterative Parameter Adjustment and Analysis**

Change one key parameter at a time to understand its impact. Use the `--run_name_suffix` to save results for each run in a uniquely named set of files. This ensures that results from different runs are stored separately for easy comparison.

**A. Varying `buy_threshold`:**
*   This threshold determines the sensitivity to sentiment scores for initiating positions. A lower threshold means the strategy will act on weaker signals, while a higher threshold requires stronger conviction.
*   Test a range of values, for example:
    ```bash
    # Example: Test a lower threshold
    python backtest_strategy.py --buy_threshold 0.03 --run_name_suffix "_thresh0.03" # ... other params as baseline ...
    # Example: Test a slightly lower threshold
    python backtest_strategy.py --buy_threshold 0.05 --run_name_suffix "_thresh0.05" # ... other params as baseline ...
    # Example: Test a higher threshold
    python backtest_strategy.py --buy_threshold 0.10 --run_name_suffix "_thresh0.10" # ... other params as baseline ...
    ```
*   **Analysis:**
    *   Lower thresholds might lead to more positions being taken. This could improve diversification if many stocks have weaker positive signals, but it might also introduce lower quality (less predictive) signals into the portfolio.
    *   Higher thresholds will likely result in fewer, higher-conviction positions. This could lead to higher concentration if not managed by other diversification rules (like the 40% max weight).
    *   Observe the impact on total returns, Sharpe ratio, maximum drawdown, the average number of holdings per rebalance, and the frequency of hitting max concentration limits.

**B. Varying `signal_lag_days`:**
*   This parameter simulates delays in processing 13F data and making it actionable. Realistically, 13F filings are due 45 days after the quarter-end, and processing takes additional time.
*   Test values reflecting realistic delays. The default might be very optimistic (e.g., 1 day).
    ```bash
    python backtest_strategy.py --signal_lag_days 5 --run_name_suffix "_lag5" # ... other params ...
    python backtest_strategy.py --signal_lag_days 15 --run_name_suffix "_lag15" # ... other params ...
    python backtest_strategy.py --signal_lag_days 30 --run_name_suffix "_lag30" # ... other params ...
    python backtest_strategy.py --signal_lag_days 45 --run_name_suffix "_lag45" # ... other params ...
    python backtest_strategy.py --signal_lag_days 50 --run_name_suffix "_lag50" # Simulating actionable date post-filing deadline
    ```
*   **Analysis:** Longer lags are expected to erode performance as the sentiment signals become stale. Quantify this erosion by observing changes in returns and other performance metrics. This helps understand the strategy's sensitivity to information delay.

**C. Varying "Smart Money" CIK List (More Involved):**
*   The definition of "Smart Money" (i.e., the list of CIKs used) is a fundamental driver of signal quality.
*   **Process:**
    1.  Prepare different lists of CIKs. For example, save them in text files (e.g., `smart_money_value_investors.txt`, `smart_money_tech_focused.txt`).
    2.  You would need to modify `filter_smart_money.py` to accept a CIK list file as an argument or temporarily change its internal `SMART_MONEY_CIKS` list.
    3.  Re-run `python filter_smart_money.py`.
    4.  Re-run `python construct_sentiment_signal.py`. This will generate a new `sentiment_signals.csv` based on the chosen CIK set. It's advisable to save this signals file with a descriptive name (e.g., `sentiment_signals_value_investors.csv`).
    5.  Run `backtest_strategy.py` using the newly generated signals file:
        ```bash
        python backtest_strategy.py --signals_file "processed_13f_data/sentiment_signals_value_investors.csv" --run_name_suffix "_cik_value" # ... other params ...
        ```
*   **CIK Categories to Test (Examples):**
    *   **Concentrated "Gurus":** Managers known for high-conviction, relatively concentrated portfolios.
    *   **Value-Oriented Managers:** Funds adhering to value investing principles.
    *   **Growth-Oriented Managers:** Funds focusing on growth stocks.
    *   **Sector Specialists:** Managers focusing on specific sectors (e.g., technology, healthcare).
    *   **Highly Diversified Managers:** Larger funds that tend to hold many positions.
*   **Analysis:** Compare performance metrics (returns, Sharpe, drawdown) and portfolio characteristics (e.g., sector biases, average holding period implied by signal changes, volatility) resulting from different manager groups. This can reveal which types of "Smart Money" provide the most alpha for this particular sentiment definition.

**D. Varying Sentiment Score Weights (More Involved):**
*   The weights in `construct_sentiment_signal.py` (e.g., `WEIGHT_CHANGE_NUM_INVESTORS`, `WEIGHT_PCT_CHANGE_VALUE`, `WEIGHT_PCT_CHANGE_SHARES`) determine how different aspects of 13F holding changes contribute to the final sentiment score.
*   **Process:**
    1.  Edit the weight constants at the top of `construct_sentiment_signal.py`.
    2.  Re-run `python construct_sentiment_signal.py`. Save the output `sentiment_signals.csv` with a descriptive name (e.g., `sentiment_signals_weights_v2.csv`).
    3.  Run `backtest_strategy.py` with the new signals file:
        ```bash
        python backtest_strategy.py --signals_file "processed_13f_data/sentiment_signals_weights_v2.csv" --run_name_suffix "_weights_v2" # ... other params ...
        ```
*   **Analysis:** Observe how changing the emphasis (e.g., giving more weight to the number of investors versus the percentage change in value) affects the quality of signals and the resulting backtest outcomes.

**3. Evaluation and Decision Making**

*   **Systematic Recording:** For each run, meticulously log all parameters used (including any changes made to scripts like `filter_smart_money.py` or `construct_sentiment_signal.py`) and the key performance metrics (`Total Return`, `Annualized Return`, `Sharpe Ratio`, `Max Drawdown`, average number of holdings per rebalance, maximum concentration observed in any stock) in a spreadsheet or a dedicated analysis notebook.
*   **Performance vs. Risk:** Prioritize configurations that offer a consistently good Sharpe ratio (indicating better risk-adjusted returns) and acceptable maximum drawdown levels according to your risk tolerance.
*   **Diversification Goals:** Ensure the strategy consistently meets the diversification targets (e.g., aiming for at least 5 stocks if possible, individual stock weights not exceeding 40%). If results show excessive concentration or too few holdings, revisit parameters influencing stock selection breadth (like `buy_threshold`) or the diversity of the CIK list.
*   **Qualitative Analysis:** Review the `quarterly_portfolio_composition_[suffix].csv` for selected promising runs. Do the chosen stocks and their weights make intuitive sense based on the strategy's intent? Is portfolio turnover (implied by changes in composition files) excessively high, which might incur significant (unmodeled) transaction costs in live trading?

**4. Further Iteration and Refinement**

*   Based on the most promising results from single-parameter variations, you can start testing combinations of optimal parameters (e.g., the best `buy_threshold` found with the most effective `signal_lag_days`).
*   If overall performance remains unsatisfactory across various configurations, it might indicate a need to explore more fundamental changes to the signal generation logic itself (e.g., different metrics in `construct_sentiment_signal.py`) or the potential need to incorporate other data sources beyond 13F filings.

This iterative approach, combining quantitative metrics with qualitative portfolio analysis, is key to developing, understanding, and validating a robust trading strategy.
