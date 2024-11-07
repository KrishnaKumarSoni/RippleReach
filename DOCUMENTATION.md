RippleReach Documentation

System Overview

RippleReach is an AI-powered B2B sales outreach system that automates cold emailing and follow-up conversations. It uses OpenAI GPT-4 for intelligent communication and integrates with Google Sheets for lead management.

Core Components

1. Lead Processing

The system processes leads through app.py (lines 21-44). It determines which leads need attention based on their status:
- New leads needing cold emails
- Leads that have replied and need responses
- Failed emails that need retry

2. Email Generation Pipeline

Located in openai_integration.py, the system uses a sophisticated two-step process:

a) Cold Email Generation (lines 559-605):
- Analyzes company background
- Generates personalized content
- Follows strict formatting guidelines
- Includes relevant portfolio items

b) Response Generation (lines 88-169):
- Analyzes conversation history
- Determines conversation stage
- Generates contextual responses
- Handles proposals when needed

3. Agency Information Management

Managed through google_sheets.py (lines 252-327):
- Pulls agency data from Google Sheets
- Structures information using OpenAI
- Maintains consistent agency profile

Setup Requirements

1. Environment Variables:
```
OPENAI_API_KEY=your_key
GOOGLE_SHEETS_ID=your_sheet_id
GOOGLE_CREDENTIALS_FILE=path_to_credentials.json
RESEND_API_KEY=your_key
SENDER_EMAIL=your@email.com
```

2. Google Sheets Structure:

Required Worksheets:
- Agency Info: Company details and configuration
- Leads: Prospect information and conversation tracking

Lead Sheet Columns:
- Name
- Email
- Company Name
- Company Domain
- Role
- Email Status
- Conversation History

Installation Steps

1. Clone the repository
2. Create virtual environment: python -m venv venv
3. Activate virtual environment: source venv/bin/activate
4. Install dependencies: pip install -r requirements.txt
5. Configure environment variables
6. Set up Google Sheets structure
7. Add portfolio assets

API Endpoints

1. POST /send_emails
- Processes all leads
- Sends appropriate emails
- Updates conversation history

2. POST /monitor_emails
- Checks for new replies
- Updates lead status
- Triggers response generation
