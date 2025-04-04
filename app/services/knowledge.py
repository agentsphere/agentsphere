
from datetime import datetime
import json
import re
from urllib.parse import urlparse, urlunparse
import uuid
from bson import ObjectId
from markdownify import markdownify as md
from pydantic import BaseModel, Field
from fp.fp import FreeProxy
import requests
from bs4 import BeautifulSoup

from app.models.models import Chat, Message, Roles
from app.config import settings, logger, embedder, knowledge_collection, query_collection, config_collection, web_search_cache_collection, TZINFO

from app.services.browser import get_page_with_selenium
from app.services.helpers import generate_hash

blacklist_entry = config_collection.find_one({"KEY": "BLACKLIST_SEARCH"})
BLACKLIST = blacklist_entry.get("urls", None) if blacklist_entry else settings.BLACKLIST_SEARCH

main_content_entry = config_collection.find_one({"KEY": "MAIN_CONTENT_SELECTOR"})
MAIN_CONTENT_SELECTORS = main_content_entry.get("selectors", []) if main_content_entry else []

WEBSEARCH_URL = settings.WEBSEARCH_URL
DOC_LIMIT=settings.DOC_LIMIT
PAGE_LIMIT=settings.PAGE_LIMIT

def get_free_proxy():
    return FreeProxy().get()

collection = knowledge_collection


def clean_url(url: str) -> str:
    """
    Removes query parameters and anchors from a URL, leaving only the main part and path.

    Args:
        url (str): The original URL.

    Returns:
        str: The cleaned URL.
    """
    parsed_url = urlparse(url)
    # Reconstruct the URL without query and fragment
    cleaned_url = urlunparse(parsed_url._replace(query="", fragment=""))
    return cleaned_url

def perform_web_search(query):
    res = web_search_cache_collection.find_one({"query": query})
    res_urls = res["urls"] if res else []
    logger.info("websearchurl %s", WEBSEARCH_URL)
    if res_urls:
        logger.info("Found %s in cache", query)
        return res_urls
    payload = json.dumps({
        "q": f"{query}"
    })
    headers = {
        'X-API-KEY': settings.SERPER_API_KEY,
        'Content-Type': 'application/json'
    }

    response = requests.request("POST", WEBSEARCH_URL, headers=headers, data=payload, timeout=10)
    data = response.json()

    # Now extract links from 'organic' results
    all_links = []
    if data is None:
        logger.warning("No data found in response.")
        return []
    for item in data.get("organic", []):
        all_links.append(clean_url(item.get("link")))
        for sitelink in item.get("sitelinks", []):
            all_links.append(clean_url(sitelink.get("link")))

    logger.info(all_links)

    web_search_cache_collection.insert({"query": query, "urls": all_links})
    return list(set(all_links))

def concatenate_strings(lst, max_char):
    result = []
    current_string = ""

    for s in lst:
        if len(current_string) + len(s) <= max_char:
            current_string += s  # Concatenate the string
        else:
            result.append(current_string)  # Save the previous concatenated string
            current_string = s  # Start a new string

    if current_string:  # Append any remaining string
        result.append(current_string)

    return result

def split(doc):
    le=len(doc.get_text(strip=True))
    if le > DOC_LIMIT:
        splits=[]
        logger.info("break %s", le)

        for tag in ["h1", "h2", "h3", "h4"]:
            count = len(doc.find_all(tag))
            if count > 1:
                logger.info("finding %s %s", tag, count)
                # Regular expression pattern
                pattern = re.compile(
                    r'(?s)(.*?)'             # Text before the first <h2>
                    rf'(?:(<{tag}.*?</{tag}>))'     # Each <h2> tag
                    rf'(.*?)(?=(?:<{tag})|\Z)'   # Content after <h2> up to the next <h2> or end
                )
                # Find all matches
                matches = pattern.findall(str(doc))

                # Process and display the sections
                for i, (pre_tag, tag_c, content) in enumerate(matches, start=1):
                    if pre_tag.strip():
                        s = BeautifulSoup(pre_tag.strip(), 'html.parser')
                        text = s.get_text(strip=True, separator="\n")
                        if len(text)>DOC_LIMIT:
                            new_splits = split(s)   # new_splits is a list
                            splits.extend(new_splits)
                        else:
                            do = md(str(s))
                            splits.append(do)
                        i += 1
                    if tag_c:
                        s = BeautifulSoup(tag_c + content, 'html.parser')
                        if len(s.get_text(strip=True))>DOC_LIMIT:
                            new_splits = split(s)   # new_splits is a list
                            splits.extend(new_splits)
                        else:
                            do = md(str(s))
                            logger.info(do)
                            splits.append(do)
        for s in splits:
            logger.info(len(s))
        return concatenate_strings(splits, DOC_LIMIT)
    return [md(str(doc))]

