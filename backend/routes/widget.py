"""Widget routes blueprint for embedded chat widget."""
import os
import json
import logging
from urllib.parse import urlparse
from flask import Blueprint, request, jsonify, current_app
from flask_limiter import Limiter
from services import llm, documents

# Create blueprint
widget_bp = Blueprint('widget', __name__, url_prefix='/backend/api/widget')

# Get limiter from app context or use a placeholder
def get_limiter():
    """Get the rate limiter from Flask app extensions."""
    return current_app.extensions.get('limiter')


@widget_bp.route('/chat', methods=['POST', 'OPTIONS'])
def widget_chat():
    """Handle chat requests from embedded widget with URL-based authorization."""
    # Handle OPTIONS preflight
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        logger = logging.getLogger(__name__)
        logger.info("=== Widget Chat Request ===")
        
        # Get auth headers
        widget_api_key = request.headers.get('X-Widget-API-Key')
        customer_id = request.headers.get('X-Customer-ID')
        parent_url = request.headers.get('X-Parent-URL')
        
        # Fallback to Origin/Referer if X-Parent-URL not provided
        if not parent_url:
            origin = request.headers.get('Origin')
            referer = request.headers.get('Referer')
            parent_url = origin or referer
        
        requesting_url = parent_url
        logger.info(f"API Key: {widget_api_key}, Customer: {customer_id}, URL: {requesting_url}")
        
        # Validate credentials
        if not widget_api_key or not customer_id:
            return jsonify({'error': 'Missing authentication credentials'}), 401
        
        if not requesting_url:
            return jsonify({'error': 'Unauthorized access - origin not provided'}), 403
        
        # Verify widget access
        parsed = urlparse(requesting_url)
        requesting_domain = parsed.netloc or ''
        
        is_authorized, error_msg = documents.verify_widget_access(
            customer_id, widget_api_key, requesting_domain
        )
        
        if not is_authorized:
            logger.warning(f"[AUTHORIZATION FAILED] {error_msg}")
            return jsonify({'error': error_msg}), 403
        
        logger.info("[AUTHORIZATION SUCCESS]")
        
        # Parse request body
        if not request.is_json:
            return jsonify({'error': 'Invalid request format, JSON expected'}), 400
            
        json_data = request.get_json()
        if not json_data:
            return jsonify({'error': 'Invalid JSON data'}), 400
            
        user_message = json_data.get('message', '')
        service = json_data.get('service', 'ChatGPT')
        mode = json_data.get('mode', 'chat')
        
        logger.info(f"Message: {user_message[:50]}..., Service: {service}, Mode: {mode}")
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Name capture mode
        if mode == 'name_capture':
            extracted_name = llm.extract_user_name(user_message, service)
            logger.info(f"Extracted name: {extracted_name}")
            return jsonify({'response': '', 'extractedName': extracted_name})
        
        # Regular chat mode - get document context
        document_context = documents.get_document_context(customer_id, user_message)
        
        # If no document context found, return out-of-scope message immediately
        if not document_context or not document_context.strip():
            logger.info(f"No document context found for: {user_message[:50]}...")
            return jsonify({
                'response': "I can only help with questions related to the information in our company documents. Please ask about topics covered in our documentation.",
                'extractedName': None
            })
        
        logger.info(f"Document context found: {document_context[:100]}...")
        
        # Get response from LLM
        try:
            response_text = llm.get_chat_completion(user_message, service, document_context)
            logger.info(f"Response: {response_text[:100]}...")
        except Exception as e:
            logger.exception("Error generating response")
            response_text = "I'm here to help! However, I'm having trouble processing your request. Please try again."
        
        return jsonify({'response': response_text, 'extractedName': None})
    
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error in widget_chat: {e}")
        return jsonify({'error': 'An error occurred processing your request'}), 500


@widget_bp.route('/context', methods=['POST', 'OPTIONS'])
def widget_context():
    """Return relevant document context for the widget (no LLM call)."""
    # Handle OPTIONS preflight
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        # Get auth headers
        widget_api_key = request.headers.get('X-Widget-API-Key')
        customer_id = request.headers.get('X-Customer-ID')
        parent_url = request.headers.get('X-Parent-URL')
        
        if not parent_url:
            origin = request.headers.get('Origin')
            referer = request.headers.get('Referer')
            parent_url = origin or referer
        
        requesting_url = parent_url
        
        # Validate credentials
        if not widget_api_key or not customer_id:
            return jsonify({'error': 'Missing authentication credentials'}), 401
        
        if not requesting_url:
            return jsonify({'error': 'Unauthorized access - origin not provided'}), 403
        
        # Verify widget access
        parsed = urlparse(requesting_url)
        requesting_domain = parsed.netloc or ''
        
        is_authorized, error_msg = documents.verify_widget_access(
            customer_id, widget_api_key, requesting_domain
        )
        
        if not is_authorized:
            return jsonify({'error': error_msg}), 403
        
        # Parse request body
        if not request.is_json:
            return jsonify({'error': 'Invalid request format, JSON expected'}), 400
            
        json_data = request.get_json()
        if not json_data:
            return jsonify({'error': 'Invalid JSON data'}), 400
            
        user_message = json_data.get('message', '')
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Get document context
        document_context = documents.get_document_context(customer_id, user_message)
        
        # If no document context found, return out-of-scope response
        if not document_context or not document_context.strip():
            return jsonify({
                'success': True,
                'context': '',
                'prompt': user_message,
                'out_of_scope': True,
                'message': "I can only help with questions related to the information in our company documents. Please ask about topics covered in our documentation."
            })
        
        # Build prompt with context
        prompt = (
            f"Based on the following company documents:\n\n{document_context}\n\n"
            f"User question: {user_message}\n\n"
            f"Give me the response in short without losing any meaning. Answer:"
        )
        
        return jsonify({
            'success': True,
            'context': document_context or '',
            'prompt': prompt
        })
    
    except Exception as e:
        logging.getLogger(__name__).exception(f"Error in widget_context: {e}")
        return jsonify({'error': 'An error occurred processing your request'}), 500
