import pandas as pd
import os

# Input CSV file from the previous processing step
INPUT_CSV = "processed_13f_data/consolidated_13f_holdings.csv"
# Output directory for processed data (should exist, but check)
PROCESSED_DIR = "processed_13f_data"
# Output CSV file for filtered data
OUTPUT_CSV = os.path.join(PROCESSED_DIR, "smart_money_holdings.csv")

# Placeholder list of "Smart Money" CIKs
# In a real scenario, this might come from a config file, database, or API.
# Using the CIK from the previous example runs: 0001067983 (Berkshire Hathaway)
SMART_MONEY_CIKS = [
    '0001067983',  # Example: Berkshire Hathaway Inc.
    'CIK_EXAMPLE_2', # Placeholder for another CIK
    'CIK_EXAMPLE_3'  # Placeholder for yet another CIK
]

def ensure_processed_dir_exists():
    """Ensures the processed data directory exists."""
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)
        print(f"Created directory: {PROCESSED_DIR}")

def filter_holdings_by_cik(df, cik_list):
    """
    Filters the DataFrame to include only records where 'filer_cik' is in the cik_list.
    """
    # Ensure filer_cik is string type for comparison, like the elements in cik_list
    # The CIKs in the CSV should now be correctly formatted strings with leading zeros.
    # However, it's good practice to ensure the column is treated as string if there's any doubt.
    df['filer_cik'] = df['filer_cik'].astype(str)
    filtered_df = df[df['filer_cik'].isin(cik_list)]
    return filtered_df

def main():
    ensure_processed_dir_exists()

    # Check if the input file exists
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Input CSV file not found at {INPUT_CSV}")
        print("Please ensure 'consolidated_13f_holdings.csv' exists from the previous processing step.")
        return

    try:
        # Read the consolidated holdings data, ensuring filer_cik and reporting_date are read as string
        holdings_df = pd.read_csv(INPUT_CSV, dtype={'filer_cik': str, 'reporting_date': str})
        print(f"Read {len(holdings_df)} records from {INPUT_CSV}")
    except pd.errors.EmptyDataError:
        print(f"Error: Input CSV file {INPUT_CSV} is empty.")
        return
    except Exception as e:
        print(f"Error reading CSV file {INPUT_CSV}: {e}")
        return

    if holdings_df.empty:
        print("Input CSV is empty. No data to filter.")
        return
        
    # Filter the DataFrame
    print(f"Filtering for CIKs: {SMART_MONEY_CIKS}")
    smart_money_df = filter_holdings_by_cik(holdings_df, SMART_MONEY_CIKS)

    if smart_money_df.empty:
        print("No holdings found for the specified Smart Money CIKs.")
    else:
        # Save the filtered data
        try:
            smart_money_df.to_csv(OUTPUT_CSV, index=False)
            print(f"Successfully saved {len(smart_money_df)} filtered records to {OUTPUT_CSV}")
        except Exception as e:
            print(f"Error writing filtered data to CSV {OUTPUT_CSV}: {e}")

if __name__ == "__main__":
    main()
