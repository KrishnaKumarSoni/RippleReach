from flask import Flask, request, jsonify
from google_sheets import get_lead_data, update_sheet, get_agency_info
from openai_integration import generate_company_description, determine_and_generate_response, generate_cold_email_content, generate_proposal, validate_final_content
from resend_integration import send_round_robin_email
from utils import format_html_email, format_portfolio_html
from portfolio_assets import PortfolioAssets  # Use this instead of drive_integration
from config import Config
import logging
from typing import Dict, Any, Tuple, List
from constants import SheetColumns, EmailStatus, SenderType
from datetime import datetime
import base64
import os
import openai
from jinja2 import Environment, FileSystemLoader

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
jinja_env = Environment(loader=FileSystemLoader('templates'))

def should_process_lead(lead: Dict[str, Any]) -> Tuple[bool, str]:
    """Determine if a lead should be processed based on various conditions."""
    email_status = lead.get(SheetColumns.EMAIL_STATUS.value)
    last_message = lead.get(SheetColumns.LAST_MESSAGE.value)
    
    logging.info(f"Processing lead - Status: {email_status}, Last Message: {last_message}")
    
    # Case 1: New lead that needs cold email
    if not email_status or email_status == EmailStatus.NEW.value:
        return True, "New lead needs cold email"
    
    # Case 2: Client replied to our email
    if email_status == EmailStatus.REPLIED.value:
        return True, "Need to respond to client reply"
    
    # Case 3: Cold email sent but no reply yet
    if email_status == EmailStatus.SENT.value and not last_message:
        return False, "Waiting for client response"
    
    # Case 4: Failed email needs retry
    if email_status == EmailStatus.FAILED.value:
        return True, "Retrying failed email"
        
    return False, f"No action needed. Status: {email_status}"

@app.route("/preview", methods=["GET"])
def preview():
    start_row = int(request.args.get("start_row", Config.STARTING_ROW))
    data = get_lead_data(start_row)
    if not data:
        logging.warning("No data available in the Google Sheet.")
        return jsonify({"status": "No data available in the Google Sheet"}), 400
    return jsonify(data)

