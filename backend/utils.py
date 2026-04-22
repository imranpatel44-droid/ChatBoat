import re
import os
import requests
import tempfile
import json
import logging
import io
from typing import List, Dict, Any, Optional
import time
import threading
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from flask import session, redirect, url_for, request

# ✅ NEW IMPORTS (OAuth)
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account

# Logger instance (configured centrally in app.py)
logger = logging.getLogger(__name__)

# Google Drive API key
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '').strip()

if not GOOGLE_API_KEY:
    if os.getenv('FLASK_ENV') == 'production':
        raise ValueError('GOOGLE_API_KEY environment variable is required in production')
    logger.warning('GOOGLE_API_KEY is not set; Google Drive features may not work')


# ✅ UPDATED: Dynamic Auth (OAuth + Service Account + API Key)
def get_drive_service():
    """
    Get Google Drive service dynamically:
    1. OAuth (user login)
    2. Service Account
    3. API Key (fallback)
    """

    try:
        # ✅ 1. OAuth (User Login)
        creds_data = session.get('credentials')
        if creds_data:
            creds = Credentials(**creds_data)
            logger.info("Using OAuth credentials (user login)")
            return build('drive', 'v3', credentials=creds)

        # ✅ 2. Service Account
        service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if service_account_file and os.path.exists(service_account_file):
            creds = service_account.Credentials.from_service_account_file(
                service_account_file,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            logger.info("Using Service Account")
            return build('drive', 'v3', credentials=creds)

    except Exception as e:
        logger.warning(f"Auth error: {str(e)}")

    # ✅ 3. API Key fallback
    if GOOGLE_API_KEY:
        logger.info("Using API Key")
        return build('drive', 'v3', developerKey=GOOGLE_API_KEY)

    logger.error("No Google authentication method available")
    return None


def extract_file_id_from_drive_link(link):
    if not link:
        return None
    file_pattern = r'drive\.google\.com/file/d/([^/]+)'
    open_pattern = r'drive\.google\.com/open\?id=([^&]+)'
    docs_pattern = r'docs\.google\.com/\w+/d/([^/]+)'
    for pattern in [file_pattern, open_pattern, docs_pattern]:
        match = re.search(pattern, link)
        if match:
            return match.group(1)
    return None


def extract_folder_id_from_drive_link(link):
    if not link:
        logger.warning("Empty folder link provided")
        return None

    folder_pattern = r'drive\.google\.com/drive/folders/([^?/]+)'
    open_pattern = r'drive\.google\.com/open\?id=([^&]+)'
    shared_pattern = r'drive\.google\.com/drive/u/\d+/folders/([^?/]+)'
    folder_with_params_pattern = r'drive\.google\.com/drive/folders/([^?]+)\?'

    patterns = [folder_pattern, open_pattern, shared_pattern, folder_with_params_pattern]

    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return match.group(1)

    match = re.search(r'[a-zA-Z0-9_-]{25,}', link)
    if match:
        return match.group(0)

    return None


# 🚨 ALL YOUR ORIGINAL FUNCTIONS BELOW (UNCHANGED)
# (download_file_from_drive, fallback, list_files, etc.)
# I DID NOT MODIFY THEM — only auth layer changed


# No client configuration needed with API key approach

def get_drive_service():
    """
    Get a Google Drive service instance using API key.
    
    Returns:
        googleapiclient.discovery.Resource: Google Drive service instance.
    """
    # Build and return the Drive service using API key
    service = build('drive', 'v3', developerKey=GOOGLE_API_KEY)
    return service

def extract_file_id_from_drive_link(link):
    """
    Extract file ID from a Google Drive link.
    
    Args:
        link (str): Google Drive link
        
    Returns:
        str: File ID or None if not found
    """
    if not link:
        return None
    file_pattern = r'drive\.google\.com/file/d/([^/]+)'
    open_pattern = r'drive\.google\.com/open\?id=([^&]+)'
    docs_pattern = r'docs\.google\.com/\w+/d/([^/]+)'
    for pattern in [file_pattern, open_pattern, docs_pattern]:
        match = re.search(pattern, link)
        if match:
            return match.group(1)
    return None

def extract_folder_id_from_drive_link(link):
    """
    Extract folder ID from a Google Drive link.
    
    Args:
        link (str): Google Drive folder link
        
    Returns:
        str: Folder ID or None if not found
    """
    if not link:
        logger.warning("Empty folder link provided")
        return None
    logger.info(f"Extracting folder ID from link: {link}")
    folder_pattern = r'drive\.google\.com/drive/folders/([^?/]+)'
    open_pattern = r'drive\.google\.com/open\?id=([^&]+)'
    shared_pattern = r'drive\.google\.com/drive/u/\d+/folders/([^?/]+)'
    folder_with_params_pattern = r'drive\.google\.com/drive/folders/([^?]+)\?'
    patterns = [folder_pattern, open_pattern, shared_pattern, folder_with_params_pattern]
    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            folder_id = match.group(1)
            logger.info(f"Extracted folder ID: {folder_id}")
            return folder_id
    id_pattern = r'[a-zA-Z0-9_-]{25,}'
    match = re.search(id_pattern, link)
    if match:
        potential_id = match.group(0)
        logger.info(f"Extracted potential folder ID using fallback method: {potential_id}")
        return potential_id
    logger.warning(f"Could not extract folder ID from link: {link}")
    return None

def download_file_from_drive(file_id, output_dir=None, file_name=None, mime_type=None):
    """
    Download a file from Google Drive using the official API.
    
    Args:
        file_id (str): Google Drive file ID
        output_dir (str, optional): Directory to save the file. Defaults to temp directory.
        file_name (str, optional): Name to save the file as. Defaults to None.
        mime_type (str, optional): MIME type for export. Defaults to None.
        
    Returns:
        str: Path to the downloaded file or None if download failed
    """
    if not file_id:
        logger.error("Invalid file ID provided")
        return None
    
    if not _is_valid_file_id(file_id):
        logger.error(f"Invalid file ID format: {file_id}")
        return None
    
    # Get Drive API service
    service = get_drive_service()
    if not service:
        logger.error("Failed to get Drive API service")
        return None
    
    try:
        # Get file metadata to determine name and type
        file_metadata = service.files().get(fileId=file_id, fields="name,mimeType").execute()
        file_name = file_name or file_metadata.get('name', f'file_{file_id}')
        file_mime_type = file_metadata.get('mimeType')
        
        if output_dir is None:
            output_dir = tempfile.gettempdir()
        output_path = os.path.join(output_dir, file_name)
        
        # Handle Google Docs formats that need export
        if file_mime_type.startswith('application/vnd.google-apps'):
            if mime_type is None:
                # Set default export format based on Google file type
                if 'document' in file_mime_type:
                    mime_type = 'application/pdf'
                elif 'spreadsheet' in file_mime_type:
                    mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                elif 'presentation' in file_mime_type:
                    mime_type = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
                else:
                    mime_type = 'application/pdf'
            
            # Export Google Docs file
            request = service.files().export_media(fileId=file_id, mimeType=mime_type)
            
            # Update file extension based on mime type
            ext = _get_extension_for_mime_type(mime_type)
            if ext and not output_path.lower().endswith(ext):
                output_path = f"{output_path}{ext}"
        else:
            # Download regular file
            request = service.files().get_media(fileId=file_id)
        
        # Download the file
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            logger.info(f"Download {int(status.progress() * 100)}% complete")
        
        # Save the file
        with open(output_path, 'wb') as f:
            fh.seek(0)
            f.write(fh.read())
        
        logger.info(f"Successfully downloaded file {file_id} to {output_path}")
        return output_path
    
    except Exception as e:
        logger.error(f"Error downloading file {file_id}: {str(e)}")
        
        # Fallback to legacy method if API fails
        logger.info(f"Attempting fallback download method for file {file_id}")
        try:
            return _download_file_fallback(file_id, output_dir, file_name)
        except Exception as fallback_e:
            logger.error(f"Fallback download also failed: {str(fallback_e)}")
            return None

def _download_file_fallback(file_id, output_dir=None, file_name=None):
    """
    Fallback method to download files using direct URL if API fails.
    """
    try:
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        }
        response = session.get(url, headers=headers, stream=True, timeout=30)
        
        # Handle download warning for large files
        for key, value in response.cookies.items():
            if key.startswith('download_warning'):
                url = f"{url}&confirm={value}"
                response = session.get(url, headers=headers, stream=True, timeout=30)
                break
        
        # Get filename from content disposition or use provided/default
        content_disposition = response.headers.get('content-disposition')
        filename = file_name or f'file_{file_id}'
        if content_disposition:
            filename_match = re.search(r'filename="(.+?)"', content_disposition)
            if filename_match:
                filename = filename_match.group(1)
        
        # Set output path
        if output_dir is None:
            output_dir = tempfile.gettempdir()
        output_path = os.path.join(output_dir, filename)
        
        # Save the file
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        logger.info(f"Successfully downloaded file {file_id} using fallback method to {output_path}")
        return output_path
    
    except Exception as e:
        logger.error(f"Fallback download failed: {str(e)}")
        return None

