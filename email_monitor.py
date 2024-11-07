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
            mail.login(config['email'], config['password'])
            mail.select('INBOX')

            # Get all leads first to check which email threads to look for
            leads = get_lead_data(Config.STARTING_ROW)
            lead_emails = {lead.get(SheetColumns.EMAIL.value, '').lower(): lead for lead in leads}
            
            logging.info(f"Checking threads for {len(lead_emails)} leads")

            # Search for all messages first
            _, messages = mail.search(None, 'ALL')
            
            if not messages[0]:
                logging.info("No messages found in inbox")
                return False

            # Process messages in reverse order (newest first)
            message_nums = messages[0].split()
            message_nums.reverse()

            processed_threads = set()  # Track processed email threads to avoid duplicates

            for num in message_nums:
                try:
                    _, msg_data = mail.fetch(num, '(RFC822)')
                    email_message = email.message_from_bytes(msg_data[0][1])
                    
                    # Get participants from From, To, Cc fields
                    participants = self._get_thread_participants(email_message)
                    thread_id = email_message.get('Message-ID', '') or email_message.get('Thread-Index', '')
                    
                    # Check if any participant is in our leads
                    matching_leads = [email for email in participants if email.lower() in lead_emails]
                    
                    if matching_leads and thread_id not in processed_threads:
                        lead_email = matching_leads[0]
                        processed_threads.add(thread_id)
                        
                        # Get the full thread
                        thread_messages = self._get_thread_messages(mail, email_message)
                        latest_message = thread_messages[-1]  # Most recent message
                        
                        # Check if latest message is from lead
                        latest_sender = self._parse_email_address(latest_message['From'])
                        if latest_sender.lower() == lead_email.lower():
                            logging.info(f"Found latest reply from lead: {lead_email}")
                            body = self._get_email_body(latest_message)
                            self._update_lead_in_sheet(lead_email, body)

                except Exception as e:
                    logging.error(f"Error processing message: {e}")
                    continue

            mail.close()
            mail.logout()
            return True

        except Exception as e:
            logging.error(f"Error checking inbox: {str(e)}")
            return False

    def _get_thread_participants(self, email_message):
        """Extract all email addresses from message headers"""
        participants = set()
        
        # Check From, To, and Cc fields
        for header in ['From', 'To', 'Cc']:
            addresses = email_message.get(header, '')
            if addresses:
                # Simple email extraction - could be made more robust
                emails = [self._parse_email_address(addr) for addr in addresses.split(',')]
                participants.update(emails)
        
        return participants

    def _get_thread_messages(self, mail, reference_message):
        """Get all messages in the same thread"""
        thread_messages = []
        references = reference_message.get('References', '') or reference_message.get('In-Reply-To', '')
        message_id = reference_message.get('Message-ID', '')
        
        # Search for messages in the same thread
        search_criteria = f'(OR HEADER References "{references}" HEADER Message-ID "{message_id}")'
        _, messages = mail.search(None, search_criteria)
        
        for num in messages[0].split():
            _, msg_data = mail.fetch(num, '(RFC822)')
            thread_messages.append(email.message_from_bytes(msg_data[0][1]))
        
        # Sort by date
        thread_messages.sort(key=lambda m: email.utils.parsedate_to_datetime(m['Date']))
        return thread_messages

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

    def _convert_html_to_text(self, html_content: str) -> str:
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

    def _update_lead_in_sheet(self, from_email: str, reply_body: str):
        """Update sheet with new message, handling HTML conversion"""
        leads = get_lead_data(Config.STARTING_ROW)
        logging.info(f"Searching for email match: {from_email}")
        
        for index, lead in enumerate(leads, start=Config.STARTING_ROW):
            lead_email = lead.get(SheetColumns.EMAIL.value, '')
            logging.info(f"Comparing with lead email: {lead_email}")
            
            if lead_email.lower() == from_email.lower():
                logging.info(f"Found matching email at row {index}")
                current_status = lead.get(SheetColumns.EMAIL_STATUS.value, '')
                new_status = EmailStatus.REPLIED.value if current_status == EmailStatus.SENT.value else current_status
                
                # Convert any HTML content in the reply to plain text
                clean_reply = self._convert_html_to_text(reply_body)
                logging.info(f"Cleaned reply: {clean_reply[:100]}...")  # Log first 100 chars
                
                # Get existing conversation history and clean it
                existing_history = lead.get(SheetColumns.CONVERSATION_HISTORY.value, '')
                if existing_history:
                    existing_history = self._convert_html_to_text(existing_history)
                
                # Format new conversation entry
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_entry = f"\n\nClient Reply ({timestamp}):\n{clean_reply}"
                
                # Combine histories
                updated_history = f"{existing_history}{new_entry}" if existing_history else new_entry
                
                # Create update payload
                update_payload = {
                    SheetColumns.LAST_MESSAGE.value: clean_reply,
                    SheetColumns.LAST_SENDER.value: SenderType.CLIENT.value,
                    SheetColumns.EMAIL_STATUS.value: new_status,
                    SheetColumns.CONVERSATION_HISTORY.value: updated_history
                }
                
                logging.info(f"Updating sheet row {index} with payload: {update_payload}")
                
                try:
                    update_sheet(index, update_payload)
                    logging.info(f"Successfully updated sheet for {from_email}")
                except Exception as e:
                    logging.error(f"Failed to update sheet: {str(e)}")
                    raise
                
                return
                
        logging.warning(f"No matching lead found for email: {from_email}")

