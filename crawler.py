from bs4 import BeautifulSoup
import re
import httpx
import asyncio
from urllib.parse import urljoin 
from custom_logger import create_logger
from tenacity import retry, stop_after_attempt, wait_exponential 
from playwright.async_api import async_playwright
from typing import Tuple
import os
from datetime import datetime
import json

myLogger = create_logger('py-scraper', 'crawlLog.txt')

INDEX_FILE="./output/index.jsonl"
MD_FILE_DIR = "./output/MDs/"
FAILED_URLS_FILE_PATH="./output/failed_urls.txt"
FAILED_URLS_COUNT = 0
CRAWL_DEPTH = 3
ALLOWED_DOMAIN = []
PAGES_PER_SEED = []
MAX_PAGES = []
BLOCKED_PAGES_FULL = []
BLOCK_PATTERNS = []
FAILED_URLS = []
MAX_RETRIES = 5
MAX_RETRY_DELAY=10
ENABLE_HEADLESS_BROWSER=False
DEFAULT_TIMEOUT=60000 # default timeout for each request either browser or http, sets to be 60s.
ALLOWED_MD_CONVERSIONS = {"simple", "robust"}
MD_CONVERSION = "simple"
VISITED_URLS = set()
MAX_CONCURRENT_TASK=2

SEM = asyncio.Semaphore(MAX_CONCURRENT_TASK)

def newSession(url:str):
    """
    A decorator utility which acts as retry-controller, with logs for each retry.
    Contains stop, wait before retry, logs as well as retry callback methods 
    """
    return retry(
        stop=stop_after_attempt(MAX_RETRIES), 
        wait=wait_exponential(multiplier=1, min=1, max=MAX_RETRY_DELAY),
        before_sleep= lambda retryStatus : myLogger.info(
        f"Retrying {getattr(retryStatus.fn, '__name__', 'unknown')}"
        f" for {retryStatus.args[0]} (attempt {retryStatus.attempt_number}) "
        f" Error Msg: {retryStatus.outcome.exception() if retryStatus.outcome else 'Unknown'}"
        ),
        retry_error_callback=lambda retryStatus: (url,False, False)
    )



def check_url(url:str) -> bool:
    """
    This method checks if the url alligned with block/ALLOWED_DOMAIN case or not. 
    Returns True if checked good, else returns False
    """
    
    if url in BLOCKED_PAGES_FULL: 
        myLogger.warning(f"url matches the FULL BLOCK URL : {url}")
        return False

    for blockPattern in BLOCK_PATTERNS:
        if re.search(blockPattern, url):
            myLogger.warning(f"url matches the block pattern : {blockPattern}")
            return False

    for allowedPattern in ALLOWED_DOMAIN:
        if not re.search(allowedPattern, url):
            myLogger.warning(f"URL outside of Allowed Domain. {url}")
            return False
    
    return True


async def sendRequest(url:str, client:httpx.AsyncClient) -> Tuple[str, str|int, str|bool]:
    """
    This method uses httpx to send a get request.
    uses newSession decorator which handles retries as well as retry logs.
    """
    
    myLogger.info(f"[scrape_url] | Processing To collect via normal request, URL: {url}")

    @newSession(url)
    async def _sendRequest(url:str, client:httpx.AsyncClient):
        async with SEM:
            response = await client.get(url)

            current_url = str(response.url) if response.url else url
            
            if response.status_code >= 400:
                raise ValueError(f"HTTP status {response.status_code}")
            
            if response.text == "":
                raise ValueError(f"Response Body Content is Empty")
            
            response_body = response.text if response.text else False
            
            status_code = response.status_code

            if checkIfValidResponse(response.content):
                response_body = False
                raise ValueError(f"Response body is not valid string")
            
            return current_url, status_code, response_body

    return await _sendRequest(url, client)

def checkIfValidResponse(content:bytes) -> bool:
    """
    This checks if the content received via httpx request is properly encoded or binary data.
    Returns True if binary content else returns False
    """
    
    try:
        content.decode("utf-8")
        return False  
    except UnicodeDecodeError:
        return True

async def loadViaPlaywright(url:str) -> Tuple[str,str|int, str|bool]:
    """
    Method to use browser automation to fetch site data
    """
    myLogger.info(f"[scrape_url] | Processing To collect via browser automation request, URL: {url}")
    
    @newSession(url)
    async def _sendRequest(url:str):
        async with async_playwright() as pl:
            async with SEM:
                browser = await pl.chromium.launch(headless=ENABLE_HEADLESS_BROWSER)
                page = await browser.new_page()
                
                response = await page.goto(url, timeout=DEFAULT_TIMEOUT)
                
                await page.wait_for_timeout(10000) # sleep for 10s for load page properly
                
                if response is None or response.status >= 400:
                    await browser.close()
                    raise ValueError(f"Request Error: Page Load Error/Invalid Status Code {url}/No Response")
                
                html = await page.content()
                status_code = response.status 
                current_url = page.url if page.url else url
                
                if html == "":
                    await browser.close()
                    raise ValueError(f"No Content Found | Status Code: {response.status}")
                
                await browser.close()
                
                return current_url,status_code, html
    
    return await _sendRequest(url)


