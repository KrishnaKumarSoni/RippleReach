import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound
import logging
from config import Config
from typing import Dict, Any, Optional, List
from constants import SheetColumns
from http.client import RemoteDisconnected  # Add this
import time  # Add this
import json  # For better logging
import openai  # Add this
import re

# Remove duplicate logging config
logging.basicConfig(level=logging.INFO)

# Google Sheets API setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SERVICE_ACCOUNT_FILE = 'service_account.json'
SPREADSHEET_ID = Config.SPREADSHEET_ID  # Add this to your Config

def get_worksheet_data(worksheet_name: str, max_retries: int = 3) -> List[Dict]:
    """
    Fetches data from specified worksheet and returns as list of dictionaries
    """
    retry_count = 0
    while retry_count < max_retries:
        try:
            # Get the worksheet
            sheet = connect_to_sheet().worksheet(worksheet_name)
            
            # Get all values including headers
            all_values = sheet.get_all_values()
            if not all_values:
                logging.error(f"No data found in worksheet: {worksheet_name}")
                return []
                
            headers = all_values[0]
            
            # Convert rows to dictionaries
            data = []
            for row in all_values[1:]:  # Skip header row
                # Pad row with empty strings if shorter than headers
                row_data = row + [''] * (len(headers) - len(row))
                data.append(dict(zip(headers, row_data)))
                
            logging.info(f"Successfully fetched {len(data)} rows from {worksheet_name}")
            return data
            
        except (ConnectionError, RemoteDisconnected) as e:
            retry_count += 1
            wait_time = 2 ** retry_count  # Exponential backoff
            logging.warning(f"Connection attempt {retry_count} failed: {str(e)}. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            
        except Exception as e:
            logging.error(f"Error fetching worksheet data: {str(e)}")
            raise
            
    raise ConnectionError(f"Failed to connect after {max_retries} attempts")

class SheetValidator:
    @staticmethod
    def validate_columns(sheet_headers: List[str]) -> tuple[bool, Optional[str]]:
        required_columns = set(SheetColumns.required_columns())
        sheet_columns = set(sheet_headers)
        missing_required = required_columns - sheet_columns
        
        if missing_required:
            return False, f"Missing required columns: {', '.join(missing_required)}"
        
        missing_optional = set(SheetColumns.optional_columns()) - sheet_columns
        if missing_optional:
            logging.warning(f"Missing optional columns: {', '.join(missing_optional)}")
        
        return True, None

    @staticmethod
    def validate_column_update(column: str, headers: List[str]) -> Optional[str]:
        if column not in headers:
            # If it's an optional column that doesn't exist, create it
            if column in SheetColumns.optional_columns():
                logging.info(f"Creating missing optional column: {column}")
                return None
            return f"Cannot update non-existent column: {column}"
        return None

class GoogleSheetManager:
    def __init__(self):
        self.spreadsheet = connect_to_sheet()
        try:
            self.sheet = self.spreadsheet.worksheet("Leads")
        except WorksheetNotFound:
            logging.error("'Leads' worksheet not found")
            logging.info("Available worksheets:", self.spreadsheet.worksheets())
            raise
        
        self.headers = self.sheet.row_values(1)
        if not self.headers:
            raise ValueError("Sheet headers not found")
        
        self._validate_sheet_structure()
        self._ensure_optional_columns()

    def _validate_sheet_structure(self):
        is_valid, error_message = SheetValidator.validate_columns(self.headers)
        if not is_valid:
            raise ValueError(f"Invalid sheet structure: {error_message}")

    def _ensure_optional_columns(self):
        """Create any missing optional columns"""
        missing_columns = set(SheetColumns.optional_columns()) - set(self.headers)
        if missing_columns:
            last_col = len(self.headers) + 1
            for col in missing_columns:
                self.sheet.update_cell(1, last_col, col)
                self.headers.append(col)
                last_col += 1
            logging.info(f"Created missing optional columns: {missing_columns}")

    def update_cells(self, row: int, updates: Dict[str, Any]):
        for column, value in updates.items():
            error = SheetValidator.validate_column_update(column, self.headers)
            if error:
                logging.warning(error)
                continue
            
            # If column doesn't exist, add it
            if column not in self.headers:
                self._ensure_optional_columns()
            
            col_index = self.headers.index(column) + 1
            self.sheet.update_cell(row, col_index, value)
            logging.info(f"Updated {column} for row {row}")

def connect_to_sheet():
    """Connect to Google Sheets with better error handling"""
    try:
        # Use broader scope for full access
        scopes = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            'service_account.json', 
            scopes
        )
        
        client = gspread.authorize(creds)
        
        try:
            spreadsheet = client.open_by_key(Config.SPREADSHEET_ID)
            logging.info(f"Successfully connected to spreadsheet: {spreadsheet.title}")
            return spreadsheet
        except SpreadsheetNotFound:
            logging.error(f"Spreadsheet not found with ID: {Config.SPREADSHEET_ID}")
            logging.info("Please check:")
            logging.info("1. Spreadsheet ID is correct")
            logging.info("2. Service account email has been shared with the spreadsheet")
            raise
            
    except FileNotFoundError:
        logging.error("service_account.json not found in current directory")
        logging.info("Please ensure service_account.json is in the project root")
        raise
    except Exception as e:
        logging.error(f"Error connecting to Google Sheets: {str(e)}")
        raise

