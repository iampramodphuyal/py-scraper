from bs4 import BeautifulSoup
import re
from bs4.element import AttributeValueWithCharsetSubstitution
import httpx
import asyncio
from custom_logger import create_logger
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
from playwright.async_api import async_playwright
from typing import Tuple

myLogger = create_logger('py-scraper', 'crawlLog.txt')

MD_FILE_DIR = "output/MDs/"
FAILED_URLS_FILE_PATH="/output/failed_urls.txt"
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
ENABLE_HEADLESS_BROWSER=True
DEFAULT_TIMEOUT=60000 # default timeout for each request either browser or http, sets to be 60s.
ALLOWED_MD_CONVERSIONS = {"simple", "robust"}
MD_CONVERSION = "simple"


def newSession(url:str):
    return retry(
        stop=stop_after_attempt(MAX_RETRIES), 
        wait=wait_exponential(multiplier=1, min=1, max=MAX_RETRY_DELAY),
        before_sleep= lambda retryStatus : myLogger.info(
        f"Retrying {getattr(retryStatus.fn, '__name__', 'unknown')}"
        f" for {retryStatus.args[0]} (attempt {retryStatus.attempt_number}) "
        f" Error Msg: {retryStatus.outcome.exception() if retryStatus.outcome else 'Unknown'}"
        ),
        retry_error_callback=lambda retryStatus: (url, False)
    )



"""
This method checks if the url alligned with block/ALLOWED_DOMAIN case or not. 
Returns True if checked good, else returns False
"""
def check_url(url:str) -> bool:
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


async def sendRequest(url:str, client:httpx.AsyncClient) -> Tuple[str, str|bool]:
    myLogger.info(f"[scrape_url] | Processing To collect via normal request, URL: {url}")

    @newSession(url)
    async def _sendRequest(url:str, client:httpx.AsyncClient):
        response = await client.get(url)
        current_url = str(response.url) if response.url else url
        
        if response.status_code >= 400:
            raise ValueError(f"HTTP status {response.status_code}")
        
        if response.text == "":
            raise ValueError(f"Response Body Content is Empty")
        
        response_body = str(response.text) if response.text else False

        return current_url, response_body

    return await _sendRequest(url, client)


"""
Method to use browser automation to fetch site data
"""
async def loadViaPlaywright(url:str) -> Tuple[str, str|bool]:
    myLogger.info(f"[scrape_url] | Processing To collect via browser automation request, URL: {url}")
    
    @newSession(url)
    async def _sendRequest():
        async with async_playwright() as pl:
            browser = await pl.chromium.launch(headless=ENABLE_HEADLESS_BROWSER)
            page = await browser.new_page()
            response = await page.goto(url, timeout=DEFAULT_TIMEOUT)
            
            if response is None or response.status >= 400:
                await browser.close()
                raise ValueError(f"Request Error: Page Load Error/Invalid Status Code {url}/No Response")
            
            html = await page.content()
            
            current_url = page.url if page.url else url
            
            if html == "":
                await browser.close()
                raise ValueError(f"No Content Found | Status Code: {response.status}")
            
            await browser.close()
            
            return current_url, html
    
    return await _sendRequest()



def save_content_to_md(pageName:str, content:str):
    if MD_CONVERSION not in ALLOWED_MD_CONVERSIONS:
        raise ValueError(f"Invalid conversion: {MD_CONVERSION}")
    if MD_CONVERSION == "simple":
        pass
    pass

def simple_md_conversion(pageName:str, content:str):
    soup = BeautifulSoup(content, "html.parser")

    markdown = soup.get_text("\n")  # just plain text, line breaks preserved, nothing fancy

    with open(f"{MD_FILE_DIR}{pageName}.md", "w", encoding="utf-8") as f:
        f.write(markdown)

    
"""
This Method will returns the urls required to process for each run. 
Each line of the seeds.txt file will be used as an input.
This method returns the list of available urls.
"""
def get_urls() -> list[str]:
    with open("seeds.txt", "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]
    
    return lines


async def process_url(client:httpx.AsyncClient, url:str):
    if not check_url(url):
        return
    
    url, html = await sendRequest(url, client)
    
    if html is False:
        myLogger.warning(f"Failed to fetch url: {url}, Fallback to Browser Automation")
        url, html = await loadViaPlaywright(url)
    
    if html is False or html is True:
        myLogger.warning(f"Request Failed: URL: {url}")
        collect_failed_urls(url)
        return

    soup = BeautifulSoup(html, "html.parser")
    print(soup)



"""
Method to append/save the failed urls to a .txt file.
Each new records are placed in each single line.
"""
def collect_failed_urls(url:str) ->bool:
    with open(FAILED_URLS_FILE_PATH, "a") as f: 
        f.write(url + "\n")
    return True

async def main():
    urls_to_process = get_urls()
    myLogger.info(f"Found: {len(urls_to_process)} urls to process.")
    
    headers = {
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'upgrade-insecure-requests': '1',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'accept-language' : 'en-US,en;q=0.5',
        'Accept-Encoding' : 'gzip, deflate, br, zstd',
        'Connection': 'keep-alive'
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as httpClient:
        tasks = [process_url(httpClient, url) for url in urls_to_process]
        await asyncio.gather(*tasks)
                        

if __name__ == "__main__":
    with open(FAILED_URLS_FILE_PATH, "w") as f:
        f.write("")
    asyncio.run(main())
   
