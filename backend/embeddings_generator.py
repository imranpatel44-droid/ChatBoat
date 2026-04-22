import os
import openai
import numpy as np
from typing import List, Dict, Any, Union

class EmbeddingsGenerator:
    """
    A class to generate embeddings from text using OpenAI's embedding models.
    """
    
    def __init__(self, api_key=None, model="text-embedding-ada-002"):
        """
        Initialize the embeddings generator.
        
        Args:
            api_key (str, optional): OpenAI API key. If None, uses the one from environment.
            model (str, optional): The embedding model to use.
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.model = model
        self._client = None
    
    def _get_client(self):
        """Get or create OpenAI client."""
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=self.api_key)
        return self._client
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate an embedding for a single text.
        
        Args:
            text (str): The text to generate an embedding for.
            
        Returns:
            List[float]: The embedding vector.
        """
        # Truncate text if it's too long (OpenAI has token limits)
        truncated_text = self._truncate_text(text)
        
        # Generate embedding
        response = self._get_client().embeddings.create(
            model=self.model,
            input=truncated_text
        )
        
        # Extract the embedding vector
        embedding = response.data[0].embedding
        
        return embedding
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts (List[str]): The texts to generate embeddings for.
            
        Returns:
            List[List[float]]: The embedding vectors.
        """
        # Truncate texts if they're too long
        truncated_texts = [self._truncate_text(text) for text in texts]
        
        # Generate embeddings
        response = self._get_client().embeddings.create(
            model=self.model,
            input=truncated_texts
        )
        
        # Extract the embedding vectors
        embeddings = [data.embedding for data in response.data]
        
        return embeddings
    
    def _truncate_text(self, text: str, max_tokens: int = 8000) -> str:
        """
        Truncate text to a maximum number of tokens.
        This is a simple approximation - OpenAI's tokenization is more complex.
        
        Args:
            text (str): The text to truncate.
            max_tokens (int, optional): Maximum number of tokens.
            
        Returns:
            str: The truncated text.
        """
        # Simple approximation: 1 token ~= 4 characters
        max_chars = max_tokens * 4
        
        if len(text) > max_chars:
            return text[:max_chars]
        
        return text
    
    @staticmethod
    def cosine_similarity(embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate the cosine similarity between two embeddings.
        
        Args:
            embedding1 (List[float]): First embedding vector.
            embedding2 (List[float]): Second embedding vector.
            
        Returns:
            float: Cosine similarity score (0-1).
        """
        # Convert to numpy arrays
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Calculate cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        return dot_product / (norm1 * norm2)