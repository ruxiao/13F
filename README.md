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
    *   **Purpose:** Simulates a trading strategy based on the generated sentiment signals and historical price data.
    *   **Key Inputs:** `processed_13f_data/sentiment_signals.csv`, price data from `price_data/`, strategy parameters (e.g., `BUY_THRESHOLD`, `SELL_THRESHOLD`, `INITIAL_CAPITAL`).
    *   **Key Outputs:**
        *   Console output of performance metrics (Total Return, Sharpe Ratio, etc.).
        *   `backtest_results/portfolio_daily_performance.csv` (daily portfolio value).
        *   `backtest_results/trades_log.csv` (log of executed trades).

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

## Example Iteration

During development, an example iteration involved:
1.  Simulating 3 quarters of 13F data for Berkshire Hathaway (CIK `0001067983`).
2.  Processing this data through the pipeline. `sentiment_signals.csv` showed dynamic scores for stocks like AAPL, AXP, BAC. For example, AXP had a sentiment score of ~0.086 for 2023-12-31, while AAPL had ~0.051.
3.  Running `backtest_strategy.py` with `BUY_THRESHOLD = 0.05`. This resulted in a "Buy" trade for AAPL (score ~0.051) and AXP (score ~0.086). Due to the capital allocation logic (dividing cash by number of buy signals), if multiple stocks are bought, the capital is split.
4.  Changing `BUY_THRESHOLD` to `0.07`.
5.  Re-running `backtest_strategy.py`. This time, only AXP (score ~0.086) was bought, as AAPL's score (~0.051) no longer met the more stringent threshold. This demonstrated how parameter changes directly impact strategy behavior and performance outcomes.

## Known Limitations

*   **SEC EDGAR Scraping Reliability:** Access to SEC EDGAR can be inconsistent due to rate limiting or blocking, making large-scale, frequent scraping challenging without more advanced techniques (e.g., distributed IPs, robust error handling beyond simple retries).
*   **Basic Sentiment Model:** The current sentiment score is based on simple changes in reported holdings (value, shares, number of investors). It does not incorporate more nuanced factors like the type of investor, concentration, or NLP on filing text.
*   **Backtester Simplifications:**
    *   No transaction costs (brokerage fees) or market slippage are modeled.
    *   Capital allocation is basic (divides available cash among current buy signals). It does not implement sophisticated portfolio construction or rebalancing rules.
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
