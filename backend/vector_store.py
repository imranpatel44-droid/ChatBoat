"""
Vector store with optimized approximate nearest neighbor search using scikit-learn.
Replaces O(N) linear search with O(log N) KD-tree/Ball tree search.
"""
import os
import json
import numpy as np
from typing import List, Dict, Any, Optional
from pathlib import Path
from sklearn.neighbors import NearestNeighbors
import logging

logger = logging.getLogger(__name__)


class VectorStore:
    """
    An optimized vector store for managing document embeddings with fast ANN search.
    Uses scikit-learn NearestNeighbors for efficient similarity search.
    """
    
    def __init__(self, storage_dir: str, customer_id: str, algorithm: str = 'auto'):
        """
        Initialize the vector store.
        
        Args:
            storage_dir: Directory to store vector data.
            customer_id: Customer ID for customer-specific storage (required).
            algorithm: ANN algorithm ('auto', 'kd_tree', 'ball_tree', 'brute').
                      'auto' selects best based on data characteristics.
        """
        if not customer_id:
            raise ValueError("customer_id is required for vector store")
        
        self.customer_id = customer_id
        self.storage_dir = storage_dir
        self.algorithm = algorithm
        
        # Data storage
        self.documents: List[Dict[str, Any]] = []
        self.embeddings: List[List[float]] = []
        self._embeddings_matrix: Optional[np.ndarray] = None
        
        # ANN index (built lazily when needed)
        self._ann_index: Optional[NearestNeighbors] = None
        self._index_needs_rebuild: bool = True
        
        # Create directory if it doesn't exist
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # Load existing data
        if os.path.exists(self.storage_dir):
            self._load_from_disk()
    
    def _normalize_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """Normalize embeddings to unit length for cosine similarity via dot product."""
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        # Avoid division by zero
        norms = np.where(norms == 0, 1, norms)
        return embeddings / norms
    
    def _build_ann_index(self) -> None:
        """Build or rebuild the ANN index for fast similarity search."""
        if not self.embeddings:
            self._ann_index = None
            self._index_needs_rebuild = False
            return
        
        # Convert to numpy matrix and normalize
        self._embeddings_matrix = np.array(self.embeddings)
        normalized = self._normalize_embeddings(self._embeddings_matrix)
        
        # Choose number of neighbors for index based on data size
        n_samples = len(self.embeddings)
        
        # Build index with cosine distance (which is 1 - cosine_similarity)
        # We use 'brute' for small datasets, 'kd_tree'/'ball_tree' for larger
        if n_samples < 50:
            algo = 'brute'  # Linear search is fine for small datasets
        else:
            algo = self.algorithm
        
        self._ann_index = NearestNeighbors(
            n_neighbors=min(50, n_samples),  # Keep top 50 for filtering
            algorithm=algo,
            metric='cosine',  # Directly use cosine distance
            n_jobs=-1  # Use all CPU cores
        )
        
        self._ann_index.fit(normalized)
        self._index_needs_rebuild = False
        
        logger.info(f"Built ANN index with {n_samples} documents using {algo} algorithm")
    
    def _ensure_index(self) -> None:
        """Ensure the ANN index is built if needed."""
        if self._index_needs_rebuild or self._ann_index is None:
            self._build_ann_index()
    
    def add_document(self, document_text: str, embedding: List[float], 
                     metadata: Dict[str, Any] = None, customer_id: str = None) -> int:
        """
        Add a document and its embedding to the store.
        
        Args:
            document_text: The document text.
            embedding: The document's embedding vector.
            metadata: Additional metadata about the document.
            customer_id: Customer ID for customer-specific storage.
            
        Returns:
            int: The document ID (index in the store).
        """
        if metadata is None:
            metadata = {}
        
        current_customer_id = customer_id or self.customer_id
        
        if current_customer_id:
            metadata['customer_id'] = current_customer_id
        
        doc_id = len(self.documents)
        
        # Store document and embedding
        self.documents.append({
            'id': doc_id,
            'text': document_text,
            'metadata': metadata
        })
        
        self.embeddings.append(embedding)
        
        # Mark index for rebuild
        self._index_needs_rebuild = True
        
        # Save to disk (consider batching for production)
        self._save_to_disk()
        
        return doc_id
    
    def search(self, query_embedding: List[float], top_k: int = 5, 
               customer_id: str = None) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query embedding using ANN.
        
        Args:
            query_embedding: The query embedding vector.
            top_k: Number of top results to return.
            customer_id: Filter results by customer ID.
            
        Returns:
            List of top matching documents with similarity scores.
        """
        if not self.embeddings:
            return []
        
        # Ensure index is built
        self._ensure_index()
        
        if self._ann_index is None:
            return []
        
        # Normalize query embedding
        query_vec = np.array(query_embedding).reshape(1, -1)
        query_norm = np.linalg.norm(query_vec)
        if query_norm > 0:
            query_vec = query_vec / query_norm
        
        # Get nearest neighbors (fetch more than needed for customer filtering)
        fetch_k = min(top_k * 3, len(self.embeddings))  # Fetch extra for filtering
        distances, indices = self._ann_index.kneighbors(query_vec, n_neighbors=fetch_k)
        
        # Convert distances to similarities (cosine distance = 1 - cosine similarity)
        # So similarity = 1 - distance
        similarities = 1 - distances[0]
        indices = indices[0]
        
        # Build results with customer filtering
        results = []
        target_customer = customer_id or self.customer_id
        
        for idx, similarity in zip(indices, similarities):
            doc = self.documents[idx]
            
            # Filter by customer ID if specified
            if target_customer:
                doc_customer = doc.get('metadata', {}).get('customer_id')
                if doc_customer and doc_customer != target_customer:
                    continue
            
            result_doc = doc.copy()
            result_doc['similarity'] = float(similarity)
            results.append(result_doc)
            
            if len(results) >= top_k:
                break
        
        return results
    
    def batch_add_documents(self, documents: List[tuple]) -> List[int]:
        """
        Add multiple documents in batch (more efficient than individual adds).
        
        Args:
            documents: List of (document_text, embedding, metadata) tuples.
            
        Returns:
            List of document IDs.
        """
        doc_ids = []
        
        for doc_text, embedding, metadata in documents:
            if metadata is None:
                metadata = {}
            
            metadata['customer_id'] = self.customer_id
            
            doc_id = len(self.documents)
            self.documents.append({
                'id': doc_id,
                'text': doc_text,
                'metadata': metadata
            })
            self.embeddings.append(embedding)
            doc_ids.append(doc_id)
        
        # Rebuild index once after batch add
        self._index_needs_rebuild = True
        self._ensure_index()
        
        # Save to disk
        self._save_to_disk()
        
        return doc_ids
    
    def _save_to_disk(self) -> None:
        """Save the vector store data to disk."""
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # Save documents
        docs_path = os.path.join(self.storage_dir, 'documents.json')
        with open(docs_path, 'w') as f:
            json.dump(self.documents, f)
        
        # Save embeddings
        embeddings_path = os.path.join(self.storage_dir, 'embeddings.npy')
        np.save(embeddings_path, np.array(self.embeddings))
    
    def _load_from_disk(self) -> None:
        """Load the vector store data from disk."""
        # Load documents
        docs_path = os.path.join(self.storage_dir, 'documents.json')
        if os.path.exists(docs_path):
            try:
                with open(docs_path, 'r') as f:
                    self.documents = json.load(f)
            except Exception as e:
                logger.error(f"Error loading documents: {e}")
                self.documents = []
        
        # Load embeddings
        embeddings_path = os.path.join(self.storage_dir, 'embeddings.npy')
        if os.path.exists(embeddings_path):
            try:
                embeddings_array = np.load(embeddings_path)
                self.embeddings = embeddings_array.tolist()
            except Exception as e:
                logger.error(f"Error loading embeddings: {e}")
                self.embeddings = []
        
        # Mark index for rebuild
        self._index_needs_rebuild = True
    
    def clear(self) -> bool:
        """Clear all documents and embeddings from the store."""
        try:
            self.documents = []
            self.embeddings = []
            self._ann_index = None
            self._embeddings_matrix = None
            self._index_needs_rebuild = False
            
            # Remove files
            docs_path = os.path.join(self.storage_dir, 'documents.json')
            embeddings_path = os.path.join(self.storage_dir, 'embeddings.npy')
            
            for path in [docs_path, embeddings_path]:
                if os.path.exists(path):
                    os.remove(path)
            
            return True
        except Exception as e:
            logger.error(f"Error clearing vector store: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store."""
        return {
            'doc_count': len(self.documents),
            'has_index': self._ann_index is not None,
            'index_needs_rebuild': self._index_needs_rebuild,
            'algorithm': self.algorithm
        }
