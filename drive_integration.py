from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os.path
import pickle
import re

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class DriveAssets:
    def __init__(self, assets_folder_id: str):
        self.folder_id = assets_folder_id
        self.service = self._get_drive_service()
        self.assets_cache = {}

    def _get_drive_service(self):
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
                
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        return build('drive', 'v3', credentials=creds)

    def get_assets_list(self):
        """Get all assets from the specified folder"""
        results = self.service.files().list(
            q=f"'{self.folder_id}' in parents",
            fields="files(id, name, webViewLink, mimeType)"
        ).execute()
        
        assets = {}
        for file in results.get('files', []):
            category = file['name'].split('_')[0].lower()
            if category not in assets:
                assets[category] = []
            assets[category].append({
                'id': file['id'],
                'name': file['name'],
                'url': file['webViewLink'],
                'type': file['mimeType']
            })
        
        self.assets_cache = assets
        return assets

    def get_asset_by_category(self, category: str):
        """Get assets for a specific category"""
        if not self.assets_cache:
            self.get_assets_list()
        return self.assets_cache.get(category, []) 

class PortfolioAssets:
    def __init__(self, folder_id: str = "1Xd7pEbuz2qKwGZcSaS1awxs-RDO3XpDU"):
        self.folder_id = folder_id
        self.service = self._get_drive_service()
        self.assets_cache = {}
        self._initialize_assets()

    def _get_drive_service(self):
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', ['https://www.googleapis.com/auth/drive.readonly'])
                creds = flow.run_local_server(port=0)
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        return build('drive', 'v3', credentials=creds)

    def _initialize_assets(self):
        """Fetch and categorize all portfolio assets"""
        results = self.service.files().list(
            q=f"'{self.folder_id}' in parents",
            fields="files(id, name, mimeType, webViewLink)"
        ).execute()

        self.assets_cache = {
            'presentations': [],
            'videos': [],
            'landing_pages': [],
            'case_studies': [],
            'other': []
        }

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
        """Remove file extension and clean up filename"""
        return os.path.splitext(filename)[0]

    def _extract_project_name(self, filename: str) -> str:
        """Extract project name from filename"""
        project = filename.split(' ')[0]  # Take first word as project name
        return project.strip()

    def get_relevant_assets(self, project_type: str, count: int = 3) -> dict:
        """Get relevant assets based on project type"""
        relevant_assets = {
            'presentations': [],
            'videos': [],
            'landing_pages': []
        }

        # Match project type with relevant assets
        keywords = project_type.lower().split()
        
        for category in self.assets_cache:
            for asset in self.assets_cache[category]:
                if any(keyword in asset['name'].lower() for keyword in keywords):
                    if len(relevant_assets[category]) < count:
                        relevant_assets[category].append(asset)

        return relevant_assets

    def get_embed_html(self, asset: dict) -> str:
        """Generate appropriate embed HTML based on asset type"""
        if asset['type'] == 'video/mp4':
            return f'<video controls width="100%"><source src="{asset["url"]}" type="video/mp4"></video>'
        elif asset['type'] == 'application/pdf':
            return f'<iframe src="{asset["url"]}?embedded=true" width="100%" height="600px"></iframe>'
        else:
            return f'<a href="{asset["url"]}" target="_blank">View {asset["name"]}</a>'