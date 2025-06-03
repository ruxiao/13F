import pandas as pd
import numpy as np
import os
from datetime import timedelta

# --- Configuration ---
SENTIMENT_SIGNALS_CSV = "processed_13f_data/sentiment_signals.csv"
PRICE_DATA_DIR = "price_data/"
OUTPUT_DIR = "backtest_results"
PORTFOLIO_PERFORMANCE_CSV = os.path.join(OUTPUT_DIR, "portfolio_daily_performance.csv")

INITIAL_CAPITAL = 100000.0
# Simple Long-Only Strategy:
# Buy if sentiment score > BUY_THRESHOLD
# Sell (exit position) if sentiment score < SELL_THRESHOLD (or if it simply drops)
# For this version, we'll hold until the next signal for that stock, or until end of backtest.
# A more advanced strategy would have explicit sell signals or stop-losses.
BUY_THRESHOLD = 0.07
SELL_THRESHOLD = -0.02

# Lag for signal activation (e.g., 1 day after reporting_date, or more realistically 15-45 days after quarter end)
# For 13F, reporting_date is the end of the quarter. Filings are due 45 days later.
# Let's assume signal is actionable 1 business day after the FILING_DATE (which we don't have).
# For simplicity now, let's assume signal is known on reporting_date + SIGNAL_LAG_DAYS for action on next trading day.
SIGNAL_LAG_DAYS = 1 # Trade on T+1 after reporting_date (highly simplified)

RISK_FREE_RATE = 0.00 # For Sharpe Ratio

# --- Helper Functions ---

def ensure_output_dir_exists():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created directory: {OUTPUT_DIR}")

def map_cusip_to_ticker(cusip):
    """
    Maps CUSIP to a ticker symbol.
    (Reusing the simple manual map from get_price_history.py)
    """
    cusip_to_ticker_map = {
        "037833100": "AAPL",        # Apple Inc.
        "023135106": "AMZN",        # Amazon.com Inc.
        "594918104": "MSFT",        # Microsoft Corp
        "060505104": "BAC",         # Bank of America Corp
        "025816109": "AXP",         # American Express Co
        "191216100": "KO",          # Coca-Cola Co
        "166764100": "CVX",         # Chevron Corp
    }
    if cusip in cusip_to_ticker_map:
        return cusip_to_ticker_map[cusip]
    # print(f"Warning: CUSIP {cusip} not in manual map. Cannot get price data.")
    return None

def load_price_data(ticker_list):
    """
    Loads all price data CSVs for the given tickers.
    Returns a dictionary of DataFrames, keyed by ticker.
    """
    price_data = {}
    for ticker in ticker_list:
        filepath = os.path.join(PRICE_DATA_DIR, f"{ticker}.csv")
        if os.path.exists(filepath):
            try:
                df = pd.read_csv(filepath, parse_dates=['Date'], index_col='Date')
                if not df.empty:
                    price_data[ticker] = df.sort_index() # Ensure sorted by date
                else:
                    print(f"Warning: Price data file for {ticker} is empty.")
            except Exception as e:
                print(f"Error loading price data for {ticker} from {filepath}: {e}")
        else:
            print(f"Warning: Price data file not found for ticker {ticker} at {filepath}")
    return price_data

def calculate_performance_metrics(portfolio_values_series, risk_free_rate=RISK_FREE_RATE):
    """Calculates common performance metrics."""
    if portfolio_values_series.empty or len(portfolio_values_series) < 2:
        return {
            "Total Return": 0, "Annualized Return": 0, "Annualized Volatility": 0,
            "Sharpe Ratio": 0, "Max Drawdown": 0, "CAGR": 0
        }

    total_return = (portfolio_values_series.iloc[-1] / portfolio_values_series.iloc[0]) - 1

    # Assuming daily data for annualized calculations
    days_in_series = (portfolio_values_series.index[-1] - portfolio_values_series.index[0]).days
    if days_in_series == 0: days_in_series = 1 # Avoid division by zero for single day data

    annualized_return = ((1 + total_return) ** (365.0 / days_in_series)) - 1

    daily_returns = portfolio_values_series.pct_change().dropna()
    annualized_volatility = daily_returns.std() * np.sqrt(252) # Assuming 252 trading days

    sharpe_ratio = 0
    if annualized_volatility != 0:
        sharpe_ratio = (annualized_return - risk_free_rate) / annualized_volatility

    # Max Drawdown
    cumulative_returns = (1 + daily_returns).cumprod()
    peak = cumulative_returns.expanding(min_periods=1).max()
    drawdown = (cumulative_returns - peak) / peak
    max_drawdown = drawdown.min()

    # CAGR
    cagr = annualized_return # For simplicity, using annualized return as CAGR here.
                             # More precise CAGR: (ending_value/starting_value)**(1/num_years) - 1

    return {
        "Total Return": total_return,
        "Annualized Return": annualized_return,
        "Annualized Volatility": annualized_volatility,
        "Sharpe Ratio": sharpe_ratio,
        "Max Drawdown": max_drawdown,
        "CAGR": cagr
    }