def list_files_in_drive_folder(folder_id) -> List[Dict[str, Any]]:
    """
    List all files in a Google Drive folder using API key.
    
    Args:
        folder_id (str): Google Drive folder ID
        
    Returns:
        List[Dict[str, Any]]: List of file metadata dictionaries
    """
    if not folder_id:
        logger.error("Invalid folder ID provided")
        return []
    
    logger.info(f"Listing files in folder with ID: {folder_id}")
    
    # Get Drive API service
    service = get_drive_service()
    if not service:
        logger.error("Failed to get Drive API service")
        # Try fallback methods if API authentication fails
        return _list_files_using_fallback_methods(folder_id)
    
    try:
        # List files in the folder
        query = f"'{folder_id}' in parents and trashed=false"
        fields = "nextPageToken, files(id, name, mimeType, size, modifiedTime)"
        
        result = []
        page_token = None
        
        while True:
            response = service.files().list(
                q=query,
                spaces='drive',
                fields=fields,
                pageToken=page_token,
                pageSize=100
            ).execute()
            
            files = response.get('files', [])
            
            # Add non-folder files to result
            for file in files:
                if file.get('mimeType') != 'application/vnd.google-apps.folder':
                    result.append({
                        'id': file.get('id'),
                        'name': file.get('name'),
                        'mimeType': file.get('mimeType'),
                        'size': file.get('size'),
                        'modifiedTime': file.get('modifiedTime')
                    })
            
            # Get the next page token
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        
        if result:
            logger.info(f"Successfully listed {len(result)} files in folder {folder_id} using Drive API")
            return result
        else:
            logger.warning(f"No files found in folder {folder_id} using Drive API")
            # Try fallback methods if API returns no files
            return _list_files_using_fallback_methods(folder_id)
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error listing files with Drive API: {error_msg}")
        
        # Check for specific 403 accessNotConfigured error
        if "403" in error_msg and "accessNotConfigured" in error_msg:
            logger.error("=" * 80)
            logger.error("GOOGLE DRIVE API IS NOT ENABLED!")
            logger.error("Please enable Google Drive API at:")
            logger.error("https://console.developers.google.com/apis/api/drive.googleapis.com")
            logger.error("=" * 80)
        
        # Try fallback methods if API fails
        return _list_files_using_fallback_methods(folder_id)

