from bson import ObjectId
import pytest
from app.services.knowledge import collection, vector, addQuery, searchVector, emb_text

def test_mongodb_and_vectordb_integration():
    # Step 1: Insert a document into MongoDB
    doc_content = "This is a test document for knowledge base."
    doc_id = collection.insert_one({"doc": doc_content}).inserted_id
    assert doc_id is not None, "Failed to insert document into MongoDB"

    # Step 2: Save a query to the vector database
    query_text = "test document"
    addQuery({"query": query_text, "doc_id": str(doc_id)})

    # Step 3: Search the vector database with the query
    search_results = searchVector(query_text)
    assert len(search_results) > 0, "No results found in vector database"
    assert str(doc_id) in search_results, "Inserted document ID not found in vector database search results"

    # Step 4: Retrieve the document from MongoDB using the returned ID
    retrieved_doc = collection.find_one({"_id": doc_id})
    assert retrieved_doc is not None, "Failed to retrieve document from MongoDB"
    assert retrieved_doc["doc"] == doc_content, "Retrieved document content does not match the inserted content"

    print(f"Test passed: Retrieved document content: {retrieved_doc['doc']}")

    from bson import ObjectId

def test_mongodb_and_vectordb_integration_Id():
    # Step 1: Insert a document into MongoDB
    doc_content = "This is a test document for knowledge base."
    doc_id = collection.insert_one({"doc": doc_content}).inserted_id
    assert doc_id is not None, "Failed to insert document into MongoDB"

    # Convert doc_id to string and back to ObjectId
    doc_id_str = str(doc_id)
    doc_id_object = ObjectId(doc_id_str)

    # Step 4: Retrieve the document from MongoDB using the ObjectId
    retrieved_doc = collection.find_one({"_id": doc_id_object})
    assert retrieved_doc is not None, "Failed to retrieve document from MongoDB"
    assert retrieved_doc["doc"] == doc_content, "Retrieved document content does not match the inserted content"

    print(f"Test passed: Retrieved document content: {retrieved_doc['doc']}")