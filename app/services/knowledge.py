
import asyncio
from datetime import datetime
import hashlib
import json
import re
from typing import Any
import uuid
from bson import ObjectId
from pydantic import BaseModel, Field
from pymilvus import MilvusClient
import ollama
from app.models.models import Chat, Message, Roles
from app.services.queue import add_to_queue
from markdownify import markdownify as md
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from app.config import settings, tzinfo, logger
from duckduckgo_search import DDGS
from fp.fp import FreeProxy

BLACKLIST=["geeksforgeeks.org", "youtube.com"]
import mongomock
# Use an in-memory MongoDB mock
client = mongomock.MongoClient()
db = client["knowledgedb"]
collection = db["knowledge"]

DOCLIMIT=25000

def get_free_proxy():
    proxy = FreeProxy().get()
    return proxy


def emb_text(text):
    response = ollama.embeddings(model="mxbai-embed-large", prompt=text)
    return response["embedding"]

vector = MilvusClient(settings.MILVUSDBFILE)
if vector.has_collection(collection_name="knowledge"):
    logger.info("Dropping existing collection:knowledge")
    vector.drop_collection(collection_name="knowledge")

if not vector.has_collection(collection_name="knowledge"):
    logger.info("creating new collection: knowledge")
    vector.create_collection(
        collection_name="knowledge",
        auto_id=True,
        dimension=1024,
    )

import requests
from bs4 import BeautifulSoup

url = "https://google.serper.dev/search"

def perform_web_search(query):
    payload = json.dumps({
        "q": f"{query}"
    })
    headers = {
    'X-API-KEY': settings.SERPER_API_KEY,
    'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    data = response.json()

    # Now extract links from 'organic' results
    all_links = []

    for item in data.get("organic", []):
        all_links.append(item.get("link"))
        for sitelink in item.get("sitelinks", []):
            all_links.append(sitelink.get("link"))



    logger.info(all_links)
    return all_links
def perform_web_searchDDGS(query, max_results=10):
    """Perform a web search using DuckDuckGo and return a list of URLs."""
    logger.info(f"Performing web search for: {query}")
    urls = []
    tries=0
    while tries<5:
        tries+=1
        try:
            proxy=get_free_proxy()
            proxies={"http": proxy, "https": proxy}
            with DDGS() as ddgs:
                for result in ddgs.text(query, max_results=max_results):
                    url = result["href"]  # Extract the URL from the result
                    if not any(blacklisted in url for blacklisted in BLACKLIST):  # Exclude blacklisted URLs
                        urls.append(url)
                    else:
                        logger.info(f"URL on blacklist: {url}")

            
            logger.info(f"urls: {urls}")
            return list(set(urls))
        except Exception as e:
            logger.error(f"Error performing web search: {e}")
        
    logger.error(f"Failed to perform web search after {tries} attempts.")
    return urls
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth
from webdriver_manager.chrome import ChromeDriverManager


def create_stealth_driver():
    """
    Initializes a Chrome WebDriver with stealth configurations to reduce detection.

    Returns:
        webdriver.Chrome: A configured instance of Chrome WebDriver.
    """
    chrome_options = Options()

    # Browser window and behavior
    chrome_options.add_argument("--start-maximized")
    
    # Uncomment for headless mode if needed (new mode is better for stealth)
    chrome_options.add_argument("--headless=new")

    # Custom user-agent to mimic a real browser
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")

    # Disable automation-related flags to avoid detection
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--disable-notifications")

    # Initialize Chrome WebDriver
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )

    # Apply stealth techniques
    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc. (Apple)",
        platform="MacIntel",
        webgl_vendor="Google Inc. (Apple)",
        renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Max, Unspecified Version)",
        fix_hairline=True,
    )

    return driver


