import requests
from bs4 import BeautifulSoup
import os
import time

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
    Returns a list of links to the 'documents' page for each filing.
    """
    soup = BeautifulSoup(atom_feed_content, 'xml') # Use 'xml' parser for Atom feeds
    filing_links = []
    # Find all 'entry' tags, which represent individual filings
    entries = soup.find_all('entry')
    for entry in entries:
        # The link to the filing's landing page is usually in 'link' tag with rel='alternate'
        link_tag = entry.find('link', {'rel': 'alternate', 'type': 'text/html'})
        if link_tag and link_tag.get('href'):
            filing_links.append(link_tag['href'])
    return filing_links

def get_filing_document_links(document_page_url):
    """
    Fetches the filing document page and extracts links to the information table
    (e.g., form13fInfoTable.xml, which is often an HTML view) AND the primary filing document (e.g. 13F-HR.xml or .txt).
    Returns a dictionary with 'info_table_link' and 'primary_doc_link'.
    """
    links = {'info_table': None, 'primary_doc': None, 'info_table_raw_xml': None}

    if not document_page_url.startswith('http'):
        document_page_url = "https://www.sec.gov" + document_page_url
        
    response = requests.get(document_page_url, headers=HEADERS)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    
    doc_table = soup.find('table', class_=['tableFile', 'tableFile2', 'tableBlue'])
    if not doc_table:
        doc_table = soup.find('table', summary='Document Format Files')
    if not doc_table: # Broader fallback
        all_tables = soup.find_all('table')
        for table_candidate in all_tables:
            if table_candidate.find('a', href=lambda x: x and '/Archives/edgar/data/' in x):
                doc_table = table_candidate
                break
    
    if not doc_table:
        print(f"Warning: Could not find any document table on page: {document_page_url}")
        return links

    rows = doc_table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 3: # Need at least Seq, Description, Link, Type
            continue

        #Indices: 0:Seq, 1:Description, 2:Document Link, 3:Type, 4:Size
        description_cell_text = cells[1].text.strip().lower()
        doc_link_tag = cells[2].find('a')
        file_type_cell_text = cells[3].text.strip().lower() if len(cells) > 3 else ""

        if doc_link_tag and doc_link_tag.get('href'):
            href = doc_link_tag['href']
            link_text = doc_link_tag.text.strip().lower() # text of the link, e.g. "form13finfotable.xml"

            # Ensure the link is absolute
            if not href.startswith('http'):
                href = "https://www.sec.gov" + href
            
            # 1. Look for the Information Table (usually an HTML view via XSL, or sometimes raw XML)
            # This is what the current `process_13f_data.py` expects (the HTML view)
            if ("form13finfotable.xml" in link_text or "form13finfotable.xml" in href) and "xslform" in href.lower(): # Check for XSL transform link
                if not links['info_table']: links['info_table'] = href
            # Fallback for info tables that might not be the XSL version but still named similarly or described as such
            elif ("form13finfotable.xml" in link_text or "infotable.xml" in link_text or "information table" == description_cell_text) and href.endswith('.xml'):
                 if not links['info_table_raw_xml']: links['info_table_raw_xml'] = href


            # 2. Look for the Primary Filing Document (13F-HR, 13F-HR/A)
            # This document contains the cover page data including the reporting date.
            # Prefer XML over TXT.
            if "13f-hr" == file_type_cell_text or "13f-hr/a" == file_type_cell_text:
                if href.endswith('.xml'): # Primary XML document
                    if not links['primary_doc'] or (links['primary_doc'] and links['primary_doc'].endswith('.txt')):
                        links['primary_doc'] = href
                elif href.endswith('.txt'): # Complete submission text file
                    if not links['primary_doc']: # Only take .txt if .xml for 13F-HR not found
                        links['primary_doc'] = href
            elif "complete submission" == description_cell_text and href.endswith('.txt'): # Another way to find the .txt
                 if not links['primary_doc']: links['primary_doc'] = href


    # If the XSL-transformed HTML info_table wasn't found, but a raw XML info_table was,
    # provide it. The processing script will need to handle raw XML info tables separately if this is used.
    # For now, the scraper prioritizes the HTML version as that's what process_13f_data.py handles.
    if not links['info_table'] and links['info_table_raw_xml']:
        print(f"FYI: Using raw XML info table for {document_page_url} as XSL/HTML version not found by specific patterns. Current processor expects HTML view.")
        links['info_table'] = links['info_table_raw_xml'] # This might break current process_13f_data.py if it's truly raw XML

    if not links['info_table']:
        print(f"Warning: Could not find a suitable Information Table link on page: {document_page_url}")
    if not links['primary_doc']:
        print(f"Warning: Could not find a suitable Primary Document (13F-HR) link on page: {document_page_url}")
        
    return links

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


def download_filing_doc(file_url, cik, accession_number, suffix="document"):
    """
    Downloads the specified filing document with a given suffix for clarity.
    """
    try:
        response = requests.get(file_url, headers=HEADERS, stream=True)
        response.raise_for_status()
        
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

def main():
    create_download_dir()
    # Example: Search for Berkshire Hathaway's 13F filings (CIK: 0001067983)
    target_cik = "0001067983"
    print(f"Searching for 13F filings for CIK: {target_cik}...")
    # Reduce count for testing to speed up, default is 40. Using 5 to get a few.
    filings_atom_feed = search_13f_filings(cik=target_cik, filing_type="13F-HR", count="5") 
    
    if filings_atom_feed:
        print("Search successful. Parsing feed...")
        document_page_links = parse_atom_feed_and_get_filing_links(filings_atom_feed)
        if document_page_links:
            print(f"Found {len(document_page_links)} filing document page links.")
            
            filings_to_process_count = 1 # Process one filing to test new download logic
            processed_count = 0

            for doc_page_link in document_page_links:
                if processed_count >= filings_to_process_count:
                    print(f"\nReached processing limit of {filings_to_process_count} for this run.")
                    break
                
                print(f"\nProcessing document page: {doc_page_link}")
                file_links = get_filing_document_links(doc_page_link)
                
                accession_num = extract_accession_number_from_url(doc_page_link)
                # Fallback for accession number if not found in main doc_page_link
                if not accession_num or accession_num == "unknown_accession":
                    if file_links.get('info_table'):
                        accession_num = extract_accession_number_from_url(file_links['info_table'])
                    elif file_links.get('primary_doc'):
                         accession_num = extract_accession_number_from_url(file_links['primary_doc'])

                if accession_num == "unknown_accession":
                    print(f"  Critical: Could not determine accession number for {doc_page_link}. Skipping downloads for this entry.")
                    processed_count +=1
                    time.sleep(1)
                    continue

                # Download Information Table
                if file_links.get('info_table'):
                    print(f"  Attempting to download Information Table from: {file_links['info_table']}")
                    download_filing_doc(file_links['info_table'], target_cik, accession_num, suffix="infotable")
                else:
                    print(f"  Info Table link not found for: {doc_page_link}")

                # Download Primary Document
                if file_links.get('primary_doc'):
                    print(f"  Attempting to download Primary Document from: {file_links['primary_doc']}")
                    download_filing_doc(file_links['primary_doc'], target_cik, accession_num, suffix="primary")
                else:
                    print(f"  Primary Document link not found for: {doc_page_link}")
                
                processed_count += 1
                time.sleep(1) # Respect SEC rate limits
        else:
            print("No filing document page links found in the feed.")
    else:
        print("No filings found or error in search.")

if __name__ == "__main__":
    main()
