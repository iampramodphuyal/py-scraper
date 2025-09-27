# Web Scraper

This project is a Python-based web scraper that crawls a list of seed URLs, extracts content from the pages, and saves it in Markdown format. It uses `httpx` for efficient asynchronous requests and falls back to `playwright` for dynamic sites.

## Features

- Asynchronous and concurrent crawling
- Configurable crawl depth
- Domain restrictions to stay within a specific scope
- HTML to Markdown conversion
- Retry logic for failed requests
- Support for browser automation for JavaScript-heavy sites

## Getting Started

### Prerequisites

- Python 3.13
- Pipenv

### Installation

1.  **Clone the repository:**
    ```bash
    git clone git@github.com:iampramodphuyal/py-scraper.git
    cd py-scrape
    ```

2.  **Install dependencies using Pipenv:**
    ```bash
    pipenv install
    ```

3. **Install Playwright browsers**
   ```bash
   playwright install
   ```

## Usage

1.  **Add seed URLs:**

    Open the `seeds.txt` file and add the URLs you want to scrape, with each URL on a new line.

2.  **Run the scraper:**
    ```bash
    pipenv run python crawler.py
    ```

The scraper will start crawling the URLs specified in `seeds.txt`. The output will be saved in the `output` directory:

-   `output/MDs/`: Contains the scraped content in Markdown format.
-   `output/index.jsonl`: Contains metadata about the scraped pages.
-   `output/failed_urls.txt`: A log of URLs that failed to be scraped.

## Configuration

You can customize the scraper's behavior by modifying the following variables at the top of `crawler.py`:

-   `CRAWL_DEPTH`: The maximum depth to crawl from the seed URLs.
-   `ALLOWED_DOMAIN`: A list of regex patterns to restrict the crawler to specific domains.
-   `PAGES_PER_SEED`: (Not yet implemented)
-   `MAX_PAGES`: (Not yet implemented)
-   `BLOCK_PATTERNS`: A list of regex patterns to block specific URLs.
-   `BLOCKED_PAGES_FULL`: A list of full URLs to block.
-   `MAX_RETRIES`: The maximum number of retries for a failed request.
-   `MAX_RETRY_DELAY`: The maximum delay between retries.
-   `ENABLE_HEADLESS_BROWSER`: Set to `True` to run the browser in headless mode.
-   `DEFAULT_TIMEOUT`: The default timeout for requests.
-   `MD_CONVERSION`: The Markdown conversion method to use (`simple` or `robust`).
-   `MAX_CONCURRENT_TASK`: The maximum number of concurrent requests.
