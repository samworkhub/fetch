import requests
from bs4 import BeautifulSoup
import markdownify # A library to convert HTML to Markdown
import os
import re
from urllib.parse import urljoin, urlparse
import time # For adding delays

# --- Configuration ---
NASA_NEWS_URL = "https://www.nasa.gov/news/recently-published/"
# File to store URLs of already processed articles to avoid duplicates
PROCESSED_ARTICLES_FILE = "processed_articles.txt"
# Directory in your GitHub repo to store markdown files
MARKDOWN_DIR = "articles"
# IMAGES_DIR is no longer needed as we are not downloading images

REQUEST_TIMEOUT = 15 # seconds
REQUEST_DELAY = 1    # second, delay between fetching full articles

# Standard User-Agent
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Helper Functions ---

def get_processed_articles():
    """Reads the list of processed article URLs."""
    if not os.path.exists(PROCESSED_ARTICLES_FILE):
        return set()
    try:
        with open(PROCESSED_ARTICLES_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f)
    except IOError as e:
        print(f"Error reading processed articles file: {e}")
        return set()

def add_to_processed_articles(article_url):
    """Adds an article URL to the processed list."""
    try:
        with open(PROCESSED_ARTICLES_FILE, "a", encoding="utf-8") as f:
            f.write(article_url + "\n")
    except IOError as e:
        print(f"Error writing to processed articles file: {e}")

def sanitize_filename(title):
    """Sanitizes a title to be a valid filename."""
    if not title:
        title = "untitled-article"
    title = str(title)
    title = re.sub(r'[^\w\s-]', '', title.lower())
    title = re.sub(r'[-\s]+', '-', title).strip('-_')
    return title if title else "untitled"

def convert_html_to_markdown(html_content_str, base_article_url):
    """
    Converts HTML to Markdown, ensuring image URLs are absolute and point to original sources.
    base_article_url is for resolving relative image paths if any.
    """
    soup = BeautifulSoup(html_content_str, 'html.parser')

    for img_tag in soup.find_all('img'):
        original_src = img_tag.get('src')
        # Handle data-src or other lazy loading attributes if necessary
        if not original_src and img_tag.get('data-src'):
            original_src = img_tag.get('data-src')
        
        if original_src:
            # Ensure image URL is absolute
            abs_img_url = urljoin(base_article_url, original_src)
            img_tag['src'] = abs_img_url # Use the absolute original URL
            # print(f"  Image URL set to: {abs_img_url}") # Uncomment for debugging
        else:
            print("  Image tag found with no src or data-src attribute.")

    # Convert the (potentially modified) HTML to Markdown
    md = markdownify.markdownify(str(soup), heading_style='atx', bullets='-', strip=['script', 'style'])
    return md

# --- Main Logic ---

def fetch_and_process_articles():
    print(f"Fetching NASA news list from: {NASA_NEWS_URL}")
    try:
        response = requests.get(NASA_NEWS_URL, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching main news page {NASA_NEWS_URL}: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')
    processed_urls = get_processed_articles()
    new_articles_found = 0

    # Selector for article links on the main news page.
    article_elements = soup.select('div.hds-content-item h3.hds-content-item-heading a')

    if not article_elements:
        print("No article links found on the main news page. Check CSS selector 'div.hds-content-item h3.hds-content-item-heading a'.")
        print("Page structure might have changed.")
        return

    print(f"Found {len(article_elements)} potential articles on the main page.")

    for item_link in reversed(article_elements): # Process older first (chronological order in repo)
        article_url_relative = item_link.get('href')
        if not article_url_relative:
            continue

        article_url_absolute = urljoin(NASA_NEWS_URL, article_url_relative)

        if article_url_absolute in processed_urls:
            # print(f"Skipping already processed: {article_url_absolute}")
            continue

        print(f"\nFetching new article: {article_url_absolute}")
        try:
            time.sleep(REQUEST_DELAY) # Be polite to the server
            article_response = requests.get(article_url_absolute, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            article_response.raise_for_status()
            article_response.encoding = article_response.apparent_encoding 
        except requests.exceptions.RequestException as e:
            print(f"Error fetching article {article_url_absolute}: {e}")
            continue

        article_soup = BeautifulSoup(article_response.content, 'html.parser')

        # Title
        title_tag = article_soup.find('h1')
        article_title = title_tag.get_text(strip=True) if title_tag else "Untitled Article"

        # Description (Meta description)
        meta_desc_tag = article_soup.find('meta', attrs={'name': 'description'})
        description = meta_desc_tag['content'].strip() if meta_desc_tag and meta_desc_tag.get('content') else ""
        
        article_slug = sanitize_filename(article_title)

        # Content: Prioritize specific content divs.
        content_element = article_soup.find('div', class_='wysiwyg')
        if not content_element:
            print(f"  Specific 'div.wysiwyg' not found for {article_url_absolute}. Trying to find <article> tag.")
            content_element = article_soup.find('article')
            if content_element:
                # If using <article>, remove H1 if it's a duplicate of the main page title
                h1_in_content = content_element.find('h1')
                if h1_in_content and h1_in_content.get_text(strip=True) == article_title:
                    h1_in_content.decompose()

        if not content_element:
            print(f"  Could not find main content element for {article_url_absolute}. Skipping.")
            continue

        article_html_content_str = str(content_element)

        print(f"  Converting '{article_title}' to Markdown...")
        markdown_body = convert_html_to_markdown(
            article_html_content_str,
            article_url_absolute # Pass base_url for resolving relative image paths
        )

        # Prepare Markdown file content
        md_file_name = f"{article_slug}.md"
        if not os.path.exists(MARKDOWN_DIR):
            os.makedirs(MARKDOWN_DIR)
        md_file_path = os.path.join(MARKDOWN_DIR, md_file_name)

        # Construct full Markdown content with metadata (YAML frontmatter)
        full_md_content = f"---\n"
        full_md_content += f"title: \"{article_title.replace('"', '“')}\"\n"
        if description:
            full_md_content += f"description: \"{description.replace('"', '“')}\"\n"
        full_md_content += f"source_url: {article_url_absolute}\n"
        full_md_content += f"---\n\n"
        full_md_content += f"# {article_title}\n\n"
        if description:
            full_md_content += f"*Summary: {description}*\n\n"
        full_md_content += f"**Source:** [{article_title}]({article_url_absolute})\n\n"
        full_md_content += "---\n\n"
        full_md_content += markdown_body

        try:
            with open(md_file_path, "w", encoding="utf-8") as f:
                f.write(full_md_content)
            print(f"  Saved: {md_file_path}")
            add_to_processed_articles(article_url_absolute)
            new_articles_found += 1
        except IOError as e:
            print(f"  Error writing markdown file {md_file_path}: {e}")


    if new_articles_found > 0:
        print(f"\nSuccessfully processed {new_articles_found} new articles.")
    else:
        print("\nNo new articles found to process.")

if __name__ == "__main__":
    # Ensure markdown base directory exists
    if not os.path.exists(MARKDOWN_DIR):
        os.makedirs(MARKDOWN_DIR)
    # No need to create IMAGES_DIR as images are not downloaded
        
    fetch_and_process_articles()
