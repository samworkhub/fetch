# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
import markdownify
import os
import re
from urllib.parse import urljoin, urlparse # urljoin might still be needed for images if we link them
import time
import feedparser # New import

# --- Configuration ---
# === NEW: RSS Feed URL ===
NASA_RSS_URL = "https://www.nasa.gov/feed/" # Example: Breaking News
# You might want to find a more general "recently published" equivalent if this one is too specific.
# Check https://www.nasa.gov/rss-feeds/ for the best option.

PROCESSED_ARTICLES_FILE = "processed_articles.txt"
MARKDOWN_DIR = "articles"

REQUEST_TIMEOUT = 15
REQUEST_DELAY = 1 # Delay before fetching full article HTML

REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Helper Functions (get_processed_articles, add_to_processed_articles, sanitize_filename are mostly the same) ---

def get_processed_articles():
    # (Same as before)
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
    # (Same as before)
    print(f"Adding URL to {PROCESSED_ARTICLES_FILE}: {article_url}")
    try:
        with open(PROCESSED_ARTICLES_FILE, "a", encoding="utf-8") as f:
            f.write(article_url + "\n")
    except IOError as e:
        print(f"Error writing to processed articles file: {e}")

def sanitize_filename(title):
    # (Same as before)
    if not title:
        title = "untitled-article"
    title = str(title)
    title = re.sub(r'[^\w\s-]', '', title.lower())
    title = re.sub(r'[-\s]+', '-', title).strip('-_')
    return title if title else "untitled"

# convert_html_to_markdown can remain similar, as it converts the *full article HTML* to markdown
def convert_html_to_markdown(html_content_str, base_article_url):
    # (Same as before - this converts the full article page, not the RSS summary)
    soup = BeautifulSoup(html_content_str, 'html.parser')
    for img_tag in soup.find_all('img'):
        original_src = img_tag.get('src')
        if not original_src and img_tag.get('data-src'):
            original_src = img_tag.get('data-src')
        if original_src:
            abs_img_url = urljoin(base_article_url, original_src) # Ensure full URL
            img_tag['src'] = abs_img_url
        else:
            print("  Image tag found with no src or data-src attribute.")
    md = markdownify.markdownify(str(soup), heading_style='atx', bullets='-', strip=['script', 'style'])
    return md

# --- Main Logic (Heavily Refactored for RSS) ---

