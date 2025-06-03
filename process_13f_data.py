import os
import xml.etree.ElementTree as ET
import pandas as pd
from bs4 import BeautifulSoup # For potential text file parsing or malformed XML
import re # For namespace detection

# Input directory for downloaded filings
DOWNLOAD_DIR = "13f_filings"
# Output directory for processed data
PROCESSED_DIR = "processed_13f_data"

# Define the columns for the output CSV
CSV_COLUMNS = [
    "filer_cik", "reporting_date", "name_of_issuer", "cusip",
    "value_usd", "quantity", "security_type", "source_file"
]

def create_processed_dir():
    """Creates the processed data directory if it doesn't exist."""
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)

def infer_cik_from_filename(filename):
    """Infers CIK from the filename (e.g., 0001067983_000095012325005701_form13fInfoTable.xml)"""
    parts = filename.split('_')
    if len(parts) > 0 and parts[0].isdigit():
        # CIKs are often 10 digits, ensure it's zero-padded to this length
        # Example: '12345' becomes '0000012345'
        return parts[0].zfill(10)
    return None

def parse_xml_infotable_content(filepath, filer_cik, reporting_date_to_assign):
    """
    Parses the 13F information table XML file (raw XML, not HTML view).
    Assigns the provided reporting_date_to_assign to each holding.
    """
    holdings = []
    try:
        print(f"DEBUG: Parsing XML infotable: {filepath}")
        tree = ET.parse(filepath)
        root = tree.getroot()
        print(f"DEBUG: XML root tag: {root.tag}")

        # Dynamically get the namespace from the root element
        root_tag_match = re.match(r'(\{.*\})(.*)', root.tag)
        ns_uri = ""
        if root_tag_match and root_tag_match.group(1):
            ns_uri = root_tag_match.group(1).strip('{}')
        print(f"DEBUG: Detected namespace URI: '{ns_uri}'")

        # Define tags based on whether namespace is present
        # For the provided simulated XMLs, the root is <informationTable> and repeating holding item is <infoTable>
        holding_entry_tag = f"{{{ns_uri}}}infoTable" if ns_uri else "infoTable" # Changed from infoTableEntry
        print(f"DEBUG: Expecting holding entry tag: '{holding_entry_tag}'")

        nameofissuer_tag = f"{{{ns_uri}}}nameOfIssuer" if ns_uri else "nameOfIssuer"
        cusip_tag = f"{{{ns_uri}}}cusip" if ns_uri else "cusip"
        value_tag = f"{{{ns_uri}}}value" if ns_uri else "value"
        shrsorprnamt_tag = f"{{{ns_uri}}}shrsOrPrnAmt" if ns_uri else "shrsOrPrnAmt"
        sshprnamt_tag = f"{{{ns_uri}}}sshPrnamt" if ns_uri else "sshPrnamt"
        sshprnamttype_tag = f"{{{ns_uri}}}sshPrnamtType" if ns_uri else "sshPrnamtType"

        # The root of the simulated file is <infoTable>, children are <infoTableEntry>
        for holding_node in root.findall(holding_entry_tag):
            try:
                name_of_issuer_node = holding_node.find(nameofissuer_tag)
                name_of_issuer = name_of_issuer_node.text if name_of_issuer_node is not None else None

                cusip_node = holding_node.find(cusip_tag)
                cusip_raw = cusip_node.text if cusip_node is not None else None
                cusip = cusip_raw.strip().zfill(9) if cusip_raw else None # Standardize CUSIP to 9 chars, zero-padded

                value_node = holding_node.find(value_tag)
                value_str = value_node.text if value_node is not None else None

                shrs_or_prn_amt_node = holding_node.find(shrsorprnamt_tag)
                quantity_str = None
                security_type = None
                if shrs_or_prn_amt_node is not None:
                    sshprnamt_node = shrs_or_prn_amt_node.find(sshprnamt_tag)
                    quantity_str = sshprnamt_node.text if sshprnamt_node is not None else None

                    sshprnamttype_node = shrs_or_prn_amt_node.find(sshprnamttype_tag)
                    security_type = sshprnamttype_node.text if sshprnamttype_node is not None else None

                # The simulated XML files have <value> reported in thousands.
                value_usd = int(value_str) * 1000 if value_str and value_str.isdigit() else None
                quantity = int(quantity_str) if quantity_str and quantity_str.isdigit() else None

                if not all([name_of_issuer, cusip, value_usd is not None, quantity is not None]):
                    # print(f"  Skipping a holding in {filepath} due to missing essential XML fields.")
                    continue

                holdings.append({
                    "filer_cik": filer_cik,
                    "reporting_date": reporting_date_to_assign,
                    "name_of_issuer": name_of_issuer,
                    "cusip": cusip,
                    "value_usd": value_usd,
                    "quantity": quantity,
                    "security_type": security_type,
                    "source_file": os.path.basename(filepath)
                })
            except AttributeError as e:
                print(f"  Skipping a holding in {filepath} due to structure issue or missing field: {e}")
                continue
        return holdings
    except ET.ParseError as e:
        print(f"Error parsing XML file {filepath}: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred while parsing XML {filepath}: {e}")
        return []

