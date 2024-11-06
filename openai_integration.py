import openai
import logging
from config import Config
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Tuple, List
import markdown
from weasyprint import HTML
from portfolio_assets import PortfolioAssets
from sheet_utils import SheetColumns  # Add this import
import re
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import time


openai.api_key = Config.OPENAI_API_KEY
logging.basicConfig(level=logging.INFO)

@retry(
    retry=retry_if_exception_type(openai.OpenAIError),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    stop=stop_after_attempt(3)
)
def make_openai_call(model: str, messages: List[Dict], temperature: float = 0.7, max_tokens: int = None) -> str:
    """Wrapper for OpenAI API calls with retry logic"""
    try:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
            
        response = openai.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()
        
    except openai.OpenAIError as e:
        if 'insufficient_quota' in str(e):
            logging.error("OpenAI API Quota exceeded. Please check billing.")
            # You might want to send an alert/notification here
        raise

def generate_company_description(company_domain):
    try:
        # Fetch the HTML content of the company's website
        url = f"http://{company_domain}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise an error if the request was unsuccessful
        
        # Parse the HTML content with BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract main text content, focusing on paragraph and heading tags
        text_content = ' '.join([p.get_text() for p in soup.find_all(['p', 'h1', 'h2', 'h3'])])
        
        # Limit the text to the first 1000 characters to focus on relevant content
        text_content = text_content[:1000]
        
        if not text_content.strip():
            logging.warning(f"No relevant text found on {company_domain}")
            return "Company description unavailable."
        
        # Use OpenAI to summarize the scraped content
        prompt = (
            f"Here is some text extracted from the homepage of {company_domain}:\n\n"
            f"{text_content}\n\n"
            "Provide a brief and professional summary of what this company does."
        )
        
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.5
        )
        
        company_description = response.choices[0].message.content.strip()
        logging.info(f"Generated company description for {company_domain}")
        return company_description

    except requests.RequestException as e:
        logging.error(f"Error fetching website content for {company_domain}: {e}")
        return "Company description unavailable."
    except Exception as e:
        logging.error(f"Error generating summary for {company_domain}: {e}")
        return "Company description unavailable."
def determine_and_generate_response(lead_info, previous_conversation, agency_info):
    """Generate a response using two-step process with careful context analysis"""
    logging.info("Starting enhanced response generation process...")
    
    # Step 1: Analyze conversation and determine context
    analysis_prompt = f"""
    You are an expert B2B sales strategist. Analyze this conversation thread:

    CONVERSATION HISTORY:
    {previous_conversation}

    LATEST MESSAGE FROM CLIENT:
    {lead_info.get('last_message', '')}

    ANALYZE AND PROVIDE:
    1. Conversation Stage:
       - Early (Discovery/Education)
       - Mid (Solution Discussion)
       - Late (Evaluation/Negotiation)
    
    2. Client Signals:
       - Explicit needs mentioned
       - Implicit pain points
       - Level of interest
       - Budget sensitivity
       - Timeline indicators
    
    3. Response Strategy:
       - Can this be handled via email? (Yes/No)
       - Is a proposal needed? (Yes/No)
       - Is a call necessary? (Yes/No)
       - Next best action
    
    4. Content Requirements:
       - Which services to highlight
       - Relevant portfolio examples
       - Pricing discussion approach
       - Value propositions to emphasize

    Provide a structured analysis focusing on these elements.
    """

    try:
        analysis = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": analysis_prompt}],
            temperature=0.7
        )
        conversation_analysis = analysis.choices[0].message.content
        logging.info(f"Conversation analysis completed: {conversation_analysis[:200]}...")

        # Step 2: Generate the actual response
        response_prompt = f"""
        You are an experienced B2B solutions consultant. Write a response email following these guidelines:

        CONVERSATION CONTEXT:
        {conversation_analysis}

        TONE & STYLE:
        - Professional and consultative
        - Warm but not overly casual
        - Focused on value and solutions
        - Confident but measured

        AVAILABLE RESOURCES:
        - Services: {', '.join(agency_info.get('services', []))}
        - Portfolio: {[f"{p.get('url')}: {p.get('description')}" for p in agency_info.get('portfolio_projects', [])]}
        - Calendar Link: {Config.CALENDAR_LINK}

        CRITICAL RULES:
        1. NEVER mention pricing strategy
        2. If discussing pricing:
           - Focus on value first
           - Use ranges if necessary
           - Defer details to proposal/call
        3. Keep response under 150 words
        4. Be specific to their message
        5. If suggesting a call, ALWAYS include calendar link
        6. Try to progress via email first
        7. If sending proposal, set clear expectations

        STRUCTURE:
        1. Acknowledge their points
        2. Provide relevant information
        3. Add value through insights
        4. Clear next step or question

        Write only the email body. No subject line or signature needed.
        """

        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": response_prompt}],
            temperature=0.7  # Reduced from 0.8 for more consistent tone
        )
        
        final_response = response.choices[0].message.content.strip()
        logging.info(f"Generated response: {final_response[:200]}...")
        
        # Validate no placeholders remain
        if "{{" in final_response or "}}" in final_response:
            logging.error("Generated response contains placeholders")
            raise ValueError("Response generation failed - contains unresolved placeholders")
        
        return final_response

    except Exception as e:
        logging.error(f"Error in response generation: {str(e)}")
        raise
        raise