def get_docs_from_html(html, url) -> list:
    if html is None or html == "":
        logger.info("No HTML content found.")
        return None
    logger.info("html %d", len(html))
    soup = BeautifulSoup(html, 'html.parser')

    matched_selector = None
    longest_match_length = 0

    for entry in MAIN_CONTENT_SELECTORS:
        prefix = entry.get("url", "")
        selector = entry.get("selector", "")

        # Check if the URL starts with the prefix and if it's the longest match so far
        if url.startswith(prefix) and len(prefix) > longest_match_length:
            matched_selector = selector
            longest_match_length = len(prefix)


    if matched_selector:
        logger.info("Matched selector: %s", matched_selector)
        main_content = soup.select_one(matched_selector)
        if main_content:
            extracted_html = str(main_content)
            soup = BeautifulSoup(extracted_html, 'html.parser')
            le=len(soup.get_text(strip=True))
            if le > DOC_LIMIT:
                logger.info("Doc larger than max size need to chunk it %s", le)
                return split(soup)
            logger.info("Doc smaller than max size just return it")
            return [md(str(soup))]
        logger.warning("Should not be here No content found with selector: %s", matched_selector)
    else:
        for tag in soup(['script', 'style', 'header', "footer", "meta", "svg"]):
            tag.decompose()  # Completely removes the tag from the soup

        total_length = len(soup.get_text(strip=True))
        logger.info("Total length of text content: %d", total_length)
        if total_length > PAGE_LIMIT:
            logger.warning("Website text larger than max size, propably junk skip and add to blacklist {url}")
            BLACKLIST.append(url)
            return []
        text_length_per_parent = {}
        if total_length == 0:
            logger.info("No text content found.")
            return []

        # Iterate over all elements and count text length
        for element in soup.find_all():
            text_length = len(element.get_text(strip=True))
            ratio = text_length / total_length
            if ratio < 0.7: # i dont want Elements with less than 70% of the main page (rather take 100%)
                break
            ratio=text_length/total_length
            text_length_per_parent[ratio] = element

        # Get the main text element which is closest to 80% of the total text length, no heading, footer, etc.
        _, main = min(text_length_per_parent.items(), key=lambda x: abs(x[0] - 0.8))
        le=len(main.get_text(strip=True))
        if le > DOC_LIMIT:
            logger.info("Doc larger than max size need to chunk it %s", le)
            return split(main)
        logger.info("Doc smaller than max size just return it")
        return [md(str(main))]

def delete_vector_with_condition(condition: str):
    query_collection.delete(document=condition)

def delete_vector_entries(ids: list[str]):
    query_collection.delete({"ids":ids})

def remove_entries_by_doc_ids(ids: list, url: str):
    """
    Remove all entries from the Milvus collection where 'doc_id' is in the provided list of IDs.

    Args:
        collection_name (str): The name of the Milvus collection.
        ids (list): A list of `doc_id` values to remove.
    """
    if not ids:
        logger.info("No IDs provided for deletion.")
        return

    # Create a filter condition for the delete operation
    delete_vector_with_condition(condition=f"doc_id in {ids}")

    collection.delete_many({"_id": {"$in": ids}})
    logger.info("Deleted old entries for URL in mongodb: %s", url)
    logger.info("Deleted entries with doc_id in %s in vectordb.", ids)


