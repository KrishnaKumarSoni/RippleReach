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
import json


openai.api_key = Config.OPENAI_API_KEY
logging.basicConfig(level=logging.INFO)

@retry(
    retry=retry_if_exception_type((openai.OpenAIError, json.JSONDecodeError)),
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
        if not response.choices:
            raise ValueError("No response choices returned from OpenAI")
            
        return response.choices[0].message.content.strip()
        
    except openai.OpenAIError as e:
        if 'insufficient_quota' in str(e):
            logging.error("OpenAI API Quota exceeded. Please check billing.")
        raise
    except Exception as e:
        logging.error(f"Error in make_openai_call: {str(e)}")
        raise

def generate_cold_email_content(lead: Dict, agency_info: Dict, company_description: str) -> str:
    try:
        
        # Validate input data
        if not lead or not agency_info:
            raise ValueError("Missing required lead or agency information")
            
        # Ensure we have minimum required fields
        required_lead_fields = [
            SheetColumns.NAME.value,
            SheetColumns.ROLE.value,
            SheetColumns.COMPANY_NAME.value
        ]
        
        for field in required_lead_fields:
            if not lead.get(field):
                raise ValueError(f"Missing required lead field: {field}")
        
        # Log input data with safe gets
        lead_info = {
            'name': lead.get(SheetColumns.NAME.value, ''),
            'role': lead.get(SheetColumns.ROLE.value, ''),
            'company': lead.get(SheetColumns.COMPANY_NAME.value, ''),
            'headline': lead.get(SheetColumns.HEADLINE.value, ''),
            'domain': lead.get(SheetColumns.COMPANY_DOMAIN.value, '')
        }
        
        recipient_name = lead.get(SheetColumns.NAME.value, '').split()[0] if lead.get(SheetColumns.NAME.value) else ''
        
        
        # Initialize portfolio
        portfolio = PortfolioAssets()
        assets = portfolio.get_all_assets()
        # Step 1: Analysis using GPT-3.5
        analysis_prompt = f"""
        Analyze this lead for a cold email:
        Name: {recipient_name}
        Role: {lead_info['role']}
        Company: {lead_info['company']}
        Description: {company_description or 'Not available'}
        Headline: {lead_info['headline']}

        Agency Context:
        {agency_info}

        Available Portfolio Items:
        {json.dumps([{
            'name': asset['name'],
            'type': asset['type'],
            'industry': asset['industry'],
            'service': asset['service_type']
        } for asset in assets], indent=2)}

        Analyze and provide:
        1. Best email formula
        2. Key pain points
        3. Most relevant service
        4. Should we include portfolio examples? (true/false)
        5. If true, which specific portfolio item would be most relevant (provide file name)
        6. Call to action approach

        Return as JSON:
        {{
            "formula": "",
            "pain_points": [],
            "relevant_service": "",
            "include_portfolio": false,
            "portfolio_item": null,
            "cta": ""
        }}
        """

        analysis_response = make_openai_call(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": analysis_prompt}],
            temperature=0.7
        )
        try:
            analysis = json.loads(analysis_response)
            logging.info(f"Lead analysis completed: {json.dumps(analysis, indent=2)}")
        except json.JSONDecodeError:
            logging.error(f"Failed to parse analysis JSON: {analysis_response}")
            raise ValueError("Analysis generation failed")
        
        
        if not assets:
            logging.warning("No portfolio assets loaded from Drive")

        # Get selected portfolio item if recommended
        portfolio_data = {"has_portfolio": False, "assets": []}  # Default portfolio data
        portfolio_content = "None"
        if analysis.get('include_portfolio'):
            selected_asset = portfolio.get_asset_by_name(analysis['portfolio_item'])
            if selected_asset:
                portfolio_data = portfolio.format_for_email_template([selected_asset])
                portfolio_content = f"\n\nRelevant Work:\n{selected_asset['name']}: {selected_asset['url']}"
                logging.info(f"Including portfolio item: {selected_asset['name']}")
            else:
                logging.warning(f"Recommended portfolio item not found: {analysis['portfolio_item']}")

        # Step 2: Email Generation using GPT-4
        email_prompt = f"""
        Write a personalized cold email using this analysis:
        {json.dumps(analysis, indent=2)}

        RECIPIENT:
        Name: {recipient_name}
        Role: {lead_info['role']}
        Company: {lead_info['company']}
        {f'PORTFOLIO TO INCLUDE:\n{portfolio_content}' if portfolio_content else ''}

        FORMAT REQUIREMENTS:
        - Start with "Hi {recipient_name},"
        - Use single line breaks between paragraphs
        - Keep paragraphs short (2-3 sentences)
        - Based on the analysis, if required and only if required, use calendar link CTA: {agency_info.get('calendar_link')}
        - 150-200 words maximum
        - No placeholders, No example sample companies like ABC XYZ etc. No subject lines, and No signatures

        Writing style: conversational, casual, engaging, simple to read, simple linear active voice sentences, informational and insightful.
    
        Use the following formulas to write effective cold emails:

        1. AIDA: Start with an attention-grabbing subject line or opening sentence. Highlight the recipient's pain points to build interest. List the benefits and use social proof, scarcity, or exclusivity to create desire. End with a specific call to action.

        2. BBB: Keep the email brief, blunt, and basic. Shorten the email, get straight to the point, and use simple language.

        3. PAS: Identify a sore point (Problem). Emphasize the severity with examples or personal experience (Agitate). Present your solution (Solve).

        4. QVC: Start with a question. Highlight what makes you unique (Value Proposition). End with a strong call to action.

        5. PPP: Open with a genuine compliment (Praise). Show how your product/service helps (Picture). Encourage them to take action (Push).

        6. SCH: Introduce your product or idea (Star). Provide strong facts and reasons (Chain). End with a powerful call to action (Hook).

        7. SSS: Introduce the star of your story (Star). Describe the problem they face (Story). Explain how your product solves the problem (Solution).

        8. RDM: Use facts (Fact-packed), be brief (Telegraphic), be specific (Specific), avoid too many adjectives (Few adjectives), and make them curious (Arouse curiosity).

        These formulas will help you craft concise, casual, friendly engaging, and compelling cold emails.

        Write only the email body following the analyzed formula.
        """

        email_content = make_openai_call(
            model="gpt-4o",
            messages=[{"role": "user", "content": email_prompt}],
            temperature=0.7
        )

        # Validate and clean the generated content
        if "{{" in email_content or "}}" in email_content:
            raise ValueError("Generated content contains unresolved placeholders")

        logging.info(f"Generated email content: {email_content[:200]}...")
        return email_content.strip(), portfolio_data
        
    except Exception as e:
        logging.error(f"Error generating cold email content: {str(e)}")
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
    
    # Initialize portfolio
    portfolio = PortfolioAssets()
    assets = portfolio.get_all_assets()
    

    # Step 1: Analyze conversation and determine context
    analysis_prompt = f"""
    You are an expert B2B sales strategist. Analyze this conversation thread:

    CONVERSATION HISTORY:
    {previous_conversation}

    LATEST MESSAGE FROM CLIENT:
    {lead_info.get('last_message', '')}

    Available Portfolio Items:
        {json.dumps([{
            'name': asset['name'],
            'type': asset['type'],
            'industry': asset['industry'],
            'service': asset['service_type']
        } for asset in assets], indent=2)}

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

    Respond only and only in JSON FORMAT. 
    Return as JSON:
    {
        "approach": "",
        "key_points": [],
        "include_portfolio": false,
        "portfolio_item": null,
        "cta": ""
    }
    """

    try:
        analysis = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": analysis_prompt}],
            temperature=0.7
        )
        conversation_analysis = analysis.choices[0].message.content.strip()
        # Extract JSON from the conversation analysis using regex
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        json_match = re.search(json_pattern, conversation_analysis)
        if not json_match:
            raise ValueError("No valid JSON found in conversation analysis")
        conversation_analysis = json_match.group()
        logging.info(f"Conversation analysis completed: {conversation_analysis[:200]}...")

        # Get analysis with portfolio recommendation
        analysis = json.loads(conversation_analysis)

        # Get portfolio data if recommended
        portfolio_data = {"has_portfolio": False, "assets": []}
        if analysis.get('include_portfolio'):
            selected_asset = portfolio.get_asset_by_name(analysis['portfolio_item'])
            if selected_asset:
                portfolio_data = portfolio.format_for_email_template([selected_asset])
                logging.info(f"Including portfolio item: {selected_asset['name']}")
            else:
                logging.warning(f"Recommended portfolio item not found: {analysis['portfolio_item']}")


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
        2. Make sure to preserve the pricing till only the most necessary point in conversation when you have to reveal it and there is no other choice.
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
            model="gpt-4o",
            messages=[{"role": "user", "content": response_prompt}],
            temperature=0.7  # Reduced from 0.8 for more consistent tone
        )
        
        final_response = response.choices[0].message.content.strip()
        logging.info(f"Generated response: {final_response[:200]}...")
        
        # Validate no placeholders remain
        if "{{" in final_response or "}}" in final_response:
            logging.error("Generated response contains placeholders")
            raise ValueError("Response generation failed - contains unresolved placeholders")
        
        return final_response, portfolio_data

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
    """Clean and refine the generated email content."""
    logging.info("Starting content cleaning and refinement")
    
    prompt = f"""
    Clean and refine the following email content:

    {content}

    SUPPORTING DATA:
    {lead}
    {agency_info}

    Instructions:
    Thoroughly go through the provided email body. 
    Check if there is anything placeholder like ABC or XYZ or anything repeating by mistake
    Check if silly mistake in the email like spelling mistake or anything
    Replace all parts you have identified as mistakes and wordsmith those parts to remove any mistakes / placeholders
    DO NOT TOUCH ANY EXISTING CORRECT PARTS OF THE EMAIL

    Provide only the cleaned and refined email content in your response.
    MOST OF THE TIMES THINGS WILL BE ACCURATE. IN SUCH CASES, JUST RETURN THE EMAIL BODY AS IS.
    TAKE A DEEP BREATH AND THINK STEP BY STEP..
    """

    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    cleaned_content = response.choices[0].message.content.strip()
    
    logging.info("==========Content cleaning and refinement completed: {cleaned_content}")
    return cleaned_content

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

