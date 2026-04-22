"""Admin routes blueprint for dashboard and document management."""
import os
import json
import time
import logging
from flask import Blueprint, request, jsonify, render_template, current_app
from auth import token_required, get_user_vector_store_dir, CUSTOMERS_DIR
from services import documents
from drive_monitor import DriveMonitor

# Create blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/backend/api/admin')

# Global drive monitor instance - initialized in app.py
drive_monitor = None


def init_drive_monitor(monitor: DriveMonitor):
    """Initialize the drive monitor reference. Called from app.py during setup."""
    global drive_monitor
    drive_monitor = monitor


@admin_bp.route('/dashboard', methods=['GET'])
def admin_dashboard():
    """Render admin dashboard template."""
    # For admin dashboard, use a default document manager
    default_stats = {'doc_count': 0, 'last_updated': time.time()}
    
    try:
        from document_manager import DocumentManager
        default_vector_store_dir = os.path.join(documents.VECTOR_STORE_BASE_DIR, 'default')
        os.makedirs(default_vector_store_dir, exist_ok=True)
        
        import openai
        default_doc_manager = DocumentManager(
            openai_api_key=os.getenv('OPENAI_API_KEY', ''),
            vector_store_dir=default_vector_store_dir,
            customer_id='default'
        )
        default_stats = default_doc_manager.get_store_stats()
    except Exception as e:
        logging.getLogger(__name__).error(f"Error loading admin dashboard stats: {e}")
    
    return render_template(
        'admin_dashboard.html',
        doc_count=default_stats.get('doc_count', 0),
        last_updated=default_stats.get('last_updated', time.time())
    )


