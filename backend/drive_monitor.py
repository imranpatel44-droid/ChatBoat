import time
import logging
from typing import Dict, List, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler

class DriveMonitor:
    """
    A class to monitor Google Drive folders for new files and automatically process them.
    """
    
    def __init__(self, document_manager=None, check_interval=300):
        """
        Initialize the drive monitor.
        
        Args:
            document_manager: The document manager instance to use for processing files (can be None).
            check_interval (int): How often to check for updates (in seconds).
        """
        self.document_manager = document_manager
        self.check_interval = check_interval
        self.monitored_folders = {}
        self.scheduler = BackgroundScheduler(
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 60
            }
        )
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self._customer_doc_managers = {}  # Cache customer document managers
        self.logger.info(f"DriveMonitor initialized with check interval of {check_interval} seconds")
        
    def start(self):
        """
        Start the monitoring scheduler.
        """
        if not self.is_running:
            try:
                self.scheduler.start()
                self.is_running = True
                self.logger.info(f"Drive monitor started.")
            except Exception as e:
                self.logger.error(f"Failed to start scheduler: {str(e)}")
                raise
    
    def stop(self):
        """
        Stop the monitoring scheduler.
        """
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            self.logger.info("Drive monitor stopped.")
            
    def _check_all_folders(self):
        """
        Check all monitored folders for updates, respecting customer separation.
        """
        self.logger.info(f"Checking {len(self.monitored_folders)} folders for updates...")
        
        # Group folders by customer_id
        customer_folders = {}
        for folder_id, folder_info in self.monitored_folders.items():
            customer_id = folder_info.get("customer_id", "default")
            if customer_id not in customer_folders:
                customer_folders[customer_id] = []
            customer_folders[customer_id].append((folder_id, folder_info))
        
        # Process each customer's folders separately
        for customer_id, folders in customer_folders.items():
            self.logger.info(f"Processing {len(folders)} folders for customer {customer_id}")
            
            # Create a customer-specific document manager if needed
            customer_doc_manager = None
            if customer_id != "default" and customer_id is not None:
                # Check if we already have a cached document manager for this customer
                if customer_id not in self._customer_doc_managers:
                    from document_manager import DocumentManager
                    import os
                    
                    api_key = os.getenv('OPENAI_API_KEY')
                    if not api_key:
                        self.logger.error("OpenAI API key not found in environment variables")
                        continue
                    
                    # Use customer-specific path
                    vector_store_base = os.path.join(os.path.dirname(__file__), 'data', 'customers', customer_id, 'vector_store')
                    self._customer_doc_managers[customer_id] = DocumentManager(
                        openai_api_key=api_key,
                        vector_store_dir=vector_store_base,
                        customer_id=customer_id
                    )
                    self.logger.info(f"Created new DocumentManager for customer {customer_id}")
                
                customer_doc_manager = self._customer_doc_managers[customer_id]
            else:
                # Use the global document manager for default case
                customer_doc_manager = self.document_manager
            
            # Process each folder for this customer
            for folder_id, folder_info in folders:
                try:
                    folder_link = folder_info["folder_link"]
                    self.logger.info(f"Checking folder {folder_id} for customer {customer_id}")
                    self._check_folder_for_updates(folder_link, document_manager=customer_doc_manager, customer_id=customer_id)
                    # Update last check time
                    folder_info["last_check"] = time.time()
                except Exception as e:
                    self.logger.error(f"Error checking folder {folder_id} for customer {customer_id}: {str(e)}")
    
    def add_folder(self, folder_link: str, interval_minutes: int = 30, customer_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Add a folder to be monitored.
        
        Args:
            folder_link (str): Google Drive folder link.
            interval_minutes (int): How often to check for new files (in minutes).
            customer_id (str, optional): ID of the customer who owns this folder.
            
        Returns:
            Dict[str, Any]: Result of the operation.
        """
        from backend.utils import extract_folder_id_from_drive_link
        
        folder_id = extract_folder_id_from_drive_link(folder_link)
        if not folder_id:
            return {
                "success": False,
                "error": "Invalid Google Drive folder link"
            }
        
        # Check if folder is already being monitored
        if folder_id in self.monitored_folders:
            return {
                "success": False,
                "error": "Folder is already being monitored"
            }
        
        # Process the folder initially to get current files
        # Use customer-specific document manager if available, otherwise use global one
        doc_manager_to_use = None
        if customer_id and customer_id != "default":
            # Create a customer-specific document manager for initial processing
            from document_manager import DocumentManager
            import os
            
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                
                # Use customer-specific path
                vector_store_base = os.path.join(os.path.dirname(__file__), 'data', 'customers', customer_id, 'vector_store')
                doc_manager_to_use = DocumentManager(
                    openai_api_key=api_key,
                    vector_store_dir=vector_store_base,
                    customer_id=customer_id
                )
        
        # If we couldn't create a customer-specific manager, use the global one
        if not doc_manager_to_use:
            doc_manager_to_use = self.document_manager
            
        # If we still don't have a document manager, return an error
        if not doc_manager_to_use:
            return {
                "success": False,
                "error": "No document manager available for processing"
            }
            
        # Process folder with appropriate customer_id parameter
        if customer_id is not None:
            initial_result = doc_manager_to_use.process_drive_folder(folder_link, incremental=True, customer_id=customer_id)
        else:
            initial_result = doc_manager_to_use.process_drive_folder(folder_link, incremental=True)
        
        if not initial_result["success"]:
            return initial_result
        
        # Make sure scheduler is running
        if not self.is_running:
            self.start()
            
        # Add job to scheduler - pass customer_id so _check_folder_for_updates can handle it properly
        job = self.scheduler.add_job(
            self._check_folder_for_updates,
            'interval',
            minutes=interval_minutes,
            args=[folder_link, None, customer_id],  # Pass None for document_manager so _check_folder_for_updates creates customer-specific one
            id=f"folder_{folder_id}",
            replace_existing=True
        )
        
        # Store folder information
        self.monitored_folders[folder_id] = {
            "folder_link": folder_link,
            "interval_minutes": interval_minutes,
            "job_id": job.id,
            "last_check": time.time() * 1000,  # Convert to milliseconds for JavaScript
            "file_count": initial_result["file_count"],
            "doc_count": initial_result["doc_count"],
            "customer_id": customer_id
        }
        
        self.logger.info(f"Added folder {folder_id} to monitoring with {interval_minutes} minute interval")
        
        return {
            "success": True,
            "folder_id": folder_id,
            "interval_minutes": interval_minutes,
            "initial_processing": initial_result
        }
    
    def remove_folder(self, folder_link: str) -> Dict[str, Any]:
        """
        Remove a folder from monitoring.
        
        Args:
            folder_link (str): Google Drive folder link.
            
        Returns:
            Dict[str, Any]: Result of the operation.
        """
        from backend.utils import extract_folder_id_from_drive_link
        
        folder_id = extract_folder_id_from_drive_link(folder_link)
        if not folder_id:
            return {
                "success": False,
                "error": "Invalid Google Drive folder link"
            }
        
        return self.remove_folder_by_id(folder_id)
    
    def remove_folder_by_id(self, folder_id: str) -> Dict[str, Any]:
        """
        Remove a folder from monitoring by its ID.
        
        Args:
            folder_id (str): Google Drive folder ID.
            
        Returns:
            Dict[str, Any]: Result of the operation.
        """
        # Check if folder is being monitored
        if folder_id not in self.monitored_folders:
            return {
                "success": False,
                "error": "Folder is not being monitored"
            }
        
        try:
            # Remove job from scheduler
            self.scheduler.remove_job(f"folder_{folder_id}")
            
            # Remove folder from monitored folders
            folder_info = self.monitored_folders.pop(folder_id)
            
            self.logger.info(f"Removed folder {folder_id} from monitoring")
            
            return {
                "success": True,
                "folder_id": folder_id
            }
        except Exception as e:
            self.logger.error(f"Error removing folder {folder_id}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def list_monitored_folders(self) -> List[Dict[str, Any]]:
        """
        List all monitored folders.
        
        Returns:
            List[Dict[str, Any]]: List of monitored folders.
        """
        result = []
        
        for folder_id, info in self.monitored_folders.items():
            result.append({
                "folder_id": folder_id,
                "folder_link": info["folder_link"],
                "interval_minutes": info["interval_minutes"],
                "last_check": info["last_check"],
                "next_check": info["last_check"] + (info["interval_minutes"] * 60),
                "file_count": info["file_count"],
                "doc_count": info["doc_count"]
            })
        
        return result
    
    def _check_folder_for_updates(self, folder_link: str, document_manager=None, customer_id: Optional[str] = None):
        """
        Check a folder for new files and process them.
        
        Args:
            folder_link (str): Google Drive folder link.
            document_manager (DocumentManager, optional): Customer-specific document manager.
            customer_id (str, optional): ID of the customer who owns this folder.
            
        Returns:
            dict: Result of the check operation.
        """
        from backend.utils import extract_folder_id_from_drive_link
        
        folder_id = extract_folder_id_from_drive_link(folder_link)
        if not folder_id:
            self.logger.error(f"Invalid folder link: {folder_link}")
            return {"success": False, "error": "Invalid folder link"}
        
        self.logger.info(f"Checking folder {folder_id} for customer {customer_id or 'default'} for updates...")
        
        try:
            # Use provided document manager or create customer-specific one or fall back to global one
            dm = document_manager
            
            # If no document manager provided, create customer-specific one if customer_id is available
            if not dm and customer_id and customer_id != "default":
                # Check if we have a cached document manager for this customer
                if customer_id not in self._customer_doc_managers:
                    from document_manager import DocumentManager
                    import os
                    
                    api_key = os.getenv('OPENAI_API_KEY')
                    if api_key:
                        vector_store_base = os.path.join(os.path.dirname(__file__), 'data', 'customers', customer_id, 'vector_store')
                        self._customer_doc_managers[customer_id] = DocumentManager(
                            openai_api_key=api_key,
                            vector_store_dir=vector_store_base,
                            customer_id=customer_id
                        )
                        self.logger.info(f"Created new DocumentManager for customer {customer_id} in check_folder")
                
                if customer_id in self._customer_doc_managers:
                    dm = self._customer_doc_managers[customer_id]
            
            # If still no document manager, use global one
            if not dm:
                dm = self.document_manager
                
            # If we still don't have a document manager, return an error
            if not dm:
                return {"success": False, "error": "No document manager available for processing"}
            
            # Process the folder incrementally with appropriate customer_id parameter
            if customer_id is not None:
                result = dm.process_drive_folder(folder_link, incremental=True, customer_id=customer_id)
            else:
                result = dm.process_drive_folder(folder_link, incremental=True)
            
            if result["success"]:
                self.logger.info(f"Successfully checked folder {folder_id} for customer {customer_id or 'default'}. Found {result.get('new_files', 0)} new files.")
                
                # Update folder information with customer-specific data
                if folder_id in self.monitored_folders:
                    self.monitored_folders[folder_id]["file_count"] = result["file_count"]
                    self.monitored_folders[folder_id]["doc_count"] = result["doc_count"]
                    self.monitored_folders[folder_id]["customer_id"] = customer_id
                    self.monitored_folders[folder_id]["last_check"] = time.time() * 1000  # Update last check time
                    
                # Log processing details
                processed = result.get("processed_files", 0)
                failed = result.get("failed_files", 0)
                skipped = result.get("skipped_files", 0)
                
                self.logger.info(f"Folder {folder_id} for customer {customer_id or 'default'}: "
                               f"Processed {processed}, Failed {failed}, Skipped {skipped}, New docs {result.get('doc_count', 0)}")
            else:
                self.logger.error(f"Error checking folder {folder_id} for customer {customer_id or 'default'}: {result.get('error', 'Unknown error')}")
            
            return result
        except Exception as e:
            self.logger.error(f"Exception checking folder {folder_id} for customer {customer_id or 'default'}: {str(e)}")
            return {"success": False, "error": str(e)}