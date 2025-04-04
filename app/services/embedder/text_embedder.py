from abc import ABC, abstractmethod
from typing import List

class TextEmbedderInterface(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """
        Generate an embedding vector for the given text.

        Args:
            text (str): The input text to embed.

        Returns:
            List[float]: The embedding vector.
        """