# Placeholder for the new function to parse primary document for reporting date
def parse_primary_document_for_date(primary_doc_path):
    """
    Parses the primary filing document (XML or TXT) to find the reporting date.
    Returns the date as a string (YYYY-MM-DD) or None if not found.
    """
    print(f"DEBUG: Attempting to parse date from primary_doc: {primary_doc_path}")
    date_str = None
    try:
        with open(primary_doc_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Regardless of original extension (.xml or .txt), parse with BeautifulSoup if it's HTML like.
        # The primary documents downloaded by the scraper are HTML views.
        soup = BeautifulSoup(content, 'html.parser')

        # Strategy 1: Find "Report for the Calendar Year or Quarter Ended:"
        # Example: <td class="FormText">Report for the Calendar Year or Quarter Ended:</td>
        #          <td class="FormDataR">03-31-2025</td>

        # Try finding by specific text in <p> tags for the simulated files
        found_p_tag_date = None
        for p_tag in soup.find_all('p'):
            text = p_tag.get_text(strip=True)
            if "Report for the Calendar Year or Quarter Ended:" in text:
                date_str_candidate = text.split("Report for the Calendar Year or Quarter Ended:")[1].strip()
                if date_str_candidate:
                    found_p_tag_date = date_str_candidate
                    break

        if found_p_tag_date:
            date_str = found_p_tag_date
        else: # Fallback to original td logic if p-tag logic fails
            form_text_elements = soup.find_all('td', class_='FormText')
            for el in form_text_elements:
                if "Report for the Calendar Year or Quarter Ended:" in el.get_text(strip=True):
                    next_td = el.find_next_sibling('td', class_='FormDataR')
                    if next_td:
                        date_str = next_td.get_text(strip=True)
                        break

        print(f"DEBUG: Extracted date_str (Report for Quarter Ended): '{date_str}'")
        if date_str:
            try:
                # Handles MM-DD-YYYY or YYYY-MM-DD if pandas can infer it
                dt_obj = pd.to_datetime(date_str, errors='raise')
                parsed_date = dt_obj.strftime('%Y-%m-%d')
                print(f"DEBUG: Parsed date to: '{parsed_date}'")
                return parsed_date
            except ValueError:
                print(f"  Could not parse date string '{date_str}' from (Calendar Year/Quarter) {primary_doc_path}.")
                date_str = None # Reset if parsing failed

        # Strategy 2: Fallback to Signature Date (less ideal as it's filing date, not period end)
        if not date_str:
            print("DEBUG: 'Report for Quarter Ended' date not found or failed to parse. Trying Signature Date.")
            # Try finding by specific text in <p> tags for signature date
            found_p_sig_date = None
            for p_tag in soup.find_all('p'):
                text = p_tag.get_text(strip=True)
                if "Signature Date:" in text:
                    date_str_candidate = text.split("Signature Date:")[1].strip()
                    if date_str_candidate:
                        found_p_sig_date = date_str_candidate
                        break
            if found_p_sig_date:
                 date_str = found_p_sig_date
            else: # Fallback to td logic for signature date
                form_data_elements = soup.find_all('td', class_='FormData')
                for el in form_data_elements:
                    parent_row = el.find_parent('tr')
                    if parent_row:
                        date_label_cell = parent_row.find('td', string=lambda t: t and "[Date]" in t)
                        if date_label_cell:
                            potential_date = el.get_text(strip=True)
                            if re.match(r"^\d{1,2}-\d{1,2}-\d{4}$", potential_date):
                                date_str = potential_date
                                break
            if date_str:
                try:
                    dt_obj = pd.to_datetime(date_str, errors='raise') # Handles MM-DD-YYYY
                    print(f"  Using signature date as fallback: {date_str} from {primary_doc_path}")
                    return dt_obj.strftime('%Y-%m-%d')
                except ValueError:
                    print(f"  Could not parse signature date string '{date_str}' from {primary_doc_path}.")
                    date_str = None

        if not date_str:
             print(f"  Reporting date not found in HTML primary document {primary_doc_path}.")

    except FileNotFoundError:
        print(f"Error: Primary document file not found at {primary_doc_path}")
    except Exception as e:
        print(f"Error parsing primary document {primary_doc_path} for date: {e}")

    return date_str # Which could be None

def process_filings():
    """
    Processes all downloaded 13F filings.
    """
    create_processed_dir()
    all_holdings_data = []

    if not os.path.exists(DOWNLOAD_DIR):
        print(f"Download directory '{DOWNLOAD_DIR}' not found. Please run the scraper first.")
        return

    for filename in os.listdir(DOWNLOAD_DIR):
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        filer_cik = infer_cik_from_filename(filename)
        if not filer_cik:
            print(f"Could not infer CIK for {filename}, skipping.")
            continue

        print(f"Processing {filename} for CIK: {filer_cik}...")

        # Process only infotable files directly; primary docs are processed to get date for infotables
        if "_infotable.xml" in filename.lower() or "_infotable.html" in filename.lower(): # Should be .xml now
            # Construct corresponding primary document name
            # Assumes CIK_ACCESSION_suffix.ext format. Example: 0001067983_000095012325005701_infotable.xml
            parts = filename.split('_')
            if len(parts) < 3:
                print(f"  Could not determine accession number from info table filename: {filename}. Skipping.")
                continue

            # Reconstruct base: CIK_ACCESSION
            base_name_for_primary = f"{parts[0]}_{parts[1]}"

            primary_doc_path_xml = os.path.join(DOWNLOAD_DIR, f"{base_name_for_primary}_primary.xml")
            primary_doc_path_txt = os.path.join(DOWNLOAD_DIR, f"{base_name_for_primary}_primary.txt")

            reporting_date = None
            if os.path.exists(primary_doc_path_xml):
                reporting_date = parse_primary_document_for_date(primary_doc_path_xml)
            elif os.path.exists(primary_doc_path_txt):
                reporting_date = parse_primary_document_for_date(primary_doc_path_txt)
            else:
                print(f"  Warning: Primary document not found for info table {filename}. Reporting date will be missing.")

            # Now parse the info table, passing the found reporting date
            # The file at `filepath` should be the raw XML info table.
            if filepath.lower().endswith(".xml"): # Ensure it's XML before sending to XML parser
                holdings = parse_xml_infotable_content(filepath, filer_cik, reporting_date)
                all_holdings_data.extend(holdings)
            else:
                print(f"  Skipping info table {filename} as it's not an XML file as expected by current parser.")

        elif "_primary.xml" in filename.lower() or "_primary.txt" in filename.lower():
            # Primary documents are processed indirectly when their corresponding infotable is processed.
            # So, we can just note their presence or skip direct processing here.
            print(f"  Skipping direct processing of primary document: {filename} (handled via its infotable)")
            pass
        elif filename.lower().endswith('.txt'): # General .txt files not yet handled
            print(f"  Text file parsing not yet implemented for {filename}.")
        else:
            print(f"  Skipping unsupported file type or already processed: {filename}")

    if all_holdings_data:
        df = pd.DataFrame(all_holdings_data, columns=CSV_COLUMNS)
        output_csv_path = os.path.join(PROCESSED_DIR, "consolidated_13f_holdings.csv")
        df.to_csv(output_csv_path, index=False)
        print(f"Successfully processed {len(df)} holdings into {output_csv_path}")
    else:
        print("No holdings data was processed.")

if __name__ == "__main__":
    process_filings()
