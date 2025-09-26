import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin, urlparse
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from datetime import datetime
import xml.etree.ElementTree as ET
from urllib.robotparser import RobotFileParser

# Page config
st.set_page_config(page_title="Ultra Frog SEO Crawler", layout="wide", page_icon="🐸")

# Initialize session state
if 'crawl_data' not in st.session_state:
    st.session_state.crawl_data = []
if 'crawling' not in st.session_state:
    st.session_state.crawling = False
if 'stop_crawling' not in st.session_state:
    st.session_state.stop_crawling = False

class UltraFrogCrawler:
    def __init__(self, max_urls=100000, ignore_robots=False, crawl_scope="subfolder"):
        self.max_urls = max_urls
        self.ignore_robots = ignore_robots
        self.crawl_scope = crawl_scope
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Ultra Frog SEO Crawler/2.0 (https://ultrafrog.seo)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        # Connection pooling for speed
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=1
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        self.robots_cache = {}
        self.base_domain = None
        self.base_path = None
    
    def set_base_url(self, url):
        parsed = urlparse(url)
        self.base_domain = parsed.netloc
        self.base_path = parsed.path.rstrip('/')
    
    def should_crawl_url(self, url):
        parsed = urlparse(url)
        
        if self.crawl_scope == "exact":
            return url == urljoin(f"https://{self.base_domain}", self.base_path)
        elif self.crawl_scope == "subdomain":
            return parsed.netloc == self.base_domain or parsed.netloc.endswith("." + self.base_domain)
        else:  # subfolder
            return (parsed.netloc == self.base_domain and 
                   parsed.path.startswith(self.base_path))
    
    def can_fetch(self, url):
        if self.ignore_robots:
            return True
        
        try:
            domain = urlparse(url).netloc
            if domain not in self.robots_cache:
                try:
                    rp = RobotFileParser()
                    rp.set_url(f"https://{domain}/robots.txt")
                    rp.read()
                    self.robots_cache[domain] = rp
                except:
                    self.robots_cache[domain] = None
            
            if self.robots_cache[domain] is None:
                return True
            
            return self.robots_cache[domain].can_fetch('*', url)
        except:
            return True
    
    def extract_sitemap_urls(self, sitemap_url):
        urls = []
        try:
            response = self.session.get(sitemap_url, timeout=8)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                namespaces = {'sitemap': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                
                sitemapindex = root.findall('.//sitemap:sitemap', namespaces)
                if sitemapindex:
                    for sitemap in sitemapindex:
                        loc = sitemap.find('sitemap:loc', namespaces)
                        if loc is not None:
                            urls.extend(self.extract_sitemap_urls(loc.text))
                else:
                    url_elements = root.findall('.//sitemap:url', namespaces)
                    for url_elem in url_elements:
                        loc = url_elem.find('sitemap:loc', namespaces)
                        if loc is not None:
                            urls.append(loc.text)
                            
        except Exception as e:
            st.error(f"Error parsing sitemap: {e}")
        
        return urls
        
    def extract_page_data(self, url):
        try:
            response = self.session.get(url, timeout=8, allow_redirects=True)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Basic SEO data extraction (optimized)
            title = soup.find('title')
            title_text = title.get_text().strip() if title else ""
            
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            meta_desc_text = meta_desc.get('content', '') if meta_desc else ""
            
            canonical = soup.find('link', attrs={'rel': 'canonical'})
            canonical_url = canonical.get('href') if canonical else ""
            
            meta_robots = soup.find('meta', attrs={'name': 'robots'})
            robots_content = meta_robots.get('content', '') if meta_robots else ""
            
            # Open Graph tags
            og_title = soup.find('meta', attrs={'property': 'og:title'})
            og_desc = soup.find('meta', attrs={'property': 'og:description'})
            og_image = soup.find('meta', attrs={'property': 'og:image'})
            
            # Twitter Card tags
            twitter_title = soup.find('meta', attrs={'name': 'twitter:title'})
            twitter_desc = soup.find('meta', attrs={'name': 'twitter:description'})
            twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
            
            # Header tags (all levels)
            h1_tags = [h1.get_text().strip() for h1 in soup.find_all('h1')]
            h2_tags = [h2.get_text().strip() for h2 in soup.find_all('h2')]
            h3_tags = [h3.get_text().strip() for h3 in soup.find_all('h3')]
            h4_tags = [h4.get_text().strip() for h4 in soup.find_all('h4')]
            
            # Links analysis (optimized)
            internal_links = []
            external_links = []
            base_domain = urlparse(url).netloc
            
            for link in soup.find_all('a', href=True):
                href = urljoin(url, link['href'])
                link_text = link.get_text().strip()[:100]  # Limit text length
                if urlparse(href).netloc == base_domain:
                    internal_links.append({'url': href, 'anchor_text': link_text})
                else:
                    external_links.append({'url': href, 'anchor_text': link_text})
            
            # Images analysis (optimized)
            images = []
            for img in soup.find_all('img'):
                img_src = urljoin(url, img.get('src', ''))
                images.append({
                    'src': img_src,
                    'alt': img.get('alt', ''),
                    'title': img.get('title', ''),
                    'width': img.get('width', ''),
                    'height': img.get('height', '')
                })
            
            # Schema markup (fast extraction)
            scripts = soup.find_all('script', type='application/ld+json')
            schema_types = []
            for script in scripts:
                try:
                    if script.string:
                        schema_data = json.loads(script.string)
                        if isinstance(schema_data, dict) and '@type' in schema_data:
                            schema_types.append(schema_data['@type'])
                        elif isinstance(schema_data, list):
                            for item in schema_data:
                                if isinstance(item, dict) and '@type' in item:
                                    schema_types.append(item['@type'])
                except:
                    pass
            
            # Performance indicators
            css_files = len(soup.find_all('link', attrs={'rel': 'stylesheet'}))
            js_files = len(soup.find_all('script', src=True))
            
            # Word count (optimized)
            text_content = soup.get_text()
            word_count = len(text_content.split())
            
            # Redirect chain with proper status codes
            redirect_chain = []
            if hasattr(response, 'history') and response.history:
                for i, resp in enumerate(response.history):
                    redirect_chain.append({
                        'step': i + 1,
                        'from_url': resp.url,
                        'to_url': resp.headers.get('location', ''),
                        'status_code': resp.status_code,
                        'redirect_type': '301 Permanent' if resp.status_code == 301 else 
                                       '302 Temporary' if resp.status_code == 302 else 
                                       f'{resp.status_code} Redirect'
                    })
            
            return {
                'url': response.url,
                'original_url': url,
                'status_code': response.status_code,
                'title': title_text,
                'title_length': len(title_text),
                'meta_description': meta_desc_text,
                'meta_desc_length': len(meta_desc_text),
                'canonical_url': canonical_url,
                'meta_robots': robots_content,
                'h1_tags': '; '.join(h1_tags),
                'h1_count': len(h1_tags),
                'h2_tags': '; '.join(h2_tags),
                'h2_count': len(h2_tags),
                'h3_tags': '; '.join(h3_tags),
                'h3_count': len(h3_tags),
                'h4_tags': '; '.join(h4_tags),
                'h4_count': len(h4_tags),
                'word_count': word_count,
                'response_time': response.elapsed.total_seconds(),
                'content_length': len(response.content),
                'internal_links_count': len(internal_links),
                'external_links_count': len(external_links),
                'internal_links': internal_links,
                'external_links': external_links,
                'images': images,
                'image_count': len(images),
                'images_without_alt': len([img for img in images if not img['alt']]),
                'schema_types': '; '.join(schema_types),
                'schema_count': len(schema_types),
                'redirect_chain': redirect_chain,
                'redirect_count': len(redirect_chain),
                'css_files': css_files,
                'js_files': js_files,
                'og_title': og_title.get('content', '') if og_title else '',
                'og_description': og_desc.get('content', '') if og_desc else '',
                'og_image': og_image.get('content', '') if og_image else '',
                'twitter_title': twitter_title.get('content', '') if twitter_title else '',
                'twitter_description': twitter_desc.get('content', '') if twitter_desc else '',
                'twitter_image': twitter_image.get('content', '') if twitter_image else '',
                'content_type': response.headers.get('content-type', ''),
                'last_modified': response.headers.get('last-modified', ''),
                'server': response.headers.get('server', ''),
                'indexability': self.get_indexability_status(response.status_code, robots_content),
                'crawl_timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {
                'url': url, 'original_url': url, 'status_code': 0, 'error': str(e),
                'title': '', 'title_length': 0, 'meta_description': '', 'meta_desc_length': 0,
                'canonical_url': '', 'meta_robots': '', 'h1_tags': '', 'h1_count': 0,
                'h2_tags': '', 'h2_count': 0, 'h3_tags': '', 'h3_count': 0,
                'h4_tags': '', 'h4_count': 0, 'word_count': 0, 'response_time': 0,
                'content_length': 0, 'internal_links_count': 0, 'external_links_count': 0,
                'internal_links': [], 'external_links': [], 'images': [], 'image_count': 0,
                'images_without_alt': 0, 'schema_types': '', 'schema_count': 0,
                'redirect_chain': [], 'redirect_count': 0, 'css_files': 0, 'js_files': 0,
                'og_title': '', 'og_description': '', 'og_image': '',
                'twitter_title': '', 'twitter_description': '', 'twitter_image': '',
                'content_type': '', 'last_modified': '', 'server': '',
                'indexability': 'Error', 'crawl_timestamp': datetime.now().isoformat()
            }
    
    def get_indexability_status(self, status_code, robots_content):
        if status_code != 200:
            return 'Non-Indexable'
        if 'noindex' in robots_content.lower():
            return 'Non-Indexable'
        return 'Indexable'

def crawl_website(start_url, max_urls, crawl_scope, progress_container, ignore_robots=False):
    crawler = UltraFrogCrawler(max_urls, ignore_robots, crawl_scope)
    crawler.set_base_url(start_url)
    
    urls_to_visit = deque([start_url])
    visited_urls = set()
    crawl_data = []
    
    progress_bar = progress_container.progress(0)
    status_text = progress_container.empty()
    
    # Increased workers for faster crawling
    with ThreadPoolExecutor(max_workers=10) as executor:
        while urls_to_visit and len(visited_urls) < max_urls:
            if st.session_state.stop_crawling:
                break
                
            current_batch = []
            batch_size = min(20, len(urls_to_visit), max_urls - len(visited_urls))  # Larger batches
            
            for _ in range(batch_size):
                if urls_to_visit and not st.session_state.stop_crawling:
                    url = urls_to_visit.popleft()
                    if url not in visited_urls and crawler.can_fetch(url):
                        current_batch.append(url)
                        visited_urls.add(url)
            
            if not current_batch:
                break
            
            future_to_url = {executor.submit(crawler.extract_page_data, url): url for url in current_batch}
            
            for future in as_completed(future_to_url):
                if st.session_state.stop_crawling:
                    for f in future_to_url:
                        f.cancel()
                    break
                    
                try:
                    page_data = future.result(timeout=12)
                    crawl_data.append(page_data)
                    
                    if not st.session_state.stop_crawling:
                        for link_data in page_data.get('internal_links', []):
                            link_url = link_data['url']
                            if (link_url not in visited_urls and 
                                link_url not in urls_to_visit and 
                                crawler.should_crawl_url(link_url) and
                                len(visited_urls) + len(urls_to_visit) < max_urls):
                                urls_to_visit.append(link_url)
                    
                    progress = min(len(crawl_data) / max_urls, 1.0)
                    progress_bar.progress(progress)
                    status_text.text(f"🚀 Crawled: {len(crawl_data)} | Queue: {len(urls_to_visit)} | Speed: {len(crawl_data)/max(1, time.time() - st.session_state.get('start_time', time.time())):.1f} URLs/sec")
                    
                except Exception as e:
                    st.error(f"Error: {e}")
    
    return crawl_data

def crawl_from_list(url_list, progress_container, ignore_robots=False):
    crawler = UltraFrogCrawler(len(url_list), ignore_robots)
    crawl_data = []
    
    progress_bar = progress_container.progress(0)
    status_text = progress_container.empty()
    
    valid_urls = [url.strip() for url in url_list if crawler.can_fetch(url.strip())]
    
    if not valid_urls:
        return crawl_data
    
    # Increased workers and batch size for list mode
    with ThreadPoolExecutor(max_workers=15) as executor:
        for i in range(0, len(valid_urls), 25):  # Larger batches
            if st.session_state.stop_crawling:
                break
                
            batch = valid_urls[i:i + 25]
            future_to_url = {executor.submit(crawler.extract_page_data, url): url for url in batch}
            
            for future in as_completed(future_to_url):
                if st.session_state.stop_crawling:
                    for f in future_to_url:
                        f.cancel()
                    break
                    
                try:
                    page_data = future.result(timeout=12)
                    crawl_data.append(page_data)
                    
                    progress = len(crawl_data) / len(valid_urls)
                    progress_bar.progress(progress)
                    status_text.text(f"🚀 Processed: {len(crawl_data)}/{len(valid_urls)} | Speed: {len(crawl_data)/max(1, time.time() - st.session_state.get('start_time', time.time())):.1f} URLs/sec")
                    
                except Exception as e:
                    st.error(f"Error: {e}")
    
    return crawl_data

def crawl_from_sitemap(sitemap_url, max_urls, progress_container, ignore_robots=False):
    crawler = UltraFrogCrawler(max_urls, ignore_robots)
    
    progress_bar = progress_container.progress(0)
    status_text = progress_container.empty()
    
    status_text.text("🗺️ Extracting URLs from sitemap...")
    sitemap_urls = crawler.extract_sitemap_urls(sitemap_url)
    
    if not sitemap_urls:
        st.error("No URLs found in sitemap")
        return []
    
    if len(sitemap_urls) > max_urls:
        sitemap_urls = sitemap_urls[:max_urls]
    
    st.info(f"Found {len(sitemap_urls)} URLs in sitemap")
    return crawl_from_list(sitemap_urls, progress_container, ignore_robots)

# CSS
st.markdown("""
<style>
.main-header {
    background: linear-gradient(90deg, #4CAF50, #45a049);
    padding: 1rem;
    border-radius: 10px;
    margin-bottom: 2rem;
}
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="main-header">
    <h1 style="color: white; margin: 0;">🐸 Ultra Frog SEO Crawler</h1>
    <p style="color: white; margin: 0; opacity: 0.9;">by Vaibhav - Professional SEO Analysis Tool</p>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("🔧 Crawl Configuration")
    
    crawl_mode = st.selectbox("🎯 Crawl Mode", [
        "🕷️ Spider Crawl (Follow Links)",
        "📝 List Mode (Upload URLs)",
        "🗺️ Sitemap Crawl (XML Sitemap)"
    ])
    
    if crawl_mode == "🕷️ Spider Crawl (Follow Links)":
        start_url = st.text_input("🌐 Website URL", placeholder="https://example.com")
        max_urls = st.number_input("📊 Max URLs to crawl", min_value=1, max_value=100000, value=1000)
        
        # Crawl scope options
        crawl_scope = st.selectbox("🎯 Crawl Scope", [
            "subfolder", "subdomain", "exact"
        ], help="Subfolder: Only URLs in same path | Subdomain: All subdomains | Exact: Only exact URL")
        
    elif crawl_mode == "📝 List Mode (Upload URLs)":
        uploaded_file = st.file_uploader("Choose file", type=['txt', 'csv'])
        url_list_text = st.text_area("Or paste URLs here (one per line)", height=100)
        
    elif crawl_mode == "🗺️ Sitemap Crawl (XML Sitemap)":
        sitemap_url = st.text_input("🗺️ Sitemap URL", placeholder="https://example.com/sitemap.xml")
        max_urls = st.number_input("📊 Max URLs from sitemap", min_value=1, max_value=100000, value=5000)
    
    ignore_robots = st.checkbox("🤖 Ignore robots.txt")
    
    col1, col2 = st.columns(2)
    with col1:
        start_btn = st.button("🚀 Start Crawl", type="primary", disabled=st.session_state.crawling)
    with col2:
        stop_btn = st.button("⛔ Stop Crawl", disabled=not st.session_state.crawling)
    
    if stop_btn:
        st.session_state.stop_crawling = True
        st.session_state.crawling = False
        st.rerun()
    
    if start_btn:
        valid_input = False
        url_list = []
        
        if crawl_mode == "🕷️ Spider Crawl (Follow Links)" and start_url:
            valid_input = True
        elif crawl_mode == "📝 List Mode (Upload URLs)":
            if uploaded_file:
                content = uploaded_file.read().decode('utf-8')
                url_list = [line.strip() for line in content.split('\n') if line.strip()]
                valid_input = len(url_list) > 0
            elif url_list_text:
                url_list = [line.strip() for line in url_list_text.split('\n') if line.strip()]
                valid_input = len(url_list) > 0
        elif crawl_mode == "🗺️ Sitemap Crawl (XML Sitemap)" and sitemap_url:
            valid_input = True
        
        if valid_input:
            st.session_state.crawling = True
            st.session_state.stop_crawling = False
            st.session_state.crawl_data = []
            st.session_state.start_time = time.time()
            st.rerun()
        else:
            st.error("Please provide valid input")
    
    if st.button("🗑️ Clear All Data"):
        st.session_state.crawl_data = []
        st.rerun()
    
    st.markdown("---")
    st.markdown("### 🚀 Speed Optimizations")
    st.markdown("""
    - ⚡ **10-15 concurrent workers**
    - 🔄 **Connection pooling**
    - 📦 **Larger batch processing**
    - 🎯 **Optimized parsing**
    - ⏱️ **Real-time speed tracking**
    """)

# Main content
if st.session_state.crawling:
    st.header("🐸 Ultra Frog is Crawling...")
    
    progress_container = st.container()
    
    try:
        if crawl_mode == "🕷️ Spider Crawl (Follow Links)":
            crawl_data = crawl_website(start_url, max_urls, crawl_scope, progress_container, ignore_robots)
        elif crawl_mode == "📝 List Mode (Upload URLs)":
            if uploaded_file:
                content = uploaded_file.read().decode('utf-8')
                url_list = [line.strip() for line in content.split('\n') if line.strip()]
            else:
                url_list = [line.strip() for line in url_list_text.split('\n') if line.strip()]
            crawl_data = crawl_from_list(url_list, progress_container, ignore_robots)
        else:
            crawl_data = crawl_from_sitemap(sitemap_url, max_urls, progress_container, ignore_robots)
        
        st.session_state.crawl_data = crawl_data if crawl_data else []
        st.session_state.crawling = False
        st.session_state.stop_crawling = False
        
        if st.session_state.stop_crawling:
            st.warning("⛔ Crawl stopped by user")
        else:
            crawl_time = time.time() - st.session_state.get('start_time', time.time())
            st.success(f"✅ Crawl completed! Found {len(crawl_data)} URLs in {crawl_time:.1f} seconds ({len(crawl_data)/max(1, crawl_time):.1f} URLs/sec)")
        
        st.rerun()
        
    except Exception as e:
        st.error(f"Error: {str(e)}")
        st.session_state.crawling = False

elif st.session_state.crawl_data:
    df = pd.DataFrame(st.session_state.crawl_data)
    
    # Summary stats
    st.header("📊 Ultra Frog Analysis Dashboard")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total URLs", len(df))
    with col2:
        indexable_count = len(df[df['indexability'] == 'Indexable'])
        st.metric("✅ Indexable", indexable_count)
    with col3:
        non_indexable_count = len(df[df['indexability'] == 'Non-Indexable'])
        st.metric("❌ Non-Indexable", non_indexable_count)
    with col4:
        redirect_count = len(df[df['redirect_count'] > 0])
        st.metric("🔄 Redirects", redirect_count)
    with col5:
        avg_response = df['response_time'].mean() if len(df) > 0 else 0
        st.metric("⚡ Avg Response", f"{avg_response:.2f}s")
    
    # Enhanced tabs with all features restored
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs([
        "🔗 Internal", "🌐 External", "🖼️ Images", "📝 Titles", "📄 Meta Desc", 
        "🏷️ Headers", "🔄 Redirects", "📊 Status", "🎯 Canonicals", "📱 Social", "🚀 Performance"
    ])
    
    with tab1:
        st.subheader("🔗 Internal Links Analysis")
        internal_df = df[['url', 'status_code', 'title', 'indexability', 'internal_links_count', 'response_time']].copy()
        st.dataframe(internal_df, use_container_width=True)
        csv = internal_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Internal", csv, f"internal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    with tab2:
        st.subheader("🌐 External Links Analysis")
        external_data = []
        for _, row in df.iterrows():
            for ext_link in row.get('external_links', []):
                external_data.append({
                    'source_url': row['url'],
                    'destination_url': ext_link['url'],
                    'anchor_text': ext_link['anchor_text']
                })
        
        if external_data:
            ext_df = pd.DataFrame(external_data)
            st.dataframe(ext_df, use_container_width=True)
            csv = ext_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download External", csv, f"external_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
        else:
            st.info("🔍 No external links found")
    
    with tab3:
        st.subheader("🖼️ Images Analysis")
        images_data = []
        for _, row in df.iterrows():
            for img in row.get('images', []):
                images_data.append({
                    'source_url': row['url'],
                    'image_url': img['src'],
                    'alt_text': img['alt'],
                    'title': img['title'],
                    'dimensions': f"{img['width']}x{img['height']}" if img['width'] and img['height'] else 'Unknown'
                })
        
        if images_data:
            img_df = pd.DataFrame(images_data)
            st.dataframe(img_df, use_container_width=True)
            missing_alt = len(img_df[img_df['alt_text'] == ''])
            st.warning(f"⚠️ {missing_alt} images missing alt text")
            csv = img_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Images", csv, f"images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
        else:
            st.info("🔍 No images found")
    
    with tab4:
        st.subheader("📝 Page Titles Analysis")
        title_df = df[['url', 'title', 'title_length']].copy()
        title_df['status'] = title_df.apply(lambda row: 
            '❌ Missing' if row['title_length'] == 0 else
            '⚠️ Too Long' if row['title_length'] > 60 else
            '⚠️ Too Short' if row['title_length'] < 30 else '✅ Good', axis=1)
        
        st.dataframe(title_df, use_container_width=True)
        issues = len(title_df[~title_df['status'].str.contains('✅')])
        st.metric("🎯 Title Issues", issues)
        csv = title_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Titles", csv, f"titles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    with tab5:
        st.subheader("📄 Meta Descriptions Analysis")
        meta_df = df[['url', 'meta_description', 'meta_desc_length']].copy()
        meta_df['status'] = meta_df.apply(lambda row: 
            '❌ Missing' if row['meta_desc_length'] == 0 else
            '⚠️ Too Long' if row['meta_desc_length'] > 160 else
            '⚠️ Too Short' if row['meta_desc_length'] < 120 else '✅ Good', axis=1)
        
        st.dataframe(meta_df, use_container_width=True)
        csv = meta_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Meta", csv, f"meta_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    with tab6:
        st.subheader("🏷️ Header Tags Analysis (H1-H4)")
        header_df = df[['url', 'h1_count', 'h2_count', 'h3_count', 'h4_count']].copy()
        header_df['h1_text'] = df['h1_tags'].apply(lambda x: x.split(';')[0][:100] if x else 'Missing')
        header_df['status'] = header_df.apply(lambda row: 
            '❌ No H1' if row['h1_count'] == 0 else
            '⚠️ Multiple H1' if row['h1_count'] > 1 else '✅ Good H1', axis=1)
        
        st.dataframe(header_df, use_container_width=True)
        csv = header_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Headers", csv, f"headers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    with tab7:
        st.subheader("🔄 Redirect Chain Analysis")
        redirect_df = df[df['redirect_count'] > 0].copy()
        
        if not redirect_df.empty:
            redirect_display = redirect_df[['original_url', 'url', 'redirect_count', 'status_code']].copy()
            redirect_display.columns = ['Original URL', 'Final URL', 'Redirect Hops', 'Final Status']
            st.dataframe(redirect_display, use_container_width=True)
            
            # Show detailed redirect chains
            for _, row in redirect_df.iterrows():
                if row['redirect_chain']:
                    with st.expander(f"🔗 Redirect Chain: {row['original_url'][:50]}..."):
                        for hop in row['redirect_chain']:
                            st.write(f"**Step {hop['step']}:** {hop['redirect_type']} → {hop['from_url']}")
            
            csv = redirect_display.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Redirects", csv, f"redirects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
        else:
            st.info("✅ No redirects found - Great for SEO!")
    
    with tab8:
        st.subheader("📊 HTTP Status Code Analysis")
        status_counts = df['status_code'].value_counts().sort_index()
        
        col1, col2 = st.columns(2)
        with col1:
            st.bar_chart(status_counts)
        with col2:
            for status, count in status_counts.items():
                color = "🟢" if status == 200 else "🟡" if 300 <= status < 400 else "🔴"
                st.metric(f"{color} Status {status}", count)
        
        status_df = df[['url', 'status_code', 'indexability', 'response_time', 'server']].copy()
        st.dataframe(status_df, use_container_width=True)
        csv = status_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Status", csv, f"status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    with tab9:
        st.subheader("🎯 Canonical URL Analysis")
        canonical_df = df[['url', 'canonical_url', 'meta_robots']].copy()
        canonical_df['canonical_status'] = canonical_df.apply(lambda row:
            '❌ Missing' if not row['canonical_url'] else
            '✅ Self-Referencing' if row['canonical_url'] == row['url'] else
            '🔄 Points Elsewhere', axis=1)
        
        st.dataframe(canonical_df, use_container_width=True)
        missing_canonical = len(canonical_df[canonical_df['canonical_url'] == ''])
        st.metric("⚠️ Missing Canonicals", missing_canonical)
        csv = canonical_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Canonicals", csv, f"canonical_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    with tab10:
        st.subheader("📱 Social Media Tags (Open Graph & Twitter)")
        social_df = df[['url', 'og_title', 'og_description', 'og_image', 'twitter_title', 'twitter_description', 'twitter_image']].copy()
        social_df['og_complete'] = social_df.apply(lambda row: 
            '✅ Complete' if all([row['og_title'], row['og_description'], row['og_image']]) else '⚠️ Incomplete', axis=1)
        social_df['twitter_complete'] = social_df.apply(lambda row:
            '✅ Complete' if all([row['twitter_title'], row['twitter_description']]) else '⚠️ Incomplete', axis=1)
        
        st.dataframe(social_df, use_container_width=True)
        csv = social_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Social", csv, f"social_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    with tab11:
        st.subheader("🚀 Performance & Technical Analysis")
        perf_df = df[['url', 'response_time', 'content_length', 'word_count', 'css_files', 'js_files', 'schema_count']].copy()
        perf_df['performance_score'] = perf_df.apply(lambda row:
            '🟢 Excellent' if row['response_time'] < 1.0 else
            '🟡 Good' if row['response_time'] < 3.0 else
            '🔴 Needs Improvement', axis=1)
        
        st.dataframe(perf_df, use_container_width=True)
        
        # Performance metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            avg_response = df['response_time'].mean()
            st.metric("⚡ Avg Response Time", f"{avg_response:.2f}s")
        with col2:
            avg_words = df['word_count'].mean()
            st.metric("📝 Avg Word Count", f"{int(avg_words)}")
        with col3:
            schema_pages = len(df[df['schema_count'] > 0])
            st.metric("🏷️ Pages with Schema", schema_pages)
        
        csv = perf_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Performance", csv, f"performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    # Quick download section
    st.header("📥 Quick Downloads")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📊 Complete Report",
            data=csv_data,
            file_name=f"ultra_frog_complete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    with col2:
        issues_df = df[
            (df['status_code'] != 200) | 
            (df['title_length'] == 0) | 
            (df['meta_desc_length'] == 0) |
            (df['h1_count'] == 0) |
            (df['redirect_count'] > 0)
        ].copy()
        if not issues_df.empty:
            issues_csv = issues_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="⚠️ Issues Report",
                data=issues_csv,
                file_name=f"ultra_frog_issues_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    
    with col3:
        redirects_data = df[df['redirect_count'] > 0][['url', 'original_url', 'status_code', 'redirect_count']].copy()
        if not redirects_data.empty:
            redirects_csv = redirects_data.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="🔄 Redirects Only",
                data=redirects_csv,
                file_name=f"ultra_frog_redirects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    
    with col4:
        # Create images report
        images_data = []
        for _, row in df.iterrows():
            for img in row.get('images', []):
                images_data.append({
                    'source_url': row['url'],
                    'image_url': img['src'],
                    'alt_text': img['alt'],
                    'has_alt': 'Yes' if img['alt'] else 'No'
                })
        
        if images_data:
            images_df = pd.DataFrame(images_data)
            images_csv = images_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="🖼️ Images Report",
                data=images_csv,
                file_name=f"ultra_frog_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    
    # Quick insights
    st.header("🎯 Quick SEO Insights")
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**❌ Issues Found:**")
        missing_titles = len(df[df['title_length'] == 0])
        missing_meta = len(df[df['meta_desc_length'] == 0])
        missing_h1 = len(df[df['h1_count'] == 0])
        images_no_alt = df['images_without_alt'].sum()
        
        if missing_titles > 0:
            st.write(f"• {missing_titles} pages missing titles")
        if missing_meta > 0:
            st.write(f"• {missing_meta} pages missing meta descriptions")
        if missing_h1 > 0:
            st.write(f"• {missing_h1} pages missing H1 tags")
        if images_no_alt > 0:
            st.write(f"• {images_no_alt} images missing alt text")
        
        if not any([missing_titles, missing_meta, missing_h1, images_no_alt]):
            st.write("🎉 No major issues found!")
    
    with col2:
        st.write("**✅ Performance Summary:**")
        status_200 = len(df[df['status_code'] == 200])
        with_schema = len(df[df['schema_count'] > 0])
        fast_pages = len(df[df['response_time'] < 2.0])
        
        st.write(f"• {status_200} pages return 200 OK")
        st.write(f"• {with_schema} pages have schema markup")
        st.write(f"• {fast_pages} pages load under 2 seconds")
        st.write(f"• Average page size: {df['word_count'].mean():.0f} words")

else:
    st.info("👈 Configure your crawl settings and click '🚀 Start Crawl' to begin Ultra Frog analysis")
    
    st.header("🐸 Ultra Frog Features")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        **🎯 Crawl Modes**
        - 🕷️ Spider crawling with scope control
        - 📝 URL list processing  
        - 🗺️ XML sitemap analysis
        - ⛔ Stop/resume functionality
        """)
    
    with col2:
        st.markdown("""
        **📊 Complete SEO Analysis**
        - 🏷️ All header tags (H1-H4)
        - 🔗 Internal/external links
        - 🖼️ Image optimization analysis
        - 📱 Open Graph & Twitter Cards
        - 🎯 Canonical URL tracking
        - 🔄 Detailed redirect chains
        """)
    
    with col3:
        st.markdown("""
        **⚡ Speed Optimizations**
        - 🚀 10-15 concurrent workers
        - 📦 Large batch processing
        - 🔄 Connection pooling
        - ⏱️ Real-time speed tracking
        - 📥 Multiple export formats
        """)

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; padding: 1rem; background: linear-gradient(90deg, #4CAF50, #45a049); border-radius: 10px;">
    <h3 style="color: white; margin: 0;">🐸 Ultra Frog SEO Crawler v2.0</h3>
    <p style="color: white; margin: 0;">Created by <strong>Vaibhav</strong> - Faster & More Powerful Than Ever</p>
</div>
""", unsafe_allow_html=True)
