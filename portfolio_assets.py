import os
from pathlib import Path
from typing import List, Dict
from google.oauth2 import service_account
from googleapiclient.discovery import build
import logging

class PortfolioAssets:
    def __init__(self, folder_id: str = "1Xd7pEbuz2qKwGZcSaS1awxs-RDO3XpDU"):
        """Initialize portfolio assets manager with Google Drive folder ID"""
        self.folder_id = folder_id
        self.service = self._get_drive_service()
        self._assets = []
        self._initialize_assets()
        
        # Log portfolio initialization
        if self._assets:
            logging.info(f"Successfully loaded {len(self._assets)} portfolio assets")
        else:
            logging.error("Failed to load portfolio assets")

    def _get_drive_service(self):
        """Initialize Google Drive service"""
        try:
            SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
            credentials = service_account.Credentials.from_service_account_file(
                'service_account.json', 
                scopes=SCOPES
            )
            return build('drive', 'v3', credentials=credentials)
        except Exception as e:
            logging.error(f"Failed to initialize Drive service: {e}")
            raise

    def _initialize_assets(self) -> None:
        """Fetch all portfolio assets from Drive folder"""
        try:
            results = self.service.files().list(
                q=f"'{self.folder_id}' in parents",
                fields="files(id, name, description, webViewLink, mimeType)"
            ).execute()

            self._assets = [{
                'id': file['id'],
                'name': self._clean_filename(file['name']),
                'description': file.get('description', ''),
                'url': file['webViewLink'],
                'type': self._get_asset_type(file['mimeType'], file['name']),
                'industry': self._extract_industry_tag(file.get('description', '')),
                'service_type': self._extract_service_tag(file.get('description', ''))
            } for file in results.get('files', [])]

            logging.info(f"Loaded {len(self._assets)} portfolio assets")
        except Exception as e:
            logging.error(f"Failed to initialize assets: {e}")
            self._assets = []

    def _clean_filename(self, filename: str) -> str:
        """Remove extension and clean up filename"""
        return os.path.splitext(filename)[0].strip()

    def _get_asset_type(self, mime_type: str, filename: str) -> str:
        """Determine asset type based on mime type and filename"""
        filename_lower = filename.lower()
        if 'presentation' in mime_type or filename_lower.endswith('.pdf'):
            return 'case_study'
        elif 'video' in mime_type or filename_lower.endswith(('.mp4', '.mov')):
            return 'video'
        elif 'landing' in filename_lower:
            return 'landing_page'
        return 'other'

    def _extract_industry_tag(self, description: str) -> str:
        """Extract industry tag from file description"""
        try:
            if not description:
                return ''
            # Assuming description format: "Industry: X, Service: Y"
            industry = description.split(',')[0].split(':')[1].strip()
            return industry.lower()
        except:
            return ''

    def _extract_service_tag(self, description: str) -> str:
        """Extract service type tag from file description"""
        try:
            if not description:
                return ''
            # Assuming description format: "Industry: X, Service: Y"
            service = description.split(',')[1].split(':')[1].strip()
            return service.lower()
        except:
            return ''

    def get_all_assets(self) -> List[Dict]:
        """Get all portfolio assets"""
        return self._assets

    def get_relevant_assets(self, industry: str = None, service: str = None, limit: int = 2) -> List[Dict]:
        """Get relevant assets based on industry and service type"""
        if not self._assets:
            return []

        # Score and sort assets based on relevance
        scored_assets = []
        for asset in self._assets:
            score = 0
            if industry and industry.lower() in asset['industry']:
                score += 2
            if service and service.lower() in asset['service_type']:
                score += 2
            if score > 0:
                scored_assets.append((score, asset))

        # Sort by score and return top N assets
        return [
            asset for _, asset in sorted(scored_assets, key=lambda x: x[0], reverse=True)
        ][:limit]

    def get_asset_by_name(self, name: str):
        """Get specific asset by name"""
        return next(
            (asset for asset in self._assets if asset['name'].lower() == name.lower()),
            None
        )

    def format_for_email_template(self, selected_assets: List[Dict]) -> Dict:
        """Format portfolio assets for email template"""
        if not selected_assets:
            return {"has_portfolio": False}
            
        formatted_assets = []
        for asset in selected_assets:
            formatted_assets.append({
                "title": asset['name'],
                "description": asset.get('description', ''),
                "url": asset['url'],
                "type": asset['type'],
                "industry": asset.get('industry', ''),
                "service": asset.get('service_type', '')
            })
            
        return {
            "has_portfolio": True,
            "assets": formatted_assets
        }