async def file_process(pageName:str, metadata:dict, content:str):
    """
    This method helps to prepare filename for md as well as for metadata save/update
    """
    myLogger.info("[file-process] Processing file i/o...")
    
    metadata["crawled_at"] = datetime.utcnow().isoformat()
    
    file_name = pageName.lower()
    file_name = re.sub(r'[^a-z0-9]+', '_', file_name)
    file_name = file_name.strip('_')
    file_name = f"{file_name}.md"
    save_content_to_md(file_name, content)

    await save_metadata(metadata)


def save_content_to_md(pageName:str, content:str):
    """ 
    This method acts as the entry point for md file creation, 
    will invoke either simple_md_conversion or advanced_md_conversion based on predefined setting
    """
    myLogger.info(f"[save-to-md] Processing to save file to md | pageName:{pageName}")
    if MD_CONVERSION not in ALLOWED_MD_CONVERSIONS:
        raise ValueError(f"Invalid conversion: {MD_CONVERSION}")
    if MD_CONVERSION == "simple":
        simple_md_conversion(pageName, content)
    else:
        advanced_md_conversion(pageName, content)

def simple_md_conversion(pageName:str, content:str):
    """ This method will simply convert a html file to md file by line braking"""
    soup = BeautifulSoup(content, "html.parser")

    markdown = soup.get_text("\n")  # just plain text, line breaks preserved, nothing fancy
    full_path = os.path.join(MD_FILE_DIR, pageName)
    
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(markdown)


def advanced_md_conversion(pageName:str, content:str):
    """This method will use html2text module to convert html to markdown file"""
    import html2text
    
    opts = html2text.HTML2Text()
    opts.ignore_links = False
    opts.ignore_images = True
    opts.body_width = 0
    opts.single_line_break = True

    markdown = opts.handle(content)

    full_path = os.path.join(MD_FILE_DIR, pageName)
    
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(markdown)

def get_urls() -> list[str]:
    """
    This Method will returns the urls required to process for each run. 
    Each line of the seeds.txt file will be used as an input.
    This method returns the list of available urls.
    """

    with open("seeds.txt", "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]
    
    return lines


async def on_request(request: httpx.Request):
    """This is a custom hook for debug requst. it's attached while creating a client"""
    
    myLogger.info("Request headers:")
    for k, v in request.headers.items():
        print(f"{k}: {v}")

async def process_url(client:httpx.AsyncClient, url:str, depth: int):
    if url in VISITED_URLS or depth > CRAWL_DEPTH:
        return
    
    VISITED_URLS.add(url)
    
    if not check_url(url):
        return
   
    myLogger.info(f"Crawling {url} at depth {depth}")
    
    current_url, status_code, html = await sendRequest(url, client)
    
    if html is False:
        myLogger.warning(f"Failed to fetch url: {url}, Fallback to Browser Automation")
        current_url, status_code, html = await loadViaPlaywright(url)
    
    if html is False or html is True:
        myLogger.warning(f"Request Failed: URL: {url}")
        collect_failed_urls(url)
        return

    soup = BeautifulSoup(html, "html.parser")
    
    title = soup.title.get_text(strip=True) if soup.title else ''

    metadata = {
        'url':url,
        'final_url': current_url,
        'status_code': status_code
    }
   
    try:
        await file_process(title,metadata ,html)
    except Exception as e:
        myLogger.error(e)
        
    links = []

    for a in soup.find_all("a"):
        # Check if 'a' is a Tag and has 'href'
        if hasattr(a, "get"):
            href = a.get("href")
            if href:
                links.append(urljoin(url, str(href)))    # print(soup)
    
    if depth < CRAWL_DEPTH:
        tasks = [process_url(client, link, depth + 1) for link in links]
        await asyncio.gather(*tasks)



async def save_metadata(metadata: dict):
    """Append a single metadata dict to JSONL file."""
    
    async with asyncio.Lock():  # ensure thread-safety if concurrent writes
        with open(INDEX_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(metadata, ensure_ascii=False) + "\n")


def collect_failed_urls(url:str) ->bool:
    """
    Method to append/save the failed urls to a .txt file.
    Each new records are placed in each single line.
    """

    with open(FAILED_URLS_FILE_PATH, "a") as f: 
        f.write(url + "\n")
    return True

async def main():
    urls_to_process = get_urls()
    myLogger.info(f"Found: {len(urls_to_process)} urls to process.")
   
    # set default headers
    headers = {
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'upgrade-insecure-requests': '1',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept-language' : 'en-US,en;q=0.5',
        'Accept-Encoding' : 'gzip, deflate, br, zstd',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest':'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'cross-site' 
    }
    
    # Default timeout for all actions are set to 60s
    timeout = httpx.Timeout(
        connect=60.0,  
        read=60.0,
        write=60.0,        
        pool=60.0
    )

    # async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=timeout, http2=True, event_hooks={"request": [on_request]}) as httpClient:
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=timeout, http2=True) as httpClient:
        tasks = [process_url(httpClient, url, 0) for url in urls_to_process]
        await asyncio.gather(*tasks)
                        

if __name__ == "__main__":
    """
    Initialize the failed url file, new for each run.
    """
    with open(os.path.abspath(FAILED_URLS_FILE_PATH), "w") as f:
        f.write("")
    
    with open(os.path.abspath(INDEX_FILE), "w") as f:
        f.write("")
    asyncio.run(main())
    myLogger.info(f"Total Failed URLs: {len(FAILED_URLS)}")
   