@app.route("/send_emails", methods=["POST"])
def send_emails():
    """Process leads and send emails where needed"""
    try:
        leads = get_lead_data(Config.STARTING_ROW)
        agency_info = get_agency_info()
        processing_results = []
        
        for index, lead in enumerate(leads, start=Config.STARTING_ROW):
            try:
                should_process, reason = should_process_lead(lead)
                logging.info(f"Row {index}: Should process? {should_process} - {reason}")
                
                if not should_process:
                    processing_results.append({
                        "row": index,
                        "action": "skipped",
                        "reason": reason
                    })
                    continue
                
                result = None  # Initialize result
                
                # Case 1: Send cold email
                if not lead.get(SheetColumns.EMAIL_STATUS.value) or lead.get(SheetColumns.EMAIL_STATUS.value) == EmailStatus.NEW.value:
                    result = process_new_lead(lead, agency_info, index)
                
                # Case 2: Process client reply (both SENT with message and REPLIED status)
                elif (lead.get(SheetColumns.EMAIL_STATUS.value) == EmailStatus.SENT.value and lead.get(SheetColumns.LAST_MESSAGE.value)) or \
                     (lead.get(SheetColumns.EMAIL_STATUS.value) == EmailStatus.REPLIED.value):
                    result = process_client_reply(lead, index, agency_info)
                
                # Case 3: Retry failed email
                elif lead.get(SheetColumns.EMAIL_STATUS.value) == EmailStatus.FAILED.value:
                    result = process_failed_email(lead, index)
                
                if result:  # Only append if we got a result
                    processing_results.append({
                        "row": index,
                        "action": "processed",
                        "result": result
                    })
                else:
                    processing_results.append({
                        "row": index,
                        "action": "skipped",
                        "reason": "No matching action found"
                    })
                
            except Exception as e:
                logging.error(f"Error processing row {index}: {str(e)}")
                processing_results.append({
                    "row": index,
                    "action": "error",
                    "error": str(e)
                })
        
        return jsonify({
            "status": "success",
            "results": processing_results
        })
        
    except Exception as e:
        logging.error(f"Error in send_emails: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500
        
def process_new_lead(lead: Dict[str, Any], agency_info: Dict, index: int) -> Dict[str, Any]:
    """Handle sending cold email to new lead"""
    try:
        # Get company description with proper error handling
        company_description = None
        try:
            company_description = generate_company_description(lead[SheetColumns.COMPANY_DOMAIN.value])
            if company_description:
                update_sheet(index, {
                    SheetColumns.COMPANY_BACKGROUND: company_description
                })
        except Exception as e:
            logging.warning(f"Could not generate company description: {str(e)}")
            company_description = f"A technology company specializing in {lead.get(SheetColumns.HEADLINE.value, 'digital solutions')}"

        # Generate email content first
        email_content = generate_cold_email_content(lead, agency_info, company_description)
        if not email_content:
            raise Exception("Failed to generate email content")
        
        # Generate subject line separately
        subject = generate_subject_line(lead, agency_info)
        if not subject:
            raise Exception("Failed to generate subject line")

        # Get portfolio items based on lead context
        portfolio = PortfolioAssets()
        relevant_assets = portfolio.get_relevant_assets(lead[SheetColumns.COMPANY_DOMAIN.value])
        
        # Format portfolio items for agency info
        portfolio_items = [
            {
                'title': asset['name'],
                'description': f"Relevant {asset['project']} showcase",
                'link': asset['url']
            }
            for asset in relevant_assets.get('case_studies', [])[:2]
        ]
        
        # Add portfolio to agency info
        complete_agency_info = {
            **agency_info,
            'portfolio_items': portfolio_items
        }

        # Validate final content
        subject, email_content = validate_final_content(email_content, subject, lead, agency_info)

        # Format email with portfolio
        html_content = format_html_email(email_content, complete_agency_info)
        
        # Send email with proper subject
        email_status = send_round_robin_email(
            lead[SheetColumns.EMAIL.value], 
            subject,  # Use the generated subject directly
            html_content
        )
        # Update sheet with proper formatting
        conversation_entry = (
            f"Email Sent ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
            f"To: {lead[SheetColumns.NAME.value]} ({lead[SheetColumns.EMAIL.value]})\n"
            f"From: {agency_info['sender']['name']} ({email_status['details']['from']})\n"
            f"\n{email_content}"
        )

        update_sheet(index, {
            SheetColumns.COLD_EMAIL_SUBJECT: subject,
            SheetColumns.EMAIL_CONTENT: email_content,
            SheetColumns.HTML_EMAIL_CONTENT: html_content,
            SheetColumns.EMAIL_STATUS: EmailStatus.SENT,
            SheetColumns.SENDER_EMAIL: email_status.get("details", {}).get("from"),
            SheetColumns.LAST_SENDER: SenderType.AGENCY,
            SheetColumns.CONVERSATION_HISTORY: conversation_entry
        })
        
        return {"status": "success", "type": "cold_email"}
        
    except Exception as e:
        logging.error(f"Error in process_new_lead: {str(e)}")
        raise

def process_client_reply(lead: Dict[str, Any], index: int, agency_info: Dict[str, Any]) -> Dict[str, Any]:
    # Get portfolio items based on lead context
    portfolio = PortfolioAssets()
    relevant_assets = portfolio.get_relevant_assets(lead[SheetColumns.COMPANY_DOMAIN.value])

    # Format portfolio items for agency info
    portfolio_items = [
        {
            'title': asset['name'],
            'description': f"Relevant {asset['project']} showcase",
            'link': asset['url']
        }
        for asset in relevant_assets.get('case_studies', [])[:2]
    ]

    # Add portfolio to agency info
    complete_agency_info = {
        **agency_info,
        'portfolio_items': portfolio_items
    }
    """Handle generating and sending response to client reply"""
    try:
        logging.info(f"Processing client reply for row {index}")
        
        previous_conversation = lead.get(SheetColumns.CONVERSATION_HISTORY.value, "")
        # Get original subject or create new one
        original_subject = lead.get(SheetColumns.COLD_EMAIL_SUBJECT.value, "Your inquiry")
        subject = f"Re: {original_subject}" if not original_subject.lower().startswith('re:') else original_subject
        
        # Generate response
        response_email = determine_and_generate_response(
            {
                **lead,
                'name': lead.get(SheetColumns.NAME.value, '').split()[0]
            }, 
            previous_conversation, 
            agency_info
        )
        
        # Check if proposal is needed
        if "proposal" in lead.get(SheetColumns.LAST_MESSAGE.value, "").lower():
            markdown_proposal, pdf_proposal = generate_proposal(lead, previous_conversation, agency_info)
            
            # Save markdown version to sheet
            update_sheet(index, {
                SheetColumns.PROPOSAL.value: markdown_proposal
            })
            
            # Encode PDF for attachment
            pdf_base64 = base64.b64encode(pdf_proposal).decode()
            
            # Send email with attachment
            html_content = format_html_email(response_email)
            email_status = send_round_robin_email(
                lead[SheetColumns.EMAIL.value], 
                subject,
                html_content,
                attachments=[{
                    'content': pdf_base64,
                    'filename': f"{lead.get(SheetColumns.COMPANY_NAME.value, 'Proposal')}.pdf"
                }]
            )
        else:
            # Format and send email without attachment
            html_content = format_html_email(response_email)
            email_status = send_round_robin_email(
                lead[SheetColumns.EMAIL.value], 
                subject,
                html_content
            )
        
        if email_status.get("status") != "success":
            raise Exception(f"Email sending failed: {email_status.get('error')}")

        # Update sheet
        update_sheet(index, {
            SheetColumns.RESPONSE.value: response_email,
            SheetColumns.EMAIL_STATUS.value: EmailStatus.ACTIVE.value,
            SheetColumns.SENDER_EMAIL.value: email_status.get("details", {}).get("from", "Unknown sender"),
            SheetColumns.LAST_SENDER.value: SenderType.AGENCY.value,
            SheetColumns.CONVERSATION_HISTORY.value: (
                f"{previous_conversation}\n\n"
                f"Client ({datetime.now()}):\n{lead.get(SheetColumns.LAST_MESSAGE.value)}\n\n"
                f"Our Response ({datetime.now()}):\n{response_email}"
            )
        })

        return {"status": "success", "type": "response"}
    except Exception as e:
        logging.error(f"Error in process_client_reply: {str(e)}")
        raise

def process_failed_email(lead: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Handle retrying failed emails"""
    # Implement retry logic here
    pass

@app.route("/monitor_emails", methods=["POST"])
def monitor_emails_endpoint():
    """Endpoint to check for email replies and update Google Sheets"""
    try:
        logging.info("Starting email monitoring process...")
        from email_monitor import EmailMonitor
        
        # Initialize and run the monitor
        monitor = EmailMonitor()
        monitor.check_replies()
        
        return jsonify({
            "status": "success",
            "message": "Email monitoring completed successfully"
        })
        
    except Exception as e:
        logging.error(f"Error in email monitoring: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

def generate_subject_line(lead: Dict[str, Any], agency_info: Dict) -> str:
    prompt = f"""
    Generate a compelling email subject line for this context:
    
    Company: {lead.get(SheetColumns.COMPANY_NAME.value)}
    Their Focus: {lead.get(SheetColumns.HEADLINE.value)}
    Our Company: {agency_info['name']}
    
    Requirements:
    - Specific to their AI SaaS business
    - Mention value proposition
    - Keep under 60 characters
    - No generic templates
    """
    
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    
    return response.choices[0].message.content.strip()

if __name__ == "__main__":
    Config.validate_config()
    app.run(debug=True)