def getPageWithSelenium(url: str) -> str:
    """getPageWithSelenium
    Fetches the HTML content of a page using a stealth-enabled Selenium driver.

    Args:
        url (str): The target webpage URL.

    Returns:
        str: HTML content of the loaded page.
    """
    driver = create_stealth_driver()

    try:
        driver.get(url)
        WebDriverWait(driver, 3).until(
            lambda d: d.execute_script(
                """
                return window.performance.getEntriesByType('resource')
                .filter(e => ['xmlhttprequest', 'fetch', 'script', 'css', 'iframe', 'beacon', 'other'].includes(e.initiatorType)).length === 0;
                """
            )
        )
        page_source = driver.page_source
        logger.info(f"Could load page {url}, not None")
        logger.info(f"Page source {len(page_source)}")
        return page_source
    except Exception as e:
        print("Timeout waiting for network requests:", e)
        page_source = driver.page_source
        logger.info(f"Getting page even if not fully loaded {url}")
        logger.info(f"Page source {len(page_source)}")            
        return page_source
    finally:
        driver.quit()
    return None



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
    if le > DOCLIMIT:
        splits=[]
        logger.info(f"break {le}")
        splitsTags= ["h1", "h2", "h3", "h4"]

        for tag in splitsTags:
            count = len(doc.find_all(tag))
            if count > 1:
                logger.info(f"finding {tag} {count}")
                
                # Regular expression pattern
                pattern = re.compile(
                    r'(?s)(.*?)'             # Text before the first <h2>
                    rf'(?:(<{tag}.*?</{tag}>))'     # Each <h2> tag
                    rf'(.*?)(?=(?:<{tag})|\Z)'   # Content after <h2> up to the next <h2> or end
                )

                # Find all matches
                matches = pattern.findall(str(doc))


                # Process and display the sections
                for i, (pre_tag, tagC, content) in enumerate(matches, start=1):
                    
                    if pre_tag.strip():
                        #print(f"Section {i} (Before first <h2>):\n{pre_tag.strip()[0:100]}\n{'-'*40}")
                        s = BeautifulSoup(pre_tag.strip(), 'html.parser')
                        text = s.get_text(strip=True, separator="\n")
                        if len(text)>DOCLIMIT:
                            new_splits = split(s)   # new_splits is a list
                            splits.extend(new_splits)  
                        else:
                            do = md(str(s))
                            splits.append(do)
                        i += 1
                    if tagC:

                        #print(f"Section {i} (Heading and Content):\n{tagC.strip()[0:100]}\n{content.strip()[0:100]}\n{'-'*40}")
                        s = BeautifulSoup(tagC + content, 'html.parser')
                        if len(s.get_text(strip=True))>DOCLIMIT:
                            new_splits = split(s)   # new_splits is a list
                            splits.extend(new_splits)  
                        else:
                            do = md(str(s))
                            logger.info(do)
                            splits.append(do)
        [logger.info(len(s)) for s in splits]
        n = concatenate_strings(splits, DOCLIMIT)

        [logger.info(f"{len(s)}" ) for s in n]
        return n
    else:
        # dont need to be split
        return [md(str(doc))]

def getDocsFromHTML(html, url):
    if html is None or html == "":
        logger.info("No HTML content found.")
        return None
    soup = BeautifulSoup(html, 'html.parser')
    total_length = len(soup.get_text(strip=True))
    if total_length > 120000:
        logger.warning("Website text larger than max size, propably junk skip and add to blacklist {url}")
        BLACKLIST.append(url)
        return None
    for tag in soup(['script', 'style', 'header', "footer", "meta", "svg"]):
        tag.decompose()  # Completely removes the tag from the soup
    text_length_per_parent = {}
    if total_length == 0:
        logger.info("No text content found.")
        return None

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
    if le > DOCLIMIT:
        logger.info(f"Doc larger than max size need to chunk it {le}")
        return split(main)
    else:
        logger.info(f"Doc smaller than max size just return it")        
        return [md(str(main))]
   
def delete_vector_with_condition(condition: str):
    vector.delete(collection_name="knowledge", filter=condition)

   
def delete_vector_entries(ids: list[str]):
    vector.delete(collection_name="knowledge", ids=ids)


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
    logger.info(f"Deleted old entries for URL in mongodb: {url}")
    logger.info(f"Deleted entries with doc_id in {ids}  in vectordb.")


def addQuery(query):
    """Adds a query to the Milvus vector database with proper error handling."""
    try:
        if not query or not query.get("query") or not query.get("doc_id"):
            logger.warning("Invalid query data provided. Skipping insertion.")
            return

        logger.info(f"Generating embedding for query: {query.get('query')}")
        emb = emb_text(query.get("query"))

        logger.info(f"Inserting query into collection: {query.get('query')} -> {query.get('doc_id')}")
        vector.insert(
            collection_name="knowledge",
            data=[{"vector": emb, "query": query.get("query"), "doc_id": query.get("doc_id"), "id": str(uuid.uuid4())}],
        )
        logger.info(f"Successfully added query: {query.get('query')} with doc: {query.get('doc_id')}")
    except Exception as e:
        logger.error(f"Error inserting query into Milvus: {e}")

def generate_hash(doc: str) -> str:
    """
    Generate a unique hash based on the document content and URL.
    """
    hash_input = doc.encode('utf-8')
    return hashlib.md5(hash_input).hexdigest()


def load_from_url(url, query):

    docs = getDocsFromHTML(getPageWithSelenium(url), url)
    if docs is None:
        return None
    from app.services.llm import getQueriesForDocument

    for doc in docs:
        queries = getQueriesForDocument(doc, query)

        
        logger.info(f"{queries}")
        id = collection.insert_one({"hash_md5": generate_hash(doc) ,"doc": f"{doc}","url": f"{url}","timestamp": f"{datetime.now(tzinfo)}" }).inserted_id
        logger.info(f"id {id} with doc {doc[0:200]}")
        for q in queries.queries:
            addQuery({"query": str(q), "doc_id": str(id)})

    return docs

