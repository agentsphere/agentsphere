from unittest.mock import patch
import pytest
import responses
import json

from app.services.knowledge import get_knowledge

# Load the expected result from the JSON file
@pytest.fixture
def serper_result():
    with open("tests/resources/serper_result.json", "r") as f:
        return json.load(f)

@pytest.fixture
def apple_result():
    with open("tests/resources/websites/www.apple.com.html", "r") as f:
        return f.read()

@responses.activate
@pytest.mark.asyncio
async def test_get_knowledge(serper_result, apple_result):
    # Mock the HTTP request made by getKnowledge
    responses.add(
        responses.POST,
        "https://google.serper.dev/search",  # Replace with the actual URL used in getKnowledge
        json=serper_result,
        status=200,
    )

    # Patch getPageWithSelenium to return the apple_result HTML content
    with patch("app.services.knowledge.getPageWithSelenium", return_value=apple_result):
        # Call the function being tested
        result = await get_knowledge("apple inc")

        # Assert that the result matches the expected output
        assert result is not None
        assert isinstance(result, dict)  # Assuming the result is a dictionary
        assert result == serper_result  # Compare with the expected result