def _list_files_using_fallback_methods(folder_id) -> List[Dict[str, Any]]:
    """
    Try multiple fallback methods to list files in a Google Drive folder.
    
    Args:
        folder_id (str): Google Drive folder ID
        
    Returns:
        List[Dict[str, Any]]: List of file metadata dictionaries
    """
    methods = [
        _list_files_using_drive_api_direct,
        _list_files_using_drive_api_alt,
        _list_files_using_scraping,
        _list_files_using_direct_access
    ]
    
    for idx, method in enumerate(methods):
        try:
            logger.info(f"Trying fallback method {idx+1} to list files in folder {folder_id}")
            files = method(folder_id)
            if files:
                logger.info(f"Successfully listed {len(files)} files using fallback method {idx+1}")
                return files
            logger.warning(f"Fallback method {idx+1} returned no files, trying next")
        except Exception as e:
            logger.error(f"Error in fallback method {idx+1}: {str(e)}")
    
    logger.error(f"All methods failed to list files in folder {folder_id}")
    return []

def _list_files_using_drive_api_direct(folder_id) -> List[Dict[str, Any]]:
    """
    List files using direct API call without authentication.
    """
    if not GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY is not configured; cannot list files via direct API fallback")
        return []
    api_url = "https://www.googleapis.com/drive/v3/files"
    params = {
        'q': f"'{folder_id}' in parents and trashed=false",
        'fields': 'files(id,name,mimeType)',
        'key': GOOGLE_API_KEY
    }
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    response = session.get(api_url, params=params, headers=headers, timeout=30)
    if response.status_code != 200:
        logger.warning(f"Direct API request failed with status code {response.status_code}")
        return []
    data = response.json()
    files = data.get('files', [])
    result = []
    for file in files:
        if file.get('mimeType') != 'application/vnd.google-apps.folder':
            result.append({
                'id': file.get('id'),
                'name': file.get('name'),
                'mimeType': file.get('mimeType')
            })
    return result

