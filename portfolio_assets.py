import os
from pathlib import Path
from typing import List, Dict
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pickle

class PortfolioAssets:
    def __init__(self, folder_id: str = "1Xd7pEbuz2qKwGZcSaS1awxs-RDO3XpDU"):
        self.folder_id = folder_id
        self.service = self._get_drive_service()
        self.assets_cache = {
            'presentations': [],
            'videos': [],
            'landing_pages': [],
            'case_studies': [],
            'other': []
        }
        self._initialize_assets()

    def _get_drive_service(self):
        SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
        credentials = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=SCOPES)
        return build('drive', 'v3', credentials=credentials)

    def _initialize_assets(self):
        """Fetch and categorize all portfolio assets"""
        # Initialize the cache first
        self.assets_cache = {
            'presentations': [],
            'videos': [],
            'landing_pages': [],
            'case_studies': [],
            'other': []
        }
        
        results = self.service.files().list(
            q=f"'{self.folder_id}' in parents",
            fields="files(id, name, mimeType, webViewLink)"
        ).execute()

        for file in results.get('files', []):
            asset = {
                'id': file['id'],
                'name': self._clean_filename(file['name']),
                'url': file['webViewLink'],
                'type': file['mimeType'],
                'project': self._extract_project_name(file['name'])
            }

            if 'presentation' in file['name'].lower() or file['name'].endswith('.pdf'):
                self.assets_cache['presentations'].append(asset)
            elif file['name'].endswith(('.mp4', '.MP4', '.mov')):
                self.assets_cache['videos'].append(asset)
            elif 'landing page' in file['name'].lower():
                self.assets_cache['landing_pages'].append(asset)
            elif 'case study' in file['name'].lower():
                self.assets_cache['case_studies'].append(asset)
            else:
                self.assets_cache['other'].append(asset)

    def _clean_filename(self, filename: str) -> str:
        return os.path.splitext(filename)[0]

    def _extract_project_name(self, filename: str) -> str:
        project = filename.split(' ')[0]
        return project.strip()

    def get_relevant_assets(self, project_type: str, count: int = 3) -> dict:
        """Get relevant assets based on project type"""
        relevant_assets = {
            'presentations': [],
            'videos': [],
            'landing_pages': []
        }

        keywords = project_type.lower().split()
        
        for category in self.assets_cache:
            for asset in self.assets_cache[category]:
                if any(keyword in asset['name'].lower() for keyword in keywords):
                    if category in relevant_assets and len(relevant_assets[category]) < count:
                        relevant_assets[category].append(asset)

        return relevant_assets

    def get_file_content(self, file_id: str) -> bytes:
        # Implement file content retrieval from Google Drive
        # This is a placeholder - implement actual file download logic
        return b""

    def get_preview_image(self, file_id: str) -> bytes:
        # Implement preview image generation/retrieval
        # This is a placeholder - implement actual preview generation logic
        return b""