# --- Main Backtesting Logic ---
def main():
    ensure_output_dir_exists()

    # 1. Load Sentiment Signals
    if not os.path.exists(SENTIMENT_SIGNALS_CSV):
        print(f"Error: Sentiment signals file not found: {SENTIMENT_SIGNALS_CSV}")
        return
    try:
        signals_df = pd.read_csv(SENTIMENT_SIGNALS_CSV, dtype={'cusip': str})
        if signals_df.empty:
            print(f"Sentiment signals file {SENTIMENT_SIGNALS_CSV} is empty.")
            return
    except Exception as e:
        print(f"Error reading sentiment signals CSV: {e}")
        return

    signals_df['reporting_date'] = pd.to_datetime(signals_df['reporting_date'])
    # For simplicity, assume signal is actionable on reporting_date + lag (next available trading day)
    signals_df['signal_active_date'] = signals_df['reporting_date'] + timedelta(days=SIGNAL_LAG_DAYS)

    # Map CUSIPs to Tickers in signals_df
    signals_df['ticker'] = signals_df['cusip'].apply(map_cusip_to_ticker)
    signals_df.dropna(subset=['ticker'], inplace=True) # Keep only signals for which we have a ticker

    if signals_df.empty:
        print("No signals remain after CUSIP-to-Ticker mapping. Exiting.")
        return

    # 2. Load Price Data for relevant tickers
    tickers_with_signals = signals_df['ticker'].unique().tolist()
    all_price_data = load_price_data(tickers_with_signals)

    if not all_price_data:
        print("No price data loaded. Cannot proceed with backtest. Ensure price_data CSVs exist for mapped tickers.")
        return

    # 3. Align Data & Prepare for Backtest Loop
    # Create a unified date range from all available price data
    min_price_date = min(df.index.min() for df in all_price_data.values())
    max_price_date = max(df.index.max() for df in all_price_data.values())
    backtest_date_range = pd.date_range(start=min_price_date, end=max_price_date, freq='B') # Business days

    # Pivot signals to have one row per date, with columns for each ticker's sentiment score
    # Forward fill signals: a signal is active until a new one for that ticker arrives
    daily_signals = pd.DataFrame(index=backtest_date_range)

    for ticker in tickers_with_signals:
        ticker_signals = signals_df[signals_df['ticker'] == ticker][['signal_active_date', 'sentiment_score']]
        if not ticker_signals.empty:
            # Set signal_active_date as index, then reindex to backtest_date_range and ffill
            ticker_signals = ticker_signals.set_index('signal_active_date').sort_index()
            # Ensure only one signal per day (take last if multiple, though unlikely with quarterly)
            ticker_signals = ticker_signals[~ticker_signals.index.duplicated(keep='last')]
            daily_signals[ticker] = ticker_signals['sentiment_score'].reindex(backtest_date_range, method='ffill')

    # Initialize Portfolio
    portfolio = {'cash': INITIAL_CAPITAL, 'holdings_value': 0.0, 'total_value': INITIAL_CAPITAL}
    positions = {ticker: {'shares': 0, 'value': 0.0} for ticker in all_price_data.keys()}
    portfolio_history = pd.DataFrame(index=backtest_date_range, columns=['total_value'])
    trades_executed = [] # Initialize list to log trades

    print(f"\nStarting backtest with initial capital: ${INITIAL_CAPITAL:,.2f}")
    print(f"Date range: {min_price_date.strftime('%Y-%m-%d')} to {max_price_date.strftime('%Y-%m-%d')}")

    # 4. Backtesting Loop
    for current_date in backtest_date_range:
        if current_date not in daily_signals.index: # Skip if no signal data for this day (should not happen with reindex)
            portfolio_history.loc[current_date, 'total_value'] = portfolio['total_value']
            continue

        active_signals_today = daily_signals.loc[current_date].dropna()

        # Determine stocks to trade based on current signals vs. previous day's signals or thresholds
        # For this simple version: if a signal is above BUY_THRESHOLD, and we don't hold it, buy.
        # If we hold it and signal drops below SELL_THRESHOLD, sell.
        # More realistically, trades would happen based on signals becoming *newly* active.

        # --- Trading Logic ---
        # Identify stocks that have an active signal today
        target_holdings = {} # Stores {'ticker': {'action': 'buy'/'sell', 'triggering_score': score}}
        for ticker, score in active_signals_today.items():
            if score >= BUY_THRESHOLD:
                target_holdings[ticker] = {'action': 'buy', 'triggering_score': score}
            elif score < SELL_THRESHOLD and positions[ticker]['shares'] > 0 :
                target_holdings[ticker] = {'action': 'sell', 'triggering_score': score}
            # else: no action or hold if already holding

        num_buys = sum(1 for details in target_holdings.values() if details['action'] == 'buy')
        capital_per_buy = 0
        if num_buys > 0:
            capital_per_buy = portfolio['cash'] / num_buys


        for ticker, trade_info in target_holdings.items():
            action = trade_info['action']
            triggering_score = trade_info['triggering_score']

            if ticker not in all_price_data or current_date not in all_price_data[ticker].index:
                continue

            execution_price = all_price_data[ticker].loc[current_date, 'Open']
            if pd.isna(execution_price):
                continue

            if action == 'buy' and positions[ticker]['shares'] == 0:
                if portfolio['cash'] > 0:
                    shares_to_buy_approx = capital_per_buy / execution_price
                    shares_to_buy = int(shares_to_buy_approx)
                    cost = shares_to_buy * execution_price
                    if shares_to_buy > 0 and portfolio['cash'] >= cost:
                        trades_executed.append({
                            'Date': current_date.strftime('%Y-%m-%d'),
                            'Ticker': ticker,
                            'Action': 'Buy',
                            'Price': execution_price,
                            'Shares': shares_to_buy,
                            'SentimentScoreAtTrade': triggering_score,
                            'PortfolioCashBeforeTrade': portfolio['cash'],
                            'PortfolioValueBeforeTrade': portfolio['total_value']
                        })
                        positions[ticker]['shares'] += shares_to_buy
                        portfolio['cash'] -= cost
                        print(f"{current_date.strftime('%Y-%m-%d')}: BOUGHT {shares_to_buy} {ticker} @ ${execution_price:.2f}, Cost: ${cost:.2f}, Sentiment: {triggering_score:.2f}")

            elif action == 'sell' and positions[ticker]['shares'] > 0:
                shares_to_sell = positions[ticker]['shares']
                proceeds = shares_to_sell * execution_price

                trades_executed.append({
                    'Date': current_date.strftime('%Y-%m-%d'),
                    'Ticker': ticker,
                    'Action': 'Sell',
                    'Price': execution_price,
                    'Shares': shares_to_sell,
                    'SentimentScoreAtTrade': triggering_score,
                    'PortfolioCashBeforeTrade': portfolio['cash'],
                    'PortfolioValueBeforeTrade': portfolio['total_value']
                })
                positions[ticker]['shares'] = 0
                portfolio['cash'] += proceeds
                print(f"{current_date.strftime('%Y-%m-%d')}: SOLD {shares_to_sell} {ticker} @ ${execution_price:.2f}, Proceeds: ${proceeds:.2f}, Sentiment: {triggering_score:.2f}")

        # --- Daily Portfolio Valuation (Mark-to-Market) ---
        current_holdings_value = 0
        for ticker, pos_data in positions.items():
            if pos_data['shares'] > 0:
                if ticker in all_price_data and current_date in all_price_data[ticker].index:
                    close_price = all_price_data[ticker].loc[current_date, 'Close']
                    if not pd.isna(close_price):
                        positions[ticker]['value'] = pos_data['shares'] * close_price
                        current_holdings_value += positions[ticker]['value']
                    else: # If close price is NaN, use last known value for this ticker (carry forward)
                        current_holdings_value += positions[ticker]['value']
                else: # If no price data for today, carry forward last known value
                     current_holdings_value += positions[ticker]['value']

        portfolio['holdings_value'] = current_holdings_value
        portfolio['total_value'] = portfolio['cash'] + portfolio['holdings_value']
        portfolio_history.loc[current_date, 'total_value'] = portfolio['total_value']

    # Fill NaNs in portfolio_history (e.g., non-trading days if not using 'B' freq)
    portfolio_history['total_value'] = portfolio_history['total_value'].ffill()
    portfolio_history.dropna(inplace=True) # Drop any leading NaNs if any

    # 5. Calculate Performance Metrics
    if portfolio_history.empty:
        print("Portfolio history is empty. Cannot calculate performance metrics.")
    else:
        metrics = calculate_performance_metrics(portfolio_history['total_value'])
        print("\n--- Backtest Performance ---")
        for metric, value in metrics.items():
            print(f"{metric}: {value:.2%}" if isinstance(value, (int, float)) and ("Return" in metric or "Rate" in metric or "Volatility" in metric or "Drawdown" in metric) else f"{metric}: {value}")

        # 6. Save Portfolio History
        try:
            portfolio_history.to_csv(PORTFOLIO_PERFORMANCE_CSV)
            print(f"\nDaily portfolio performance saved to: {PORTFOLIO_PERFORMANCE_CSV}")
        except Exception as e:
            print(f"Error saving portfolio performance: {e}")

        # Save Trades Log
        if trades_executed:
            trades_df = pd.DataFrame(trades_executed)
            trades_log_csv = os.path.join(OUTPUT_DIR, "trades_log.csv")
            try:
                trades_df.to_csv(trades_log_csv, index=False)
                print(f"Trades log saved to: {trades_log_csv}")
            except Exception as e:
                print(f"Error saving trades log: {e}")
        else:
            print("No trades were executed during the backtest.")

if __name__ == "__main__":
    main()