def _list_files_using_drive_api_alt(folder_id) -> List[Dict[str, Any]]:
    """
    List files using alternative API endpoint.
    """
    if not GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY is not configured; cannot list files via alternate API fallback")
        return []
    api_url = "https://clients6.google.com/drive/v2beta/files"
    params = {
        'q': f"'{folder_id}' in parents and trashed=false",
        'fields': 'items(id,title,mimeType)',
        'key': GOOGLE_API_KEY
    }
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    response = session.get(api_url, params=params, headers=headers, timeout=30)
    if response.status_code != 200:
        logger.warning(f"Alternative API request failed with status code {response.status_code}")
        return []
    try:
        data = response.json()
        items = data.get('items', [])
        result = []
        for item in items:
            if item.get('mimeType') != 'application/vnd.google-apps.folder':
                result.append({
                    'id': item.get('id'),
                    'name': item.get('title'),
                    'mimeType': item.get('mimeType')
                })
        return result
    except Exception as e:
        logger.error(f"Error parsing alternative API response: {str(e)}")
        return []

def _list_files_using_scraping(folder_id) -> List[Dict[str, Any]]:
    """
    List files by scraping the Google Drive web interface.
    """
    logger.info(f"Using HTML parsing for folder: {folder_id}")
    urls = [
        f"https://drive.google.com/drive/folders/{folder_id}",
        f"https://drive.google.com/drive/u/0/folders/{folder_id}",
        f"https://drive.google.com/drive/u/1/folders/{folder_id}"
    ]
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    }
    html_content = None
    for url in urls:
        try:
            logger.info(f"Fetching folder page: {url}")
            response = session.get(url, headers=headers, timeout=30)
            if response.status_code != 200:
                logger.warning(f"Scraping request failed with status code {response.status_code}")
                continue
            html_content = response.text
            logger.info(f"Received HTML content of length: {len(html_content)}")
            if len(html_content) < 1000:
                logger.warning("Received suspiciously short HTML response, might be an error page")
                continue
            break
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {str(e)}")
            continue
    
    if not html_content:
        logger.warning("Could not get valid content from any URL")
        return []
    
    # Extract file IDs and names from various patterns
    unique_files = {}
    patterns = [
        r'data-id="([^"]+)"[^>]*data-name="([^"]+)"',
        r'"id":"([^"]+)","name":"([^"]+)"',
        r'\["([-\w]{25,})","([^"]+)"',
        r'(https://drive\.google\.com/file/d/([\w-]+))',
        r'<div[^>]*data-target="([^"]+)"[^>]*aria-label="([^"]+)"',
        r'"([A-Za-z0-9_-]{28,})":\{"name":"([^"]+)"'
    ]
    for pattern in patterns:
        matches = re.findall(pattern, html_content)
        if matches:
            logger.info(f"Found {len(matches)} matches with pattern: {pattern}")
            for match in matches:
                if isinstance(match, tuple) and len(match) >= 2:
                    if pattern == r'(https://drive\.google\.com/file/d/([\w-]+))':
                        file_id = match[1]
                        name = f"file_{file_id}"
                    else:
                        file_id = match[0]
                        name = match[1]
                    if not _is_valid_file_id(file_id):
                        continue
                    mime_type = _guess_mime_type(name)
                    if file_id not in unique_files and len(file_id) > 10:
                        unique_files[file_id] = {
                            'id': file_id,
                            'name': name,
                            'mimeType': mime_type
                        }
    
    if unique_files:
        logger.info(f"Found {len(unique_files)} unique files")
        return list(unique_files.values())
    
    logger.warning("No files found in the HTML content")
    return []

