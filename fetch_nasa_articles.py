# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
import markdownify # A library to convert HTML to Markdown
import os
import re
from urllib.parse import urljoin, urlparse
import time # For adding delays

# --- Configuration ---
NASA_NEWS_URL = "https://www.nasa.gov/news/recently-published/"
PROCESSED_ARTICLES_FILE = "processed_articles.txt"
MARKDOWN_DIR = "articles"

REQUEST_TIMEOUT = 15
REQUEST_DELAY = 1

REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Helper Functions ---
# (Helper functions: get_processed_articles, add_to_processed_articles, sanitize_filename, convert_html_to_markdown - remain the same as before)
def get_processed_articles():
    """Reads the list of processed article URLs."""
    print(f"Attempting to read processed articles from: {PROCESSED_ARTICLES_FILE}")
    if not os.path.exists(PROCESSED_ARTICLES_FILE):
        print(f"{PROCESSED_ARTICLES_FILE} not found. Returning empty set.")
        return set()
    try:
        with open(PROCESSED_ARTICLES_FILE, "r", encoding="utf-8") as f:
            processed = set(line.strip() for line in f)
            print(f"Read {len(processed)} URLs from {PROCESSED_ARTICLES_FILE}")
            return processed
    except IOError as e:
        print(f"Error reading processed articles file: {e}")
        return set()

def add_to_processed_articles(article_url):
    """Adds an article URL to the processed list."""
    print(f"Adding URL to {PROCESSED_ARTICLES_FILE}: {article_url}")
    try:
        with open(PROCESSED_ARTICLES_FILE, "a", encoding="utf-8") as f:
            f.write(article_url + "\n")
    except IOError as e:
        print(f"Error writing to processed articles file: {e}")

def sanitize_filename(title):
    if not title:
        title = "untitled-article"
    title = str(title)
    title = re.sub(r'[^\w\s-]', '', title.lower())
    title = re.sub(r'[-\s]+', '-', title).strip('-_')
    return title if title else "untitled"

def convert_html_to_markdown(html_content_str, base_article_url):
    soup = BeautifulSoup(html_content_str, 'html.parser')
    for img_tag in soup.find_all('img'):
        original_src = img_tag.get('src')
        if not original_src and img_tag.get('data-src'):
            original_src = img_tag.get('data-src')
        if original_src:
            abs_img_url = urljoin(base_article_url, original_src)
            img_tag['src'] = abs_img_url
        else:
            print("  Image tag found with no src or data-src attribute.")
    md = markdownify.markdownify(str(soup), heading_style='atx', bullets='-', strip=['script', 'style'])
    return md

