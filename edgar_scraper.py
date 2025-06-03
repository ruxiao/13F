import requests
from bs4 import BeautifulSoup
import os
import time
import pandas as pd # Added for pd.to_datetime
import re # For CIK extraction

# Define the base URL for SEC EDGAR searches
BASE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"

# Define headers to mimic a browser visit
# SEC requires a custom User-Agent: https://www.sec.gov/os/developer_faq#how-can-i-prevent-my-automated-crawler-from-being-blocked
HEADERS = {
    'User-Agent': 'MyCompanyName MyContactEmail@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

# Directory to store downloaded filings
DOWNLOAD_DIR = "13f_filings"

def create_download_dir():
    """Creates the download directory if it doesn't exist."""
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

def search_13f_filings(company_name="", cik="", filing_type="13F-HR", count="40"):
    """
    Searches for 13F filings on SEC EDGAR.
    'count' is the number of results per page.
    """
    params = {
        "action": "getcompany",
        "company": company_name,
        "type": filing_type,
        "dateb": "",
        "owner": "exclude",
        "start": "",
        "count": str(count), # Ensure count is a string for the request params
        "output": "atom" # Atom feed for easier parsing
    }
    if cik:
        params["CIK"] = cik

    response = requests.get(BASE_URL, params=params, headers=HEADERS)
    response.raise_for_status() # Raise an exception for HTTP errors

    return response.content

def parse_atom_feed_and_get_filing_links(atom_feed_content):
    """
    Parses the Atom feed to find links to the filing detail pages.
    Returns a list of dictionaries, each containing 'filing_date' and 'link',
    sorted by filing_date descending.
    """
    soup = BeautifulSoup(atom_feed_content, 'xml') # Use 'xml' parser for Atom feeds
    filing_entries = [] # Will store dicts: {'filing_date': 'YYYY-MM-DD', 'link': '...'}
    entries = soup.find_all('entry')
    for entry in entries:
        link_tag = entry.find('link', {'rel': 'alternate', 'type': 'text/html'})
        updated_tag = entry.find('updated')

        if link_tag and link_tag.get('href') and updated_tag and updated_tag.text:
            filing_date_str = updated_tag.text
            try:
                filing_date = pd.to_datetime(filing_date_str).strftime('%Y-%m-%d')
                filing_entries.append({'filing_date': filing_date, 'link': link_tag['href']})
            except Exception as e:
                print(f"Warning: Could not parse filing date '{filing_date_str}': {e}")

    if filing_entries:
        filing_entries.sort(key=lambda x: x['filing_date'], reverse=True)

    return filing_entries

def get_filing_document_links(doc_page_soup, base_url):
    """
    Parses the BeautifulSoup object of a filing's index page to find links for:
    1. Primary Document (13F-HR, XML/HTML view preferred, then TXT)
    2. Information Table (XML preferred, then TXT)
    Returns a dictionary: {'primary_doc': {'link': str, 'type': str},
                           'info_table': {'link': str, 'type': str}}
    Type can be 'xml', 'txt', 'html'.
    """
    results = {
        'primary_doc': {'link': None, 'type': None},
        'info_table': {'link': None, 'type': None}
    }

    doc_table = doc_page_soup.find('table', class_=['tableFile', 'tableFile2', 'tableBlue'])
    if not doc_table: doc_table = doc_page_soup.find('table', summary='Document Format Files')
    if not doc_table: # Broader fallback
        all_tables = doc_page_soup.find_all('table')
        for table_candidate in all_tables:
            if table_candidate.find('a', href=lambda x: x and '/Archives/edgar/data/' in x):
                doc_table = table_candidate; break

    if not doc_table:
        print(f"Warning: Could not find any document table on page URL {base_url}")
        return results

    info_table_candidates = [] # Store as {'priority': P, 'link': L, 'type': T}

    rows = doc_table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 3: continue

        description_text = cells[1].text.strip().lower()
        link_tag = cells[2].find('a')
        doc_type_text = cells[3].text.strip().lower() if len(cells) > 3 else ""

        if not (link_tag and link_tag.get('href')): continue

        href = link_tag['href']
        link_text = link_tag.text.strip().lower()

        # Resolve relative URLs
        if not href.startswith('http'):
            # Correctly join base URL (e.g., https://www.sec.gov/Archives/edgar/data/CIK/ACC/...-index.html)
            # with relative href (e.g., form13finfotable.xml)
            # The base_url needs to be the path to the directory containing the file, not the file itself.
            # Example: base_url = "https://www.sec.gov/Archives/edgar/data/1067983/000106798324000009/"
            # Simple approach: if href doesn't start with /Archives, it's relative to current path
            if not href.startswith('/'):
                current_path = base_url.rsplit('/', 1)[0]
                href = f"{current_path}/{href}"
            else: # Starts with /Archives
                 href = "https://www.sec.gov" + href


        # --- Primary Document Logic ---
        # Check if it's a 13F-HR type or described as primary document
        is_13f_hr_type = "13f-hr" == doc_type_text or "13f-hr/a" == doc_type_text
        is_primary_description = "primary document" in description_text or \
                                 ("form 13f-hr" in description_text and "information table" not in description_text)

        if is_13f_hr_type or is_primary_description:
            if href.endswith('.xml'): # This is often an HTML view styled by XSL
                if not results['primary_doc']['link'] or results['primary_doc']['type'] == 'txt':
                    results['primary_doc'] = {'link': href, 'type': 'html_or_xml'} # Could be raw XML or HTML view
            elif href.endswith('.txt'):
                if not results['primary_doc']['link']: # Prioritize XML/HTML view over full TXT
                    results['primary_doc'] = {'link': href, 'type': 'txt'}
        # Fallback for "complete submission" text file if no other primary doc found
        elif "complete submission" == description_text and href.endswith('.txt'):
            if not results['primary_doc']['link']:
                results['primary_doc'] = {'link': href, 'type': 'txt'}

        # --- Information Table Logic ---
        # Priority 1: Exact match for 'form13fInfoTable.xml' (typically raw XML)
        if "form13finfotable.xml" == link_text and href.endswith(".xml"):
            info_table_candidates.append({'priority': 1, 'link': href, 'type': 'xml'})
        # Priority 1.5: Link text contains 'INFORMATION TABLE' and href is .xml
        elif 'information table' in description_text and href.endswith(".xml"):
            info_table_candidates.append({'priority': 1.5, 'link': href, 'type': 'xml'})
        # Priority 2: href contains 'form13fInfoTable.xml' or 'infotable.xml' (could be HTML view or raw XML)
        elif ("form13finfotable.xml" in href or "infotable.xml" in href) and href.endswith(".xml"):
            info_table_candidates.append({'priority': 2, 'link': href, 'type': 'xml'})
        # Priority 3: href ends with '_table.xml'
        elif href.endswith("_table.xml"):
            info_table_candidates.append({'priority': 3, 'link': href, 'type': 'xml'})
        # Priority 4: TXT file described as 'information table' or '13f holdings' or 'table'
        elif href.endswith(".txt") and ("information table" in description_text or "13f holdings" in description_text or "table" in description_text):
            # Avoid if it's the primary document (complete submission text file)
            if not (results['primary_doc']['link'] == href and results['primary_doc']['type'] == 'txt'):
                 info_table_candidates.append({'priority': 4, 'link': href, 'type': 'txt'})
        # Priority 5: Any other XML not clearly the primary doc
        elif href.endswith(".xml") and not (is_13f_hr_type or is_primary_description):
             info_table_candidates.append({'priority': 5, 'link': href, 'type': 'xml'})
        # Priority 6: Any other TXT not clearly the primary doc or complete submission
        elif href.endswith(".txt") and not (is_13f_hr_type or is_primary_description or "complete submission" == description_text):
             info_table_candidates.append({'priority': 6, 'link': href, 'type': 'txt'})


    if info_table_candidates:
        info_table_candidates.sort(key=lambda x: x['priority'])
        results['info_table'] = {'link': info_table_candidates[0]['link'], 'type': info_table_candidates[0]['type']}

    if not results['info_table']['link']: print(f"Warning: Could not find a suitable Information Table link on page URL {base_url}")
    if not results['primary_doc']['link']: print(f"Warning: Could not find a suitable Primary Document link on page URL {base_url}")

    return results

def extract_accession_number_from_url(url_str):
    """Helper to extract accession number from SEC URL for filename uniqueness."""
    try:
        # Example URL: https://www.sec.gov/Archives/edgar/data/1067983/000106798323000038/0001067983-23-000038-index.html
        # Or direct file URL: /Archives/edgar/data/1067983/000106798323000038/form13fInfoTable.xml
        parts = url_str.split('/')
        for i, part in enumerate(parts):
            if part.isdigit() and len(part) >= 10 and (part.count('-') == 0 or part.count('-') == 2) : # Likely an accession number part
                # Check if the previous part is a CIK (numeric)
                if i > 0 and parts[i-1].isdigit():
                    # Check if the accession number is the directory name like 0001067983-23-000038
                    # Or if it's embedded in a filename
                    acc_num_candidate = part
                    if '-' in acc_num_candidate and len(acc_num_candidate.split('-')) == 3: # e.g. 0001067983-23-000038
                        return acc_num_candidate
                    # Try to find it in the filename like 000106798323000038
                    elif len(acc_num_candidate) > 15 and acc_num_candidate.startswith(parts[i-1]): # e.g. 000106798323000038
                         # Attempt to format it like 0001067983-23-000038
                        if len(acc_num_candidate) == len(parts[i-1]) + 8: # CIK + YY + Number
                            return f"{parts[i-1]}-{acc_num_candidate[len(parts[i-1]):len(parts[i-1])+2]}-{acc_num_candidate[len(parts[i-1])+2:]}"
        # Fallback for accession numbers that are just numeric directories before the file
        # e.g. /Archives/edgar/data/886982/000110465923122468/infotable.xml -> 000110465923122468
        for part in reversed(parts):
            if part.isdigit() and len(part) > 15: # A long numeric string is often the accession number directory
                return part

    except Exception as e:
        print(f"Error extracting accession number: {e}")
    return "unknown_accession"

def extract_cik_from_url(url_str):
    """Helper to extract CIK from SEC URL."""
    try:
        # Example URL: https://www.sec.gov/Archives/edgar/data/1067983/000106798323000038/...
        # The CIK is usually the directory name after '/data/'
        match = re.search(r"/data/(\d+)/", url_str)
        if match:
            return match.group(1).zfill(10) # Pad with leading zeros to 10 digits
    except Exception as e:
        print(f"Error extracting CIK from URL {url_str}: {e}")
    return "unknown_cik"

def fetch_page_with_retries(url, headers, max_retries=3, initial_delay=2):
    """Fetches a page with retries and exponential backoff for server errors."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=15) # Added stream=True and timeout
            response.raise_for_status() # Raise HTTPError for bad responses (4XX, 5XX)
            return response
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [500, 502, 503, 504] and attempt < max_retries - 1:
                delay = initial_delay * (2 ** attempt)
                print(f"  Server error ({e.response.status_code}) fetching {url}. Retrying in {delay}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                print(f"  Failed to fetch {url} after {attempt + 1} attempts due to HTTPError: {e}")
                return None # Propagate error if it's a client error or final attempt
        except requests.exceptions.RequestException as e:
            print(f"  Request failed for {url}: {e}. (Attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                delay = initial_delay * (2 ** attempt)
                time.sleep(delay)
            else:
                return None # All retries failed
    return None


def download_filing_doc(file_url, cik, accession_number, suffix="document"):
    """
    Downloads the specified filing document with a given suffix for clarity, using retries.
    """
    response = fetch_page_with_retries(file_url, HEADERS)
    if not response:
        print(f"  Failed to download {file_url} after multiple retries.")
        return None

    try:
        original_filename = file_url.split('/')[-1]
        if not original_filename or original_filename.endswith('/'): # Handle cases where URL might end with / or filename is missing
            # Try to get a name from the suffix and common extensions
            if "xml" in file_url.lower(): original_filename = f"{suffix}.xml"
            elif "txt" in file_url.lower(): original_filename = f"{suffix}.txt"
            else: original_filename = f"{suffix}.html" # Default if truly unknown

        # Sanitize accession number for use in filename
        safe_accession_number = accession_number.replace('-', '').replace('/', '_')

        # Determine a more descriptive name using suffix
        _ , ext = os.path.splitext(original_filename)
        if not ext: # If original_filename somehow had no extension
            if "xml" in original_filename.lower(): ext = ".xml"
            elif "txt" in original_filename.lower(): ext = ".txt"
            else: ext = ".html" # Default

        # Construct filename: CIK_Accession_Suffix.Extension
        filename = os.path.join(DOWNLOAD_DIR, f"{cik}_{safe_accession_number}_{suffix}{ext}")

        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  Successfully downloaded: {filename}")
        return filename
    except requests.exceptions.RequestException as e:
        print(f"  Error downloading {file_url}: {e}")
        return None

# Removed older main() function that was here.

def main(target_urls=None):
    """
    Main function to scrape 13F filings from a list of specific filing page URLs.
    :param target_urls: List of SEC EDGAR *-index.html URLs.
    """
    if target_urls is None:
        # Default to the list specified in the subtask
        target_urls = [
            "https://www.sec.gov/Archives/edgar/data/1067983/000106798324000009/0001067983-24-000009-index.html",
            "https://www.sec.gov/Archives/edgar/data/1067983/000106798323000013/0001067983-23-000013-index.html",
            "https://www.sec.gov/Archives/edgar/data/1067983/000106798323000008/0001067983-23-000008-index.html",
        ]

    create_download_dir()

    for url_index, doc_page_url in enumerate(target_urls):
        print(f"\nProcessing URL ({url_index + 1}/{len(target_urls)}): {doc_page_url}")

        print(f"  Waiting for 2 seconds before fetching page...")
        time.sleep(2) # Delay before fetching the index page

        page_response = fetch_page_with_retries(doc_page_url, HEADERS)
        if not page_response or not page_response.content:
            print(f"  Failed to fetch main document page {doc_page_url} after retries. Skipping.")
            continue

        doc_page_soup = BeautifulSoup(page_response.content, 'html.parser')
        # The base_url for resolving relative links is the URL of the directory containing the index page
        base_url_for_relative = doc_page_url.rsplit('/', 1)[0] + '/'


        cik = extract_cik_from_url(doc_page_url) # CIK from index page URL
        accession_num = extract_accession_number_from_url(doc_page_url) # Accession from index page URL

        if cik == "unknown_cik" or accession_num == "unknown_accession":
            print(f"  Critical: Could not determine CIK or Accession number for {doc_page_url}. Skipping.")
            continue

        print(f"  Extracted CIK: {cik}, Accession: {accession_num}")

        file_links = get_filing_document_links(doc_page_soup, base_url_for_relative)

        downloaded_primary = False
        primary_doc_info = file_links.get('primary_doc', {})
        info_table_info = file_links.get('info_table', {})

        if primary_doc_info.get('link'):
            print(f"    Attempting to download Primary Document ({primary_doc_info.get('type', 'N/A')}) from: {primary_doc_info['link']}")
            if download_filing_doc(primary_doc_info['link'], cik, accession_num, suffix="primary"):
                downloaded_primary = True
        else:
            print(f"    Primary Document link not found for: {doc_page_url}")

        if downloaded_primary: # Only proceed if primary (needed for date context) was obtained
            if info_table_info.get('link'):
                print(f"    Attempting to download Information Table ({info_table_info.get('type', 'N/A')}) from: {info_table_info['link']}")
                download_filing_doc(info_table_info['link'], cik, accession_num, suffix="infotable")
            else:
                print(f"    Info Table link not found for: {doc_page_url}, but primary was downloaded.")
        elif not downloaded_primary:
             print(f"    Skipping info table download because primary document was not successfully downloaded or found for {doc_page_url}.")

        time.sleep(1.1) # Respect SEC rate limits between processing different filing pages

    print("\nScraping run completed for all specified URLs.")


if __name__ == "__main__":
    # URLs for Berkshire Hathaway (CIK 1067983) filings as per subtask
    target_filing_urls = [
        "https://www.sec.gov/Archives/edgar/data/1067983/000106798324000009/0001067983-24-000009-index.html", # Q1 2024 (filed May 2024)
        "https://www.sec.gov/Archives/edgar/data/1067983/000106798323000013/0001067983-23-000013-index.html", # Q4 2023 (filed Feb 2024)
        "https://www.sec.gov/Archives/edgar/data/1067983/000106798323000008/0001067983-23-000008-index.html", # Q3 2023 (filed Nov 2023)
    ]
    main(target_urls=target_filing_urls)