def add_query(query):
    """Adds a query to the Milvus vector database with proper error handling."""
    try:
        if not query or not query.get("query") or not query.get("doc_id"):
            logger.warning("Invalid query data provided. Skipping insertion.")
            return

        logger.info("Generating embedding for query: %s", query.get("query"))
        emb = embedder.embed_text(query.get("query"))

        logger.info("Inserting query into collection: %s -> %s", query.get('query'), query.get('doc_id'))
        query_collection.insert([{"vector": emb, "query": query.get("query"), "doc_id": query.get("doc_id"), "id": str(uuid.uuid4())}])
        logger.info("Successfully added query: %s with doc: %s", query.get('query'), query.get('doc_id'))
    except (ValueError, TypeError, RuntimeError) as e:  # Replace with specific exceptions
        logger.error("Error inserting query into Milvus: %s", e)


def load_from_url(url, query):

    docs = get_docs_from_html(get_page_with_selenium(url), url)
    if docs is None:
        logger.warning("Failed to load documents from URL: %s", url)
        return None
    from app.services.llm import get_queries_for_document

    for doc in docs:
        queries = get_queries_for_document(doc, query)

        logger.info("%s", queries)
        doc_id=uuid.uuid4()
        c= knowledge_collection.insert({"doc_id": str(doc_id),"hash_md5": generate_hash(doc) ,"doc": f"{doc}","url": f"{url}","timestamp": f"{datetime.now(TZINFO)}" }) 
        logger.info("id %s with doc %s", doc_id, doc[0:200])
        for q in queries.queries:
            add_query({"query": str(q), "doc_id": str(doc_id)})

    return docs

def update_knowledge(url: str):
    """
    Update the knowledge database with new information from a URL.
    """
    # Find Existing id
    results = collection.find({"url": url})
    ids = []
    for result in results:
        logger.info(result.get("_id"))
        ids.append(result.get("_id"))

    logger.info("Loading knowledge from URL: %s", url)

    #load_from_url(url)
    #remove_entries_by_doc_ids(ids, url)

def search_vector(query):
    logger.info("Searching vector for: %s", query)
    results_list = query_collection.query_text([query]
        #limit=40,
        #output_fields=["query", "doc_id","id"],
    )
    logger.info("Raw search results: %s", results_list)
    ids_to_get = {}
    res_filtered = []
    # Collect doc_id and distance for each result
    for results in results_list:
        for result in results:
            logger.debug("Search result: %s", result)
            distance = result.get("distance")
            if distance > 0.8:  # Filter results based on distance threshold
                element = result.get("entity")
                doc_id = element.get("doc_id")
                res_filtered.append(element)
                if ids_to_get.get(doc_id, None) is None:
                    ids_to_get[doc_id] = {"doc_id": doc_id, "distance": distance}
                elif ids_to_get[doc_id]["distance"] < distance:
                    ids_to_get[doc_id] = {"doc_id": doc_id, "distance": distance}

    unique_ids = list(ids_to_get.values())

    # Sort by distance in descending order
    unique_ids = sorted(unique_ids, key=lambda x: x["distance"], reverse=True)

    # Get the top 2 results
    top_ids = [entry["doc_id"] for entry in unique_ids]
    max_distance = unique_ids[0]["distance"] if unique_ids else 0

    logger.info("Top 2 IDs: %s with max distance: %s", top_ids, max_distance)
    return res_filtered, top_ids


class KnowledgeSummary(BaseModel):
    """
    Represents a summary of knowledge retrieved in response to a query.

    Attributes:
        answer (str): The generated answer or summary based on the knowledge source.
        is_irrelevant (bool): Indicates whether the provided documentation is irrelevant to the query.
    """
    answer: str = Field(..., description="The generated answer or knowledge summary.")
    is_irrelevant: bool = Field(False, description="True if the provided docmentation is not relevant for query.")


