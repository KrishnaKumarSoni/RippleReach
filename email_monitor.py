import imaplib
import email
from email.header import decode_header
import logging
from config import Config
from google_sheets import update_sheet, get_lead_data
import time
from datetime import datetime
from constants import SheetColumns, EmailStatus, SenderType
from bs4 import BeautifulSoup
import html2text

logging.basicConfig(level=logging.INFO)

class EmailMonitor:
    def __init__(self):
        self.email_configs = [
            {
                "email": config["email"],
                "password": config["password"],
                "imap_server": "mail.privateemail.com",
                "imap_port": 993
            }
            for config in Config.SENDER_CONFIGS
        ]

    def check_replies(self):
        for config in self.email_configs:
            try:
                self._check_single_inbox(config)
            except Exception as e:
                logging.error(f"Error checking {config['email']}: {e}")

    def _check_single_inbox(self, config):
        try:
            logging.info(f"Connecting to {config['email']}...")
            mail = imaplib.IMAP4_SSL(config['imap_server'], config['imap_port'])
            logging.info(f"Attempting login for {config['email']}...")
            mail.login(config['email'], config['password'])
            mail.select('INBOX')

            # Search for unread messages
            _, messages = mail.search(None, 'UNSEEN')
            
            if messages[0]:
                logging.info(f"Found {len(messages[0].split())} unread messages for {config['email']}")
            
            for num in messages[0].split():
                try:
                    _, msg_data = mail.fetch(num, '(RFC822)')
                    email_body = msg_data[0][1]
                    email_message = email.message_from_bytes(email_body)

                    # Get sender's email
                    from_email = self._parse_email_address(email_message['From'])
                    subject = self._decode_header(email_message['Subject'])
                    body = self._get_email_body(email_message)

                    logging.info(f"Processing message from {from_email} with subject: {subject}")

                    # Find the lead in Google Sheet
                    self._update_lead_in_sheet(from_email, body)

                except Exception as e:
                    logging.error(f"Error processing message: {e}")

            mail.close()
            mail.logout()
            logging.info(f"Successfully checked {config['email']}")

        except Exception as e:
            logging.error(f"Error checking {config['email']}: {str(e)}")

    def _parse_email_address(self, from_header):
        # Extract email from "Name <email@domain.com>" format
        if '<' in from_header:
            return from_header.split('<')[1].split('>')[0]
        return from_header

    def _decode_header(self, header):
        if header is None:
            return ""
        decoded_header, encoding = decode_header(header)[0]
        if isinstance(decoded_header, bytes):
            return decoded_header.decode(encoding or 'utf-8')
        return decoded_header

    def _get_email_body(self, email_message):
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    return part.get_payload(decode=True).decode()
        else:
            return email_message.get_payload(decode=True).decode()
        return ""

    def _update_lead_in_sheet(self, from_email: str, reply_body: str):
        """Update sheet with new message, handling HTML conversion"""
        leads = get_lead_data(Config.STARTING_ROW)
        for index, lead in enumerate(leads, start=Config.STARTING_ROW):
            if lead.get(SheetColumns.EMAIL).lower() == from_email.lower():
                current_status = lead.get(SheetColumns.EMAIL_STATUS, "")
                new_status = EmailStatus.REPLIED if current_status == EmailStatus.SENT else current_status
                
                # Convert any HTML content in the reply to plain text
                clean_reply = self._convert_html_to_text(reply_body)
                
                # Get existing conversation history and clean it
                existing_history = lead.get(SheetColumns.CONVERSATION_HISTORY, '')
                if existing_history:
                    existing_history = self._convert_html_to_text(existing_history)
                
                # Format new conversation entry
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_entry = f"\n\nClient Reply ({timestamp}):\n{clean_reply}"
                
                # Combine histories
                updated_history = f"{existing_history}{new_entry}" if existing_history else new_entry
                
                update_sheet(index, {
                    SheetColumns.LAST_MESSAGE: clean_reply,
                    SheetColumns.LAST_SENDER: SenderType.CLIENT,
                    SheetColumns.EMAIL_STATUS: new_status,
                    SheetColumns.CONVERSATION_HISTORY: updated_history
                })
                
                logging.info(f"Updated sheet with reply from {from_email}")
                break

def _convert_html_to_text(html_content: str) -> str:
    """Convert HTML content to plain text while preserving structure"""
    try:
        # First try to parse with BeautifulSoup to clean the HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Initialize html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.body_width = 0  # Don't wrap text
        h.protect_links = True  # Keep the full URLs
        
        # Convert to markdown-style text
        text = h.handle(str(soup))
        
        # Clean up extra whitespace while preserving structure
        lines = [line.strip() for line in text.splitlines()]
        text = '\n'.join(line for line in lines if line)
        
        return text
    except Exception as e:
        logging.error(f"Error converting HTML to text: {e}")
        return html_content  # Return original content if conversion fails

def monitor_emails():
    monitor = EmailMonitor()
    while True:
        try:
            monitor.check_replies()
            time.sleep(300)  # Check every 5 minutes
        except Exception as e:
            logging.error(f"Error in email monitoring: {e}")
            time.sleep(60)  # Wait a minute before retrying if there's an error 