def generate_standard_response(lead_info, previous_conversation):
    prompt = (
        f"Generate a response email based on the following conversation and lead info:\n\n{previous_conversation}\n\n and Lead INFO: {lead_info}"
        "The response should be polite, engaging, and should focus on building rapport. Do not reference agency info or services."
    )

    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150,
        temperature=0.7
    )

    logging.info("Generated standard response without agency info")
    return response.choices[0].message.content.strip()

def clean_and_validate_content(content: str, lead: Dict, agency_info: Dict) -> str:
    """Clean and validate email content, replacing known placeholders."""
    logging.info("Starting content cleaning and validation")
    
    # Create mapping of known placeholders to actual values
    replacements = {
        # Name variations
        '[name]': lead.get(SheetColumns.NAME.value, ''),
        '{name}': lead.get(SheetColumns.NAME.value, ''),
        '[recipient name]': lead.get(SheetColumns.NAME.value, ''),
        '{recipient name}': lead.get(SheetColumns.NAME.value, ''),
        '[first name]': lead.get(SheetColumns.NAME.value, '').split()[0],
        '{first name}': lead.get(SheetColumns.NAME.value, '').split()[0],
        
        # Sender variations
        '[your name]': agency_info.get('sender', {}).get('name', ''),
        '{your name}': agency_info.get('sender', {}).get('name', ''),
        '[sender name]': agency_info.get('sender', {}).get('name', ''),
        '{sender name}': agency_info.get('sender', {}).get('name', ''),
        
        # Company variations
        '[company]': lead.get(SheetColumns.COMPANY_NAME.value, ''),
        '{company}': lead.get(SheetColumns.COMPANY_NAME.value, ''),
        '[company name]': lead.get(SheetColumns.COMPANY_NAME.value, ''),
        '{company name}': lead.get(SheetColumns.COMPANY_NAME.value, ''),
        
        # Agency variations
        '[agency]': agency_info.get('name', ''),
        '{agency}': agency_info.get('name', ''),
        '[agency name]': agency_info.get('name', ''),
        '{agency name}': agency_info.get('name', '')
    }
    
    # Clean content
    cleaned_content = content
    for placeholder, value in replacements.items():
        if value:  # Only replace if we have a value
            cleaned_content = cleaned_content.replace(placeholder, value)
            cleaned_content = cleaned_content.replace(placeholder.upper(), value)
            cleaned_content = cleaned_content.replace(placeholder.title(), value)
    
    # Check for any remaining placeholders
    placeholder_patterns = [
        r'\[.*?\]',  # Anything in []
        r'\{.*?\}',  # Anything in {}
        r'<.*?>',    # Anything in <>
        r'\[\[.*?\]\]',  # Double [[]]
        r'\{\{.*?\}\}'   # Double {{}}
    ]
    
    remaining_placeholders = []
    for pattern in placeholder_patterns:
        matches = re.findall(pattern, cleaned_content)
        if matches:
            remaining_placeholders.extend(matches)
    
    if remaining_placeholders:
        logging.error(f"Found unhandled placeholders: {remaining_placeholders}")
        raise ValueError(f"Unhandled placeholders remain: {', '.join(remaining_placeholders)}")
    
    logging.info("Content cleaning and validation successful")
    return cleaned_content

