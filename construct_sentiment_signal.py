import pandas as pd
import numpy as np # For NaN and infinity handling
import os

# Input CSV file
INPUT_CSV = "processed_13f_data/smart_money_holdings.csv"
# Output directory (should exist)
PROCESSED_DIR = "processed_13f_data"
# Output CSV file
OUTPUT_CSV = os.path.join(PROCESSED_DIR, "sentiment_signals.csv")

# Sentiment Score Weights
WEIGHT_CHANGE_NUM_INVESTORS = 1.0
WEIGHT_PCT_CHANGE_VALUE = 0.5 # Example weight
WEIGHT_PCT_CHANGE_SHARES = 0.5 # Example weight

def calculate_sentiment_score(row):
    """
    Calculates the sentiment score for a given row of data.
    Assumes the row contains necessary change metrics.
    """
    score = 0
    # Handle potential NaN values by treating them as 0 for scoring contribution
    score += row.get('change_in_num_sm_investors', 0) * WEIGHT_CHANGE_NUM_INVESTORS
    score += row.get('pct_change_in_total_sm_value', 0) * WEIGHT_PCT_CHANGE_VALUE
    score += row.get('pct_change_in_total_sm_shares', 0) * WEIGHT_PCT_CHANGE_SHARES
    return score

def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Input CSV file not found at {INPUT_CSV}")
        print("Please ensure 'smart_money_holdings.csv' exists.")
        return

    try:
        holdings_df = pd.read_csv(INPUT_CSV)
        if holdings_df.empty:
            print(f"Input file {INPUT_CSV} is empty. No sentiment signals to generate.")
            # Create an empty output file with headers if it's empty
            if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0 :
                 pd.DataFrame(columns=[
                    'cusip', 'reporting_date', 'total_sm_value', 'total_sm_shares', 'num_sm_investors',
                    'change_in_total_sm_value', 'change_in_total_sm_shares', 'change_in_num_sm_investors',
                    'pct_change_in_total_sm_value', 'pct_change_in_total_sm_shares', 'sentiment_score'
                ]).to_csv(OUTPUT_CSV, index=False)
            return
        print(f"Read {len(holdings_df)} records from {INPUT_CSV}")
    except pd.errors.EmptyDataError:
        print(f"Input file {INPUT_CSV} is empty. No sentiment signals to generate.")
        if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0 :
             pd.DataFrame(columns=[
                'cusip', 'reporting_date', 'total_sm_value', 'total_sm_shares', 'num_sm_investors',
                'change_in_total_sm_value', 'change_in_total_sm_shares', 'change_in_num_sm_investors',
                'pct_change_in_total_sm_value', 'pct_change_in_total_sm_shares', 'sentiment_score'
            ]).to_csv(OUTPUT_CSV, index=False)
        return
    except Exception as e:
        print(f"Error reading CSV file {INPUT_CSV}: {e}")
        return

    # Data Preparation
    holdings_df['reporting_date'] = pd.to_datetime(holdings_df['reporting_date'], errors='coerce')
    holdings_df.dropna(subset=['reporting_date'], inplace=True) # Remove rows where date couldn't be parsed
    
    if holdings_df.empty: # Check if DataFrame is empty after date parsing and dropna
        print(f"DataFrame became empty after date parsing/cleaning. No data to process for sentiment signals.")
        # Create an empty output file with headers
        pd.DataFrame(columns=[
            'cusip', 'reporting_date', 'total_sm_value', 'total_sm_shares', 'num_sm_investors',
            'change_in_total_sm_value', 'change_in_total_sm_shares', 'change_in_num_sm_investors',
            'pct_change_in_total_sm_value', 'pct_change_in_total_sm_shares', 'sentiment_score'
        ]).to_csv(OUTPUT_CSV, index=False)
        print(f"Empty {OUTPUT_CSV} created.")
        return

    # Sort by CUSIP and reporting_date for correct change calculation
    # Using CUSIP as the primary stock identifier. Name can be ambiguous.
    holdings_df.sort_values(by=['cusip', 'reporting_date'], inplace=True)

    # Group by cusip and reporting_date to get aggregate metrics
    # Note: The input smart_money_holdings.csv already contains one row per (filer_cik, cusip, reporting_date)
    # So, we need to aggregate across different 'filer_cik' for the same 'cusip' and 'reporting_date'.
    
    # Ensure correct dtypes for aggregation
    holdings_df['value_usd'] = pd.to_numeric(holdings_df['value_usd'], errors='coerce').fillna(0)
    holdings_df['quantity'] = pd.to_numeric(holdings_df['quantity'], errors='coerce').fillna(0)

    aggregated_df = holdings_df.groupby(['cusip', 'reporting_date']).agg(
        total_sm_value=('value_usd', 'sum'),
        total_sm_shares=('quantity', 'sum'),
        num_sm_investors=('filer_cik', 'nunique') # Count unique CIKs holding this stock
    ).reset_index()

    if aggregated_df.empty: # Should not happen if holdings_df was not empty post-dropna
        print("aggregated_df is empty after grouping. This implies no valid groups were formed.")
        pd.DataFrame(columns=[
            'cusip', 'reporting_date', 'total_sm_value', 'total_sm_shares', 'num_sm_investors',
            'change_in_total_sm_value', 'change_in_total_sm_shares', 'change_in_num_sm_investors',
            'pct_change_in_total_sm_value', 'pct_change_in_total_sm_shares', 'sentiment_score'
        ]).to_csv(OUTPUT_CSV, index=False)
        print(f"Empty {OUTPUT_CSV} created as aggregated_df was empty after grouping.")
        return

    # Calculate changes from the previous period for each stock (cusip)
    # We use groupby('cusip') and then diff() on the sorted data.
    # diff() calculates the difference from the PREVIOUS row within each group.
    
    # Ensure data is sorted before diff for correctness
    aggregated_df.sort_values(by=['cusip', 'reporting_date'], inplace=True)

    # Calculate absolute changes
    aggregated_df['change_in_total_sm_value'] = aggregated_df.groupby('cusip')['total_sm_value'].diff().fillna(0)
    aggregated_df['change_in_total_sm_shares'] = aggregated_df.groupby('cusip')['total_sm_shares'].diff().fillna(0)
    aggregated_df['change_in_num_sm_investors'] = aggregated_df.groupby('cusip')['num_sm_investors'].diff().fillna(0)

    # Calculate percentage changes
    # To avoid division by zero or issues with new stocks (previous value is NaN or 0),
    # we need to get the previous period's values carefully.
    # shift(1) gets the value from the previous row in the group.
    
    prev_total_sm_value = aggregated_df.groupby('cusip')['total_sm_value'].shift(1)
    prev_total_sm_shares = aggregated_df.groupby('cusip')['total_sm_shares'].shift(1)
    # prev_num_sm_investors = aggregated_df.groupby('cusip')['num_sm_investors'].shift(1) # Not typically used for pct change

    # Replace 0 with NaN in previous values to handle division by zero -> results in NaN for pct change
    # which can then be filled with 0 (for new stocks) or a large number if preferred.
    # np.where condition: if prev value is 0, use np.nan, else use prev value.
    # Then (current - prev) / prev_with_nan. Resulting NaN can be filled.
    
    # pct_change = (current - previous) / previous
    # If previous is 0 and current is >0, pct_change is infinite. If both 0, it's NaN.
    # If previous is NaN (first entry in group), pct_change is NaN.
    
    aggregated_df['pct_change_in_total_sm_value'] = (aggregated_df['change_in_total_sm_value'] / prev_total_sm_value.replace(0, np.nan)).fillna(0)
    aggregated_df['pct_change_in_total_sm_shares'] = (aggregated_df['change_in_total_sm_shares'] / prev_total_sm_shares.replace(0, np.nan)).fillna(0)
    
    # Replace inf with a large number or 0, depending on desired handling.
    # For sentiment, a very large positive change might be a strong signal.
    # Let's cap it or set to a high value (e.g., 10 for 1000% if prev was tiny, or just fill with 0 if it's new)
    # A common approach for new stocks (where prev is NaN, leading to .fillna(0) above) is that pct_change is 0.
    # If prev_value was 0 and current is >0, then pct_change is inf.
    aggregated_df.replace([np.inf, -np.inf], 0, inplace=True) # Or a defined cap like 10 (for 1000%)

    # Calculate Sentiment Score
    # Ensure NaNs in change columns are 0 before applying score to avoid NaN scores
    change_cols_for_scoring = ['change_in_num_sm_investors', 'pct_change_in_total_sm_value', 'pct_change_in_total_sm_shares']
    for col in change_cols_for_scoring:
        if col not in aggregated_df.columns: # Should not happen with current logic
             aggregated_df[col] = 0 
        else:
            aggregated_df[col] = aggregated_df[col].fillna(0)


    aggregated_df['sentiment_score'] = aggregated_df.apply(calculate_sentiment_score, axis=1)

    # Select and order columns for the output CSV
    output_columns = [
        'cusip', 'reporting_date', 
        'total_sm_value', 'total_sm_shares', 'num_sm_investors',
        'change_in_total_sm_value', 'change_in_total_sm_shares', 'change_in_num_sm_investors',
        'pct_change_in_total_sm_value', 'pct_change_in_total_sm_shares', 
        'sentiment_score'
    ]
    # Ensure all output columns exist, add missing ones with default value (e.g. 0 or NaN)
    for col in output_columns:
        if col not in aggregated_df.columns:
            aggregated_df[col] = 0 # Or np.nan if preferred for missing metric columns

    final_df = aggregated_df[output_columns]

    try:
        final_df.to_csv(OUTPUT_CSV, index=False)
        print(f"Successfully generated sentiment signals and saved to {OUTPUT_CSV}")
    except Exception as e:
        print(f"Error writing sentiment signals to CSV {OUTPUT_CSV}: {e}")

if __name__ == "__main__":
    main()
