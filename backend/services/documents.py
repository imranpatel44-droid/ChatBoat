"""Document service layer with parallel processing and connection pooling."""
import os
import logging
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from document_manager import DocumentManager

logger = logging.getLogger(__name__)

# Base directory for customer vector stores
VECTOR_STORE_BASE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'customers')

# Thread pool for parallel operations
_executor = None
MAX_WORKERS = 4  # Limit concurrent operations

def _get_executor():
    """Get or create thread pool executor."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    return _executor


def get_customer_vector_store_dir(customer_id: str) -> str:
    """Get the vector store directory for a specific customer."""
    return os.path.join(VECTOR_STORE_BASE_DIR, customer_id, 'vector_store')


def get_customer_data_dir(customer_id: str) -> str:
    """Get the base data directory for a specific customer."""
    return os.path.join(VECTOR_STORE_BASE_DIR, customer_id)


def create_document_manager(customer_id: str, openai_api_key: Optional[str] = None) -> DocumentManager:
    """
    Create a customer-specific DocumentManager instance.
    
    Args:
        customer_id: The customer's unique ID
        openai_api_key: OpenAI API key (defaults to env var)
        
    Returns:
        DocumentManager instance
    """
    if not openai_api_key:
        openai_api_key = os.getenv('OPENAI_API_KEY', '')
        
    vector_store_dir = get_customer_vector_store_dir(customer_id)
    os.makedirs(vector_store_dir, exist_ok=True)
    
    return DocumentManager(
        openai_api_key=openai_api_key,
        vector_store_dir=vector_store_dir,
        customer_id=customer_id
    )


def get_document_context(customer_id: str, query: str, max_length: int = 4000) -> str:
    """
    Get relevant document context for a query.
    
    Args:
        customer_id: The customer's unique ID
        query: The search query
        max_length: Maximum context length
        
    Returns:
        Relevant context string
    """
    try:
        doc_manager = create_document_manager(customer_id)
        return doc_manager.get_relevant_context(query, max_length=max_length)
    except Exception as e:
        logger.error(f"Error getting document context for customer {customer_id}: {e}")
        return ""


def process_drive_link(customer_id: str, drive_link: str) -> Dict[str, Any]:
    """
    Process a Google Drive link for a customer.
    
    Args:
        customer_id: The customer's unique ID
        drive_link: The Google Drive link to process
        
    Returns:
        Result dict with success status and metadata
    """
    try:
        doc_manager = create_document_manager(customer_id)
        return doc_manager.process_drive_link(drive_link, customer_id=customer_id)
    except Exception as e:
        logger.error(f"Error processing drive link for customer {customer_id}: {e}")
        return {"success": False, "error": str(e)}


def process_drive_folder(customer_id: str, folder_link: str, incremental: bool = True) -> Dict[str, Any]:
    """
    Process a Google Drive folder for a customer.
    Uses parallel processing by default for faster operation.
    
    Args:
        customer_id: The customer's unique ID
        folder_link: The Google Drive folder link
        incremental: Whether to do incremental processing
        
    Returns:
        Result dict with success status and file counts
    """
    # Use parallel processing for better performance
    return process_drive_folder_parallel(customer_id, folder_link, incremental, max_workers=4)


def process_drive_folder_parallel(customer_id: str, folder_link: str, incremental: bool = True, max_workers: int = 4) -> Dict[str, Any]:
    """
    Process a Google Drive folder with parallel file processing for speed.
    
    Args:
        customer_id: The customer's unique ID
        folder_link: The Google Drive folder link
        incremental: Whether to do incremental processing
        max_workers: Number of parallel workers
        
    Returns:
        Result dict with success status and file counts
    """
    from utils import extract_folder_id_from_drive_link, list_files_in_drive_folder
    
    try:
        folder_id = extract_folder_id_from_drive_link(folder_link)
        if not folder_id:
            return {"success": False, "error": "Invalid folder link"}
        
        # List files
        files = list_files_in_drive_folder(folder_id)
        if not files:
            return {"success": True, "file_count": 0, "message": "No files found"}
        
        # Get document manager
        doc_manager = create_document_manager(customer_id)
        
        # Get existing file IDs for incremental processing
        existing_ids = set()
        if incremental:
            for doc in doc_manager.vector_store.documents:
                if doc.get('metadata', {}).get('source_id'):
                    existing_ids.add(doc['metadata']['source_id'])
        
        # Filter files to process
        files_to_process = []
        skipped_count = 0
        for file in files:
            file_id = file['id']
            if incremental and file_id in existing_ids:
                skipped_count += 1
            else:
                files_to_process.append(file)
        
        # Process files in parallel
        processed_count = 0
        failed_count = 0
        processed_files = []
        failed_files = []
        
        def process_single_file(file_info):
            """Process a single file."""
            file_id = file_info['id']
            file_name = file_info.get('name', f"file_{file_id}")
            file_link = f"https://drive.google.com/file/d/{file_id}/view"
            
            try:
                result = doc_manager.process_drive_link(file_link, customer_id=customer_id)
                return {'success': result['success'], 'name': file_name, 'error': result.get('error')}
            except Exception as e:
                return {'success': False, 'name': file_name, 'error': str(e)}
        
        # Use thread pool for parallel processing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(process_single_file, f): f for f in files_to_process}
            
            for future in as_completed(future_to_file):
                result = future.result()
                if result['success']:
                    processed_count += 1
                    processed_files.append(result['name'])
                else:
                    failed_count += 1
                    failed_files.append({'name': result['name'], 'error': result.get('error', 'Unknown')})
        
        return {
            "success": True,
            "file_count": len(files),
            "processed_count": processed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "doc_count": len(doc_manager.vector_store.documents),
            "processed_files": processed_files,
            "failed_files": failed_files
        }
        
    except Exception as e:
        logger.error(f"Error in parallel folder processing: {e}")
        return {"success": False, "error": str(e)}


def clear_vector_store(customer_id: str) -> Dict[str, Any]:
    """
    Clear all documents from a customer's vector store.
    
    Args:
        customer_id: The customer's unique ID
        
    Returns:
        Result dict with success status
    """
    try:
        doc_manager = create_document_manager(customer_id)
        return doc_manager.clear_vector_store()
    except Exception as e:
        logger.error(f"Error clearing vector store for customer {customer_id}: {e}")
        return {"success": False, "error": str(e)}


def get_store_stats(customer_id: str) -> Dict[str, Any]:
    """
    Get vector store statistics for a customer.
    
    Args:
        customer_id: The customer's unique ID
        
    Returns:
        Dict with document count and last updated timestamp
    """
    try:
        doc_manager = create_document_manager(customer_id)
        return doc_manager.get_store_stats()
    except Exception as e:
        logger.error(f"Error getting store stats for customer {customer_id}: {e}")
        return {"doc_count": 0, "error": str(e)}


def get_widget_config(customer_id: str) -> Optional[Dict[str, Any]]:
    """
    Get widget configuration for a customer.
    
    Args:
        customer_id: The customer's unique ID
        
    Returns:
        Widget config dict or None if not found
    """
    config_path = os.path.join(get_customer_data_dir(customer_id), 'widget_config.json')
    if not os.path.exists(config_path):
        return None
        
    import json
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading widget config for customer {customer_id}: {e}")
        return None


def save_widget_config(customer_id: str, config: Dict[str, Any]) -> bool:
    """
    Save widget configuration for a customer.
    
    Args:
        customer_id: The customer's unique ID
        config: The configuration dict to save
        
    Returns:
        True if successful, False otherwise
    """
    import json
    config_path = os.path.join(get_customer_data_dir(customer_id), 'widget_config.json')
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving widget config for customer {customer_id}: {e}")
        return False


def verify_widget_access(customer_id: str, widget_api_key: str, requesting_domain: str) -> tuple[bool, Optional[str]]:
    """
    Verify widget API key and domain authorization.
    
    Args:
        customer_id: The customer's unique ID
        widget_api_key: The API key from the request
        requesting_domain: The domain making the request
        
    Returns:
        Tuple of (is_authorized, error_message)
    """
    requesting_clean = (requesting_domain or '').lower().replace('www.', '')
    is_localhost = requesting_clean in [
        'localhost:3000', 'localhost:5000',
        '127.0.0.1:3000', '127.0.0.1:5000',
        'localhost', '127.0.0.1'
    ]

    config = get_widget_config(customer_id)
    if not config:
        # Dev-friendly auto-config: if you're testing on localhost and the customer profile exists,
        # create widget_config.json automatically so the widget can respond.
        # This keeps strict security for real domains.
        if is_localhost:
            try:
                profile_path = os.path.join(get_customer_data_dir(customer_id), 'profile.json')
                if os.path.exists(profile_path):
                    import json
                    with open(profile_path, 'r') as f:
                        profile = json.load(f)

                    website_url = profile.get('website_url') or 'http://localhost:3000'
                    auto_config = {
                        'api_key': widget_api_key,
                        'customer_id': customer_id,
                        'website_url': website_url,
                        'created_at': __import__('time').time(),
                    }
                    save_widget_config(customer_id, auto_config)
                    config = auto_config
            except Exception as e:
                logger.warning(f"Failed to auto-create widget config for {customer_id}: {e}")

        if not config:
            return False, "Widget not configured. Go to Admin Dashboard and click 'Generate Widget API Key'."
        
    stored_api_key = config.get('api_key')
    stored_customer_id = config.get('customer_id')
    registered_website_url = config.get('website_url', '')
    
    # Verify API key and customer ID match
    if stored_api_key != widget_api_key or stored_customer_id != customer_id:
        return False, "Invalid credentials"
    
    # Parse registered domain
    from urllib.parse import urlparse
    registered_parsed = urlparse(registered_website_url)
    registered_domain = (registered_parsed.netloc or '').lower().replace('www.', '')
    
    if registered_domain != requesting_clean and not is_localhost:
        return False, f"Unauthorized domain. This widget is only authorized for {registered_website_url}"
    
    return True, None