@admin_bp.route('/process-drive-folder', methods=['POST'])
@token_required
def process_drive_folder(current_user):
    """Process all files in a Google Drive folder."""
    try:
        if not request.is_json:
            return jsonify({'error': 'Invalid request format, JSON expected'}), 400
            
        json_data = request.get_json()
        if not json_data:
            return jsonify({'error': 'Invalid JSON data'}), 400
            
        folder_link = json_data.get('folder_link', '')
        monitor = json_data.get('monitor', False)
        interval_minutes = json_data.get('interval_minutes', 30)
        
        if not folder_link:
            return jsonify({'error': 'No Google Drive folder link provided'}), 400
        
        customer_id = current_user.get('customer_id')
        
        # Process the folder
        result = documents.process_drive_folder(customer_id, folder_link, incremental=True)
        
        if not result['success']:
            return jsonify({'error': result.get('error', 'Unknown error')}), 400
        
        # If monitor flag is set, add the folder to monitoring
        if monitor and drive_monitor:
            monitor_result = drive_monitor.add_folder(folder_link, interval_minutes, customer_id)
            if not monitor_result['success']:
                result['monitor_error'] = monitor_result.get('error', 'Unknown error')
            else:
                result['monitoring'] = True
                result['interval_minutes'] = interval_minutes
        
        # Get updated stats
        stats = documents.get_store_stats(customer_id)
        
        return jsonify({
            'success': True,
            'file_count': result.get('file_count', 0),
            'processed_count': result.get('processed_count', 0),
            'failed_count': result.get('failed_count', 0),
            'doc_count': stats.get('doc_count', 0)
        })
    
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error in process_drive_folder: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/clear-vector-store', methods=['POST'])
@token_required
def clear_vector_store(current_user):
    """Clear all documents from the vector store."""
    try:
        customer_id = current_user.get('customer_id')
        result = documents.clear_vector_store(customer_id)
        
        if not result.get('success', False):
            return jsonify({'error': 'Failed to clear vector store'}), 500
        
        return jsonify({
            'success': True,
            'message': 'Vector store cleared successfully',
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error clearing vector store: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/vector-store-stats', methods=['GET'])
@token_required
def vector_store_stats(current_user):
    """Get vector store statistics."""
    try:
        customer_id = current_user.get('customer_id')
        stats = documents.get_store_stats(customer_id)
        
        # Get folder count for this customer
        folder_count = 0
        if drive_monitor and hasattr(drive_monitor, 'monitored_folders'):
            for folder_id, folder_info in drive_monitor.monitored_folders.items():
                if folder_info.get('customer_id') == customer_id:
                    folder_count += 1
        
        return jsonify({
            'document_count': stats.get('doc_count', 0),
            'vector_count': stats.get('doc_count', 0),
            'folderCount': folder_count
        })
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error getting vector store stats: {e}")
        return jsonify({
            'document_count': 0,
            'vector_count': 0,
            'error': str(e)
        })


@admin_bp.route('/monitor-drive-folder', methods=['POST'])
@token_required
def monitor_drive_folder(current_user):
    """Add a Google Drive folder to monitoring."""
    try:
        if not request.is_json:
            return jsonify({'error': 'Invalid request format, JSON expected'}), 400
            
        json_data = request.get_json()
        if not json_data:
            return jsonify({'error': 'Invalid JSON data'}), 400
            
        folder_link = json_data.get('folder_link', '')
        interval_minutes = int(json_data.get('interval_minutes', 30))
        
        if not folder_link:
            return jsonify({'message': 'No Google Drive folder link provided'}), 400
        
        customer_id = current_user.get('customer_id')
        
        # Process the folder initially
        initial_result = documents.process_drive_folder(customer_id, folder_link, incremental=True)
        
        # Add to monitoring
        if drive_monitor:
            result = drive_monitor.add_folder(folder_link, interval_minutes, customer_id)
            
            if not result['success']:
                return jsonify({'message': result.get('error', 'Unknown error')}), 200
            
            return jsonify({
                'success': True,
                'message': f'Folder is now being monitored every {interval_minutes} minutes',
                'folder_id': result.get('folder_id'),
                'interval_minutes': interval_minutes
            })
        
        return jsonify({'error': 'Drive monitor not initialized'}), 500
    
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error monitoring drive folder: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/stop-monitoring-folder', methods=['POST'])
@token_required
def stop_monitoring_folder(current_user):
    """Stop monitoring a folder."""
    try:
        if not request.is_json:
            return jsonify({'error': 'Invalid request format, JSON expected'}), 400
            
        json_data = request.get_json()
        if not json_data:
            return jsonify({'error': 'Invalid JSON data'}), 400
            
        folder_id = json_data.get('folder_id', '')
        
        if not folder_id:
            return jsonify({'message': 'No folder ID provided'}), 400
        
        if not drive_monitor:
            return jsonify({'error': 'Drive monitor not initialized'}), 500
            
        # Check if folder exists and belongs to this customer
        if folder_id not in drive_monitor.monitored_folders:
            return jsonify({'message': 'Invalid folder ID or folder not monitored'}), 404
            
        customer_id = current_user.get('customer_id')
        if drive_monitor.monitored_folders[folder_id].get('customer_id') != customer_id:
            return jsonify({'message': 'This folder does not belong to your account'}), 403
        
        # Remove folder from monitoring
        result = drive_monitor.remove_folder_by_id(folder_id)
        
        if not result.get('success', False):
            return jsonify({'message': result.get('error', 'Unknown error')}), 200
        
        return jsonify({
            'success': True,
            'message': 'Folder monitoring stopped successfully',
            'folder_id': folder_id
        })
    
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error stopping folder monitoring: {e}")
        return jsonify({'message': str(e)}), 200


@admin_bp.route('/sync-folder-now', methods=['POST'])
@token_required
def sync_folder_now(current_user):
    """Manually trigger a sync for a specific folder."""
    try:
        if not request.is_json:
            return jsonify({'error': 'Invalid request format, JSON expected'}), 400
            
        json_data = request.get_json()
        if not json_data:
            return jsonify({'error': 'Invalid JSON data'}), 400
            
        folder_id = json_data.get('folder_id', '')
        customer_id = current_user.get('customer_id')
        
        if not folder_id:
            return jsonify({'success': False, 'message': 'No folder ID provided'}), 400
        
        if not drive_monitor:
            return jsonify({'error': 'Drive monitor not initialized'}), 500
            
        if folder_id not in drive_monitor.monitored_folders:
            return jsonify({'success': False, 'message': 'Invalid folder ID or folder not monitored'}), 404
        
        # Check if folder belongs to this customer
        if drive_monitor.monitored_folders[folder_id].get('customer_id') != customer_id:
            return jsonify({
                'success': False,
                'message': 'This folder does not belong to your account'
            }), 403
        
        # Get folder link
        folder_link = drive_monitor.monitored_folders[folder_id]['folder_link']
        
        # Create document manager for this customer
        doc_manager = documents.create_document_manager(customer_id)
        
        # Trigger sync
        drive_monitor._check_folder_for_updates(folder_link, document_manager=doc_manager, customer_id=customer_id)
        
        # Update last check time
        drive_monitor.monitored_folders[folder_id]['last_check'] = time.time()
        
        folder_info = drive_monitor.monitored_folders[folder_id]
        
        return jsonify({
            'success': True,
            'message': 'Folder synced successfully',
            'folder_id': folder_id,
            'processed_count': folder_info.get('doc_count', 0)
        })
    
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error syncing folder: {e}")
        return jsonify({'success': False, 'message': f'Error syncing folder: {str(e)}'}), 200


@admin_bp.route('/list-monitored-folders', methods=['GET'])
@token_required
def list_monitored_folders(current_user):
    """List all folders being monitored for the current customer."""
    try:
        if not drive_monitor:
            return jsonify({'success': True, 'folders': []})
            
        customer_id = current_user.get('customer_id')
        folders = []
        
        for folder_id, folder_info in drive_monitor.monitored_folders.items():
            if folder_info.get('customer_id') == customer_id:
                folders.append({
                    'folder_id': folder_id,
                    'folder_link': folder_info['folder_link'],
                    'interval_minutes': folder_info['interval_minutes'],
                    'last_check': folder_info['last_check'],
                    'file_count': folder_info.get('file_count', 0),
                    'doc_count': folder_info.get('doc_count', 0),
                    'next_check': folder_info.get('next_check', 0)
                })
        
        return jsonify({
            'success': True,
            'folders': folders
        })
    
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error listing monitored folders: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/sync-all-folders-now', methods=['POST'])
@token_required
def sync_all_folders_now(current_user):
    """Sync all monitored folders immediately."""
    try:
        if not drive_monitor:
            return jsonify({'error': 'Drive monitor not initialized'}), 500
            
        customer_id = current_user.get('customer_id')
        
        # Filter folders for this customer
        customer_folders = {}
        for folder_id, info in drive_monitor.monitored_folders.items():
            if info.get('customer_id') == customer_id:
                customer_folders[folder_id] = info
        
        if not customer_folders:
            return jsonify({
                'success': False,
                'message': 'No folders are currently being monitored for your account'
            }), 200
        
        # Create document manager
        doc_manager = documents.create_document_manager(customer_id)
        
        folder_count = 0
        total_processed_count = 0
        
        # Sync each folder
        for folder_id, info in list(customer_folders.items()):
            try:
                folder_link = info['folder_link']
                drive_monitor._check_folder_for_updates(folder_link, document_manager=doc_manager, customer_id=customer_id)
                folder_count += 1
                total_processed_count += info.get('doc_count', 0)
            except Exception as e:
                logging.getLogger(__name__).error(f"Error syncing folder {folder_id}: {e}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully synced {folder_count} folders for your account',
            'folder_count': folder_count,
            'total_processed_count': total_processed_count
        })
    
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error syncing all folders: {e}")
        return jsonify({'success': False, 'message': f'Error syncing folders: {str(e)}'}), 200


@admin_bp.route('/generate-widget-key', methods=['POST'])
@token_required
def generate_widget_key(current_user):
    """Generate a widget API key for the customer."""
    try:
        import hashlib
        customer_id = current_user.get('customer_id')
        
        # Load customer profile
        profile_path = os.path.join(CUSTOMERS_DIR, customer_id, 'profile.json')
        if not os.path.exists(profile_path):
            return jsonify({'error': 'Customer profile not found'}), 404
        
        with open(profile_path, 'r') as f:
            profile = json.load(f)
        
        website_url = profile.get('website_url')
        if not website_url:
            return jsonify({'error': 'No website URL registered'}), 400
        
        # Generate API key
        api_key_string = f"{customer_id}-{time.time()}"
        widget_api_key = hashlib.sha256(api_key_string.encode()).hexdigest()
        
        # Save config
        config = {
            'api_key': widget_api_key,
            'customer_id': customer_id,
            'website_url': website_url,
            'created_at': time.time()
        }
        
        if documents.save_widget_config(customer_id, config):
            return jsonify({
                'success': True,
                'api_key': widget_api_key,
                'customer_id': customer_id,
                'website_url': website_url
            })
        else:
            return jsonify({'error': 'Failed to save widget configuration'}), 500
    
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error generating widget key: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/get-widget-code', methods=['GET'])
@token_required
def get_widget_code(current_user):
    """Get the embed code for the widget."""
    try:
        customer_id = current_user.get('customer_id')
        
        # Get widget config
        config = documents.get_widget_config(customer_id)
        if not config:
            return jsonify({
                'success': False,
                'error': 'Widget not configured. Please generate an API key first.'
            }), 404
        
        api_key = config.get('api_key')
        website_url = config.get('website_url', '')
        
        # Get URLs from environment
        widget_host_url = os.getenv('WIDGET_HOST_URL', 'http://localhost:3000')
        backend_api_url = os.getenv('BACKEND_API_URL', 'http://localhost:5000')
        
        embed_code = f"""<!-- Chat Widget Embed Code -->
<!-- IMPORTANT: This widget is authorized ONLY for: {website_url} -->

<script>
  (function() {{
    var parentUrl = encodeURIComponent(window.location.href);
    var iframe = document.createElement('iframe');
    iframe.src = '{widget_host_url}/widget?apiKey={api_key}&customerId={customer_id}&apiUrl={backend_api_url}&parentUrl=' + parentUrl;
    iframe.style.cssText = 'position: fixed; bottom: 20px; right: 20px; width: 400px; height: 650px; border: none; z-index: 999999;';
    iframe.title = 'Chat Widget';
    document.body.appendChild(iframe);
  }})();
</script>"""
        
        return jsonify({
            'success': True,
            'embed_code': embed_code,
            'api_key': api_key,
            'customer_id': customer_id,
            'website_url': website_url
        })
    
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error getting widget code: {e}")
        return jsonify({'error': str(e)}), 500