def monitor_emails():
    monitor = EmailMonitor()
    while True:
        try:
            monitor.check_replies()
            time.sleep(600)  # Check every 10 minutes since we're checking all messages
        except Exception as e:
            logging.error(f"Error in email monitoring: {e}")
            logging.exception("Full traceback:")
            time.sleep(60)  # Wait a minute before retrying if there's an error
            logging.error(f"Error in email monitoring: {e}")
            time.sleep(60)  # Wait a minute before retrying if there's an error 
            monitor.check_replies()
            time.sleep(600)  # Check every 10 minutes since we're checking all messages
        except Exception as e:
            logging.error(f"Error in email monitoring: {e}")
            logging.exception("Full traceback:")
            time.sleep(60)  # Wait a minute before retrying if there's an error
            logging.error(f"Error in email monitoring: {e}")
            time.sleep(60)  # Wait a minute before retrying if there's an error 
            time.sleep(60)  # Wait a minute before retrying if there's an error 
            logging.error(f"Error in email monitoring: {e}")
            time.sleep(60)  # Wait a minute before retrying if there's an error 
    while True:
        try:
            monitor.check_replies()
            time.sleep(600)  # Check every 10 minutes since we're checking all messages
        except Exception as e:
            logging.error(f"Error in email monitoring: {e}")
            logging.exception("Full traceback:")
            time.sleep(60)  # Wait a minute before retrying if there's an error
            logging.error(f"Error in email monitoring: {e}")
            time.sleep(60)  # Wait a minute before retrying if there's an error 
            time.sleep(600)  # Check every 10 minutes since we're checking all messages
        except Exception as e:
            logging.error(f"Error in email monitoring: {e}")
            logging.exception("Full traceback:")
            time.sleep(60)  # Wait a minute before retrying if there's an error
            logging.error(f"Error in email monitoring: {e}")
            time.sleep(60)  # Wait a minute before retrying if there's an error 
            time.sleep(60)  # Wait a minute before retrying if there's an error
            logging.error(f"Error in email monitoring: {e}")
            time.sleep(60)  # Wait a minute before retrying if there's an error 
            time.sleep(60)  # Wait a minute before retrying if there's an error
            logging.error(f"Error in email monitoring: {e}")
            time.sleep(60)  # Wait a minute before retrying if there's an error 