# --- Main Logic ---
def fetch_and_process_articles():
    print(f"Fetching NASA news list from: {NASA_NEWS_URL}")
    try:
        response = requests.get(NASA_NEWS_URL, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        print("Successfully fetched main news page.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching main news page {NASA_NEWS_URL}: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')
    processed_urls = get_processed_articles() # Will print how many it read
    new_articles_found = 0

    article_elements = soup.select('div.hds-content-item h3.hds-content-item-heading a')
    print(f"Found {len(article_elements)} potential article links on the main page.")

    if not article_elements:
        print("No article links found using selector. Page structure might have changed or selector is incorrect.")
        # Save HTML for debugging if needed
        # with open("debug_main_page_content.html", "w", encoding="utf-8") as f_debug:
        # f_debug.write(response.text)
        # print("Saved main page HTML to debug_main_page_content.html")
        return

    for item_link in reversed(article_elements):
        article_url_relative = item_link.get('href')
        if not article_url_relative:
            print("Found an item link with no href, skipping.")
            continue

        article_url_absolute = urljoin(NASA_NEWS_URL, article_url_relative)
        print(f"Checking article: {article_url_absolute}")

        if article_url_absolute in processed_urls:
            # print(f"Skipping already processed: {article_url_absolute}") # Verbose, uncomment if needed
            continue
        
        print(f"--- PROCESSING NEW ARTICLE: {article_url_absolute} ---")
        new_articles_found += 1 # Increment here to count attempts for new articles

        try:
            time.sleep(REQUEST_DELAY)
            article_response = requests.get(article_url_absolute, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            article_response.raise_for_status()
            article_response.encoding = article_response.apparent_encoding 
            print(f"  Successfully fetched article content for: {article_url_absolute}")
        except requests.exceptions.RequestException as e:
            print(f"  Error fetching article {article_url_absolute}: {e}")
            new_articles_found -= 1 # Decrement if fetch fails
            continue

        article_soup = BeautifulSoup(article_response.content, 'html.parser')

        title_tag = article_soup.find('h1')
        article_title_raw = title_tag.get_text(strip=True) if title_tag else "Untitled Article"

        meta_desc_tag = article_soup.find('meta', attrs={'name': 'description'})
        description_raw = meta_desc_tag['content'].strip() if meta_desc_tag and meta_desc_tag.get('content') else ""
        
        article_slug = sanitize_filename(article_title_raw)
        print(f"  Article Title: '{article_title_raw}', Slug: '{article_slug}'")

        content_element = article_soup.find('div', class_='wysiwyg')
        if not content_element:
            print(f"  'div.wysiwyg' not found for {article_url_absolute}. Trying <article> tag.")
            content_element = article_soup.find('article')
            if content_element:
                h1_in_content = content_element.find('h1')
                if h1_in_content and h1_in_content.get_text(strip=True) == article_title_raw:
                    h1_in_content.decompose()
            else:
                print(f"  Could not find main content element (div.wysiwyg or article) for {article_url_absolute}. Skipping.")
                # Save article HTML for debugging if needed
                # with open(f"debug_article_{article_slug}.html", "w", encoding="utf-8") as f_debug_art:
                #    f_debug_art.write(article_response.text)
                # print(f"  Saved article HTML to debug_article_{article_slug}.html for inspection.")
                new_articles_found -= 1 # Decrement if content extraction fails
                continue
        
        article_html_content_str = str(content_element)
        print(f"  Converting '{article_title_raw}' to Markdown...")
        markdown_body = convert_html_to_markdown(article_html_content_str, article_url_absolute)

        md_file_name = f"{article_slug}.md"
        if not os.path.exists(MARKDOWN_DIR):
            print(f"  Creating MARKDOWN_DIR: {MARKDOWN_DIR}")
            os.makedirs(MARKDOWN_DIR)
        md_file_path = os.path.join(MARKDOWN_DIR, md_file_name)

        full_md_content = f"---\n"
        processed_title_for_yaml = article_title_raw.replace('"', '\u201C') 
        full_md_content += f"title: \"{processed_title_for_yaml}\"\n"
        if description_raw:
            processed_description_for_yaml = description_raw.replace('"', '\u201C')
            full_md_content += f"description: \"{processed_description_for_yaml}\"\n"
        full_md_content += f"source_url: {article_url_absolute}\n"
        full_md_content += f"---\n\n"
        full_md_content += f"# {article_title_raw}\n\n"
        if description_raw:
            full_md_content += f"*Summary: {description_raw}*\n\n"
        full_md_content += f"**Source:** [{article_title_raw}]({article_url_absolute})\n\n"
        full_md_content += "---\n\n"
        full_md_content += markdown_body

        try:
            with open(md_file_path, "w", encoding="utf-8") as f:
                f.write(full_md_content)
            print(f"  SUCCESS: Saved Markdown to: {md_file_path}")
            add_to_processed_articles(article_url_absolute) # Will print confirmation
        except IOError as e:
            print(f"  Error writing markdown file {md_file_path}: {e}")
            new_articles_found -= 1 # Decrement if save fails

    # Correct final count based on successful processing and saving
    print(f"\nScript finished. Attempted to process {new_articles_found} new articles.")
    if new_articles_found > 0:
        print(f"Check the 'Commit and Push Changes' step in GitHub Actions logs to see if files were committed.")
    else:
        print("No new articles were successfully processed and saved.")


if __name__ == "__main__":
    print("Script execution started.")
    if not os.path.exists(MARKDOWN_DIR):
        # This check is also inside the loop, but good to have here too.
        # However, git add articles/ will fail if articles/ never gets created.
        # The script creates it if it finds an article.
        # To ensure `git add articles/` doesn't fail if no articles are found and the dir isn't created:
        print(f"Ensuring {MARKDOWN_DIR} directory exists before script logic.")
        os.makedirs(MARKDOWN_DIR, exist_ok=True) 
        
    fetch_and_process_articles()
    print("Script execution finished.")
