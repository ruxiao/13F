import pandas as pd
import yfinance as yf
import os
from datetime import timedelta

# Input CSV file
SENTIMENT_SIGNALS_CSV = "processed_13f_data/sentiment_signals.csv"
# Output directory for price data
PRICE_DATA_DIR = "price_data"

# Date range extension
# Fetch data from 1 year before the first reporting date
# to 1 month after the last reporting date (or today if later)
DATE_RANGE_PRE_EXTENSION = timedelta(days=365)
DATE_RANGE_POST_EXTENSION = timedelta(days=30)

def ensure_price_data_dir_exists():
    """Ensures the price data directory exists."""
    if not os.path.exists(PRICE_DATA_DIR):
        os.makedirs(PRICE_DATA_DIR)
        print(f"Created directory: {PRICE_DATA_DIR}")

def get_cusips_and_date_range(filepath):
    """
    Reads the sentiment signals CSV to get unique CUSIPs and the min/max reporting dates.
    Returns a list of unique CUSIPs, a start date, and an end date for fetching price data.
    """
    if not os.path.exists(filepath):
        print(f"Error: Sentiment signals file not found at {filepath}")
        return [], None, None

    try:
        df = pd.read_csv(filepath, dtype={'cusip': str}) # Ensure CUSIP is read as string
        if df.empty:
            print(f"Sentiment signals file {filepath} is empty.")
            return [], None, None
    except pd.errors.EmptyDataError:
        print(f"Sentiment signals file {filepath} is empty (pd.errors.EmptyDataError).")
        return [], None, None
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return [], None, None

    unique_cusips = df['cusip'].unique().tolist()

    if 'reporting_date' not in df.columns or df['reporting_date'].isnull().all():
        print("Error: 'reporting_date' column is missing or all null in sentiment signals file.")
        return unique_cusips, None, None # Return CUSIPs but no dates

    df['reporting_date'] = pd.to_datetime(df['reporting_date'], errors='coerce')
    df.dropna(subset=['reporting_date'], inplace=True)

    if df.empty:
        print("No valid reporting dates found after parsing.")
        return unique_cusips, None, None

    min_date = df['reporting_date'].min()
    max_date = df['reporting_date'].max()

    # Extend date range
    start_date_fetch = min_date - DATE_RANGE_PRE_EXTENSION
    end_date_fetch = max_date + DATE_RANGE_POST_EXTENSION

    # Ensure end_date_fetch is not in the future beyond today for yfinance practical purposes
    # (yfinance typically fetches up to the last trading day)
    today = pd.to_datetime('today')
    if end_date_fetch > today:
        end_date_fetch = today + timedelta(days=1) # Fetch up to tomorrow to include today's data

    return unique_cusips, start_date_fetch.strftime('%Y-%m-%d'), end_date_fetch.strftime('%Y-%m-%d')

def map_cusip_to_ticker(cusip):
    """
    Maps CUSIP to a ticker symbol.
    Placeholder: Currently assumes CUSIP can be used as a ticker.
    A robust implementation would use an API or a mapping file.
    """
    # print("WARNING: Assuming CUSIP can be used as a ticker for yfinance. This may not work for all CUSIPs.")
    # For testing with known CUSIPs that are also tickers (e.g. some major stocks might have this)
    # Or if yfinance has some internal CUSIP handling (unlikely for most)

    # Manual mapping for a few known CUSIPs from the sample data
    cusip_to_ticker_map = {
        "037833100": "AAPL",        # Apple Inc.
        "023135106": "AMZN",        # Amazon.com Inc. (will not be in current signals)
        "594918104": "MSFT",        # Microsoft Corp (present in one of the simulated info tables, but not in all periods)
        "060505104": "BAC",         # Bank of America Corp
        "025816109": "AXP",         # American Express Co
        "191216100": "KO",          # Coca-Cola Co (will not be in current signals)
        "166764100": "CVX",         # Chevron Corp (will not be in current signals)
        # Add more if other CUSIPs from sentiment_signals.csv are easily identifiable
    }

    if cusip in cusip_to_ticker_map:
        ticker = cusip_to_ticker_map[cusip]
        print(f"  Manually mapped CUSIP {cusip} to Ticker {ticker}")
        return ticker

    # Fallback: if not in our manual map, try using the CUSIP directly (will likely fail for most)
    # Or return None to skip if CUSIPs are known to not be tickers generally.
    # For now, returning CUSIP to see yfinance attempt and fail, as per original design for unmapped.
    print(f"  CUSIP {cusip} not in manual map. Attempting to use CUSIP as ticker.")
    return cusip

