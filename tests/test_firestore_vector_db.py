import pytest
from unittest.mock import MagicMock, patch
from app.services.vectordb.firestore_vector_db import FirestoreVectorDB
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

@pytest.fixture
def mock_firestore_vector_db():
    with patch("app.services.vectordb.firestore_vector_db.firestore.Client") as mock_client, \
         patch("app.services.vectordb.firestore_vector_db.service_account.Credentials") as mock_creds:
        mock_instance = FirestoreVectorDB(collection_name="test_collection")
        mock_instance.collection = MagicMock()
        yield mock_instance

@patch("app.services.vectordb.firestore_vector_db.embedder.embed_text")
def test_query_text_success(mock_embed_text, mock_firestore_vector_db):
    # Mock inputs
    queries = ["test query 1", "test query 2"]
    query_params = {"param1": "value1"}
    mock_embed_text.side_effect = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    # Mock Firestore behavior
    mock_query_result = MagicMock()
    mock_query_result.to_dict.return_value = {"id": "doc1", "data": "mock_data"}
    mock_firestore_vector_db.collection.find_nearest.return_value.stream.return_value = [mock_query_result]

    # Call the method
    results = mock_firestore_vector_db.query_text(queries, query_params)

    # Assertions
    assert len(results) == 1
    assert results[0] == {"id": "doc1", "data": "mock_data"}
    mock_embed_text.assert_called_with("test query 1")
    mock_firestore_vector_db.collection.find_nearest.assert_called_with(
        vector_field="vector",
        query_vector=Vector([0.1, 0.2, 0.3]),
        distance_measure=DistanceMeasure.EUCLIDEAN,
        limit=10,
    )

def test_query_text_failure(mock_firestore_vector_db):
    # Mock inputs
    queries = ["test query"]
    query_params = None

    # Mock Firestore behavior to raise an exception
    mock_firestore_vector_db.collection.find_nearest.side_effect = Exception("Firestore error")

    # Call the method and assert exception
    with pytest.raises(Exception, match="Firestore error"):
        mock_firestore_vector_db.query_text(queries, query_params)