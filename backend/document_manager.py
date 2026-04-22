"""Document Manager with parallel processing and batch operations."""
import os
import tempfile
import time
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils import extract_file_id_from_drive_link, download_file_from_drive, extract_folder_id_from_drive_link, list_files_in_drive_folder
from document_processor import DocumentProcessor
from embeddings_generator import EmbeddingsGenerator
from vector_store import VectorStore

# Thread pool for parallel operations
_executor = None
MAX_WORKERS = 4

def _get_executor():
    """Get or create thread pool executor."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    return _executor

class DocumentManager:
    """
    A class to manage the entire document processing pipeline:
    1. Download documents from Google Drive
    2. Extract text from documents
    3. Generate embeddings
    4. Store embeddings in vector store
    5. Query the vector store
    """
    
    def __init__(self, openai_api_key: str, vector_store_dir: str, customer_id: str):
        """
        Initialize the document manager.
        
        Args:
            openai_api_key (str): OpenAI API key for generating embeddings.
            vector_store_dir (str): Directory to store vector data.
            customer_id (str): Customer ID for customer-specific storage (required).
        """
        if not customer_id:
            raise ValueError("customer_id is required for document management")
            
        self.openai_api_key = openai_api_key
        self.embeddings_generator = EmbeddingsGenerator(api_key=openai_api_key)
        self.customer_id = customer_id
        
        # Ensure we're using a customer-specific directory
        # The vector_store_dir should already include the customer_id path
        self.vector_store_dir = vector_store_dir
        
        # Create directory if it doesn't exist
        os.makedirs(self.vector_store_dir, exist_ok=True)
            
        # Only create the directory when actually storing data, not on initialization
        self.vector_store = VectorStore(storage_dir=self.vector_store_dir, customer_id=customer_id)
    
    def process_drive_link(self, drive_link: str, customer_id: str = None) -> Dict[str, Any]:
        """
        Process a Google Drive link: download, extract text, generate embeddings, and store.
        
        Args:
            drive_link (str): Google Drive link to the document.
            customer_id (str, optional): Customer ID for customer-specific processing.
            
        Returns:
            Dict[str, Any]: Information about the processed document.
        """
        # Use provided customer_id or fall back to the one set during initialization
        current_customer_id = customer_id or self.customer_id
        
        # Extract file ID from the link
        file_id = extract_file_id_from_drive_link(drive_link)
        if not file_id:
            return {"success": False, "error": "Invalid Google Drive link"}
        
        try:
            # Create a temporary directory for the download
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download the file using API key
                download_path = download_file_from_drive(file_id, temp_dir)
                if not download_path:
                    return {"success": False, "error": "Failed to download file"}
                
                # Get filename for metadata
                filename = os.path.basename(download_path)
                
                # Extract text from the document with optimized PDF handling
                document_text = DocumentProcessor.process_document(download_path)
                if not document_text:
                    return {"success": False, "error": f"Failed to extract text from {filename}"}
                
                # Generate embedding for the document
                embedding = self.embeddings_generator.generate_embedding(document_text)
                
                # Store in vector store
                metadata = {
                    "filename": filename,
                    "source": "google_drive",
                    "drive_link": drive_link,
                    "file_id": file_id,
                    "source_id": file_id,  # Add source_id for tracking in incremental updates
                    "file_type": os.path.splitext(filename)[1].lower(),
                    "customer_id": current_customer_id  # Add customer_id to metadata
                }
                
                doc_id = self.vector_store.add_document(
                    document_text=document_text,
                    embedding=embedding,
                    metadata=metadata,
                    customer_id=current_customer_id  # Pass customer_id to vector store
                )
                
                return {
                    "success": True,
                    "doc_id": doc_id,
                    "filename": filename,
                    "text_length": len(document_text),
                    "file_type": os.path.splitext(filename)[1].lower()
                }
                
        except Exception as e:
            return {"success": False, "error": f"Error processing {os.path.basename(drive_link)}: {str(e)}"}
    
    def query_documents(self, query: str, top_k: int = 3, customer_id: str = None) -> List[Dict[str, Any]]:
        """
        Query the vector store for documents relevant to the query.
        
        Args:
            query (str): The query text.
            top_k (int, optional): Number of top results to return.
            customer_id (str, optional): Filter results by customer ID.
            
        Returns:
            List[Dict[str, Any]]: Relevant documents with similarity scores.
        """
        # Use provided customer_id or fall back to the one set during initialization
        current_customer_id = customer_id or self.customer_id
        
        # Generate embedding for the query
        query_embedding = self.embeddings_generator.generate_embedding(query)
        
        # Search the vector store with customer filtering
        results = self.vector_store.search(query_embedding, top_k=top_k, customer_id=current_customer_id)
        
        return results
    
    def get_relevant_context(self, query: str, max_length: int = 4000) -> str:
        """
        Get relevant context from documents for a given query.
        
        Args:
            query (str): The query text.
            max_length (int, optional): Maximum length of the returned context.
            
        Returns:
            str: Relevant context from documents.
        """
        # Get relevant documents
        results = self.query_documents(query)
        
        if not results:
            return ""
        
        # Combine relevant document texts
        context = ""
        for result in results:
            # Add document text with metadata
            doc_text = f"Document: {result['metadata'].get('filename', 'Unknown')}\n\n"
            doc_text += result['text'][:1000] + "...\n\n"  # Truncate long documents
            
            # Check if adding this document would exceed max length
            if len(context) + len(doc_text) > max_length:
                # Truncate if necessary
                remaining = max_length - len(context)
                if remaining > 0:
                    context += doc_text[:remaining]
                break
            
            context += doc_text
        
        return context
        
    def get_completion(self, prompt: str) -> str:
        """
        Get completion from OpenAI API.
        
        Args:
            prompt (str): The prompt to send to OpenAI.
            
        Returns:
            str: The completion text.
        """
        try:
            from services.llm import _get_openai_client
            client = _get_openai_client()
            response = client.chat.completions.create(
                model="gpt-5-nano-2025-08-07",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that provides information based on document context. Please provide concise and clear responses that convey the essential information in as few words as possible. Aim for brevity without sacrificing clarity or meaning."
                    },
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error getting completion: {str(e)}")
            return f"I'm sorry, I couldn't process that request. Error: {str(e)}"
            
    def get_store_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the vector store.
        
        Returns:
            Dict[str, Any]: Statistics about the vector store.
        """
        doc_count = len(self.vector_store.documents) if hasattr(self.vector_store, 'documents') else 0
        last_updated = time.time()
        
        return {
            'doc_count': doc_count,
            'last_updated': last_updated
        }
        
    def process_drive_folder_parallel(self, folder_link: str, incremental: bool = False, 
                                        customer_id: str = None, max_workers: int = 4) -> Dict[str, Any]:
        """
        Process all files in a Google Drive folder with parallel processing.
        
        Args:
            folder_link (str): Google Drive folder link.
            incremental (bool, optional): If True, only process new files.
            customer_id (str, optional): Customer ID for customer-specific processing.
            max_workers (int, optional): Number of parallel workers. Defaults to 4.
            
        Returns:
            Dict[str, Any]: Information about the processed files.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        current_customer_id = customer_id or self.customer_id
        folder_id = extract_folder_id_from_drive_link(folder_link)
        
        if not folder_id:
            return {"success": False, "error": "Invalid Google Drive folder link"}
        
        try:
            # List files
            files = list_files_in_drive_folder(folder_id)
            if not files:
                return {"success": True, "file_count": 0, "message": "No compatible files"}
            
            # Get existing file IDs for incremental
            existing_ids = set()
            if incremental:
                for doc in self.vector_store.documents:
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
            results = {'processed': 0, 'failed': 0, 'processed_files': [], 'failed_files': []}
            
            def process_file(file_info):
                file_id = file_info['id']
                file_name = file_info.get('name', f"file_{file_id}")
                file_link = f"https://drive.google.com/file/d/{file_id}/view"
                try:
                    result = self.process_drive_link(file_link, current_customer_id)
                    return {'success': result['success'], 'name': file_name, 'error': result.get('error')}
                except Exception as e:
                    return {'success': False, 'name': file_name, 'error': str(e)}
            
            # Use thread pool
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_file = {executor.submit(process_file, f): f for f in files_to_process}
                for future in as_completed(future_to_file):
                    result = future.result()
                    if result['success']:
                        results['processed'] += 1
                        results['processed_files'].append(result['name'])
                    else:
                        results['failed'] += 1
                        results['failed_files'].append({'name': result['name'], 'error': result.get('error')})
            
            return {
                "success": True,
                "file_count": len(files),
                "processed_count": results['processed'],
                "failed_count": results['failed'],
                "skipped_count": skipped_count,
                "doc_count": len(self.vector_store.documents),
                "processed_files": results['processed_files'],
                "failed_files": results['failed_files']
            }
            
        except Exception as e:
            logger.exception(f"Error in parallel folder processing: {e}")
            return {"success": False, "error": str(e)}
    
    def process_drive_folder(self, folder_link: str, incremental: bool = False, customer_id: str = None) -> Dict[str, Any]:
        """
        Process all files in a Google Drive folder.
        Uses parallel processing for better performance.
        
        Args:
            folder_link (str): Google Drive folder link.
            incremental (bool, optional): If True, only process new files.
            customer_id (str, optional): Customer ID for customer-specific processing.
            
        Returns:
            Dict[str, Any]: Information about the processed files.
        """
        # Use parallel processing by default for speed
        return self.process_drive_folder_parallel(folder_link, incremental, customer_id, max_workers=4)
    
    def clear_vector_store(self) -> Dict[str, Any]:
        """
        Clear all documents and embeddings from the vector store.
        
        Returns:
            Dict[str, Any]: Result of the operation.
        """
        try:
            success = self.vector_store.clear()
            return {
                "success": success,
                "timestamp": time.time()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
        
    def get_store_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the vector store.
        
        Returns:
            Dict[str, Any]: Statistics about the vector store.
        """
        return {
            "doc_count": len(self.vector_store.documents),
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        }