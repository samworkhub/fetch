import requests
from bs4 import BeautifulSoup
import markdownify # A library to convert HTML to Markdown
import os
import re
from urllib.parse import urljoin, urlparse

# --- Configuration ---
NASA_NEWS_URL = "https://www.nasa.gov/news/recently-published/"
# File to store URLs of already processed articles to avoid duplicates
PROCESSED_ARTICLES_FILE = "processed_articles.txt"
# Directory in your GitHub repo to store markdown files
MARKDOWN_DIR = "articles"
# Optional: Directory in your GitHub repo to store images (if downloading)
IMAGES_DIR = os.path.join(MARKDOWN_DIR, "images")

# --- Helper Functions ---

def get_processed_articles():
    """Reads the list of processed article URLs."""
    if not os.path.exists(PROCESSED_ARTICLES_FILE):
        return set()
    with open(PROCESSED_ARTICLES_FILE, "r") as f:
        return set(line.strip() for line in f)

def add_to_processed_articles(article_url):
    """Adds an article URL to the processed list."""
    with open(PROCESSED_ARTICLES_FILE, "a") as f:
        f.write(article_url + "\n")

def sanitize_filename(title):
    """Sanitizes a title to be a valid filename."""
    title = re.sub(r'[^\w\s-]', '', title.lower())
    title = re.sub(r'[-\s]+', '-', title).strip('-')
    return title

def download_image(img_url, article_slug):
    """
    Downloads an image and saves it locally.
    Returns the new local path for the markdown.
    """
    if not img_url.startswith(('http:', 'https:')):
        print(f"Skipping non-absolute image URL: {img_url}")
        return None # Or try to resolve it if it's relative to nasa.gov

    try:
        response = requests.get(img_url, stream=True)
        response.raise_for_status()

        img_name = os.path.basename(urlparse(img_url).path)
        # Ensure image name is somewhat unique if multiple articles use same image name
        local_img_folder = os.path.join(IMAGES_DIR, article_slug)
        if not os.path.exists(local_img_folder):
            os.makedirs(local_img_folder)

        local_img_path = os.path.join(local_img_folder, img_name)

        with open(local_img_path, 'wb') as f:
            for chunk in response.iter_content(8192):
                f.write(chunk)

        # Return a relative path for the markdown file
        # e.g., images/article-slug/image.jpg
        return os.path.join("images", article_slug, img_name)
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {img_url}: {e}")
        return None # Return original URL as fallback or skip
    except Exception as e:
        print(f"Error processing image {img_url}: {e}")
        return None

def convert_html_to_markdown(html_content, base_url, article_slug, download_images_flag=True):
    """
    Converts HTML to Markdown, handling images.
    Base_url is for resolving relative image paths if any.
    Article_slug is used for creating a dedicated image folder.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    if download_images_flag:
        for img_tag in soup.find_all('img'):
            original_src = img_tag.get('src')
            if original_src:
                # Ensure image URL is absolute
                abs_img_url = urljoin(base_url, original_src)
                print(f"Processing image: {abs_img_url}")
                local_image_path = download_image(abs_img_url, article_slug)
                if local_image_path:
                    img_tag['src'] = local_image_path
                else:
                    # Fallback: use original URL if download fails
                    img_tag['src'] = abs_img_url
                    print(f"Failed to download or link image locally: {abs_img_url}. Using original URL.")
            else:
                print("Image tag found with no src attribute.")

    # Convert the (potentially modified) HTML to Markdown
    # You might need to experiment with options for markdownify for best results
    # e.g., markdownify.markdownify(str(soup), heading_style=markdownify. एटएक्स)
    md = markdownify.markdownify(str(soup), heading_style='atx', bullets='-')
    return md

# --- Main Logic ---

def fetch_and_process_articles():
    print("Fetching NASA news page...")
    try:
        response = requests.get(NASA_NEWS_URL)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching main news page: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')
    processed_urls = get_processed_articles()
    new_articles_found = False

    # **IMPORTANT**: The selectors below are EXAMPLES and WILL LIKELY NEED ADJUSTMENT
    # You need to inspect `https://www.nasa.gov/news/recently-published/`
    # and find the correct HTML elements that contain the article links and titles.
    # Common patterns involve looking for <div>s with specific classes, then <a> tags within them.

    # Example (you MUST adapt this based on current NASA HTML structure):
    # article_elements = soup.select('div.list-item article > div.content > h3 > a')
    # Or for a more modern NASA layout, it might be something like:
    article_elements = soup.select('article .hds-content-item-heading a') # Hypothetical selector

    if not article_elements:
        print("No article elements found. Check your BeautifulSoup selectors for the main news page.")
        return

    print(f"Found {len(article_elements)} potential articles on the main page.")

    for item in reversed(article_elements): # Process older first, or remove reversed()
        article_url_relative = item.get('href')
        if not article_url_relative:
            continue

        article_url_absolute = urljoin(NASA_NEWS_URL, article_url_relative)

        if article_url_absolute in processed_urls:
            print(f"Skipping already processed: {article_url_absolute}")
            continue

        print(f"\nFetching new article: {article_url_absolute}")
        try:
            article_response = requests.get(article_url_absolute)
            article_response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching article {article_url_absolute}: {e}")
            continue

        article_soup = BeautifulSoup(article_response.content, 'html.parser')

        # **IMPORTANT**: Adjust these selectors for the individual article page
        # Title
        title_tag = article_soup.find('h1') # Often a good guess for the main title
        article_title = title_tag.get_text(strip=True) if title_tag else "Untitled Article"

        # Description (Meta description or first paragraph)
        meta_desc_tag = article_soup.find('meta', attrs={'name': 'description'})
        description = meta_desc_tag['content'] if meta_desc_tag else ""

        # Content (This is often the hardest part to get right)
        # Look for a main content div, e.g., <article>, <div class="article-body">
        # The selector here is CRITICAL and specific to NASA's article layout.
        # content_element = article_soup.find('div', class_='article-content-body') # Example
        # A more generic approach, if there's a main article tag:
        content_element = article_soup.find('article')
        if not content_element:
            # Fallback to a common content div class if 'article' isn't the main container
            content_element = article_soup.find('div', id='wysiwyg-content') # Another example for NASA pages
            if not content_element:
                print(f"Could not find main content element for {article_url_absolute}. Skipping.")
                continue

        article_html_content = str(content_element)
        article_slug = sanitize_filename(article_title)

        print(f"Converting '{article_title}' to Markdown...")
        markdown_content = convert_html_to_markdown(article_html_content, article_url_absolute, article_slug, download_images_flag=True)

        # Prepare Markdown file content
        md_file_name = f"{article_slug}.md"
        if not os.path.exists(MARKDOWN_DIR):
            os.makedirs(MARKDOWN_DIR)
        md_file_path = os.path.join(MARKDOWN_DIR, md_file_name)

        full_md_content = f"# {article_title}\n\n"
        if description:
            full_md_content += f"**Description:** {description}\n\n"
        full_md_content += f"Source: [{article_url_absolute}]({article_url_absolute})\n\n---\n\n"
        full_md_content += markdown_content

        with open(md_file_path, "w", encoding="utf-8") as f:
            f.write(full_md_content)
        print(f"Saved: {md_file_path}")

        add_to_processed_articles(article_url_absolute)
        new_articles_found = True

    if not new_articles_found:
        print("No new articles found to process.")

if __name__ == "__main__":
    if not os.path.exists(IMAGES_DIR): # Ensure images base directory exists if we plan to download
        os.makedirs(IMAGES_DIR)
    fetch_and_process_articles()
