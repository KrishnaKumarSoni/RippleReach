import logging
from config import Config
from typing import List, Dict, Optional
import requests
import json
from portfolio_assets import PortfolioAssets
from datetime import datetime

# Enhanced logging format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class EmailDeliveryError(Exception):
    """Custom exception for email delivery failures"""
    pass

class EmailSender:
    _current_index = 0
    
    @classmethod
    def validate_sender_config(cls, config: Dict) -> bool:
        """Validates sender configuration"""
        required_fields = ['email', 'api_key', 'display_name']
        return all(field in config and config[field] for field in required_fields)

    @classmethod
    def get_next_sender_config(cls) -> Dict:
        """Returns the next sender config in round-robin fashion with validation"""
        if not Config.SENDER_CONFIGS:
            raise ValueError("No sender configurations available")
            
        config = Config.SENDER_CONFIGS[cls._current_index]
        
        # Validate config
        if not cls.validate_sender_config(config):
            logging.error(f"Invalid sender config at index {cls._current_index}")
            raise ValueError(f"Invalid sender configuration: {json.dumps(config, default=str)}")
            
        logging.info(f"Selected sender config index: {cls._current_index}")
        logging.info(f"Using email: {config['email']} | Display Name: {config['display_name']}")
        
        # Increment for next time
        cls._current_index = (cls._current_index + 1) % len(Config.SENDER_CONFIGS)
        return config

def validate_email_content(to_email: str, subject: str, html_content: str) -> None:
    """Validates email content before sending"""
    if not to_email or '@' not in to_email:
        raise ValueError(f"Invalid recipient email: {to_email}")
        
    if not subject or len(subject.strip()) < 2:
        raise ValueError(f"Invalid subject line: {subject}")
        
    if not html_content or len(html_content.strip()) < 10:
        raise ValueError(f"Invalid email content length: {len(html_content) if html_content else 0} chars")

def send_round_robin_email(to_email: str, subject: str, html_content: str, attachments: List[Dict] = None) -> Dict:
    """Send email using round-robin sender configuration with enhanced validation and logging"""
    start_time = datetime.now()
    request_id = f"email_{start_time.strftime('%Y%m%d_%H%M%S')}"
    
    try:
        logging.info(f"[{request_id}] Starting email send process")
        
        # Validate email content
        validate_email_content(to_email, subject, html_content)
        
        # Get next sender configuration
        sender_config = EmailSender.get_next_sender_config()
        
        # Clean subject line
        clean_subject = subject.strip().strip('"\'').strip()
        
        # Prepare email data
        from_email = f"{sender_config['display_name']} <{sender_config['email']}>"
        
        email_data = {
            "from": from_email,
            "to": to_email,
            "subject": clean_subject,
            "html": html_content,
            "attachments": attachments or []
        }
        
        # Detailed logging
        logging.info(f"[{request_id}] Email Configuration:")
        logging.info(f"[{request_id}] - From: {from_email}")
        logging.info(f"[{request_id}] - To: {to_email}")
        logging.info(f"[{request_id}] - Subject: {clean_subject}")
        logging.info(f"[{request_id}] - Content Length: {len(html_content)} chars")
        logging.info(f"[{request_id}] - Attachments: {len(attachments or [])} files")
        
        # Make API request with timeout
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {sender_config['api_key']}",
                "Content-Type": "application/json"
            },
            json=email_data,
            timeout=10  # 10 seconds timeout
        )
        
        # Parse response
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            response_data = {"raw_response": response.text}
        
        logging.info(f"[{request_id}] Resend API Response: {json.dumps(response_data, indent=2)}")
        
        if not response.ok:
            error_msg = f"Email sending failed: Status {response.status_code} - {response.text}"
            logging.error(f"[{request_id}] {error_msg}")
            raise EmailDeliveryError(error_msg)
            
        # Verify successful response format
        if 'id' not in response_data:
            raise EmailDeliveryError("Missing email ID in successful response")
            
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        success_response = {
            "status": "success",
            "request_id": request_id,
            "email_id": response_data.get('id'),
            "details": {
                "from": from_email,
                "to": to_email,
                "subject": clean_subject,
                "sent_at": end_time.isoformat(),
                "duration_seconds": duration
            }
        }
        
        logging.info(f"[{request_id}] Email sent successfully in {duration:.2f} seconds")
        return success_response
        
    except Exception as e:
        error_response = {
            "status": "failed",
            "request_id": request_id,
            "error": str(e),
            "error_type": type(e).__name__,
            "details": {
                "from": from_email if 'from_email' in locals() else "unknown",
                "to": to_email,
                "subject": clean_subject if 'clean_subject' in locals() else subject,
                "failed_at": datetime.now().isoformat()
            }
        }
        
        logging.error(f"[{request_id}] Error in send_round_robin_email: {str(e)}", exc_info=True)
        return error_response