def generate_cold_email_content(lead: Dict, agency_info: Dict, company_description: str) -> str:
    try:
        # Log all input data
        logging.info("=== Starting Cold Email Generation ===")
        logging.info("Lead Information:")
        lead_info = {
            'name': lead.get(SheetColumns.NAME.value),
            'role': lead.get(SheetColumns.ROLE.value),
            'company': lead.get(SheetColumns.COMPANY_NAME.value),
            'headline': lead.get(SheetColumns.HEADLINE.value),
            'domain': lead.get(SheetColumns.COMPANY_DOMAIN.value)
        }
        logging.info(f"Lead Details: {lead_info}")
        
        logging.info("Agency Information:")
        agency_details = {
            'name': agency_info.get('name'),
            'sender': agency_info.get('sender', {}),
            'services': agency_info.get('services', []),
            'portfolio_projects': agency_info.get('portfolio_projects', []),
            'experience': agency_info.get('description', '')
        }
        logging.info(f"Agency Details: {agency_details}")
        
        logging.info(f"Company Description: {company_description[:200]}...")

        # First, analyze the lead to determine best email formula
        analysis_prompt = f"""
        Analyze this lead to determine the best email approach:

        RECIPIENT:
        Name: {lead.get(SheetColumns.NAME.value)}
        Role: {lead.get(SheetColumns.ROLE.value)}
        Company: {lead.get(SheetColumns.COMPANY_NAME.value)}
        Description: {company_description}
        Headline: {lead.get(SheetColumns.HEADLINE.value)}

        OUR AGENCY:
        Name: {agency_info.get('name')}
        Services: {agency_info.get('services', [])}
        Experience: {agency_info.get('description', '')}
        Portfolio: {[f"{p.get('url')}: {p.get('details')}" for p in agency_info.get('portfolio_projects', [])]}
        
        DETERMINE:
        1. Best email formula (AIDA/BBB/PAS/QVC/PPP/SCH/SSS/RDM)
        2. Key pain points to address
        3. Most relevant service to highlight
        4. Best social proof elements
        5. Ideal call to action approach

        Provide a structured analysis of these elements. Take a deep breath and think step by step.
        """
        
        try:
            email_strategy = make_openai_call(
                model="gpt-4",
                messages=[{"role": "user", "content": analysis_prompt}],
                temperature=0.5
            )
            
            # Generate the actual email
            email_prompt = f"""
            You are an expert in writing friendly, casual, and effective cold emails.
            Write a personalized cold email using this strategy analysis:

            {email_strategy}

            RECIPIENT CONTEXT:
            - Name: {lead.get(SheetColumns.NAME.value)}
            - Role: {lead.get(SheetColumns.ROLE.value)}
            - Company: {lead.get(SheetColumns.COMPANY_NAME.value)}
            - About Their Company: {company_description}
            - Their Focus: {lead.get(SheetColumns.HEADLINE.value)}

            SENDER CONTEXT:
            - Name: {agency_info.get('sender_name')}
            - Role: {agency_info.get('sender_position')}
            - Agency Name: {agency_info.get('name')}
            - Services: {', '.join(agency_info.get('services', []))}
            - Calendar Link: {agency_info.get('calendar_link')}

            WRITING STYLE:
            - Conversational and casual
            - Simple, active voice sentences
            - Engaging and personal
            - Informational but concise
            - Natural flow without obvious formula

            FORMATTING REQUIREMENTS:
            - Use markdown for emphasis: **bold** for key points
            - Bold important elements like: company names, numbers, key benefits, action items
            - Format the calendar link call-to-action prominently
            - Keep paragraphs short and focused
            - Use subtle formatting - don't overdo bold text
            
            KEY ELEMENTS TO BOLD [DO NOT OVER-BOLD THINGS]:
            - Company names when mentioned
            - Key metrics or numbers
            - Primary value propositions
            - Action items or next steps
            - Important dates or timeframes
            
            EMAIL STRUCTURE (STRICT):
            1. Opening paragraph (2-3 sentences)
            2. Value proposition paragraph (2-3 sentences)
            3. Social proof or relevance paragraph (2-3 sentences)
            4. Call to action paragraph (1-2 sentences)

            FORMAT RULES:
            - Start with "Hi {lead.get(SheetColumns.NAME.value).split()[0]},"
            - Use exactly ONE line break between paragraphs
            - Keep paragraphs short and focused
            - End with clear calendar link call-to-action
            - Total length: 150-200 words maximum

            MUST AVOID:
            - Subject line
            - Signature block
            - Generic phrases
            - [Your Name] placeholders
            - Multiple line breaks
            - Bullet points or lists
            DO NOT use any placeholders like [Name] or [Company] or anything other placeholder
            Take a deep breath and think step by step.
            """
            
            email_content = make_openai_call(
                model="gpt-4",
                messages=[{"role": "user", "content": email_prompt}],
                temperature=0.7,
                max_tokens=400
            )
            
            
            return email_content
            
        except Exception as api_error:
            logging.error(f"OpenAI API Error: {str(api_error)}")
            # Return a graceful fallback or raise depending on your needs
            raise
            
    except Exception as e:
        logging.error(f"Error generating cold email content: {str(e)}")
        raise