def fetch_and_process_articles_from_rss():
    print(f"Fetching NASA RSS feed from: {NASA_RSS_URL}")
    
    # Parse the RSS feed
    feed_data = feedparser.parse(NASA_RSS_URL, agent=REQUEST_HEADERS['User-Agent'])

    if feed_data.bozo: # feedparser sets bozo to 1 if there was an error parsing
        print(f"Error parsing RSS feed: {feed_data.bozo_exception}")
        # You could try to save feed_data.feed (the raw response) for debugging if this happens
        # with open("debug_rss_feed_error.xml", "w", encoding="utf-8") as f_debug_rss:
        #     f_debug_rss.write(requests.get(NASA_RSS_URL, headers=REQUEST_HEADERS).text) # Re-fetch for raw text
        # print("Saved raw feed content to debug_rss_feed_error.xml")
        return

    if not feed_data.entries:
        print("No entries found in the RSS feed.")
        return

    print(f"Found {len(feed_data.entries)} entries in the RSS feed.")
    processed_urls = get_processed_articles()
    new_articles_found = 0

    # Entries are often in reverse chronological order (newest first)
    # If you want to process older ones first to keep commit history chronological:
    for entry in reversed(feed_data.entries):
        article_url = entry.get('link')
        if not article_url:
            print("Skipping entry with no link.")
            continue

        print(f"Checking RSS entry: {article_url}")

        if article_url in processed_urls:
            # print(f"Skipping already processed: {article_url}")
            continue
        
        print(f"--- PROCESSING NEW ARTICLE FROM RSS: {article_url} ---")
        
        article_title_from_rss = entry.get('title', "Untitled Article")
        # RSS description can be a summary or the full content. We'll use it as a summary.
        description_from_rss = ""
        if 'summary' in entry:
            # Clean up HTML from summary if it exists
            summary_soup = BeautifulSoup(entry.summary, 'html.parser')
            description_from_rss = summary_soup.get_text(separator=' ', strip=True)
        elif 'description' in entry: # Some feeds use 'description'
            summary_soup = BeautifulSoup(entry.description, 'html.parser')
            description_from_rss = summary_soup.get_text(separator=' ', strip=True)


        # Now, fetch the full article page from article_url to get complete content
        print(f"  Fetching full article content from: {article_url}")
        try:
            time.sleep(REQUEST_DELAY)
            article_response = requests.get(article_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            article_response.raise_for_status()
            article_response.encoding = article_response.apparent_encoding 
        except requests.exceptions.RequestException as e:
            print(f"  Error fetching full article content for {article_url}: {e}")
            continue # Skip this article

        article_soup = BeautifulSoup(article_response.content, 'html.parser')

        # We can use the title from RSS, or try to get a more definitive one from the H1 of the page
        h1_tag = article_soup.find('h1')
        article_title_from_page = h1_tag.get_text(strip=True) if h1_tag else article_title_from_rss
        if not article_title_from_page: # Fallback if H1 is empty or not found
            article_title_from_page = article_title_from_rss


        # For description, we can prioritize meta description from the page, fallback to RSS summary
        meta_desc_tag = article_soup.find('meta', attrs={'name': 'description'})
        description_from_page = meta_desc_tag['content'].strip() if meta_desc_tag and meta_desc_tag.get('content') else description_from_rss


        article_slug = sanitize_filename(article_title_from_page)
        print(f"  Article Title: '{article_title_from_page}', Slug: '{article_slug}'")

        # Content extraction from the full article page (same as before)
        content_element = article_soup.find('div', class_='wysiwyg')
        if not content_element:
            print(f"  'div.wysiwyg' not found on page {article_url}. Trying <article> tag.")
            content_element = article_soup.find('article')
            if content_element:
                h1_in_content = content_element.find('h1')
                if h1_in_content and h1_in_content.get_text(strip=True) == article_title_from_page:
                    h1_in_content.decompose() # Remove duplicate H1
            else:
                print(f"  Could not find main content element (div.wysiwyg or article) on page {article_url}. Skipping.")
                continue
        
        article_html_content_str = str(content_element)
        print(f"  Converting '{article_title_from_page}' HTML content to Markdown...")
        markdown_body = convert_html_to_markdown(article_html_content_str, article_url)

        # --- Prepare Markdown file content (same as before) ---
        md_file_name = f"{article_slug}.md"
        if not os.path.exists(MARKDOWN_DIR):
            print(f"  Creating MARKDOWN_DIR: {MARKDOWN_DIR}")
            os.makedirs(MARKDOWN_DIR)
        md_file_path = os.path.join(MARKDOWN_DIR, md_file_name)

        full_md_content = f"---\n"
        processed_title_for_yaml = article_title_from_page.replace('"', '\u201C') 
        full_md_content += f"title: \"{processed_title_for_yaml}\"\n"
        if description_from_page:
            processed_description_for_yaml = description_from_page.replace('"', '\u201C')
            full_md_content += f"description: \"{processed_description_for_yaml}\"\n"
        full_md_content += f"source_url: {article_url}\n"
        # You could add publication date from RSS:
        # if 'published_parsed' in entry and entry.published_parsed:
        #    pub_date = time.strftime('%Y-%m-%d %H:%M:%S %Z', entry.published_parsed)
        #    full_md_content += f"date: {pub_date}\n"
        # elif 'updated_parsed' in entry and entry.updated_parsed:
        #    upd_date = time.strftime('%Y-%m-%d %H:%M:%S %Z', entry.updated_parsed)
        #    full_md_content += f"date: {upd_date}\n" # or published_date

        full_md_content += f"---\n\n"
        full_md_content += f"# {article_title_from_page}\n\n"
        if description_from_page:
            full_md_content += f"*Summary: {description_from_page}*\n\n"
        full_md_content += f"**Source:** [{article_title_from_page}]({article_url})\n\n"
        full_md_content += "---\n\n"
        full_md_content += markdown_body

        try:
            with open(md_file_path, "w", encoding="utf-8") as f:
                f.write(full_md_content)
            print(f"  SUCCESS: Saved Markdown to: {md_file_path}")
            add_to_processed_articles(article_url)
            new_articles_found += 1 
        except IOError as e:
            print(f"  Error writing markdown file {md_file_path}: {e}")

    print(f"\nRSS Script finished. Successfully processed and saved {new_articles_found} new articles.")
    if new_articles_found == 0:
        print("No new articles found in the RSS feed that weren't already processed.")


if __name__ == "__main__":
    print("RSS Script execution started.")
    if not os.path.exists(MARKDOWN_DIR):
        os.makedirs(MARKDOWN_DIR, exist_ok=True) 
        
    fetch_and_process_articles_from_rss() # Call the new function
    print("RSS Script execution finished.")