def get_lead_data(start_row: int, end_row: int = 0) -> List[Dict[str, Any]]:
    """Fetch lead data from Google Sheet"""
    try:
        logging.info("Successfully connected to spreadsheet: Sales Tracker KX02")
        sheet = connect_to_sheet().worksheet("Leads")
        
        # Get all values including headers
        all_values = sheet.get_all_values()
        if not all_values:
            return []
            
        headers = all_values[0]
        
        # Debug the actual headers
        logging.info(f"Actual sheet headers: {headers}")
        
        # Calculate end row
        if end_row == 0:
            end_row = len(all_values)
        
        # Convert row data to dictionaries
        leads = []
        for row_idx in range(start_row - 1, min(end_row, len(all_values))):
            row = all_values[row_idx]
            lead = {}
            
            # Print the raw row data
            logging.info(f"Raw row data: {row}")
            
            for col_idx, header in enumerate(headers):
                value = row[col_idx] if col_idx < len(row) else ""
                lead[header] = value if value != "" else None
                
            logging.info(f"Processed lead data: {lead}")
            leads.append(lead)
            
        return leads
        
    except Exception as e:
        logging.error(f"Error fetching lead data: {str(e)}")
        raise

def get_agency_worksheet():
    """Returns the agency info worksheet"""
    try:
        return connect_to_sheet().worksheet("Agency Info")
    except Exception as e:
        logging.error(f"Error accessing agency worksheet: {str(e)}")
        return None

def get_agency_worksheet_data() -> Dict:
    """Fetches and structures all agency data from the worksheet"""
    try:
        worksheet = get_agency_worksheet()
        if not worksheet:
            raise ValueError("Could not access agency worksheet")
            
        # Get all values from the worksheet
        all_rows = worksheet.get_all_values()
        
        # Initialize data structures
        agency_data = {
            'services': [],
            'company_structure': [],
            'portfolio_projects': [],
            'single_values': {}
        }
        
        # Process each row
        for row in all_rows:
            if len(row) < 2:  # Skip empty rows
                continue
                
            category, description = row[0].strip(), row[1].strip()
            
            # Skip empty entries
            if not category or not description:
                continue
                
            # Group data by category
            if category == 'Services':
                agency_data['services'].append(description)
            elif category == 'Company Structure':
                agency_data['company_structure'].append(description)
            elif category == 'Portfolio Projects':
                # Parse portfolio project entries
                if ' - ' in description:
                    name, details = description.split(' - ', 1)
                    agency_data['portfolio_projects'].append({
                        'name': name.strip(),
                        'details': details.strip()
                    })
            else:
                # Store other single values
                agency_data['single_values'][category] = description
        
        # Format the final structure
        formatted_data = {
            'name': agency_data['single_values'].get('Agency Name', ''),
            'description': agency_data['single_values'].get('Agency Info', ''),
            'website': agency_data['single_values'].get('Agency Website', ''),
            'calendar_link': agency_data['single_values'].get('Calendar Link', ''),
            'services': agency_data['services'],
            'company_structure': agency_data['company_structure'],
            'portfolio_projects': agency_data['portfolio_projects'],
            'sender': {
                'name': agency_data['single_values'].get('Sender Name', ''),
                'position': agency_data['single_values'].get('Sender Position', ''),
                'meta': agency_data['single_values'].get('Sender Meta Data', ''),
                'email': f"krishna@kuberanix.agency"  # Hardcoded as per sheet
            },
            'labs': agency_data['company_structure'],
            'pricing_info': agency_data['single_values'].get('Pricing', '')
        }
        
        logging.info(f"Raw agency data dump: {json.dumps(formatted_data, indent=2)}")
        return formatted_data
        
    except Exception as e:
        logging.error(f"Error fetching agency worksheet data: {str(e)}")
        raise