def download_price_data(ticker_symbol, start_date, end_date):
    """
    Downloads historical OHLCV data for a given ticker.
    Returns a DataFrame or None if download fails.
    """
    try:
        print(f"Attempting to download data for ticker: {ticker_symbol} from {start_date} to {end_date}")
        stock = yf.Ticker(ticker_symbol)
        # history_df = stock.history(start=start_date, end=end_date, auto_adjust=False, back_adjust=False)
        # Using yf.download for potentially more reliability with multiple tickers / error handling
        history_df = yf.download(ticker_symbol, start=start_date, end=end_date, progress=False, auto_adjust=False)

        if history_df.empty:
            print(f"No data found for ticker {ticker_symbol} for the given date range.")
            return None

        # Handle potential MultiIndex columns if yfinance returns them even for a single ticker
        if isinstance(history_df.columns, pd.MultiIndex):
            # For a single ticker, the second level of column index is the ticker itself, which is redundant here.
            # We can drop it or, more simply, just use the first level.
            # Example: [('Open', 'AAPL'), ('Close', 'AAPL')] becomes ['Open', 'Close']
            history_df.columns = history_df.columns.droplevel(1) # Drop the ticker level from columns

        history_df.reset_index(inplace=True)
        history_df['Ticker'] = ticker_symbol # Add ticker symbol for reference
        print(f"Successfully downloaded data for {ticker_symbol}")
        return history_df
    except Exception as e:
        print(f"Error downloading data for ticker {ticker_symbol}: {e}")
        return None

def main():
    ensure_price_data_dir_exists()

    cusips, start_date, end_date = get_cusips_and_date_range(SENTIMENT_SIGNALS_CSV)

    if not cusips:
        print("No CUSIPs found to process. Exiting.")
        return

    if not start_date or not end_date:
        print("Could not determine a valid date range for fetching price data. Exiting.")
        return

    print(f"Identified {len(cusips)} unique CUSIPs.")
    print(f"Price data will be fetched for the period: {start_date} to {end_date}")
    print("WARNING: This script currently assumes CUSIPs can be directly used as ticker symbols for yfinance.")
    print("This assumption may fail for many CUSIPs. A proper CUSIP-to-Ticker mapping is recommended for robust use.")

    for cusip in cusips:
        print(f"\nProcessing CUSIP: {cusip}")
        ticker = map_cusip_to_ticker(cusip) # This currently just returns the CUSIP

        if not ticker: # Should not happen with current map_cusip_to_ticker
            print(f"Could not map CUSIP {cusip} to a ticker. Skipping.")
            continue

        price_df = download_price_data(ticker, start_date, end_date)

        if price_df is not None and not price_df.empty:
            output_filename = os.path.join(PRICE_DATA_DIR, f"{ticker.replace('/', '_')}.csv") # Sanitize ticker for filename
            try:
                price_df.to_csv(output_filename, index=False)
                print(f"Saved price data for {ticker} to {output_filename}")
            except Exception as e:
                print(f"Error saving price data for {ticker} to CSV: {e}")
        else:
            print(f"No price data downloaded for CUSIP {cusip} (Ticker: {ticker}).")

if __name__ == "__main__":
    main()
