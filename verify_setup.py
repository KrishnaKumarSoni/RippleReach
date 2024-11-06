import logging
from google_sheets import connect_to_sheet
from config import Config

logging.basicConfig(level=logging.INFO)

def verify_setup():
    """Verify Google Sheets setup and permissions"""
    try:
        # 1. Check environment variables
        logging.info("Checking environment variables...")
        if not Config.SPREADSHEET_ID:
            raise ValueError("SPREADSHEET_ID not set in .env")
            
        # 2. Check service account file
        logging.info("Checking service account file...")
        try:
            with open('service_account.json', 'r') as f:
                logging.info("service_account.json found")
        except FileNotFoundError:
            raise FileNotFoundError("service_account.json not found in current directory")
            
        # 3. Test Google Sheets connection
        logging.info("Testing Google Sheets connection...")
        spreadsheet = connect_to_sheet()
        logging.info(f"Successfully connected to: {spreadsheet.title}")
        
        # 4. Check worksheet
        logging.info("Checking 'Leads' worksheet...")
        worksheet = spreadsheet.worksheet("Leads")
        headers = worksheet.row_values(1)
        logging.info(f"Found headers: {headers}")
        
        logging.info("✅ Setup verification complete!")
        return True
        
    except Exception as e:
        logging.error(f"❌ Setup verification failed: {str(e)}")
        return False

if __name__ == "__main__":
    verify_setup() 