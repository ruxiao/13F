import pandas as pd
import numpy as np
import os
import argparse # Added for command-line arguments
from datetime import timedelta

# --- Global constants that are not typically changed by CLI args ---
# SELL_THRESHOLD is not actively used in the current quarterly full liquidation strategy,
# but kept for potential future strategy variations.
SELL_THRESHOLD = -0.02
RISK_FREE_RATE = 0.00 # For Sharpe Ratio

# --- Helper Functions ---

def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Run a backtesting strategy for 13F sentiment signals.")
    parser.add_argument('--signals_file', type=str, default="processed_13f_data/sentiment_signals.csv",
                        help="Path to the sentiment signals CSV file.")
    parser.add_argument('--price_dir', type=str, default="price_data/",
                        help="Directory containing historical price CSV files for tickers.")
    parser.add_argument('--output_dir', type=str, default="backtest_results/",
                        help="Directory to save backtest results.")
    parser.add_argument('--initial_capital', type=float, default=100000.0,
                        help="Initial capital for the backtest.")
    parser.add_argument('--buy_threshold', type=float, default=0.07,
                        help="Sentiment score threshold to trigger a buy.")
    parser.add_argument('--signal_lag_days', type=int, default=1,
                        help="Number of days to lag the signal activation after reporting date.")
    parser.add_argument('--run_name_suffix', type=str, default="",
                        help="Suffix to append to output file names (e.g., '_run1').")
    return parser.parse_args()

