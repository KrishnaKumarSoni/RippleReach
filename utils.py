import re
from typing import Dict, List
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import time
import openai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from jinja2 import Environment, FileSystemLoader
jinja_env = Environment(loader=FileSystemLoader('templates'))
import json  # Add this with other imports

def format_html_email(email_content: str, agency_info: Dict) -> str:
    """Format email content into HTML template"""
    try:
        # Split content into paragraphs and clean up
        paragraphs = [p.strip() for p in email_content.split('\n') if p.strip()]
        
        template = jinja_env.get_template('email_template.html')
        return template.render(
            paragraphs=paragraphs,
            portfolio=agency_info.get('portfolio', {"has_portfolio": False, "assets": []}),
            calendar_link=agency_info.get('calendar_link', '#'),
            agency_website=agency_info.get('website', '#'),
            sender_name=agency_info.get('sender', {}).get('name', ''),
            sender_position=agency_info.get('sender', {}).get('position', ''),
            agency_name=agency_info.get('name', ''),
            sender_meta=agency_info.get('sender', {}).get('meta', '')
        )
    except Exception as e:
        logging.error(f"Error formatting HTML email: {e}")
        raise

def format_portfolio_html(portfolio_items: List[Dict]) -> str:
    if not portfolio_items:
        return ""
        
    html = ""
    for item in portfolio_items:
        title = item.get('title', '').strip()
        description = item.get('description', '').strip()
        link = item.get('link', '').strip()
        
        if not all([title, description, link]):
            continue
            
        html += f"""
        <div class="portfolio-item">
            <h4>{title}</h4>
            <p>{description}</p>
            <a href="{link}" target="_blank" rel="noopener noreferrer">
                View Project →
            </a>
        </div>
        """
    return html.strip()

def generate_company_description(domain: str) -> str:
    try:
        # Clean and validate the URL
        if not domain.startswith(('http://', 'https://')):
            domain = f'https://{domain}'
        
        parsed_url = urlparse(domain)
        clean_domain = parsed_url.netloc or parsed_url.path.strip('/')
        
        # Set up headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Try different URLs
        urls_to_try = [
            f'https://{clean_domain}',
            f'https://{clean_domain}/about',
            f'https://{clean_domain}/about-us',
            f'https://{clean_domain}/company'
        ]
        
        description = ""
        for url in urls_to_try:
            try:
                response = requests.get(url, headers=headers, timeout=10, verify=False)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Remove script and style elements
                for script in soup(['script', 'style']):
                    script.decompose()
                
                # Try to find relevant content
                meta_description = soup.find('meta', {'name': ['description', 'og:description']})
                if meta_description and meta_description.get('content'):
                    description += meta_description['content'] + " "
                
                # Look for about section content
                about_sections = soup.find_all(['div', 'section'], class_=lambda x: x and ('about' in x.lower() or 'company' in x.lower()))
                for section in about_sections[:2]:  # Limit to first 2 matching sections
                    description += section.get_text(strip=True) + " "
                
                if description:
                    break
                
                time.sleep(1)  # Be polite with requests
                
            except requests.RequestException as e:
                logging.warning(f"Failed to fetch {url}: {str(e)}")
                continue
        
        if not description:
            # If we couldn't get a description, use GPT to generate one based on the domain
            return generate_ai_company_description(clean_domain)
        
        # Clean up and format the description
        description = ' '.join(description.split())[:500]  # Limit to 500 chars
        return description
        
    except Exception as e:
        logging.error(f"Error generating company description: {str(e)}")
        return "Company description unavailable."

def generate_ai_company_description(domain: str) -> str:
    """Generate a company description using GPT when web scraping fails"""
    try:
        prompt = f"""
        Based on the company domain name '{domain}', generate a brief, professional description 
        of what this company likely does. Focus on:
        1. Industry/sector
        2. Likely products/services
        3. Target market
        Keep it factual and avoid speculation. If uncertain, keep it general but professional.
        Maximum 2-3 sentences.
        """
        
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=150
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logging.error(f"Error generating AI company description: {str(e)}")
        return "Company description unavailable."

class PortfolioManager:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
        self.PORTFOLIO_FOLDER_ID = 'your-folder-id'  # Add to config
        self._init_drive_service()

    def _init_drive_service(self):
        credentials = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=self.SCOPES
        )
        self.service = build('drive', 'v3', credentials=credentials)

    def get_relevant_assets(self, context: Dict) -> List[Dict]:
        """Filter and return relevant portfolio items based on context"""
        try:
            # Get all files from portfolio folder
            results = self.service.files().list(
                q=f"'{self.PORTFOLIO_FOLDER_ID}' in parents",
                fields="files(id, name, webViewLink)"
            ).execute()
            files = results.get('files', [])

            # Extract keywords from context
            keywords = self._extract_keywords(context)

            # Filter and categorize relevant files
            relevant_files = []
            for file in files:
                if any(keyword.lower() in file['name'].lower() for keyword in keywords):
                    file_type = self._determine_file_type(file['name'])
                    relevant_files.append({
                        'title': self._format_title(file['name']),
                        'description': self._get_file_description(file['name']),
                        'link': file['webViewLink'],
                        'type': file_type
                    })

            # Limit to 2-3 most relevant items
            return relevant_files[:2]

        except Exception as e:
            logging.error(f"Error fetching portfolio assets: {e}")
            return []

    def _extract_keywords(self, context: Dict) -> List[str]:
        """Extract relevant keywords from context"""
        keywords = []
        if 'company_description' in context:
            keywords.extend(re.findall(r'\b\w+\b', context['company_description'].lower()))
        if 'headline' in context:
            keywords.extend(re.findall(r'\b\w+\b', context['headline'].lower()))
        # Add industry-specific keywords
        keywords.extend(['saas', 'ai', 'analytics', 'cloud', 'devops'])
        return list(set(keywords))

    def _determine_file_type(self, filename: str) -> str:
        """Determine file type from filename"""
        lower_name = filename.lower()
        if any(ext in lower_name for ext in ['.pdf', '.ppt', '.pptx']):
            return 'presentation'
        if any(ext in lower_name for ext in ['.mp4', '.mov', '.avi']):
            return 'video'
        return 'case_study'

    def _format_title(self, filename: str) -> str:
        """Convert filename to presentable title"""
        # Remove extension and replace separators
        title = re.sub(r'\.[^.]+$', '', filename)
        title = re.sub(r'[_-]', ' ', title)
        return title.title()

    def _get_file_description(self, filename: str) -> str:
        """Generate description based on filename"""
        # You could enhance this with a mapping of known files to descriptions
        title = self._format_title(filename)
        return f"Detailed {title} showcasing our expertise in this area"
