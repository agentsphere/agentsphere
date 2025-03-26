
import re
import time
from typing import Any
from pymilvus import MilvusClient
import ollama
import logging
from markdownify import markdownify as md
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from duckduckgo_search import DDGS


driver = webdriver.Chrome()
import mongomock
# Use an in-memory MongoDB mock
client = mongomock.MongoClient()
db = client["knowledgedb"]
collection = db["knowledge"]

DOCLIMIT=6000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger=logging.getLogger(__name__)

def emb_text(text):
    response = ollama.embeddings(model="mxbai-embed-large", prompt=text)
    return response["embedding"]

vector = MilvusClient("milvus_demo.db")
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


def perform_web_search(query, max_results=5):
    """Perform a web search using DuckDuckGo and return a list of URLs."""
    logger.info(f"Performing web search for: {query}")
    urls = []
    with DDGS() as ddgs:
        for result in ddgs.text(query, max_results=max_results):
            urls.append(result["href"])  # Extract the URL from the result
    
    logger.info(f"urls: {urls}")
    return list(set(urls))

def getPageWithSelenium(url):
    driver.get(url)

    try:
        WebDriverWait(driver, 3).until(
            lambda d: d.execute_script(
                """
                return window.performance.getEntriesByType('resource')
                .filter(e => ['xmlhttprequest', 'fetch', 'script', 'css', 'iframe', 'beacon', 'other'].includes(e.initiatorType)).length === 0;
                """
            )
        )
    except Exception as e:
        print("Timeout waiting for network requests:", e)
 
    page_source = driver.page_source
    driver.quit()
    return page_source


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
                        print(f"Section {i} (Before first <h2>):\n{pre_tag.strip()[0:100]}\n{'-'*40}")
                        s = BeautifulSoup(pre_tag.strip(), 'html.parser')
                        text = s.get_text(strip=True, separator="\n")
                        if len(text)>DOCLIMIT:
                            splits.append(split(s))
                        else:
                            do = md(str(s))
                            splits.append(do)
                        i += 1
                    if tagC:

                        print(f"Section {i} (Heading and Content):\n{tagC.strip()[0:100]}\n{content.strip()[0:100]}\n{'-'*40}")
                        s = BeautifulSoup(tagC + content, 'html.parser')
                        if len(s.get_text(strip=True))>DOCLIMIT:
                            splits.append(split(s))
                        else:
                            do = md(str(s))
                            logger.info(do)
                            splits.append(do)
        [logger.info(len(s)) for s in splits]
        n = concatenate_strings(splits, DOCLIMIT)

        [logger.info(len(s)) for s in n]
        return n
    else:
        # dont need to be split
        return [doc]

def getDocsFromHTML(html):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'header', "footer", "meta", "svg"]):
        tag.decompose()  # Completely removes the tag from the soup
    text_length_per_parent = {}
    total_length = len(soup.get_text(strip=True))
    if total_length == 0:
        return

    # Iterate over all elements and count text length
    for element in soup.find_all():
        text_length = len(element.get_text(strip=True))
        ratio = text_length / total_length
        if ratio < 0.7: # i dont want 
            break
        ratio=text_length/total_length
        text_length_per_parent[ratio] = element

    _, main = min(text_length_per_parent.items(), key=lambda x: abs(x[0] - 0.8))
    le=len(main.get_text(strip=True))
    if le > DOCLIMIT:
        logger.info(f"break {le}")
        return split(main)
   


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
            data=[{"vector": emb, "query": query.get("query"), "doc_id": query.get("doc_id")}]
        )
        logger.info(f"Successfully added query: {query.get('query')} with doc: {query.get('doc_id')}")
    except Exception as e:
        logger.error(f"Error inserting query into Milvus: {e}")


def load_from_url(url):

    docs = getDocsFromHTML(getPageWithSelenium(url))
    
    from app.services.llm import getQueriesForDocument
    for doc in docs:
        queries = getQueriesForDocument(doc)

        
        logger.info(f"{queries}")
        id = collection.insert_one({"doc": f"{doc}"}).inserted_id
        logger.info(f"id {id} with doc {doc[0:200]}")
        for q in queries.queries:
            addQuery({"query": str(q), "doc_id": str(id)})

    return docs


def getKnowledge(query):
    logger.info(f"Searching for: {query}")

    resultsList = vector.search(
            collection_name="knowledge",
            data=[emb_text(query)],
            limit=10,
            output_fields=["query", "doc_id"],
        )

    logger.info(f"{resultsList}")
    knowledge = f"""For query: {query} 

I have following information available: 
"""
    idsToGet=[]
    for results in resultsList:
        for result in results:
            logger.debug(f"Search result: {result}")
            if result.get("distance") > 0.75:

                idsToGet.append(result.get("entity").get("doc_id"))
    idsUnique = list(set(idsToGet))
    logger.info(f" id  {idsUnique}")
    if idsUnique:
        res = collection.find({"_id": {"$in": idsUnique}})
        for re in res:
            logger.info(re.get("doc"))
            knowledge += re.get("doc")
    else:
        urls = perform_web_search(query)
        for url in urls:
            knowledge += load_from_url(url)
        
    #logger.info(res)
    #logger.info(doc)
    #knowledge += doc.get("doc")
   
    logger.info(knowledge)
    return knowledge


