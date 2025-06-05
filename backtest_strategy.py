import pandas as pd
import numpy as np
import os
from datetime import timedelta

# --- Configuration ---
SENTIMENT_SIGNALS_CSV = "processed_13f_data/sentiment_signals.csv"
PRICE_DATA_DIR = "price_data/"
OUTPUT_DIR = "backtest_results"
PORTFOLIO_PERFORMANCE_CSV = os.path.join(OUTPUT_DIR, "portfolio_daily_performance.csv")
QUARTERLY_PORTFOLIO_COMPOSITION_CSV = os.path.join(OUTPUT_DIR, "quarterly_portfolio_composition.csv")

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
    signals_df['signal_active_date'] = signals_df['reporting_date'] + timedelta(days=SIGNAL_LAG_DAYS)

    # --- Determine Rebalancing Dates ---
    # These are the dates on which we will actually execute trades (sell all, then buy new)
    # It's derived from unique reporting_dates + SIGNAL_LAG_DAYS
    unique_reporting_dates = signals_df['reporting_date'].sort_values().unique()
    rebalancing_dates = sorted(list(pd.to_datetime(unique_reporting_dates) + timedelta(days=SIGNAL_LAG_DAYS)))
    # Ensure rebalancing_dates are business days and within the overall price data range later.
    # For now, we just generate them. We'll filter them against backtest_date_range.

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
    # This daily_signals is used for MTM valuation. Trading decisions will use specific signals on rebalancing days.
    daily_signals_for_valuation = pd.DataFrame(index=backtest_date_range)

    for ticker in tickers_with_signals:
        ticker_signals = signals_df[signals_df['ticker'] == ticker][['signal_active_date', 'sentiment_score']]
        if not ticker_signals.empty:
            ticker_signals = ticker_signals.set_index('signal_active_date').sort_index()
            ticker_signals = ticker_signals[~ticker_signals.index.duplicated(keep='last')]
            daily_signals_for_valuation[ticker] = ticker_signals['sentiment_score'].reindex(backtest_date_range, method='ffill')

    # Filter rebalancing_dates to be within the actual backtest_date_range (price availability)
    rebalancing_dates = [date for date in rebalancing_dates if date in backtest_date_range]
    # Convert to set for faster lookups
    rebalancing_dates_set = set(rebalancing_dates)


    # Initialize Portfolio
    portfolio = {'cash': INITIAL_CAPITAL, 'holdings_value': 0.0, 'total_value': INITIAL_CAPITAL}
    # Store execution price along with shares and value for logging quarterly composition
    positions = {ticker: {'shares': 0, 'value': 0.0, 'execution_price': 0.0} for ticker in all_price_data.keys()}
    portfolio_history = pd.DataFrame(index=backtest_date_range, columns=['total_value'])
    trades_executed = [] # Initialize list to log trades
    quarterly_portfolio_log = [] # For logging portfolio composition after each rebalance

    print(f"\nStarting backtest with initial capital: ${INITIAL_CAPITAL:,.2f}")
    print(f"Date range: {min_price_date.strftime('%Y-%m-%d')} to {max_price_date.strftime('%Y-%m-%d')}")
    if rebalancing_dates:
        print(f"First rebalancing date: {rebalancing_dates[0].strftime('%Y-%m-%d')}")
        print(f"Last rebalancing date: {rebalancing_dates[-1].strftime('%Y-%m-%d')}")
        print(f"Total rebalancing dates: {len(rebalancing_dates)}")
    else:
        print("No rebalancing dates found within the price data range.")


    # 4. Backtesting Loop
    for current_date in backtest_date_range:
        # --- Quarterly Rebalancing Logic ---
        if current_date in rebalancing_dates_set:
            print(f"\n--- Rebalancing Day: {current_date.strftime('%Y-%m-%d')} ---")
            current_reporting_date = current_date - timedelta(days=SIGNAL_LAG_DAYS)

            # 1. Liquidate all existing positions
            for ticker in list(positions.keys()): # Iterate over a copy of keys if modifying dict
                if positions[ticker]['shares'] > 0:
                    if ticker in all_price_data and current_date in all_price_data[ticker].index:
                        execution_price = all_price_data[ticker].loc[current_date, 'Open']
                        if not pd.isna(execution_price):
                            shares_to_sell = positions[ticker]['shares']
                            proceeds = shares_to_sell * execution_price
                            trades_executed.append({
                                'Date': current_date.strftime('%Y-%m-%d'),
                                'Ticker': ticker,
                                'Action': 'Sell (Quarterly Rebalance)',
                                'Price': execution_price,
                                'Shares': shares_to_sell,
                                'SentimentScoreAtTrade': np.nan, # Not relevant for liquidation
                                'PortfolioCashBeforeTrade': portfolio['cash'],
                                'PortfolioValueBeforeTrade': portfolio['total_value']
                            })
                            positions[ticker]['shares'] = 0
                            positions[ticker]['value'] = 0.0
                            portfolio['cash'] += proceeds
                            print(f"{current_date.strftime('%Y-%m-%d')}: LIQUIDATED (Q Rebalance) {shares_to_sell} {ticker} @ ${execution_price:.2f}, Proceeds: ${proceeds:.2f}")
                        else:
                            print(f"Warning: NaN open price for {ticker} on {current_date.strftime('%Y-%m-%d')}. Cannot liquidate.")
                    else:
                        print(f"Warning: No price data for {ticker} on {current_date.strftime('%Y-%m-%d')}. Cannot liquidate.")

            portfolio['holdings_value'] = 0.0 # All sold

            # 2. Identify New Positions to Buy
            # Get signals for the specific reporting_date that triggered this rebalance
            active_signals_for_rebalance = signals_df[signals_df['reporting_date'] == current_reporting_date]

            buy_targets = []
            for idx, signal_row in active_signals_for_rebalance.iterrows():
                ticker = signal_row['ticker']
                score = signal_row['sentiment_score']
                if score >= BUY_THRESHOLD:
                    buy_targets.append({'ticker': ticker, 'score': score})

            print(f"Found {len(buy_targets)} potential buy targets for reporting date {current_reporting_date.strftime('%Y-%m-%d')}.")

            # 3. Capital Allocation & Execution
            capital_allocations = {}
            if buy_targets:
                cash_to_allocate = portfolio['cash'] # Cash after all sells

                # Calculate total positive sentiment score for weighting
                total_positive_sentiment_score = sum(item['score'] for item in buy_targets if item['score'] > 0)

                if total_positive_sentiment_score > 0:
                    print(f"Allocating based on score weights. Total positive score: {total_positive_sentiment_score:.2f}. Cash to allocate: ${cash_to_allocate:,.2f}")
                    for item in buy_targets:
                        ticker = item['ticker']
                        score = item['score']
                        if score > 0:
                            weight = score / total_positive_sentiment_score
                            capital_allocations[ticker] = cash_to_allocate * weight
                        else:
                            # Assign zero capital if score is not positive, even if it met BUY_THRESHOLD (e.g. BUY_THRESHOLD <= 0)
                            capital_allocations[ticker] = 0.0
                else: # Fallback: Equal weight if no positive scores or no buy_targets (though covered by outer 'if buy_targets')
                    print("Total positive sentiment score is not > 0. Falling back to equal weight allocation.")
                    num_buys = len(buy_targets)
                    if num_buys > 0:
                        equal_capital_per_buy = cash_to_allocate / num_buys
                        for item in buy_targets:
                            ticker = item['ticker']
                            capital_allocations[ticker] = equal_capital_per_buy

            if capital_allocations:
                print("Planned capital allocations:")
                for t, cap in capital_allocations.items():
                    print(f"  {t}: ${cap:,.2f}")

            # Execute trades based on calculated allocations
            for target_item in buy_targets: # Iterate buy_targets to easily get original score for logging
                ticker = target_item['ticker']
                original_score = target_item['score'] # Score used for BUY_THRESHOLD and weighting

                allocated_capital = capital_allocations.get(ticker)
                if allocated_capital is None or allocated_capital <= 1.0: # Check for None and skip if capital is negligible (e.g. $1)
                    print(f"Skipping buy for {ticker}: No capital allocated or allocation too small (${allocated_capital:.2f}).")
                    continue

                if ticker not in all_price_data or current_date not in all_price_data[ticker].index:
                    print(f"Skipping buy for {ticker}: No price data available for {current_date.strftime('%Y-%m-%d')}")
                    continue

                execution_price = all_price_data[ticker].loc[current_date, 'Open']
                if pd.isna(execution_price) or execution_price <= 0:
                    print(f"Skipping buy for {ticker}: Invalid execution price ${execution_price} on {current_date.strftime('%Y-%m-%d')}")
                    continue

                # Check if there's any cash left in the portfolio at all before attempting the trade
                if portfolio['cash'] <= 1.0: # If practically no cash left
                    print(f"Skipping buy for {ticker}: Insufficient total cash (${portfolio['cash']:.2f}) left in portfolio.")
                    continue

                shares_to_buy_approx = allocated_capital / execution_price
                shares_to_buy = int(shares_to_buy_approx)
                cost = shares_to_buy * execution_price

                if shares_to_buy > 0 and portfolio['cash'] >= cost :
                    trades_executed.append({
                        'Date': current_date.strftime('%Y-%m-%d'),
                        'Ticker': ticker,
                        'Action': 'Buy (Quarterly Rebalance)',
                        'Price': execution_price,
                        'Shares': shares_to_buy,
                        'SentimentScoreAtTrade': original_score, # Log the score that triggered the buy
                        'PortfolioCashBeforeTrade': portfolio['cash'],
                        'PortfolioValueBeforeTrade': portfolio['total_value']
                    })
                    positions[ticker]['shares'] += shares_to_buy
                    positions[ticker]['execution_price'] = execution_price
                    portfolio['cash'] -= cost
                    print(f"{current_date.strftime('%Y-%m-%d')}: BOUGHT (Q Rebalance) {shares_to_buy} {ticker} @ ${execution_price:.2f}, Cost: ${cost:.2f}, Allocated Cap: ${allocated_capital:,.2f}, Sentiment: {original_score:.2f}")
                else:
                    print(f"Could not buy {ticker}: Shares_to_buy={shares_to_buy}, Current Cash=${portfolio['cash']:.2f}, Cost=${cost:.2f}, Allocated Cap: ${allocated_capital:,.2f}")

            # --- Log Portfolio Composition After Rebalancing ---
            # First, update position values based on execution prices for newly bought assets
            current_holdings_value_at_rebalance = 0
            for ticker_p, pos_data_p in positions.items():
                if pos_data_p['shares'] > 0:
                    # For newly bought positions, value is shares * execution_price
                    # This ensures the logged 'MarketValue' for stocks is based on rebalance day's buy prices.
                    positions[ticker_p]['value'] = pos_data_p['shares'] * pos_data_p['execution_price']
                    current_holdings_value_at_rebalance += positions[ticker_p]['value']

            final_cash_after_rebalance = portfolio['cash']
            total_portfolio_value_after_rebalance = final_cash_after_rebalance + current_holdings_value_at_rebalance

            # Log stock positions
            for ticker_log, pos_details_log in positions.items():
                if pos_details_log['shares'] > 0:
                    market_value = pos_details_log['shares'] * pos_details_log['execution_price']
                    weight = market_value / total_portfolio_value_after_rebalance if total_portfolio_value_after_rebalance else 0
                    quarterly_portfolio_log.append({
                        'RebalanceDate': current_date.strftime('%Y-%m-%d'),
                        'AssetType': 'Stock',
                        'Ticker': ticker_log,
                        'Shares': pos_details_log['shares'],
                        'PriceAtRebalance': pos_details_log['execution_price'],
                        'MarketValue': market_value,
                        'WeightInPortfolio': weight,
                        'CashAfterRebalance': final_cash_after_rebalance,
                        'TotalPortfolioValueAfterRebalance': total_portfolio_value_after_rebalance
                    })

            # Log cash position
            cash_weight = final_cash_after_rebalance / total_portfolio_value_after_rebalance if total_portfolio_value_after_rebalance else 0
            quarterly_portfolio_log.append({
                'RebalanceDate': current_date.strftime('%Y-%m-%d'),
                'AssetType': 'Cash',
                'Ticker': 'CASH',
                'Shares': final_cash_after_rebalance, # Using cash value as 'Shares' for cash type
                'PriceAtRebalance': 1.0, # Price for cash is 1
                'MarketValue': final_cash_after_rebalance,
                'WeightInPortfolio': cash_weight,
                'CashAfterRebalance': final_cash_after_rebalance,
                'TotalPortfolioValueAfterRebalance': total_portfolio_value_after_rebalance
            })
            print(f"Logged portfolio composition for {current_date.strftime('%Y-%m-%d')}. Holdings: {current_holdings_value_at_rebalance:.2f}, Cash: {final_cash_after_rebalance:.2f}, Total: {total_portfolio_value_after_rebalance:.2f}")


        # --- Daily Portfolio Valuation (Mark-to-Market) ---
        # This runs every day, regardless of rebalancing.
        # For MTM, we use daily closing prices.
        current_holdings_value = 0
        for ticker, pos_data in positions.items():
            if pos_data['shares'] > 0:
                if ticker in all_price_data and current_date in all_price_data[ticker].index:
                    close_price = all_price_data[ticker].loc[current_date, 'Close']
                    if not pd.isna(close_price):
                        positions[ticker]['value'] = pos_data['shares'] * close_price
                # If close price is NaN, or if ticker/date not in price_data,
                # the value from the previous day (already in positions[ticker]['value']) is carried forward.
                # So, no specific 'else' needed here to handle missing price,
                # as long as positions[ticker]['value'] is not reset before this.
            # Add the ticker's value (either updated or carried over) to current_holdings_value
            current_holdings_value += positions[ticker]['value']

        portfolio['holdings_value'] = current_holdings_value
        portfolio['total_value'] = portfolio['cash'] + portfolio['holdings_value']

    if current_date in portfolio_history.index:
         portfolio_history.loc[current_date, 'total_value'] = portfolio['total_value']

