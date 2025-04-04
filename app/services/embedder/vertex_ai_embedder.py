from time import sleep
from google import genai
from google.genai.types import EmbedContentConfig
from google.oauth2 import service_account

from app.services.embedder.text_embedder import TextEmbedderInterface
from app.config import logger, settings

class VertexAIEmbedder(TextEmbedderInterface):
    def __init__(self):
        """Initialize the Vertex AI client."""
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]

        creds = service_account.Credentials.from_service_account_file(settings.GOOGLE_APPLICATION_CREDENTIALS,scopes=scopes)
        logger.info("Initializing Vertex AI Embedder")
        self.client = genai.Client(vertexai=True,location=settings.GOOGLE_CLOUD_LOCATION,project=settings.GCLOUD_PROJECT_ID,credentials=creds)
        self.model = settings.VERTEX_EMBEDDING_MODEL
        self.dimensionality = settings.EMBEDDING_DIMENSIONALITY
        logger.debug("Using model: %s", self.model)

    def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector using Vertex AI."""
        logger.debug("Generating embedding for text using Vertex AI: %s...", text[:100])
        try:
            response = self.client.models.embed_content(
                model="text-embedding-005",
                contents=[text],
                config=EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=self.dimensionality,
                ),
            )
            sleep(1)
            embedding_vector = response.embeddings[0].values
            logger.info("Successfully generated embedding using Vertex AI")
            return embedding_vector
        except Exception as e:
            logger.error("Error generating embedding with Vertex AI: %s", e)
            raise