async def summarize_knowledge(query: str, knowledge: str, chat: Chat):
    from app.services.llm_wrapper import llm_call_wrapper

    return await llm_call_wrapper(
        response_format=KnowledgeSummary,
        messages=[
    Message(role=Roles.SYSTEM.value, content=(
        "You are a helpful and detail-oriented research assistant. "
        "Your job is to extract and explain relevant information from internal documentation in a clear, comprehensive, and self-contained manner. "
        "Your responses should read as if YOU know the answer, not as if you are pointing to the documentation. "
        "Do not mention the documentation at all. Do not make anything up."
    )).model_dump(),
    Message(role=Roles.USER.value, content=f'''You are given internal documentation below. Use only the information it contains to answer the query.

--- DOCUMENTATION START ---
{knowledge}
--- DOCUMENTATION END ---

Now, answer the following query:

{query}

Your response must:
- Contain all relevant details available in the documentation.
- Be fully self-contained (do not say "as per the documentation").
- Be clear and structured if possible (bullets, sections).
- If the documentation does not contain relevant information, respond with:
    "is_irrelevant": true

Respond only with the final answer object in JSON format:
{{
    "answer": "<your complete answer>",
    "is_irrelevant": false | true
}}
''').model_dump()
        ])

async def get_knowledge(query: str, chat: Chat = None, pre_text: bool = True):
    if not query:
        logger.warning("Invalid query or chat object provided.")
        return None
    logger.info("Searching for: %s", query)
    entities, ids_unique = search_vector(query)

    hit = False
    knowledge = []
    if pre_text:
        knowledge.append(f"&&& BEGIN DOCUMENTATION for query: {query} &&&")
    if len(ids_unique)>0:
        logger.info("First search in vectordb hit")
        logger.info("Found %d results for query: %s", len(ids_unique), query)
        doc_texts = []
        for doc_id in ids_unique:
            ids_current = [entity["id"] for entity in entities if entity["doc_id"] == doc_id]
            res = collection.find_one({"doc_id": doc_id})
            if res:
                doc_texts.append(res["doc"])
            else:
                logger.warning("No result found for doc_id: %s", doc_id)
                logger.info("Delete the vector entry with doc_id %s", doc_id)
                delete_vector_entries(ids=ids_current)
        if doc_texts:
            summary = await summarize_knowledge(query, "n ".join(doc_texts), chat)
            logger.info("Summary: %s", summary)
            if summary.is_irrelevant:
                knowledge.append(f"No relevant information found for your query: {query}. please try again with a different query. maybe splitting your original query in multiple yield better results.")
                logger.warning("No relevant information found.")
            #    #delete entities
            #    delete_vector_entries(ids=ids_current)
            else:
                knowledge.append(summary.answer)
    else:

        logger.info("First search in vectordb no hit")

        urls = perform_web_search(query)
        for url in urls:
            # if url in mongo
            res = collection.find_one({"url": url})
            if res:
                logger.info("Found URL in knowledge database, but no entries in vectordb website might be crap, or needs to be re checked for query strings: %s", url)
            else:
                if chat:
                    await chat.set_message(f"Searching in {url} \n\n")
                load_from_url(url, query)
                break
        entities, ids_unique = search_vector(query)
        hit=False

        if len(ids_unique)>0:
            logger.info("Second search in vectordb hit")
            logger.info("Found %d results for query: %s", len(ids_unique), query)
            for doc_id in ids_unique:
                ids_current = [entity["id"] for entity in entities if entity["doc_id"] == doc_id]
                res = collection.find_one({"doc_id": doc_id})
                if res:
                    doc_texts.append(res["doc"])
                else:
                    logger.warning("No result found for doc_id: %s", doc_id)
                    logger.info("Delete the vector entry with doc_id %s", doc_id)
                    delete_vector_entries(ids=ids_current)
            if doc_texts:
                summary = await summarize_knowledge(query, "n ".join(doc_texts), chat)
                logger.info("Summary: %s", summary)
                if summary.is_irrelevant:
                    knowledge.append(f"No relevant information found for your query: {query}. please try again with a different query. maybe splitting your original query in multiple yield better results.")
                    logger.warning("No relevant information found.")
                #    #delete entities
                #    delete_vector_entries(ids=ids_current)
                else:
                    knowledge.append(summary.answer)
        else:
            logger.warning("No relevant information found.")
            knowledge.extend(await get_knowledge(query, chat, False))
            #return ["apple"]
    if pre_text:
        knowledge.append("\n\n&&& END DOCUMENTATION &&&")

    return knowledge