# Fill NaNs in portfolio_history (e.g., from weekends if original range included them, or holidays)
# This is important for days that might be in backtest_date_range (like holidays) but have no trades or price updates.
    portfolio_history['total_value'] = portfolio_history['total_value'].ffill()
# Drop any leading NaNs if backtest started before any valid price/signal data or if initial days are NaNs.
portfolio_history.dropna(subset=['total_value'], inplace=True)


    # 5. Calculate Performance Metrics
    if portfolio_history.empty:
        print("Portfolio history is empty. Cannot calculate performance metrics.")
    else:
        metrics = calculate_performance_metrics(portfolio_history['total_value'])
        print("\n--- Backtest Performance ---")
        for metric, value in metrics.items():
            print(f"{metric}: {value:.2%}" if isinstance(value, (int, float)) and ("Return" in metric or "Rate" in metric or "Volatility" in metric or "Drawdown" in metric) else f"{metric}: {value}")

    # 6. Save Results
        try:
            portfolio_history.to_csv(PORTFOLIO_PERFORMANCE_CSV)
            print(f"\nDaily portfolio performance saved to: {PORTFOLIO_PERFORMANCE_CSV}")
        except Exception as e:
            print(f"Error saving portfolio performance: {e}")

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

    if quarterly_portfolio_log:
        quarterly_df = pd.DataFrame(quarterly_portfolio_log)
        try:
            quarterly_df.to_csv(QUARTERLY_PORTFOLIO_COMPOSITION_CSV, index=False)
            print(f"Quarterly portfolio composition saved to: {QUARTERLY_PORTFOLIO_COMPOSITION_CSV}")
        except Exception as e:
            print(f"Error saving quarterly portfolio composition: {e}")
    else:
        print("No quarterly portfolio compositions were logged.")


if __name__ == "__main__":
    main()
