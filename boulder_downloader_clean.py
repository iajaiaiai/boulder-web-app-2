#!/usr/bin/env python3
"""
Boulder Clerk & Recorder PublicSearch Portal PDF Downloader - CLEAN VERSION

Focused on the core issues:
1. Proper session persistence (storage_state only)
2. Frame-aware authentication detection
3. Single timeout guard
4. Simple download logic
"""

import asyncio
import argparse
import logging
import re
import sys
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError

# Session persistence - ONLY use storage_state
STORAGE_STATE_PATH = "boulder_storage_state.json"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BoulderPortalDownloader:
    """Clean Boulder portal PDF downloader."""
    
    def __init__(self, headless: bool = True, download_dir: str = None, limit: int = None):
        self.headless = headless
        self.base_url = "https://boulder.co.publicsearch.us"
        self.limit = limit  # Limit number of downloads for testing
        
        # Create a simple, easily accessible download folder
        if download_dir is None:
            # Create folder with current date for easy organization
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            self.download_dir = Path(f"Boulder_PDFs_{today}")
        else:
            self.download_dir = Path(download_dir)
        
        self.download_dir.mkdir(exist_ok=True)
        print(f"📁 PDFs will be saved to: {self.download_dir.absolute()}")
        
        if self.limit:
            print(f"🧪 TEST MODE: Limited to {self.limit} downloads")
        
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe filesystem storage."""
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        if len(filename) > 200:
            filename = filename[:200]
        return filename
    
    def create_query_slug(self, query: str) -> str:
        """Create a URL-safe slug from the query string."""
        slug = re.sub(r'[^a-zA-Z0-9\s-]', '', query)
        slug = re.sub(r'\s+', '_', slug.strip())
        return slug[:50]
    
    async def setup_browser(self):
        """Initialize browser with proper session persistence."""
        playwright = await async_playwright().start()
        
        # Try to use system Chrome first, fallback to Chromium
        try:
            browser = await playwright.chromium.launch(
                headless=self.headless,
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
        except Exception as e:
            logger.warning(f"Failed to launch system Chrome: {e}")
            logger.info("Falling back to bundled Chromium...")
            browser = await playwright.chromium.launch(
                headless=self.headless,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
        
        # ONLY use storage_state for session persistence
        storage = STORAGE_STATE_PATH if Path(STORAGE_STATE_PATH).exists() else None
        if storage:
            logger.info("Loading existing session state")
        else:
            logger.info("Starting with fresh session")
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            accept_downloads=True,
            storage_state=storage  # This is the ONLY way to persist sessions
        )
        
        page = await context.new_page()
        return browser, page, context
    
    async def ensure_authenticated(self, page: Page, timeout: float = 30.0) -> tuple[bool, bool]:
        """Frame-aware authentication with single timeout guard.
        
        Returns:
            tuple[bool, bool]: (is_authenticated, just_logged_in)
                - is_authenticated: True if authenticated
                - just_logged_in: True if login was performed in this call
        """
        import asyncio
        
        just_logged_in = False
        
        async def _is_authenticated():
            """Check if we're authenticated by looking for download button."""
            try:
                # Look for download button on main page
                download_btn = page.get_by_role("button", name=re.compile(r"download", re.I)).first
                if await download_btn.is_visible():
                    return True
                
                # Check all frames for download button
                for frame in page.frames:
                    if frame == page.main_frame:
                        continue
                    try:
                        frame_download_btn = frame.get_by_role("button", name=re.compile(r"download", re.I)).first
                        if await frame_download_btn.is_visible():
                            return True
                    except:
                        continue
                
                return False
            except:
                return False
        
        async def _has_login_forms():
            """Check for login forms in main page and all frames."""
            login_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'button:has-text("Sign In")',
                'button:has-text("Login")'
            ]
            
            # Check main page
            for selector in login_selectors:
                if await page.locator(selector).count() > 0:
                    return True
            
            # Check all frames
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    for selector in login_selectors:
                        if await frame.locator(selector).count() > 0:
                            return True
                except:
                    continue
            
            return False
        
        async def _handle_login():
            """Handle login in the correct context (main page, frame, or popup)."""
            # Try main page first
            if await _has_login_forms():
                logger.info("Found login form on main page")
                await self._fill_login_form(page, "main page")
                return True
            
            # Try frames
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    if await frame.locator('input[type="password"]').count() > 0:
                        logger.info(f"Found login form in frame: {frame.url}")
                        await self._fill_login_form(frame, f"frame: {frame.url}")
                        return True
                except:
                    continue
            
            # Try popups
            pages = page.context.pages
            if len(pages) > 1:
                for popup_page in pages[1:]:
                    try:
                        if await popup_page.locator('input[type="password"]').count() > 0:
                            logger.info(f"Found login form in popup: {popup_page.url}")
                            await self._fill_login_form(popup_page, f"popup: {popup_page.url}")
                            return True
                    except:
                        continue
            
            return False
        
        # Single timeout guard - try authentication until timeout
        try:
            login_performed = await asyncio.wait_for(
                self._auth_loop(_is_authenticated, _has_login_forms, _handle_login), 
                timeout=timeout
            )
            return True, login_performed
        except asyncio.TimeoutError:
            logger.error(f"Authentication timed out after {timeout}s")
            return False, False
    
    async def _auth_loop(self, _is_authenticated, _has_login_forms, _handle_login):
        """Single authentication loop with early exit.
        
        Returns:
            bool: True if login was performed, False if already authenticated
        """
        for attempt in range(6):  # 6 attempts * 5s = 30s max
            # Check if already authenticated
            if await _is_authenticated():
                logger.info("Already authenticated")
                return False  # No login needed, already authenticated
            
            # Try to handle login if needed
            if await _has_login_forms():
                logger.info(f"Authentication attempt {attempt + 1}")
                if await _handle_login():
                    # Wait for login to complete
                    await asyncio.sleep(3)
                    if await _is_authenticated():
                        logger.info("Authentication successful")
                        return True  # Just logged in
            
            # Brief wait before next attempt
            await asyncio.sleep(2)
        
        raise asyncio.TimeoutError("Authentication did not complete")
    
    async def _fill_login_form(self, page_or_frame, context: str):
        """Fill login form in the correct context."""
        try:
            logger.info(f"Filling login form in {context}")
            
            # Fill username
            username_selectors = ['input[type="email"]', 'input[name="username"]', 'input[name="email"]']
            for selector in username_selectors:
                try:
                    username_input = page_or_frame.locator(selector)
                    if await username_input.is_visible():
                        await username_input.fill("ofori.ohene1@gmail.com")
                        logger.info(f"Filled username in {context}")
                        break
                except:
                    continue
            
            # Fill password
            password_selectors = ['input[type="password"]', 'input[name="password"]']
            for selector in password_selectors:
                try:
                    password_input = page_or_frame.locator(selector)
                    if await password_input.is_visible():
                        await password_input.fill("Boulder123")
                        logger.info(f"Filled password in {context}")
                        break
                except:
                    continue
            
            # Submit form
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Sign In")',
                'button:has-text("Login")',
                'button:has-text("Submit")'
            ]
            
            for selector in submit_selectors:
                try:
                    submit_btn = page_or_frame.locator(selector)
                    if await submit_btn.is_visible():
                        await submit_btn.click()
                        logger.info(f"Submitted login form in {context}")
                        break
                except:
                    continue
                    
        except Exception as e:
            logger.error(f"Error filling login form in {context}: {e}")
    
    async def perform_search(self, page: Page, query: str) -> bool:
        """Navigate directly to search results with OCR enabled."""
        try:
            clean_query = query.strip('"\'')
            logger.info(f"Searching for: {clean_query}")
            
            encoded_query = quote(clean_query)
            results_url = f"{self.base_url}/results?department=RP&keywordSearch=false&recordedDateRange=18600626%2C20251023&searchOcrText=true&searchType=quickSearch&searchValue={encoded_query}"
            
            await page.goto(results_url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            
            logger.info("Search completed")
            return True
                
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return False
    
    async def get_search_results(self, page: Page) -> list:
        """Extract search results from the page."""
        try:
            await page.wait_for_selector('tr:has(td)', timeout=10000)
            result_rows = await page.locator('tr:has(td)').all()
            results = []
            
            for i, row in enumerate(result_rows, 1):
                try:
                    text = await row.text_content()
                    if text and len(text.strip()) > 10:
                        results.append({
                            'index': i,
                            'text': text.strip(),
                            'row_element': row
                        })
                except:
                    continue
            
            logger.info(f"Found {len(results)} search results")
            return results
            
        except Exception as e:
            logger.error(f"Error extracting results: {e}")
            return []
    
    async def download_pdf_from_result(self, page: Page, result: dict, query_slug: str, results_url: str) -> str:
        """Download PDF using the reliable pattern: wrap click in expect_download().
        
        Returns:
            str: The filename of the downloaded PDF, or None if download failed
        """
        try:
            index = result['index']
            row = result['row_element']
            
            print(f"📄 Processing result {index}...")
            logger.info(f"Processing result {index}")
            
            # Click on result row to navigate to detail page
            await row.click()
            await page.wait_for_timeout(3000)
            
            # Check if we're on a detail page
            current_url = page.url
            if '/doc/' not in current_url:
                print(f"❌ Failed to navigate to detail page for result {index}")
                logger.warning(f"Did not navigate to detail page for result {index}")
                return None
            
            print(f"✅ Navigated to detail page for result {index}")
            logger.info(f"Navigated to detail page for result {index}")
            
            # Ensure authentication before attempting download
            was_authenticated, just_logged_in = await self.ensure_authenticated(page, timeout=30.0)
            if not was_authenticated:
                print(f"❌ Authentication failed for result {index}")
                logger.error(f"Authentication failed for result {index}")
                return None
            
            # If we just authenticated, save the session state immediately
            if just_logged_in:
                try:
                    context = page.context
                    await context.storage_state(path=STORAGE_STATE_PATH)
                    logger.info(f"💾 Session saved immediately after authentication")
                    print(f"💾 Session state saved for future runs")
                except Exception as e:
                    logger.warning(f"Could not save session: {e}")
            
            # Find download button
            download_btn = page.get_by_role("button", name=re.compile(r"download\s*\(free\)", re.IGNORECASE))
            
            if await download_btn.is_visible():
                print(f"🔍 Found download button for result {index}")
                logger.info(f"Found download button for result {index}")
                
                # RELIABLE PATTERN: Wrap the click in expect_download()
                async with page.expect_download(timeout=30000) as download_info:
                    await download_btn.click()
                    print(f"⬇️  Downloading result {index}...")
                    logger.info(f"Clicked download button for result {index}")
                
                # Save the download
                download = await download_info.value
                suggested_filename = download.suggested_filename or f"document_{index}.pdf"
                safe_filename = self.sanitize_filename(suggested_filename)
                final_filename = f"{index:02d}_{query_slug}__{safe_filename}"
                
                await download.save_as(self.download_dir / final_filename)
                print(f"✅ Downloaded: {final_filename}")
                logger.info(f"Downloaded: {final_filename}")
                
                # CRITICAL: Navigate back to results page after download
                print(f"🔄 Returning to results page...")
                logger.info(f"Navigating back to results page for result {index}")
                await page.goto(results_url, wait_until='networkidle', timeout=30000)
                await page.wait_for_timeout(2000)  # Wait for results to reload
                logger.info(f"Returned to results page for result {index}")
                
                return final_filename
            else:
                print(f"❌ No download button found for result {index}")
                logger.warning(f"No download button found for result {index}")
                return None
                
        except Exception as e:
            print(f"❌ Error downloading result {index}: {e}")
            logger.error(f"Error downloading result {index}: {e}")
            return None
    
    async def download_all_pdfs(self, query: str) -> dict:
        """Main method to download all PDFs for a query.
        
        Returns:
            dict: {'count': int, 'files': list[str]} - Number of downloads and list of filenames
        """
        query_slug = self.create_query_slug(query)
        
        print(f"\n🎯 Starting download process for: {query}")
        print(f"📁 Download folder: {self.download_dir.absolute()}")
        print("-" * 60)
        
        logger.info(f"Starting download process for: {query}")
        
        browser = None
        try:
            browser, page, context = await self.setup_browser()
            
            # Perform search and get results URL
            if not await self.perform_search(page, query):
                return {'count': 0, 'files': []}
            
            # Store the results URL for navigation back
            results_url = page.url
            logger.info(f"Results URL: {results_url}")
            
            # Get results
            results = await self.get_search_results(page)
            if not results:
                logger.info("No results found")
                return {'count': 0, 'files': []}
            
            # Download PDFs - process each result and return to results page
            successful_downloads = 0
            downloaded_files = []
            total_results = len(results)
            
            # Apply limit if specified
            if self.limit and self.limit < total_results:
                results = results[:self.limit]
                total_results = len(results)
                print(f"\n🧪 TEST MODE: Processing only {total_results} results (limited from {len(results)})")
            
            print(f"\n🚀 Starting download of {total_results} results...")
            print("=" * 50)
            
            for i, result in enumerate(results, 1):
                try:
                    print(f"\n📋 Progress: {i}/{total_results} results")
                    logger.info(f"Processing result {result['index']} of {len(results)}")
                    
                    downloaded_filename = await self.download_pdf_from_result(page, result, query_slug, results_url)
                    if downloaded_filename:
                        successful_downloads += 1
                        downloaded_files.append(downloaded_filename)
                        print(f"✅ Success! ({successful_downloads}/{total_results} completed)")
                        logger.info(f"Successfully downloaded result {result['index']}: {downloaded_filename}")
                    else:
                        print(f"❌ Failed to download result {result['index']}")
                        logger.warning(f"Failed to download result {result['index']}")
                    
                    # Brief pause between results
                    await page.wait_for_timeout(1000)
                    
                except Exception as e:
                    print(f"❌ Error processing result {result['index']}: {e}")
                    logger.error(f"Error processing result {result['index']}: {e}")
                    # Try to navigate back to results page even if there was an error
                    try:
                        await page.goto(results_url, wait_until='networkidle', timeout=30000)
                        await page.wait_for_timeout(2000)
                    except:
                        pass
                    continue
            
            print("\n" + "=" * 50)
            print(f"🎉 Download complete! {successful_downloads}/{total_results} files downloaded")
            print(f"📁 All PDFs saved to: {self.download_dir.absolute()}")
            print("=" * 50)
            
            # ALWAYS save session state after any activity (whether successful or not)
            # This ensures authentication persists for future runs
            try:
                await context.storage_state(path=STORAGE_STATE_PATH)
                logger.info(f"✅ Session state saved to {STORAGE_STATE_PATH}")
                print(f"💾 Session state saved for future runs")
            except Exception as e:
                logger.error(f"Failed to save session state: {e}")
            
            logger.info(f"Successfully downloaded {successful_downloads} out of {len(results)} results")
            return {'count': successful_downloads, 'files': downloaded_files}
            
        except Exception as e:
            logger.error(f"Error in download process: {e}")
            return {'count': 0, 'files': []}
        finally:
            if browser:
                await browser.close()


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Download PDFs from Boulder PublicSearch portal")
    parser.add_argument("query", help="Subdivision query string")
    parser.add_argument("--no-headless", action="store_true", help="Run in non-headless mode")
    parser.add_argument("--download-dir", help="Download directory (default: Boulder_PDFs_YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, help="Limit number of downloads (useful for testing)")
    
    args = parser.parse_args()
    
    downloader = BoulderPortalDownloader(
        headless=not args.no_headless,
        download_dir=args.download_dir,
        limit=args.limit
    )
    
    try:
        successful_downloads = await downloader.download_all_pdfs(args.query)
        
        if successful_downloads > 0:
            logger.info(f"✅ Successfully downloaded {successful_downloads} PDFs")
        else:
            logger.warning("❌ No PDFs were downloaded")
            
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
