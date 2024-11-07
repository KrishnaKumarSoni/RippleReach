def write_documentation():
    with open('DOCUMENTATION.md', 'w') as f:
        f.write('RippleReach Documentation\n\n')
        
        # System Overview
        f.write('System Overview\n\n')
        f.write('RippleReach is an AI-powered B2B sales outreach system that automates cold emailing and follow-up conversations. It uses OpenAI GPT-4 for intelligent communication and integrates with Google Sheets for lead management.\n\n')
        
        # Core Components
        f.write('Core Components\n\n')
        
        # 1. Lead Processing
        f.write('1. Lead Processing\n\n')
        f.write('The system processes leads through app.py (lines 21-44). It determines which leads need attention based on their status:\n')
        f.write('- New leads needing cold emails\n')
        f.write('- Leads that have replied and need responses\n')
        f.write('- Failed emails that need retry\n\n')
        
        # 2. Email Generation
        f.write('2. Email Generation Pipeline\n\n')
        f.write('Located in openai_integration.py, the system uses a sophisticated two-step process:\n\n')
        f.write('a) Cold Email Generation (lines 559-605):\n')
        f.write('- Analyzes company background\n')
        f.write('- Generates personalized content\n')
        f.write('- Follows strict formatting guidelines\n')
        f.write('- Includes relevant portfolio items\n\n')
        
        f.write('b) Response Generation (lines 88-169):\n')
        f.write('- Analyzes conversation history\n')
        f.write('- Determines conversation stage\n')
        f.write('- Generates contextual responses\n')
        f.write('- Handles proposals when needed\n\n')
        
        # 3. Agency Information
        f.write('3. Agency Information Management\n\n')
        f.write('Managed through google_sheets.py (lines 252-327):\n')
        f.write('- Pulls agency data from Google Sheets\n')
        f.write('- Structures information using OpenAI\n')
        f.write('- Maintains consistent agency profile\n\n')
        
        # Setup Requirements
        f.write('Setup Requirements\n\n')
        f.write('1. Environment Variables:\n')
        f.write('```\n')
        f.write('OPENAI_API_KEY=your_key\n')
        f.write('GOOGLE_SHEETS_ID=your_sheet_id\n')
        f.write('GOOGLE_CREDENTIALS_FILE=path_to_credentials.json\n')
        f.write('RESEND_API_KEY=your_key\n')
        f.write('SENDER_EMAIL=your@email.com\n')
        f.write('```\n\n')
        
        # Google Sheets Structure
        f.write('2. Google Sheets Structure:\n\n')
        f.write('Required Worksheets:\n')
        f.write('- Agency Info: Company details and configuration\n')
        f.write('- Leads: Prospect information and conversation tracking\n\n')
        
        f.write('Lead Sheet Columns:\n')
        f.write('- Name\n')
        f.write('- Email\n')
        f.write('- Company Name\n')
        f.write('- Company Domain\n')
        f.write('- Role\n')
        f.write('- Email Status\n')
        f.write('- Conversation History\n\n')
        
        # Installation
        f.write('Installation Steps\n\n')
        f.write('1. Clone the repository\n')
        f.write('2. Create virtual environment: python -m venv venv\n')
        f.write('3. Activate virtual environment: source venv/bin/activate\n')
        f.write('4. Install dependencies: pip install -r requirements.txt\n')
        f.write('5. Configure environment variables\n')
        f.write('6. Set up Google Sheets structure\n')
        f.write('7. Add portfolio assets\n\n')
        
        # API Endpoints
        f.write('API Endpoints\n\n')
        f.write('1. POST /send_emails\n')
        f.write('- Processes all leads\n')
        f.write('- Sends appropriate emails\n')
        f.write('- Updates conversation history\n\n')
        
        f.write('2. POST /monitor_emails\n')
        f.write('- Checks for new replies\n')
        f.write('- Updates lead status\n')
        f.write('- Triggers response generation\n')

if __name__ == '__main__':
    write_documentation()