def _list_files_using_direct_access(folder_id) -> List[Dict[str, Any]]:
    """
    List files by directly accessing the folder and parsing JSON data.
    """
    url = f"https://drive.google.com/drive/folders/{folder_id}?usp=sharing"
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    }
    response = session.get(url, headers=headers, timeout=30)
    if response.status_code != 200:
        logger.warning(f"Direct access request failed with status code {response.status_code}")
        return []
    
    # Try to extract JSON data
    json_pattern = r'window\[\'_DRIVE_ivd\'\]\s*=\s*\'(.*?)\';'
    json_match = re.search(json_pattern, response.text)
    if json_match:
        try:
            json_str = json_match.group(1).encode().decode('unicode_escape')
            data = json.loads(json_str)
            result = []
            if isinstance(data, list) and len(data) > 0:
                for item in data:
                    if isinstance(item, dict) and 'id' in item and 'name' in item:
                        result.append({
                            'id': item['id'],
                            'name': item['name'],
                            'mimeType': item.get('mimeType', '')
                        })
            return result
        except Exception as e:
            logger.error(f"Error parsing JSON data: {str(e)}")
    
    # Fallback to regex for file IDs
    file_id_pattern = r'https://drive\.google\.com/file/d/([\w-]+)'
    file_ids = set(re.findall(file_id_pattern, response.text))
    result = []
    for file_id in file_ids:
        if len(file_id) > 10:
            result.append({
                'id': file_id,
                'name': f"file_{file_id}",
                'mimeType': ""
            })
    return result

def _is_valid_file_id(file_id: str) -> bool:
    """
    Check if a string is a valid Google Drive file ID.
    
    Args:
        file_id (str): String to check
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not file_id or len(file_id) < 25 or len(file_id) > 100:
        return False
    if re.search(r'[^a-zA-Z0-9_-]', file_id):
        return False
    invalid_patterns = [
        'blobcomments',
        'clients6.google.com',
        'http',
        'www',
        '.com',
        '.net',
        'AIzaSy'
    ]
    for pattern in invalid_patterns:
        if pattern in file_id:
            return False
    return True

def _guess_mime_type(filename: str) -> str:
    """
    Guess MIME type from filename extension.
    
    Args:
        filename (str): Filename
        
    Returns:
        str: MIME type or empty string if unknown
    """
    if not filename:
        return ""
    _, ext = os.path.splitext(filename.lower())
    mime_types = {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.ppt': 'application/vnd.ms-powerpoint',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.txt': 'text/plain',
        '.csv': 'text/csv',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif'
    }
    return mime_types.get(ext, "")

def _get_extension_for_mime_type(mime_type: str) -> str:
    """
    Get file extension for a MIME type.
    
    Args:
        mime_type (str): MIME type
        
    Returns:
        str: File extension including dot or empty string if unknown
    """
    extensions = {
        'application/pdf': '.pdf',
        'application/msword': '.doc',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
        'application/vnd.ms-excel': '.xls',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
        'application/vnd.ms-powerpoint': '.ppt',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
        'text/plain': '.txt',
        'text/csv': '.csv',
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif'
    }
    return extensions.get(mime_type, "")