def update_knowledge(url: str):
    """
    Update the knowledge database with new information from a URL.
    """
    
    # Find Existing id
    existingEntries = collection.find({"url": url})
    res = collection.find({"url": url})
    ids = []
    for re in res:
        logger.info(re.get("_id"))
        ids.append(re.get("_id"))

    logger.info(f"Loading knowledge from URL: {url}")

    load_from_url(url)
    remove_entries_by_doc_ids(ids, url) 




def searchVector(query):
    logger.info(f"Searching vector for: {query}")
    resultsList = vector.search(
        collection_name="knowledge",
        data=[emb_text(query)],
        limit=40,
        output_fields=["query", "doc_id","id"],
    )


    logger.info(f"Raw search results: {resultsList}")
    idsToGet = {}
    resFiltered = []

    # Collect doc_id and distance for each result
    for results in resultsList:
        for result in results:
            logger.debug(f"Search result: {result}")
            distance = result.get("distance")
            if distance > 0.8:  # Filter results based on distance threshold
                element = result.get("entity")
                doc_id = element.get("doc_id")
                resFiltered.append(element) 
                if idsToGet.get(doc_id, None) is None:
                    idsToGet[doc_id] = {"doc_id": doc_id, "distance": distance}
                elif idsToGet[doc_id]["distance"] < distance:
                    idsToGet[doc_id] = {"doc_id": doc_id, "distance": distance}

    unique_ids = list(idsToGet.values())

    # Sort by distance in descending order
    unique_ids = sorted(unique_ids, key=lambda x: x["distance"], reverse=True)

    # Get the top 2 results
    top_ids = [entry["doc_id"] for entry in unique_ids]
    max_distance = unique_ids[0]["distance"] if unique_ids else 0

    logger.info(f"Top 2 IDs: {top_ids} with max distance: {max_distance}")
    return resFiltered, top_ids


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
    from app.services.litellm_wrapper import litellm_call

    return await litellm_call(
        oneShot=True,
        chat=chat,
        response_format=KnowledgeSummary,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are a research specialist").model_dump(),
            Message(role=Roles.USER.value, content=f'''Given the following Documentation: 
                
                    {knowledge}
                    
                    _____________________________________git ___

                    Dont make stuff up. Answer the query with information from the documentation.
                    If the documentation is irrelevant for the query set is_irrelevant to true. 
                    Do not reference the documentation in your answer, provide all the information needed which is relevant to the query in YOUR answer.
                    query:
                    {query}
            ''').model_dump()
        ])
   





async def getKnowledge(query: str, chat: Chat, preText: bool = True):
    if not query or not chat:
        logger.warning("Invalid query or chat object provided.")
        return None
    logger.info(f"Searching for: {query}")
    entities, idsUnique = searchVector(query)

    hit = False
    knowledge = []
    if preText:
        knowledge.append(f"&&& BEGIN DOCUMENTATION for query: {query} &&&")
    if len(idsUnique)>0:
        logger.info(f"Found {len(idsUnique)} results for query: {query}")
        for id in idsUnique:
            res = collection.find_one({"_id": ObjectId(id)})
            summary = await summarize_knowledge(query, res["doc"], chat)
            if summary.is_irrelevant:
                #delete entities
                ids = [entity["id"] for entity in entities if entity["doc_id"] == id]
                delete_vector_entries(ids=ids)
            else:
                hit = True
                knowledge.append(summary.answer)
        if not hit:
            logger.warning("No relevant information found.")
            knowledge.extend(await getKnowledge(query, chat, False))
    else:

        urls = perform_web_search(query)
        for url in urls:
            # if url in mongo
            res = collection.find_one({"url": url})
            if res:
                logger.info(f"Found URL in knowledge database, but no entries in vectordb website might be crap, or needs to be re checked for query strings: {url}")
            else:
                await chat.set_message(f"Searching in {url} \n\n")
                load_from_url(url, query)
                break
        entities, idsUnique = searchVector(query)
        hit=False
        
        if len(idsUnique)>0:
            logger.info(f"Found {len(idsUnique)} results for query: {query}")
            for id in idsUnique:
                res = collection.find_one({"_id": ObjectId(id)})
                summary = await summarize_knowledge(query, res["doc"], chat)
                if summary.is_irrelevant:
                    #delete entities
                    ids = [entity["id"] for entity in entities if entity["doc_id"] == id]
                    delete_vector_entries(ids=ids)
                else:
                    hit = True
                    knowledge.append(summary.answer)
            if not hit:
                logger.warning("No hit no relevant information found.")
                knowledge.extend(await getKnowledge(query, chat, False))
        else:
            logger.warning("No relevant information found.")
            knowledge.extend(await getKnowledge(query, chat, False))
    if preText:
        knowledge.append("\n\n&&& END DOCUMENTATION &&&")

    
    return knowledge