def get_agency_info() -> Dict:
    """Returns agency information using OpenAI to process and structure the data"""
    try:
        # Get raw data from worksheet
        agency_data = get_agency_worksheet_data()
        
        # Format data for OpenAI processing
        data_dump = json.dumps(agency_data, indent=2)
        # Log the raw data from worksheet
        logging.info(f"Raw agency data dump: {data_dump}")
        
        processing_prompt = f"""
        Process this agency information dump and create a well-structured agency profile.
        Raw data from worksheet:
        {data_dump}

        Use all this data and then accurately and precisely Create a complete agency profile JSON with the following structure:
        {{
            "name": "Agency name",
            "description": "Comprehensive agency description",
            "website": "Agency website",
            "calendar_link": "calendar link provided in raw data from worksheet",
            "services": ["List of services"],
            "company_structure": ["Company structure details"],
            "portfolio_projects": [
                {{"url": "project url", "details": "project details"}}
            ],
            "sender": {{
                "name": "Full name",
                "position": "Job title",
                "meta": "Professional background and role description",
                "email": "Contact email"
            }},
            "labs": ["Research/development labs"],
            "pricing_info": "Pricing structure"
        }}
        Ensure you use original data from the raw data from worksheet and not the sample data / descriptions mentioned in the json above.
        Requirements:
        1. Ensure only the fields mentioned above are included
        2. Ensure all fields are properly populated
        3. Format portfolio projects consistently
        4. Structure services clearly
        5. Create comprehensive sender meta description
        6. Return valid JSON only
         IMPORTANT: Return ONLY the JSON object, no other text.

        """

        response = openai.chat.completions.create(
            model="gpt-4o",  # Fixed typo in model name from gpt-4o to gpt-4
            messages=[{"role": "user", "content": processing_prompt}],
            temperature=0.3
        )

        # Get the response content and clean it
        response_content = response.choices[0].message.content.strip()
        
        try:
            # Log the raw response for debugging
            logging.info(f"Raw OpenAI response: {response_content}")
            # Strip quotes if response is wrapped in them
            # Clean response content to extract just the JSON
            response_content = re.sub(r'^[^{]*({.*})[^}]*$', r'\1', response_content)
            # Remove any escaped quotes around the JSON
            response_content = re.sub(r'^"({.*})"$', r'\1', response_content)
            # Remove any remaining non-JSON text
            response_content = re.sub(r'^[^{]*({[\s\S]*})[^}]*$', r'\1', response_content)
            # Log the processed response content
            logging.info(f"Processed response content: {response_content}")
            agency_info = json.loads(response_content)
            logging.info("Successfully processed agency information")
            return agency_info
            
        except json.JSONDecodeError:
            logging.error("Failed to parse OpenAI response")
            raise
    except Exception as e:
        logging.error(f"Error in get_agency_info: {str(e)}")
        # Return fallback values
        return {
            'name': 'Kuberanix',
            'description': 'Product Design & Development Studio',
            'website': 'https://kuberanix.com',
            'calendar_link': 'https://calendly.com/kuberanix',
            'sender': {
                'name': 'Krishna Kumar Soni',
                'position': 'Founder',
                'meta': 'Founder of Kuberanix, Product Design & Development Studio',
                'email': 'krishna@kuberanix.agency'
            }
        }

def update_sheet(row_index: int, updates: Dict[str, Any]) -> None:
    """Update specific cells in the sheet for a given row"""
    try:
        logging.info(f"Updating row {row_index} with: {updates}")
        
        # Get the worksheet
        sheet = connect_to_sheet().worksheet("Leads")
        
        # Convert column names to indices
        header_row = sheet.row_values(1)
        updates_with_indices = {}
        
        for col_name, value in updates.items():
            try:
                col_index = header_row.index(col_name) + 1  # 1-based indexing
                updates_with_indices[col_index] = value
                logging.info(f"Mapped column {col_name} to index {col_index}")
            except ValueError:
                logging.error(f"Column {col_name} not found in sheet headers: {header_row}")
        
        # Update each cell
        for col_index, value in updates_with_indices.items():
            try:
                sheet.update_cell(row_index, col_index, value)
                logging.info(f"Updated cell ({row_index}, {col_index}) with value: {value}")
            except Exception as e:
                logging.error(f"Failed to update cell ({row_index}, {col_index}): {str(e)}")
                raise
                
    except Exception as e:
        logging.error(f"Error in update_sheet: {str(e)}")
        raise
