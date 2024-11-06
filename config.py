from dotenv import load_dotenv
import os
import logging

load_dotenv()

class Config:
    GOOGLE_SHEETS_API_KEY = os.getenv("GOOGLE_SHEETS_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    RESEND_API_KEYS = [
        os.getenv("RESEND_API_KEY_1"),
        os.getenv("RESEND_API_KEY_2"),
        os.getenv("RESEND_API_KEY_3")
    ]
    SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
    if not SPREADSHEET_ID:
        raise ValueError("SPREADSHEET_ID not found in environment variables")
    
    CALENDAR_LINK = os.getenv("CALENDAR_LINK")
    STARTING_ROW = int(os.getenv("STARTING_ROW"))
    ENDING_ROW = int(os.getenv("ENDING_ROW", 0))  # 0 means process till the end
    
    # Sender configurations with consistent domain ordering
    SENDER_CONFIGS = [
        {
            "email": "krishna@kuberanix.agency",  # Domain 1
            "display_name": "Krishna",
            "api_key": RESEND_API_KEYS[0],
            "password": os.getenv("EMAIL_PASSWORD_1")
        },
        {
            "email": "krishna@kuberanix.online",  # Domain 2
            "display_name": "Krishna",
            "api_key": RESEND_API_KEYS[1],
            "password": os.getenv("EMAIL_PASSWORD_2")
        },
        {
            "email": "krishna@kuberanix.site",    # Domain 3
            "display_name": "Krishna",
            "api_key": RESEND_API_KEYS[2],
            "password": os.getenv("EMAIL_PASSWORD_3")
        }
    ]

    # Design Configuration
    DESIGN = {
        'colors': {
            'primary': '#FF5A1F',    # Energetic Orange
            'secondary': '#1A1A1A',  # Rich Black
            'accent': '#FF8C5F',     # Light Orange
            'background': '#FFFFFF',
            'text': '#2D2D2D',
            'success': '#34D399',
            'error': '#EF4444',
        },
        'fonts': {
            'heading': 'Plus Jakarta Sans',
            'body': 'Inter',
        },
        'spacing': {
            'xs': '0.5rem',
            'sm': '1rem',
            'md': '1.5rem',
            'lg': '2rem',
            'xl': '3rem'
        }
    }
    
    # Google Drive Configuration
    DRIVE_ASSETS_FOLDER = os.getenv('DRIVE_ASSETS_FOLDER_ID')
    
    # Agency Information
    AGENCY_INFO = {
        'name': os.getenv("AGENCY_NAME", "Kuberanix"),
        'description': os.getenv("AGENCY_INFO", "We specialize in digital transformation through web development, mobile apps, cloud solutions, and DevOps services."),
        'website': os.getenv("AGENCY_WEBSITE_LINK", "https://kuberanix.com"),
        'calendar_link': os.getenv("CALENDAR_LINK", "https://calendly.com/kuberanix"),
        'services': [
            'Web Development',
            'Mobile Apps',
            'Cloud Solutions',
            'DevOps Services'
        ],
        'sender': {
            'name': "Krishna",
            'position': "Business Development Manager",
            'email': "krishna@kuberanix.agency"
        }
    }

    @classmethod
    def validate_config(cls):
        """Validate configuration during startup"""
        for i, config in enumerate(cls.SENDER_CONFIGS):
            if not all([config['email'], config['api_key'], config['password']]):
                logging.warning(f"Incomplete configuration for sender {i+1}")
            else:
                logging.info(f"Validated config for {config['email']}")
