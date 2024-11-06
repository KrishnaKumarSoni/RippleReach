from weasyprint import HTML, CSS
from jinja2 import Environment, FileSystemLoader
import os

def generate_beautiful_pdf(content: dict, output_path: str = "proposal.pdf"):
    """Generate a beautifully styled PDF with Inter Tight font"""
    
    # Create Jinja2 environment
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('proposal_template.html')
    
    # Custom CSS with Inter Tight font
    css = CSS(string='''
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap');
        
        :root {
            --primary: #FF5A1F;
            --secondary: #1A1A1A;
            --accent: #FF8C5F;
            --background: #FFFFFF;
            --text: #2D2D2D;
            --success: #34D399;
            --error: #EF4444;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            line-height: 1.6;
            color: var(--text);
            margin: 0;
            padding: 0;
            background: var(--background);
        }
        
        .header {
            padding: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid var(--accent);
        }
        
        .logo {
            height: 40px;
        }
        
        .proposal-badge {
            background: var(--primary);
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-weight: 600;
        }
        
        /* ... more modern CSS styles ... */
    ''')
    
    # Render HTML template
    html_content = template.render(**content)
    
    # Generate PDF
    HTML(string=html_content).write_pdf(
        output_path,
        stylesheets=[css],
        presentational_hints=True
    )
    
    return output_path 