def extract_requirements(conversation_history: str) -> str:
    """Extract key requirements from conversation history using GPT."""
    try:
        prompt = f"""
        Extract and summarize the key project requirements from this conversation:
        {conversation_history}
        
        List only the concrete requirements mentioned.
        Take a deep breath and think step by step.
        """
        
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error extracting requirements: {e}")
        return "Requirements extraction failed"

def generate_proposal(lead_info: Dict[str, Any], conversation_history: str, agency_info: Dict[str, Any]) -> Tuple[str, bytes]:
    """Generate proposal and return both markdown and PDF versions"""
    markdown_content = generate_proposal_content(lead_info, conversation_history, agency_info)  # Your existing logic
    pdf_content = convert_markdown_to_pdf(markdown_content)
    return markdown_content, pdf_content

def convert_markdown_to_pdf(markdown_content: str) -> bytes:
    """Convert markdown to PDF using markdown2pdf"""
    # Convert markdown to HTML
    html_content = markdown.markdown(markdown_content)
    
    # Convert HTML to PDF
    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes

def generate_proposal_content(lead_info: Dict[str, Any], conversation_history: str, agency_info: Dict[str, Any]) -> str:
    """Generate the proposal content in markdown format"""
    try:
        requirements = extract_requirements(conversation_history)
        
        # Get relevant portfolio assets
        portfolio = PortfolioAssets("path/to/your/portfolio/folder")
        relevant_assets = portfolio.get_relevant_assets(requirements)
        
        # Add portfolio links to agency info
        agency_info['portfolio_examples'] = {
            'presentations': [asset['url'] for asset in relevant_assets['presentations']],
            'videos': [asset['url'] for asset in relevant_assets['videos']],
            'landing_pages': [asset['url'] for asset in relevant_assets['landing_pages']]
        }
        
        prompt = f"""
        Create a detailed business proposal in markdown format for:
        Company: {lead_info.get('company_name')}
        Requirements: {requirements}
        
        Include these portfolio examples in your proposal:
        Presentations: {agency_info['portfolio_examples']['presentations']}
        Videos: {agency_info['portfolio_examples']['videos']}
        Landing Pages: {agency_info['portfolio_examples']['landing_pages']}
        
        Include:
        1. Executive Summary
        2. Proposed Solution
        3. Timeline
        4. Investment
        5. Next Steps
        
        Use our agency services: {agency_info.get('services', [])}
        Take a deep breath and think step by step.
        """
        
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error generating proposal content: {e}")
        return "Error generating proposal content"

def analyze_conversation(conversation_history: str) -> Dict[str, Any]:
    """Analyze conversation to determine context and next steps."""
    try:
        prompt = f"""
        Analyze this conversation and provide:
        1. Conversation stage (early/mid/late)
        2. Key points discussed
        3. Client's main concerns
        4. Recommended next steps
        
        Conversation:
        {conversation_history}
        Take a deep breath and think step by step.
        """
        
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        return {"analysis": response.choices[0].message.content.strip()}
    except Exception as e:
        logging.error(f"Error analyzing conversation: {e}")
        return {"analysis": "Analysis failed", "error": str(e)}