def generate_proposal_content(lead_info: Dict[str, Any], conversation_history: str, agency_info: Dict[str, Any]) -> Dict[str, Any]:
    """Generate structured proposal content for HTML template"""
    try:
        # Reference existing requirements extraction
        requirements = extract_requirements(conversation_history)
        logging.info(f"Extracted requirements: {requirements}")
        
        # Get portfolio assets
        portfolio = PortfolioAssets()
        relevant_assets = portfolio.get_relevant_assets(requirements)
        
        analysis_prompt = f"""
        You are an expert business proposal strategist with extensive experience crafting winning proposals for technology and digital service companies. Your goal is to analyze this opportunity and provide strategic insights that will inform a compelling, value-focused proposal.

        COMPANY CONTEXT:
        Company Name: {lead_info.get('company_name')}
        Industry Requirements: {requirements}
        Prior Discussions: {conversation_history}

        PROVIDE A DETAILED ANALYSIS COVERING:

        1. Project Scope Assessment
        - Core business challenges being addressed
        - Technical and operational requirements
        - Key success metrics and outcomes
        - Potential risks and mitigation strategies

        2. Value Opportunity Analysis  
        - Immediate business impact
        - Long-term strategic benefits
        - Competitive advantages gained
        - ROI potential and measurement approach

        3. Timeline & Resource Planning
        - Critical project phases and dependencies
        - Resource requirements and allocation
        - Key milestones and deliverables
        - Flexibility considerations

        4. Investment Structure Recommendations
        - Value-based pricing strategy
        - Payment milestone alignment
        - Risk-reward considerations
        - Optional enhancements

        FORMAT YOUR RESPONSE AS:
        - Clear section headers
        - Bulleted key points
        - Specific, actionable insights
        - Data-driven recommendations where possible

        Focus on demonstrating deep understanding of the client's needs while highlighting unique value propositions. Be specific, strategic and business outcome focused.
        """

        # Get strategic analysis first
        analysis = make_openai_call(
            model="gpt-4o",
            messages=[{"role": "user", "content": analysis_prompt}],
            temperature=0.3
        )
        
        # Now generate the actual proposal content
        proposal_prompt = f"""
        You are a professional proposal writer. Create a detailed proposal based on this analysis:
        {analysis}

        PORTFOLIO EXAMPLES:
        {[f"{p.get('url')}: {p.get('details')}" for p in relevant_assets]}

        Generate a complete proposal with these EXACT keys in valid JSON format:
        {{
            "executive_summary": "2-3 paragraphs",
            "project_scope": {{
                "overview": "High-level description",
                "deliverables": ["item1", "item2"],
                "technical_requirements": ["req1", "req2"]
            }},
            "timeline": [
                {{
                    "phase": "Phase name",
                    "duration": "X weeks",
                    "deliverables": ["item1", "item2"]
                }}
            ],
            "investment": {{
                "total": "Total amount",
                "breakdown": [
                    {{
                        "item": "Component name",
                        "amount": "Cost",
                        "description": "Details"
                    }}
                ],
                "payment_schedule": [
                    {{
                        "milestone": "Description",
                        "percentage": "XX%",
                        "amount": "Amount"
                    }}
                ]
            }},
            "next_steps": ["step1", "step2"]
        }}

        REQUIREMENTS:
        1. Must be valid JSON
        2. Use exact keys shown above
        3. Include realistic values
        4. Be specific and detailed
        5. Focus on value delivery
        """

        # Generate proposal with strict JSON output
        proposal_json = make_openai_call(
            model="gpt-4o",
            messages=[{"role": "user", "content": proposal_prompt}],
            temperature=0.4
        )

        # Validate JSON structure
        try:
            return json.loads(proposal_json)
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON from OpenAI: {proposal_json}")
            logging.error(f"JSON Error: {str(e)}")
            raise

    except Exception as e:
        logging.error(f"Error in generate_proposal_content: {str(e)}")
        raise

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
        if not email_body or not subject_line:
            raise ValueError("Email body or subject line is empty")
            
        # Ensure email_body has proper paragraph structure
        if '\n\n' not in email_body:
            email_body = email_body.replace('\n', '\n\n')
        
        validation_prompt = f"""
        Analyze this email content and subject line for any remaining placeholders, dummy data, or sample text.
        Ensure the email has proper paragraph breaks (double newlines between paragraphs).
        Replace any placeholders with the correct values or remove them.
        Maintain the exact same tone and structure.

        Subject: {subject_line}
        Email Body: {email_body}

        Real values to use:
        - Recipient Name: {lead.get(SheetColumns.NAME.value, '')}
        - Recipient Company: {lead.get(SheetColumns.COMPANY_NAME.value, '')}
        - Sender Name: {agency_info.get('sender', {}).get('name', '')}
        - Agency Name: {agency_info.get('name', '')}

        Return the cleaned content in this exact format:
        SUBJECT: <cleaned subject>
        BODY: <cleaned email body with proper paragraph breaks>
        """

        response = make_openai_call(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": validation_prompt}],
            temperature=0.3
        )

        # Extract and validate response
        cleaned_content = response.strip()
        if not cleaned_content or 'SUBJECT:' not in cleaned_content or 'BODY:' not in cleaned_content:
            raise ValueError("Invalid validation response format")
            
        subject_match = re.search(r'SUBJECT:\s*(.*?)\s*BODY:', cleaned_content, re.DOTALL)
        body_match = re.search(r'BODY:\s*(.*)', cleaned_content, re.DOTALL)
        
        if not subject_match or not body_match:
            raise ValueError("Could not extract subject or body from validation response")
            
        cleaned_subject = subject_match.group(1).strip()
        cleaned_body = body_match.group(1).strip()
        
        # Ensure proper paragraph structure
        if '\n\n' not in cleaned_body:
            cleaned_body = cleaned_body.replace('\n', '\n\n')
        
        logging.info("Final content validation completed successfully")
        return cleaned_subject, cleaned_body

    except Exception as e:
        logging.error(f"Error in final content validation: {str(e)}")
        raise