def ensure_output_dir_exists(output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

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
    Loads all price data CSVs for the given tickers from the specified price_dir.
    Returns a dictionary of DataFrames, keyed by ticker.
    """
    price_data = {}
    for ticker in ticker_list:
        filepath = os.path.join(price_dir, f"{ticker}.csv") # Use price_dir argument
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

def calculate_performance_metrics(portfolio_values_series, risk_free_rate_param=RISK_FREE_RATE): # Use a parameter for clarity
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
        sharpe_ratio = (annualized_return - risk_free_rate_param) / annualized_volatility

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
def main(args): # Accept parsed arguments
    ensure_output_dir_exists(args.output_dir)

    # Define output file paths using args
    portfolio_performance_csv_path = os.path.join(args.output_dir, f"portfolio_daily_performance{args.run_name_suffix}.csv")
    trades_log_csv_path = os.path.join(args.output_dir, f"trades_log{args.run_name_suffix}.csv")
    quarterly_portfolio_composition_csv_path = os.path.join(args.output_dir, f"quarterly_portfolio_composition{args.run_name_suffix}.csv")

    # 1. Load Sentiment Signals
    if not os.path.exists(args.signals_file):
        print(f"Error: Sentiment signals file not found: {args.signals_file}")
        return
    try:
        signals_df = pd.read_csv(args.signals_file, dtype={'cusip': str})
        if signals_df.empty:
            print(f"Sentiment signals file {args.signals_file} is empty.")
            return
    except Exception as e:
        print(f"Error reading sentiment signals CSV: {e}")
        return

    signals_df['reporting_date'] = pd.to_datetime(signals_df['reporting_date'])
    signals_df['signal_active_date'] = signals_df['reporting_date'] + timedelta(days=args.signal_lag_days)

    # --- Determine Rebalancing Dates ---
    # These are the dates on which we will actually execute trades (sell all, then buy new)
    # It's derived from unique reporting_dates + SIGNAL_LAG_DAYS
    unique_reporting_dates = signals_df['reporting_date'].sort_values().unique()
    rebalancing_dates = sorted(list(pd.to_datetime(unique_reporting_dates) + timedelta(days=args.signal_lag_days)))
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
    all_price_data = load_price_data(tickers_with_signals, args.price_dir) # Pass price_dir

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
    portfolio = {'cash': args.initial_capital, 'holdings_value': 0.0, 'total_value': args.initial_capital}
    # Store execution price along with shares and value for logging quarterly composition
    positions = {ticker: {'shares': 0, 'value': 0.0, 'execution_price': 0.0} for ticker in all_price_data.keys()}
    portfolio_history = pd.DataFrame(index=backtest_date_range, columns=['total_value'])
    trades_executed = [] # Initialize list to log trades
    quarterly_portfolio_log = [] # For logging portfolio composition after each rebalance

    print(f"\nStarting backtest with initial capital: ${args.initial_capital:,.2f}")
    print(f"Buy Threshold: {args.buy_threshold}, Signal Lag: {args.signal_lag_days} days")
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
            current_reporting_date = current_date - timedelta(days=args.signal_lag_days)

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
                if score >= args.buy_threshold: # Use args.buy_threshold
                    buy_targets.append({'ticker': ticker, 'score': score})

            print(f"Found {len(buy_targets)} potential buy targets (score >= {args.buy_threshold}) for reporting date {current_reporting_date.strftime('%Y-%m-%d')}.")

            # 3. Capital Allocation & Execution
            final_allocations = {} # This will store the final capital for each stock
            if buy_targets:
                cash_to_allocate = portfolio['cash'] # Cash available after all sells

                # Initial provisional allocation (score-weighted or equal-weighted)
                provisional_allocations = {}
                original_scores_map = {item['ticker']: item['score'] for item in buy_targets}

                total_positive_sentiment_score = sum(score for score in original_scores_map.values() if score > 0)

                if total_positive_sentiment_score > 0:
                    print(f"Initial allocation: Score-weighted. Total positive score: {total_positive_sentiment_score:.2f}. Cash: ${cash_to_allocate:,.2f}")
                    for ticker, score in original_scores_map.items():
                        if score > 0:
                            provisional_allocations[ticker] = (score / total_positive_sentiment_score) * cash_to_allocate
                        else:
                            provisional_allocations[ticker] = 0.0 # No capital for non-positive scores initially
                elif buy_targets: # Fallback to equal weight if no positive scores but targets exist
                    print(f"Initial allocation: Equal-weighted (no positive scores). Cash: ${cash_to_allocate:,.2f}")
                    num_buys = len(buy_targets)
                    if num_buys > 0:
                        equal_capital = cash_to_allocate / num_buys
                        for ticker in original_scores_map.keys():
                            provisional_allocations[ticker] = equal_capital

                # Iteratively apply 40% cap and redistribute excess
                if provisional_allocations:
                    max_capital_per_stock = cash_to_allocate * 0.40
                    MAX_ITERATIONS = 10

                    current_round_allocations = provisional_allocations.copy()

                    for iteration in range(MAX_ITERATIONS):
                        print(f"Cap & Redistribute Iteration {iteration + 1}")
                        excess_from_capping_this_round = 0
                        stocks_newly_capped_this_round = {} # Ticker -> capped_amount

                        eligible_for_capping_pass = {t: v for t, v in current_round_allocations.items() if t not in final_allocations and v > 0.01}

                        if not eligible_for_capping_pass:
                            print("No stocks eligible for current capping pass.")
                            break

                        # Identify stocks exceeding cap and calculate excess
                        for ticker, proposed_capital in eligible_for_capping_pass.items():
                            if proposed_capital > max_capital_per_stock:
                                stocks_newly_capped_this_round[ticker] = max_capital_per_stock
                                excess_from_capping_this_round += (proposed_capital - max_capital_per_stock)

                        # Move newly capped stocks to final_allocations
                        for ticker, capped_amount in stocks_newly_capped_this_round.items():
                            final_allocations[ticker] = capped_amount
                            current_round_allocations.pop(ticker, None) # Remove from current round's pool

                        if excess_from_capping_this_round < 0.01: # Minimal or no excess to redistribute
                            print("No significant excess capital to redistribute in this iteration.")
                            break

                        # Prepare for redistribution: stocks not yet in final_allocations
                        pool_for_redistribution = {t: v for t,v in current_round_allocations.items() if t not in final_allocations and v > 0.01}
                        if not pool_for_redistribution:
                            print(f"Excess capital ${excess_from_capping_this_round:,.2f} remains but no stocks to redistribute to.")
                            # This excess will implicitly remain in portfolio cash
                            break

                        # Sum original scores of stocks in the current redistribution pool
                        sum_scores_redist_pool = sum(original_scores_map[t] for t in pool_for_redistribution if original_scores_map.get(t,0) > 0)

                        if sum_scores_redist_pool > 0: # Redistribute based on score
                            print(f"Redistributing ${excess_from_capping_this_round:,.2f} based on scores to {len(pool_for_redistribution)} stocks.")
                            for ticker in list(pool_for_redistribution.keys()): # list() for safe modification
                                score = original_scores_map.get(ticker,0)
                                if score > 0:
                                    additional_capital = (score / sum_scores_redist_pool) * excess_from_capping_this_round
                                    current_round_allocations[ticker] += additional_capital
                        else: # Fallback: Redistribute excess equally if no positive scores in pool
                            print(f"Redistributing ${excess_from_capping_this_round:,.2f} equally to {len(pool_for_redistribution)} stocks (no positive scores in pool).")
                            if pool_for_redistribution: # Ensure non-empty before division
                                capital_per_ticker_excess = excess_from_capping_this_round / len(pool_for_redistribution)
                                for ticker in list(pool_for_redistribution.keys()):
                                     current_round_allocations[ticker] += capital_per_ticker_excess
                            else: # Should not happen due to check above, but as safeguard
                                print(f"Error: Tried equal redistribution with no pool. Excess ${excess_from_capping_this_round:,.2f} remains.")
                                break # Break from iterations

                        if iteration == MAX_ITERATIONS - 1:
                            print("Warning: Max iterations reached in capital allocation capping.")

                    # Add any remaining allocations from current_round_allocations (that were never capped) to final_allocations
                    for ticker, capital in current_round_allocations.items():
                        if ticker not in final_allocations:
                            if capital > max_capital_per_stock: # Final check against cap
                                final_allocations[ticker] = max_capital_per_stock
                                print(f"Post-loop cap for {ticker} at ${max_capital_per_stock:,.2f}. Initial: ${capital:,.2f}")
                            elif capital > 1.0: # Minimum meaningful allocation
                                final_allocations[ticker] = capital
                            else:
                                print(f"Final allocation for {ticker} (${capital:,.2f}) too small, discarded.")
                else: # No buy_targets initially
                    print("No buy targets to allocate capital to.")

            if final_allocations:
                print("Final capital allocations after 40% cap and redistribution:")
                for t, cap in final_allocations.items():
                    print(f"  {t}: ${cap:,.2f}")
                print(f"Total allocated: ${sum(final_allocations.values()):,.2f} from initial cash of ${cash_to_allocate:,.2f}")

            # Execute trades based on final_allocations
            # Note: The `buy_targets` list still holds all initial candidates. We only trade those in `final_allocations`.
            for ticker, allocated_capital in final_allocations.items():
                if allocated_capital <= 1.0: # Skip if capital is negligible (e.g. $1)
                    print(f"Skipping buy for {ticker}: Final allocation too small (${allocated_capital:.2f}).")
                    continue

                # Retrieve original score for logging
                original_score = original_scores_map.get(ticker, 0) # Should exist if ticker in final_allocations

                if ticker not in all_price_data or current_date not in all_price_data[ticker].index:
                    print(f"Skipping buy for {ticker}: No price data available for {current_date.strftime('%Y-%m-%d')}")
                    continue

                execution_price = all_price_data[ticker].loc[current_date, 'Open']
                if pd.isna(execution_price) or execution_price <= 0:
                    print(f"Skipping buy for {ticker}: Invalid execution price ${execution_price} on {current_date.strftime('%Y-%m-%d')}")
                    continue

                if portfolio['cash'] <= 1.0: # If practically no cash left for any more trades
                    print(f"Skipping buy for {ticker} (and subsequent buys): Insufficient total cash (${portfolio['cash']:.2f}) left in portfolio.")
                    break # Stop trying to buy more stocks if cash is depleted

                shares_to_buy_approx = allocated_capital / execution_price
                shares_to_buy = int(shares_to_buy_approx)
                cost = shares_to_buy * execution_price

                if shares_to_buy > 0 and portfolio['cash'] >= cost:
                    trades_executed.append({
                        'Date': current_date.strftime('%Y-%m-%d'),
                        'Ticker': ticker,
                        'Action': 'Buy (Quarterly Rebalance)',
                        'Price': execution_price,
                        'Shares': shares_to_buy,
                        'SentimentScoreAtTrade': original_score,
                        'PortfolioCashBeforeTrade': portfolio['cash'],
                        'PortfolioValueBeforeTrade': portfolio['total_value']
                    })
                    positions[ticker]['shares'] += shares_to_buy
                    positions[ticker]['execution_price'] = execution_price
                    portfolio['cash'] -= cost
                    print(f"{current_date.strftime('%Y-%m-%d')}: BOUGHT (Q Rebalance) {shares_to_buy} {ticker} @ ${execution_price:.2f}, Cost: ${cost:.2f}, Final Alloc Cap: ${allocated_capital:,.2f}, Sentiment: {original_score:.2f}")
                else:
                    print(f"Could not buy {ticker}: Shares_to_buy={shares_to_buy}, Current Cash=${portfolio['cash']:.2f}, Cost=${cost:.2f}, Final Alloc Cap: ${allocated_capital:,.2f}")

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
        metrics = calculate_performance_metrics(portfolio_history['total_value'], risk_free_rate_param=RISK_FREE_RATE)
        print("\n--- Backtest Performance ---")
        for metric, value in metrics.items():
            print(f"{metric}: {value:.2%}" if isinstance(value, (int, float)) and ("Return" in metric or "Rate" in metric or "Volatility" in metric or "Drawdown" in metric) else f"{metric}: {value}")

    # 6. Save Results
        try:
            portfolio_history.to_csv(portfolio_performance_csv_path)
            print(f"\nDaily portfolio performance saved to: {portfolio_performance_csv_path}")
        except Exception as e:
            print(f"Error saving portfolio performance: {e}")

        if trades_executed:
            trades_df = pd.DataFrame(trades_executed)
            try:
                trades_df.to_csv(trades_log_csv_path, index=False)
                print(f"Trades log saved to: {trades_log_csv_path}")
            except Exception as e:
                print(f"Error saving trades log: {e}")
        else:
            print("No trades were executed during the backtest.")

    if quarterly_portfolio_log:
        quarterly_df = pd.DataFrame(quarterly_portfolio_log)
        try:
            quarterly_df.to_csv(quarterly_portfolio_composition_csv_path, index=False)
            print(f"Quarterly portfolio composition saved to: {quarterly_portfolio_composition_csv_path}")
        except Exception as e:
            print(f"Error saving quarterly portfolio composition: {e}")
    else:
        print("No quarterly portfolio compositions were logged.")


if __name__ == "__main__":
    cli_args = parse_arguments()
    main(cli_args)
