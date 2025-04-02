import ollama
from app.services.embedder.text_embedder import TextEmbedderInterface
from app.config import logger, settings

class OllamaEmbedder(TextEmbedderInterface):
    def __init__(self):
        """Initialize the Ollama Embedder."""
        logger.info("Initializing Ollama Embedder")
        self.model = settings.EMBEDDING_MODEL

    def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector using Ollama."""
        logger.debug(f"Generating embedding for text using Ollama: {text[:100]}...")
        try:
            response = ollama.embeddings(model=self.model, prompt=text)
            embedding_vector = response["embedding"]
            logger.info("Successfully generated embedding using Ollama")
            return embedding_vector
        except Exception as e:
            logger.error(f"Error generating embedding with Ollama: {e}")
            raise