def generate_response_email(lead: Dict[str, Any], conversation_history: str, agency_info: Dict[str, Any]) -> Tuple[str, str]:
    try:
        # Analyze conversation
        analysis = analyze_conversation(conversation_history)
        
        # Get portfolio examples
        portfolio = PortfolioAssets()
        relevant_assets = portfolio.get_relevant_assets(lead['company_domain'])
        
        # Format portfolio examples for the email
        portfolio_section = format_portfolio_examples(relevant_assets)
        
        prompt=f"""Please craft a detailed response to the email conversation based on the following information + instructions. Follow accurately and be focused.
            RECIPIENT CONTEXT:
            - Name: {lead.get(SheetColumns.NAME.value)}

            SENDER CONTEXT:
            - Name: {agency_info.get('sender_name')}
            - Role: {agency_info.get('sender_position')}
            - Agency Name: {agency_info.get('name')}
            - Services: {', '.join(agency_info.get('services', []))}
            - Calendar Link: {agency_info.get('calendar_link')}

            WRITING STYLE:
            - Conversational and casual
            - Simple, active voice sentences
            - Engaging and personal
            - Informational but concise
            - Natural flow without obvious formula

            FORMATTING REQUIREMENTS:
            - Use markdown for emphasis: **bold** for key points
            - Bold important elements like: company names, numbers, key benefits, action items
            - Format the calendar link call-to-action prominently
            - Keep paragraphs short and focused
            - Use subtle formatting - don't overdo bold text
            
            KEY ELEMENTS TO BOLD [DO NOT OVER-BOLD THINGS]:
            - Company names when mentioned
            - Key metrics or numbers
            - Primary value propositions
            - Action items or next steps
            - Important dates or timeframes
            
            EMAIL STRUCTURE (STRICT):
            1. Opening paragraph (2-3 sentences)
            2. Value proposition paragraph (2-3 sentences)
            3. Social proof or relevance paragraph (2-3 sentences)
            4. Call to action paragraph (1-2 sentences)

            FORMAT RULES:
            - Start with "Hi {lead.get(SheetColumns.NAME.value).split()[0]},"
            - Use exactly ONE line break between paragraphs
            - Keep paragraphs short and focused
            - End with clear calendar link call-to-action
            - Total length: 150-200 words maximum

            If and only if required basis the conversation flow, include one or more projects from our portfolio. 
            {portfolio_section}
            
            MUST AVOID:
            - Subject line
            - Signature block
            - Generic phrases
            - [Your Name] placeholders
            - Multiple line breaks
            - Bullet points or lists
            DO NOT use any placeholders like [Name] or [Company] or anything other placeholder

            Conversation Analysis: 
            {analysis}

            Take a deep breath and think step by step.
        """

        # Generate personalized response
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user", 
                "content": prompt
            }],
            temperature=0.7
        )
        
        email_content = response.choices[0].message.content.strip()
        
        # Ensure no placeholders remain
        email_content = email_content.replace("[Your Name]", agency_info['sender_name'])
        email_content = email_content.replace("{{", "").replace("}}", "")
        
        return email_content, f"Re: {lead['Cold Email Subject']}"
        
    except Exception as e:
        logging.error(f"Error generating response email: {e}")
        raise

def format_portfolio_examples(relevant_assets: Dict[str, Any]) -> str:
    """Format portfolio assets into a readable string for email inclusion."""
    formatted = []
    for asset_type, assets in relevant_assets.items():
        if assets:
            examples = ", ".join([f"{a.get('name', 'Project')}: {a.get('url', '')}" for a in assets[:2]])
            formatted.append(f"{asset_type.title()}: {examples}")
    return "\n".join(formatted) if formatted else "Portfolio examples available upon request."

def validate_final_content(email_body: str, subject_line: str, lead: Dict, agency_info: Dict) -> Tuple[str, str]:
    """Final validation using GPT-3.5-turbo to catch any remaining placeholders or dummy content"""
    try:
        validation_prompt = f"""
        Analyze this email content and subject line for any remaining placeholders, dummy data, or sample text.
        Replace them with the correct values or remove them. Maintain the exact same tone and structure.

        Subject: {subject_line}
        Email Body: {email_body}

        Real values to use:
        - Recipient Name: {lead.get(SheetColumns.NAME.value)}
        - Recipient Company: {lead.get(SheetColumns.COMPANY_NAME.value)}
        - Sender Name: {agency_info.get('sender', {}).get('name')}
        - Agency Name: {agency_info.get('name')}

        Return only the cleaned subject line and email body in this exact format:
        SUBJECT: <cleaned subject>
        BODY: <cleaned email body>
        """

        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": validation_prompt}],
            temperature=0.3  # Low temperature for consistent cleaning
        )

        cleaned_content = response.choices[0].message.content.strip()
        
        # Extract subject and body
        subject_match = re.search(r'SUBJECT:\s*(.*?)\s*BODY:', cleaned_content, re.DOTALL)
        body_match = re.search(r'BODY:\s*(.*)', cleaned_content, re.DOTALL)
        
        if not subject_match or not body_match:
            raise ValueError("Validation response not in expected format")
            
        cleaned_subject = subject_match.group(1).strip()
        cleaned_body = body_match.group(1).strip()
        
        logging.info("Final content validation completed successfully")
        return cleaned_subject, cleaned_body

    except Exception as e:
        logging.error(f"Error in final content validation: {str(e)}")
        raise
