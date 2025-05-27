# dual repo pushing Removing
import logging
import time
from datetime import datetime, timedelta # timedelta اضافه شده است
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import os 
import glob 
from selenium.webdriver.support.ui import Select 




class MofidBroker:
    def __init__(self):
        self.driver = None # باید توسط setup_driver مقداردهی شود
        self.logs = []
        self.submission_logs = []
        # دایرکتوری برای دانلود فایل‌های اکسل تعریف و ایجاد می‌شود
        self.download_dir = os.path.join(os.getcwd(), "temp_mofid_downloads")
        os.makedirs(self.download_dir, exist_ok=True)
        
        # این بخش برای اجرای مستقل کد اضافه شده، در کد اصلی شما نیاز نیست
        global logger, tehran_tz
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        tehran_tz = pytz.timezone('Asia/Tehran')

    def setup_driver(self, headless=True):  # Changed default to True for headless
        """Initialize and return a Chrome WebDriver with optimized settings for headless operation."""
        try:
            chrome_options = Options()
            # --- Essential Headless Mode Options ---
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")

            # --- Performance & Resource Optimization Options ---
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-infobars")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--disable-logging")
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_argument("--silent")
            chrome_options.add_argument("--blink-settings=imagesEnabled=false")

            # --- Stability & Compatibility Options ---
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")

            # --- Download Preferences ---
            prefs = {
                "download.default_directory": self.download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safeBrowse.enabled": True  # Keep safeBrowse enabled for security unless it causes issues
            }
            chrome_options.add_experimental_option("prefs", prefs)

            self.driver = webdriver.Chrome(options=chrome_options)
            
            # --- Attempt to mask WebDriver presence ---
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                """
            })
            logger.info(f"WebDriver setup complete. Download directory set to: {self.download_dir}")
            return True
        except WebDriverException as e:
            print(f"Error setting up WebDriver: {e}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred during WebDriver setup: {e}")
            return False


    def get_order_history_excel(self, stock_name, order_action_persian, order_status_filter_value="1: 1", download_timeout=45): # مقدار پیش‌فرض برای "همه"
        if not self.driver:
            logger.error("Driver not initialized for get_order_history_excel.")
            self.add_log("خطا: درایور برای دریافت تاریخچه سفارشات مقداردهی نشده است.", "error")
            return None
        
        try:
            status_description = "همه وضعیت‌ها"
            if order_status_filter_value == "0: 0":
                status_description = "بدون خطا"
            
            logger.info(f"Starting order history Excel retrieval for stock: {stock_name}, action: {order_action_persian}, status_filter: {status_description}")
            self.add_log(f"شروع دریافت تاریخچه سفارشات (اکسل) برای نماد: {stock_name}, نوع: {order_action_persian}, وضعیت: {status_description}", "info")

            # Step 1: Click "Order History" icon
            logger.info("Clicking Order History icon...")
            history_icon_selector = "li[data-cy='order-history-menu-icon']"
            history_icon = self.wait_for_element(By.CSS_SELECTOR, history_icon_selector, timeout=15)
            self.driver.execute_script("arguments[0].click();", history_icon) 
            self.add_log("آیکون تاریخچه سفارشات کلیک شد", "info")
            time.sleep(1.5) 

            # Step 2: Fill stock symbol
            self.wait_for_element(By.XPATH, "//button[normalize-space()='اعمال فیلتر']", timeout=10) 
            logger.info(f"Entering stock symbol: {stock_name}...")
            search_input_selector = "input[data-cy='layout-search-input']"
            stock_input_field = self.wait_for_element(By.CSS_SELECTOR, search_input_selector, timeout=10)
            stock_input_field.clear()
            stock_input_field.send_keys(stock_name)
            self.add_log(f"نماد '{stock_name}' در فیلد جستجو وارد شد", "info")
            time.sleep(2.5) 

            # Step 3: Click stock symbol from list
            logger.info(f"Selecting '{stock_name}' from results...")
            clickable_stock_xpath = f"//div[@data-cy='search-symbol-item'][.//span[@class='fw-bold' and normalize-space(text())='{stock_name}']]//div[contains(@class, 'cup')]"
            stock_element_in_list = self.wait_for_element(By.XPATH, clickable_stock_xpath, timeout=10)
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, clickable_stock_xpath)))
            stock_element_in_list.click()
            self.add_log(f"نماد '{stock_name}' از لیست نتایج انتخاب شد", "info")
            time.sleep(0.5)

            # Step 4: Select order side
            logger.info(f"Selecting order side: {order_action_persian}...")
            order_side_select_elem = self.wait_for_element(By.ID, "orderSide", timeout=5)
            order_side_select = Select(order_side_select_elem)
            if order_action_persian == "خرید":
                order_side_select.select_by_value("1: 0") # Buy
            elif order_action_persian == "فروش":
                order_side_select.select_by_value("2: 1") # Sell
            self.add_log(f"سمت سفارش '{order_action_persian}' انتخاب شد", "info")
            time.sleep(0.5)

            # Step 5: Select status based on order_status_filter_value
            logger.info(f"Selecting status with filter value: '{order_status_filter_value}' ({status_description})...")
            status_select_elem = self.wait_for_element(By.ID, "states", timeout=5)
            status_select = Select(status_select_elem)
            try:
                status_select.select_by_value(order_status_filter_value)
                self.add_log(f"وضعیت سفارشات '{status_description}' (value: {order_status_filter_value}) انتخاب شد", "info")
            except Exception as e_status_select:
                logger.error(f"Could not select status with value '{order_status_filter_value}'. Defaulting to 'همه'. Error: {e_status_select}")
                self.add_log(f"خطا در انتخاب وضعیت '{status_description}'. انتخاب پیش‌فرض 'همه'. خطا: {e_status_select}", "warning")
                status_select.select_by_value("1: 1") # Fallback to "همه"
                self.add_log("وضعیت سفارشات 'همه' (پیش‌فرض پس از خطا) انتخاب شد", "info")
            time.sleep(0.5)

            # Step 6: Date selection is REMOVED as per user request
            self.add_log("مرحله انتخاب تاریخ (فیلتر تاریخ) طبق درخواست حذف شد.", "info")
            logger.info("Date selection (Step 6) has been removed.")

            # Step 7: Click "اعمال فیلتر" button
            logger.info("Clicking 'اعمال فیلتر' button...")
            apply_filter_button_xpath = "//button[normalize-space()='اعمال فیلتر' and @type='submit']"
            apply_filter_button = WebDriverWait(self.driver,15).until(
                EC.element_to_be_clickable((By.XPATH, apply_filter_button_xpath))
            )
            self.driver.execute_script("arguments[0].click();", apply_filter_button)
            self.add_log("دکمه 'اعمال فیلتر' کلیک شد", "info")
            time.sleep(3.5) # Wait for table to load/update based on other filters

            # Step 8: Click "Export to Excel" and handle download
            logger.info("Preparing to download Excel file...")
            for pattern in ["*.xlsx", "*.xls", "*.crdownload"]:
                for old_file in glob.glob(os.path.join(self.download_dir, pattern)):
                    try: 
                        os.remove(old_file)
                        logger.info(f"Removed old/partial file: {old_file}")
                    except OSError as e:
                        logger.warning(f"Could not remove old/partial file {old_file}: {e}")
            
            files_before = set(os.listdir(self.download_dir))
            logger.info(f"Files in download dir before Excel export click ('{self.download_dir}'): {files_before}")

            export_icon_xpath = "//svg-icon[@title='خروجی اکسل']" 
            self.add_log(f"جستجو برای آیکون خروجی اکسل: {export_icon_xpath}", "debug")
            
            export_button_element = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, export_icon_xpath))
            )
            self.add_log("آیکون خروجی اکسل پیدا و قابل کلیک است.", "info")
            
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", export_button_element)
            time.sleep(0.3)
            self.driver.execute_script("arguments[0].click();", export_button_element) 
            self.add_log("آیکون 'خروجی اکسل' کلیک شد.", "info")
            
            time.sleep(2.0) 

            start_time = time.time()
            downloaded_file_path = None
            self.add_log(f"Monitoring download directory: {self.download_dir} for {download_timeout}s", "debug")

            while time.time() - start_time < download_timeout:
                current_files_in_dir = os.listdir(self.download_dir)
                logger.debug(f"Files currently in download dir: {current_files_in_dir}")
                files_after = set(current_files_in_dir)
                new_files = files_after - files_before
                
                if new_files:
                    logger.info(f"New items detected in download dir: {new_files}")
                    for new_file_name in new_files:
                        if new_file_name.lower().endswith(('.xlsx', '.xls')) and not new_file_name.lower().endswith('.crdownload'):
                            full_path = os.path.join(self.download_dir, new_file_name)
                            try:
                                if os.path.exists(full_path):
                                    initial_size = os.path.getsize(full_path)
                                    if initial_size > 0: 
                                        time.sleep(1.0) 
                                        if os.path.exists(full_path) and os.path.getsize(full_path) == initial_size:
                                            downloaded_file_path = full_path
                                            self.add_log(f"فایل اکسل '{new_file_name}' (size: {initial_size} bytes) دانلود و تایید شد.", "success")
                                            logger.info(f"Excel file downloaded and confirmed: {downloaded_file_path}")
                                            break
                                        else:
                                            logger.debug(f"File '{new_file_name}' size changed or file disappeared, still writing/transient...")
                                    else: 
                                        logger.debug(f"Detected Excel file '{new_file_name}' but size is 0, waiting...")
                                else: 
                                     logger.debug(f"File '{new_file_name}' detected in dir listing but os.path.exists is false.")        
                            except FileNotFoundError:
                                logger.debug(f"File '{new_file_name}' was detected but then disappeared (possibly temp file before rename).")
                                continue 
                        elif new_file_name.lower().endswith('.crdownload'):
                            logger.debug(f"Download in progress: {new_file_name}")
                    if downloaded_file_path:
                        break 
                time.sleep(1.5) 
            
            if not downloaded_file_path:
                self.add_log(f"فایل اکسل در زمان {download_timeout} ثانیه دانلود نشد.", "error")
                logger.error(f"Excel download timed out. Monitored directory: {self.download_dir}")
                final_files_in_dir = os.listdir(self.download_dir)
                logger.error(f"Files present at timeout: {final_files_in_dir}")
                self.driver.save_screenshot(f"excel_download_timeout_{stock_name}_{int(time.time())}.png")
                return None
            self.add_log("فرآیند دانلود اکسل تکمیل شد.", "info")
            return downloaded_file_path

        except TimeoutException as e:
            logger.error(f"TimeoutException during order history retrieval for {stock_name}: {e}", exc_info=True)
            self.add_log(f"خطای وقفه زمانی در دریافت تاریخچه سفارشات برای {stock_name}: {type(e).__name__}", "error")
            try:
                self.driver.save_screenshot(f"history_timeout_{stock_name}_{int(time.time())}.png")
            except Exception as ex_ss:
                 logger.error(f"Could not save screenshot on TimeoutException: {ex_ss}")
            return None
        except Exception as e:
            logger.error(f"An error occurred during order history retrieval for {stock_name}: {e}", exc_info=True) 
            self.add_log(f"خطا در دریافت تاریخچه سفارشات برای {stock_name}: {type(e).__name__} - {str(e)[:100]}", "error")
            try:
                self.driver.save_screenshot(f"history_error_{stock_name}_{int(time.time())}.png")
            except Exception as ex_ss:
                logger.error(f"Could not save screenshot on Exception: {ex_ss}")
            return None

    def click_watchlist_tab(self):
        """
        Clicks on the 'Watchlist' (دیده‌بان) tab to ensure the UI is in the correct state
        for new stock selection, especially after viewing order history.
        """
        if not self.driver:
            logger.error("Driver not initialized for click_watchlist_tab.")
            self.add_log("خطا: درایور برای کلیک روی تب دیده‌بان مقداردهی نشده است.", "error")
            return False
        
        try:
            logger.info("Attempting to click the 'Watchlist' (دیده‌بان) tab.")
            self.add_log("در تلاش برای کلیک روی تب 'دیده‌بان'...", "info")

            # Selector based on the provided HTML: li[data-cy="mw-menu-icon"]
            # This is the main tab for watchlist/market view.
            watchlist_tab_selector = "li[data-cy='mw-menu-icon']"
            
            watchlist_tab_element = self.wait_for_element(By.CSS_SELECTOR, watchlist_tab_selector, timeout=10)
            
            # Check if the tab is already active to potentially avoid an unnecessary click,
            # though clicking an active tab usually just reloads or does nothing harmful.
            is_active = "menu_item--active" in watchlist_tab_element.get_attribute("class")
            if is_active:
                logger.info("Watchlist tab is already active.")
                self.add_log("تب 'دیده‌بان' هم اکنون فعال است.", "info")
                # Even if active, a click might be needed if a sub-panel (like order history) is overlaying it.
                # So, we proceed with the click.
            
            # Using JavaScript click can be more reliable for elements that might be
            # partially obscured or have complex event listeners.
            self.driver.execute_script("arguments[0].click();", watchlist_tab_element)
            logger.info("Clicked on the 'Watchlist' (دیده‌بان) tab successfully.")
            self.add_log("کلیک روی تب 'دیده‌بان' با موفقیت انجام شد.", "success")
            
            # Add a small delay to allow the UI to update if necessary
            time.sleep(0.5) # Adjust as needed, but keep it short
            return True

        except TimeoutException:
            logger.error("TimeoutException: 'Watchlist' (دیده‌بان) tab not found or not clickable.")
            self.add_log("خطای وقفه زمانی: تب 'دیده‌بان' پیدا نشد یا قابل کلیک نبود.", "error")
            try:
                # Attempt to take a screenshot for debugging
                self.driver.save_screenshot(f"watchlist_click_timeout_{int(time.time())}.png")
            except Exception as ss_err:
                logger.error(f"Could not save screenshot on watchlist click timeout: {ss_err}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while clicking 'Watchlist' (دیده‌بان) tab: {e}", exc_info=True)
            self.add_log(f"خطای غیرمنتظره هنگام کلیک روی تب 'دیده‌بان': {str(e)}", "error")
            try:
                self.driver.save_screenshot(f"watchlist_click_error_{int(time.time())}.png")
            except Exception as ss_err:
                logger.error(f"Could not save screenshot on watchlist click error: {ss_err}")
            return False


    def wait_for_element(self, by, value, timeout=10, retries=5):
        """Wait for an element to be present with retry logic."""
        for attempt in range(retries):
            try:
                return WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, value))
                )
            except TimeoutException:
                logger.warning(f"Attempt {attempt + 1}/{retries} - Timeout waiting for element: {by}={value}")
                if attempt == retries - 1:
                    # Save screenshot for debugging
                    screenshot_path = f"timeout_error_{int(time.time())}.png"
                    self.driver.save_screenshot(screenshot_path)
                    logger.error(f"Screenshot saved to {screenshot_path}")
                    # Log page source (truncated)
                    page_source = self.driver.page_source[:1000]  # Limit to 1000 chars
                    logger.error(f"Page source (truncated):\n{page_source}")
                    raise
                time.sleep(0.5) # Pause before retrying

    def login_to_website(self, username, password):
        """Automate login process for the website."""
        try:
            # Step 1: Set up driver
            if not self.setup_driver(headless=True): # یا False برای مشاهده عملکرد
                self.add_log("خطا در مقداردهی اولیه WebDriver", "error")
                raise Exception("Failed to initialize WebDriver")

            # Step 2: Navigate to the website
            url = "https://d.easytrader.ir/"
            logger.info(f"Navigating to {url}")
            self.driver.get(url)
            self.add_log(f"در حال ناوبری به {url}", "info")

            # Step 3: Use provided username and password
            logger.info("Locating username field")
            username_field = self.wait_for_element(By.ID, "user-name")
            username_field.clear()
            username_field.send_keys(username)
            logger.info("Username entered")
            self.add_log("نام کاربری وارد شد", "info")

            # Step 4: Fill password field
            logger.info("Locating password field")
            password_field = self.wait_for_element(By.ID, "password")
            password_field.clear()
            password_field.send_keys(password)
            logger.info("Password entered")
            self.add_log("رمز عبور وارد شد", "info")

            # Step 5: Click submit button
            logger.info("Locating submit button")
            submit_button = self.wait_for_element(By.CSS_SELECTOR, "button.btn-primary.w-full")
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary.w-full")))
            submit_button.click()
            logger.info("Submit button clicked")
            self.add_log("دکمه ورود کلیک شد", "info")
            
            # Step 5.1: Check for error message
            try:
                error_alert = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((By.ID, "alert"))
                )
                error_message_element = error_alert.find_element(By.CLASS_NAME, "validation-summary-errors")
                error_message = error_message_element.find_element(By.TAG_NAME, "li").text.strip()
                logger.error(f"Login failed: {error_message}")
                self.add_log(f"ورود ناموفق: {error_message}", "error")
                raise Exception(error_message)
            except TimeoutException:
                logger.info("No error alert found, proceeding with login verification")
                self.add_log("هشدار خطا یافت نشد، ادامه تایید ورود", "info")


            # Step 5.2: Quick check for easy-hero-cta-button
            try:
                WebDriverWait(self.driver, 2).until(EC.element_to_be_clickable((By.ID, "easy-hero-cta-button")))
                cta_button = self.driver.find_element(By.ID, "easy-hero-cta-button")
                cta_button.click()
                logger.info("easy-hero-cta-button found and clicked")
                self.add_log("دکمه easy-hero-cta-button کلیک شد", "info")
            except TimeoutException:
                logger.info("easy-hero-cta-button not found, continuing process")
                self.add_log("دکمه easy-hero-cta-button یافت نشد", "info")

            # Step 6: Verify login success (placeholder, replace with specific element)
            logger.info("Verifying login success")
            self.wait_for_element(By.TAG_NAME, "body") # انتظار برای بارگذاری کامل صفحه
            logger.info("Login process completed successfully")
            self.add_log("فرآیند ورود با موفقیت انجام شد", "success")
            return True

        except TimeoutException as e:
            logger.error(f"Timeout waiting for element during login: {e}")
            self.add_log(f"خطای وقفه زمانی در ورود: {str(e)}", "error")
            raise
        except Exception as e:
            logger.error(f"An error occurred during login: {e}")
            self.add_log(f"خطا در ورود: {str(e)}", "error")
            raise

    def search_stock(self, stock_name):
        """Search for a stock by name and select it from the results."""
        try:
            # Step 1: Use provided stock name
            logger.info(f"Searching for stock: {stock_name}")
            self.add_log(f"در حال جستجوی نماد: {stock_name}", "info")

            # Step 2: Click the search icon
            logger.info("Locating search icon")
            try:
                search_icon = self.wait_for_element(By.CSS_SELECTOR, "li[data-cy='search-menu-icon']")
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li[data-cy='search-menu-icon']")))
            except TimeoutException:
                logger.warning("Primary search icon selector failed, trying fallback")
                self.add_log("انتخابگر اصلی آیکون جستجو ناموفق بود، تلاش با انتخابگر جایگزین", "warning")
                search_icon = self.wait_for_element(By.XPATH, "//li[contains(@class, 'search') or contains(@data-cy, 'search')]")
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//li[contains(@class, 'search') or contains(@data-cy, 'search')]")))
            search_icon.click()
            logger.info("Search icon clicked")
            self.add_log("آیکون جستجو کلیک شد", "info")

            # Step 3: Enter stock name in search input
            logger.info("Locating search input field")
            try:
                self.wait_for_element(By.TAG_NAME, "body") # اطمینان از بارگذاری صفحه
                time.sleep(1) # انتظار کوتاه برای اطمینان از آمادگی فیلد جستجو
                search_input = self.wait_for_element(By.ID, "searchInputControl")
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.ID, "searchInputControl")))
            except TimeoutException:
                logger.warning("Primary search input selector failed, trying fallback")
                self.add_log("انتخابگر اصلی فیلد جستجو ناموفق بود، تلاش با انتخابگر جایگزین", "warning")
                search_input = self.wait_for_element(By.CSS_SELECTOR, "input[type='search'], input[placeholder*='جستجو'], input[name='search']")
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='search'], input[placeholder*='جستجو'], input[name='search']")))
            search_input.clear()
            search_input.send_keys(stock_name)
            logger.info(f"Stock name '{stock_name}' entered")
            self.add_log(f"نام نماد '{stock_name}' وارد شد", "info")
            
            # Step 4: Click the stock from search results
            logger.info(f"Locating search result for stock: {stock_name}")
            try:
                # استفاده از یک XPath انعطاف‌پذیرتر برای پیدا کردن نماد در نتایج
                stock_result_xpath = f"//div[contains(@data-cy, 'search-item-name') and contains(., '{stock_name}')] | //div[contains(text(), '{stock_name}') and ancestor::div[contains(@class, 'search-result')]]"
                stock_result = self.wait_for_element(By.XPATH, stock_result_xpath)
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, stock_result_xpath)))
            except TimeoutException:
                logger.warning(f"Primary stock result selector failed, trying specific data-cy")
                self.add_log(f"انتخابگر اصلی نتیجه جستجوی نماد '{stock_name}' ناموفق بود.", "warning")
                # تلاش با سلکتور قبلی به عنوان جایگزین نهایی
                stock_result = self.wait_for_element(By.CSS_SELECTOR, f"div[data-cy='search-item-name-{stock_name}']")
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, f"div[data-cy='search-item-name-{stock_name}']")))

            stock_result.click()
            logger.info(f"Stock '{stock_name}' selected from results")
            self.add_log(f"نماد '{stock_name}' از نتایج انتخاب شد", "info")

            # Step 5: Verify search result selection
            logger.info("Verifying stock selection")
            self.wait_for_element(By.TAG_NAME, "body") # انتظار برای بارگذاری صفحه نماد
            logger.info("Stock search and selection completed successfully")
            self.add_log("جستجو و انتخاب نماد با موفقیت انجام شد", "success")
            return True

        except TimeoutException as e:
            logger.error(f"Timeout waiting for element during stock search: {e}")
            self.add_log(f"خطای وقفه زمانی در جستجوی نماد: {str(e)}", "error")
            raise
        except Exception as e:
            logger.error(f"An error occurred during stock search: {e}")
            self.add_log(f"خطا در جستجوی نماد: {str(e)}", "error")
            raise

    def place_order(self, action, quantity, price_option, custom_price=None, send_option="now", scheduled_time_str=None):
        """
        Handle buy/sell action, quantity, price selection, scheduling,
        and ultra-fast burst submit with no artificial rate limiting.
        Logging and message checking are minimized during the burst loop for maximum speed.
        """
        try:
            # پاک کردن لاگ‌های قبلی برای این فراخوانی خاص (اختیاری)
            # self.logs = []
            # self.submission_logs = []
            self.add_log(f"شروع فرآیند سفارش: {action.capitalize()} برای تعداد {quantity}", "info")

            action = action.strip().lower()
            if action not in ['buy', 'sell']:
                self.add_log(f"عملیات نامعتبر: {action}. باید 'buy' یا 'sell' باشد.", "error")
                raise ValueError("Action must be 'buy' or 'sell'")

            logger.info(f"Locating {action} button")
            # انتخابگر دکمه خرید یا فروش
            button_selector = f"button[data-cy='order-{action}-btn']"
            try:
                action_button = self.wait_for_element(By.CSS_SELECTOR, button_selector)
            except TimeoutException:
                self.add_log(f"انتخابگر اصلی دکمه {action} ناموفق بود، تلاش با انتخابگر جایگزین.", "warning")
                button_selector_fallback = f"button.btn-outline-{'success' if action == 'buy' else 'danger'}"
                action_button = self.wait_for_element(By.CSS_SELECTOR, button_selector_fallback)
                button_selector = button_selector_fallback

            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, button_selector)))
            action_button.click()
            logger.info(f"{action.capitalize()} button clicked")
            self.add_log(f"دکمه {action.capitalize()} کلیک شد", "info")

            # اعتبارسنجی و وارد کردن تعداد
            try:
                quantity = int(quantity)
                if quantity <= 0:
                    raise ValueError("Quantity must be positive")
            except ValueError as e:
                self.add_log(f"تعداد نامعتبر: {quantity}. {e}", "error")
                raise ValueError("Quantity must be a positive integer")

            logger.info("Locating quantity input field")
            quantity_input = None
            selectors = [
                "order-form-value[data-cy='order-form-quantity'] input[data-cy='custom-number-box-input-quantity']",
                "input[data-cy='custom-number-box-input-quantity']",
                "input[id='quantity']", "input[name='quantity']"
            ]
            for idx, selector in enumerate(selectors):
                try:
                    quantity_input = self.wait_for_element(By.CSS_SELECTOR, selector, timeout=2) # کاهش timeout برای سرعت
                    self.add_log(f"فیلد تعداد با سلکتور '{selector}' پیدا شد", "info")
                    break
                except TimeoutException:
                    self.add_log(f"فیلد تعداد با سلکتور '{selector}' پیدا نشد (تلاش {idx+1}/{len(selectors)})", "warning")
            
            if not quantity_input:
                self.add_log("خطا: فیلد تعداد پیدا نشد پس از تمام تلاش‌ها", "error")
                raise TimeoutException("Quantity input field not found after all attempts")

            try:
                quantity_input.clear()
                # time.sleep(0.1) # حذف یا کاهش شدید تاخیر
                quantity_input.send_keys(str(quantity))
                # time.sleep(0.2) # حذف یا کاهش شدید تاخیر
                self.add_log(f"تعداد {quantity} با موفقیت وارد شد", "info")
            except Exception as e:
                self.add_log(f"خطا در وارد کردن تعداد: {str(e)}", "error")
                raise

            # انتخاب گزینه قیمت
            price_option = price_option.strip().lower()
            if price_option not in ['max', 'min', 'custom']:
                self.add_log(f"گزینه قیمت نامعتبر: {price_option}", "error")
                raise ValueError("Price option must be 'max', 'min', or 'custom'")

            if price_option == 'max':
                logger.info("Locating maximum price button")
                max_price_button = self.wait_for_element(By.CSS_SELECTOR, "div[data-cy='order-form-max-price']")
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[data-cy='order-form-max-price']")))
                max_price_button.click()
                self.add_log("قیمت حداکثر انتخاب شد", "info")
            elif price_option == 'min':
                logger.info("Locating minimum price button")
                min_price_button = self.wait_for_element(By.CSS_SELECTOR, "div[data-cy='order-form-min-price']")
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[data-cy='order-form-min-price']")))
                min_price_button.click()
                self.add_log("قیمت حداقل انتخاب شد", "info")
            else: # custom price
                try:
                    custom_price = float(custom_price)
                    if custom_price <= 0:
                        raise ValueError("Price must be positive")
                except (ValueError, TypeError) as e:
                    self.add_log(f"قیمت سفارشی نامعتبر: {custom_price}. {e}", "error")
                    raise ValueError("Custom price must be a positive number")
                
                logger.info("Locating custom price input field")
                price_input_selector = "custom-number-box input[data-cy='custom-number-box-input-price']"
                try:
                    price_input = self.wait_for_element(By.CSS_SELECTOR, price_input_selector)
                except TimeoutException:
                    self.add_log(f"انتخابگر اصلی قیمت '{price_input_selector}' ناموفق بود، تلاش با جایگزین.", "warning")
                    price_input_selector = "input[id*='price'], input[data-cy*='price']" # انتخابگر جایگزین
                    price_input = self.wait_for_element(By.CSS_SELECTOR, price_input_selector)

                price_input.clear()
                # time.sleep(0.1) # حذف یا کاهش
                price_input.send_keys(str(custom_price))
                self.add_log(f"قیمت سفارشی '{custom_price}' وارد شد", "info")

            # مدیریت زمان ارسال
            send_option = send_option.strip().lower()
            if send_option not in ['now', 'schedule']:
                self.add_log(f"گزینه ارسال نامعتبر: {send_option}", "error")
                raise ValueError("Send option must be 'now' or 'schedule'")

            if send_option == 'schedule':
                if not scheduled_time_str:
                    self.add_log("خطا: زمانبندی انتخاب شده اما زمان ارائه نشده است.", "error")
                    raise ValueError("Scheduled time string is required for schedule option.")
                
                now_system = datetime.now(tehran_tz)
                try:
                    # پشتیبانی از فرمت با میلی‌ثانیه و بدون میلی‌ثانیه
                    if '.' in scheduled_time_str:
                        scheduled_time_obj = datetime.strptime(scheduled_time_str, "%H:%M:%S.%f").time()
                    else:
                        scheduled_time_obj = datetime.strptime(scheduled_time_str, "%H:%M:%S").time()
                except (ValueError, TypeError) as e:
                    logger.error(f"فرمت زمان برنامه‌ریزی شده نامعتبر است: {scheduled_time_str}. فرمت مورد انتظار: HH:MM:SS یا HH:MM:SS.sss - {e}")
                    self.add_log(f"خطا: فرمت زمان برنامه‌ریزی شده نامعتبر: {scheduled_time_str}", "error")
                    raise ValueError(f"Invalid scheduled time format: {e}")

                naive_target_datetime = datetime.combine(now_system.date(), scheduled_time_obj)
                target_datetime = tehran_tz.localize(naive_target_datetime)

                if target_datetime < now_system:
                    # اگر زمان گذشته است، بررسی کنید که آیا مربوط به روز بعد است یا خیر
                    if (now_system - target_datetime).total_seconds() > 300: # اگر بیش از 5 دقیقه گذشته باشد
                        logger.warning(f"زمان برنامه‌ریزی شده {target_datetime.strftime('%H:%M:%S.%f')} برای امروز گذشته است. بررسی برای روز بعد...")
                        # اگر زمان برای امروز گذشته، آن را برای فردا تنظیم کنید
                        # این بخش نیاز به بررسی دقیق‌تر دارد که آیا این رفتار مطلوب است یا خیر
                        # target_datetime += timedelta(days=1)
                        # logger.info(f"زمان برنامه‌ریزی شده به روز بعد منتقل شد: {target_datetime.strftime('%Y-%m-%d %H:%M:%S.%f')}")
                        # self.add_log(f"هشدار: زمان برنامه‌ریزی شده {scheduled_time_str} برای امروز گذشته، در نظر گرفتن برای فردا.", "warning")
                        # فعلا فرض می‌کنیم اگر گذشته، خطاست یا باید بلافاصله اجرا شود
                        self.add_log(f"خطا: زمان برنامه‌ریزی شده {target_datetime.strftime('%H:%M:%S.%f')} برای امروز به طور قابل توجهی گذشته است.", "error")
                        raise ValueError("Scheduled time for today has already significantly passed.")
                    logger.warning(f"زمان برنامه‌ریزی شده {target_datetime.strftime('%H:%M:%S.%f')} برای امروز کمی گذشته است (زمان فعلی: {now_system.strftime('%H:%M:%S.%f')}). بلافاصله ادامه می‌دهیم.")
                    self.add_log(f"هشدار: زمان برنامه‌ریزی شده {target_datetime.strftime('%H:%M:%S.%f')} کمی گذشته، ادامه فوری.", "warning")

                else: # انتظار برای زمان برنامه‌ریزی شده
                    self.add_log(f"بات در حال انتظار برای زمان برنامه‌ریزی شده (ساعت تهران): {target_datetime.strftime('%H:%M:%S.%f')}", "info")
                    logger.info(f"Waiting for scheduled time (Tehran clock): {target_datetime.strftime('%H:%M:%S.%f')}")

                    # حلقه انتظار دقیق‌تر
                    while True:
                        current_system_time = datetime.now(tehran_tz)
                        remaining_seconds = (target_datetime - current_system_time).total_seconds()
                        
                        if remaining_seconds <= 0: 
                            break
                        
                        # استفاده از sleep‌های بسیار کوتاه برای دقت بالا
                        # این مقادیر ممکن است نیاز به تنظیم دقیق بر اساس سیستم داشته باشند
                        if remaining_seconds > 0.01: # اگر بیش از 10 میلی‌ثانیه باقی مانده
                            time.sleep(0.001) # خواب 1 میلی‌ثانیه
                        elif remaining_seconds > 0.0001: # اگر بیش از 0.1 میلی‌ثانیه باقی مانده
                            time.sleep(0.00001) # خواب 10 میکروثانیه
                        # برای زمان‌های بسیار کوتاه، حلقه بدون sleep اجرا می‌شود (busy-waiting)
                        # این کار CPU را مصرف می‌کند اما دقت زمانی را افزایش می‌دهد
                
                logger.info(f"زمان برنامه‌ریزی شده {target_datetime.strftime('%H:%M:%S.%f')} فرا رسید. شروع ارسال سریع.")
                self.add_log(f"زمان برنامه‌ریزی شده فرا رسید. شروع ارسال سریع در {datetime.now(tehran_tz).strftime('%H:%M:%S.%f')}", "info")

            # --- شروع حلقه ارسال سریع سفارش (بخش بهینه‌سازی شده) ---
            logger.info(f"Locating {action} submit button for burst")
            # انتخابگر دکمه ارسال نهایی (خرید/فروش)
            submit_selector = f"button.btn-sm.btn-{'success' if action == 'buy' else 'danger'}"
            try:
                submit_button = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, submit_selector))
                )
            except TimeoutException:
                self.add_log(f"انتخابگر اصلی دکمه ارسال {action} ناموفق بود، تلاش با XPath.", "warning")
                # انتخابگر XPath جایگزین و عمومی‌تر
                submit_selector_xpath = f"//button[contains(@class, 'btn-sm') and (contains(., 'ارسال {('خرید' if action == 'buy' else 'فروش')}') or contains(., '{action.capitalize()}')) and contains(@class, 'btn-{'success' if action == 'buy' else 'danger'}')]"
                submit_button = self.wait_for_element(By.XPATH, submit_selector_xpath)
            
            WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(submit_button))
            self.add_log("دکمه ارسال برای حلقه سریع آماده است.", "info")

            start_burst_time = time.perf_counter() # زمان شروع دقیق با perf_counter
            burst_duration_seconds = 20  # مدت زمان ارسال سریع (مثلا 20 ثانیه)
            
            click_count = 0
            order_successful = False
            # کلمه کلیدی برای تشخیص پیام موفقیت (باید با پیام واقعی کارگزاری تطابق داشته باشد)
            success_message_keyword = "هسته معاملات ثبت گردید" 
            
            # لاگ شروع حلقه ارسال سریع با زمان دقیق
            self.add_log(f"شروع حلقه ارسال سریع در {datetime.now(tehran_tz).strftime('%H:%M:%S.%f')} بدون محدودیت نرخ مصنوعی.", "info")
            self.submission_logs.append(f"{datetime.now(tehran_tz).strftime('%H:%M:%S.%f')[:-3]}: شروع  ارسال سریع سفارشات.")

            # حلقه اصلی ارسال سفارش با حداکثر سرعت
            while (time.perf_counter() - start_burst_time) < burst_duration_seconds:
                try:
                    # کلیک با جاوااسکریپت برای سرعت بیشتر و جلوگیری از مشکلات احتمالی کلیک استاندارد
                    self.driver.execute_script("arguments[0].click();", submit_button)
                    click_count += 1
                    # لاگ‌برداری در این بخش به حداقل ممکن کاهش یافته است
                    # می‌توان زمان هر کلیک را در یک لیست ذخیره کرد و بعدا پردازش نمود
                    # self.submission_logs.append(f"{datetime.now(tehran_tz).strftime('%H:%M:%S.%f')[:-3]}: کلیک {click_count}")

                except Exception as e:
                    # در صورت بروز خطا در کلیک، آن را لاگ کرده و ادامه می‌دهیم
                    # این خطاها ممکن است به دلیل سرعت بالای ارسال باشند
                    current_error_time = datetime.now(tehran_tz).strftime("%H:%M:%S.%f")[:-3]
                    self.submission_logs.append(f"{current_error_time}: خطا در ارسال سفارشات (تلاش {click_count}): {str(e)[:100]}") # کوتاه کردن پیام خطا
                    # در صورت بروز خطای زیاد، شاید بهتر باشد حلقه متوقف شود یا تاخیر کوچکی ایجاد شود
                    # اما طبق درخواست، هدف حداکثر سرعت است
                    continue 
                
                # بررسی پیام موفقیت در اینجا حذف شده تا سرعت حلقه کم نشود
                # این بررسی پس از اتمام حلقه انجام خواهد شد

            # پایان حلقه ارسال سریع
            end_burst_time = time.perf_counter()
            total_burst_duration = end_burst_time - start_burst_time
            self.add_log(f"پایان حلقه ارسال سریع. کل کلیک‌ها: {click_count}. زمان سپری شده: {total_burst_duration:.4f} ثانیه.", "info")
            self.submission_logs.append(f"{datetime.now(tehran_tz).strftime('%H:%M:%S.%f')[:-3]}: پایان ارسال سفارشات . تعداد کل سفارشات ارسالی : {click_count}, مدت: {total_burst_duration:.4f}s")

            # بررسی نهایی برای پیام موفقیت پس از اتمام زمان انفجار
            # این بخش مهم است چون در طول حلقه، پیام‌ها چک نمی‌شوند
            logger.info("بررسی نهایی برای پیام پس از اتمام زمان انفجار")
            self.add_log("شروع بررسی نهایی پیام کارگزاری پس از اتمام حلقه ارسال.", "info")
            try:
                # کمی صبر برای اینکه پیام‌های احتمالی در DOM ظاهر شوند
                time.sleep(0.5) # این زمان ممکن است نیاز به تنظیم داشته باشد
                
                # تلاش برای یافتن همه پیام‌های اعلان
                message_elements = self.driver.find_elements(By.CSS_SELECTOR, "span[data-cy='notify-message']")
                
                if message_elements:
                    # بررسی آخرین پیام یا همه پیام‌ها برای کلمه کلیدی موفقیت
                    for msg_element in reversed(message_elements): # بررسی از آخرین پیام
                        final_message = msg_element.text.strip()
                        if final_message: # اگر پیام خالی نباشد
                            msg_time = datetime.now(tehran_tz).strftime("%H:%M:%S.%f")[:-3]
                            log_msg = f"{msg_time}: پیام نهایی کارگزار (پس از انفجار): {final_message}"
                            self.submission_logs.append(log_msg)
                            self.add_log(f"پیام نهایی پس از انفجار: {final_message}", "info")
                            
                            if success_message_keyword in final_message:
                                order_successful = True
                                self.add_log(f"موفقیت بر اساس پیام '{success_message_keyword}' تأیید شد.", "success")
                                break # اگر پیام موفقیت پیدا شد، از حلقه خارج شو
                    if not order_successful:
                         self.add_log("پیام موفقیت در بررسی نهایی یافت نشد.", "warning")
                else:
                    self.add_log("هیچ پیام نهایی پس از ارسال سفارشاتیافت نشد.", "warning")
                    self.submission_logs.append(f"{datetime.now(tehran_tz).strftime('%H:%M:%S.%f')[:-3]}: هیچ پیام نهایی کارگزار (پس از انفجار) یافت نشد")

            except Exception as e:
                # خطاهایی که ممکن است در حین تلاش برای خواندن پیام‌ها رخ دهد
                self.add_log(f"خطا در بررسی پیام نهایی: {str(e)}", "warning")
                self.submission_logs.append(f"{datetime.now(tehran_tz).strftime('%H:%M:%S.%f')[:-3]}: خطا در بررسی پیام نهایی: {str(e)}")

            logger.info("Order placement process completed within place_order.")
            self.add_log("فرآیند ارسال سفارش در place_order تکمیل شد", "info")
            return {"success": order_successful, "logs": self.logs, "submission_logs": self.submission_logs, "click_count": click_count, "burst_duration": total_burst_duration}

        except TimeoutException as e:
            logger.error(f"Timeout waiting for element during order placement: {e}")
            self.add_log(f"خطای وقفه زمانی در ارسال سفارش: {str(e)}", "error")
            current_time = datetime.now(tehran_tz).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.submission_logs.append(f"{current_time}: خطای وقفه زمانی: {str(e)}")
            # raise # یا برگرداندن نتیجه ناموفق بدون raise کردن مجدد
            return {"success": False, "logs": self.logs, "submission_logs": self.submission_logs, "error": f"Timeout: {str(e)}"}
        except Exception as e:
            logger.error(f"An error occurred during order placement: {e}")
            self.add_log(f"خطا در ارسال سفارش: {str(e)}", "error")
            current_time = datetime.now(tehran_tz).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.submission_logs.append(f"{current_time}: خطا در ارسال سفارش: {str(e)}")
            # raise # یا برگرداندن نتیجه ناموفق
            return {"success": False, "logs": self.logs, "submission_logs": self.submission_logs, "error": f"Exception: {str(e)}"}


            raise


    def add_log(self, message, status="info"):
        log_time = datetime.now(tehran_tz).strftime("%H:%M:%S.%f")[:-3] # زمان با دقت میلیثانیه
        log_entry = f"{log_time} - {status.upper()} - {message}"
        self.logs.append(log_entry)
        # print(log_entry) # برای نمایش لحظه‌ای لاگ‌ها در کنسول (اختیاری)
        return log_entry

    def run(self, username, password, stock_name, action, quantity, price_option, custom_price=None, send_option="now", scheduled_time_str=None):
        """Run the automation process."""
        try:
            self.logs = []
            self.submission_logs = []
            self.add_log(f"شروع فرآیند اتوماسیون برای نماد {stock_name}", "info")
            
            if not self.login_to_website(username, password):
                 self.add_log("فرآیند اتوماسیون به دلیل عدم موفقیت در ورود متوقف شد.", "critical")
                 return {"success": False, "logs": self.logs, "submission_logs": self.submission_logs, "error": "Login Failed"}

            if not self.search_stock(stock_name):
                self.add_log("فرآیند اتوماسیون به دلیل عدم موفقیت در جستجوی نماد متوقف شد.", "critical")
                return {"success": False, "logs": self.logs, "submission_logs": self.submission_logs, "error": "Stock Search Failed"}

            result = self.place_order(action, quantity, price_option, custom_price, send_option, scheduled_time_str)
            
            self.add_log("اتمام فرآیند اتوماسیون", "info")
            return {"success": result.get("success", False), "logs": self.logs, "submission_logs": result.get("submission_logs", [])}
        except Exception as e:
            logger.error(f"Automation failed: {e}")
            self.add_log(f"خطای بحرانی در اتوماسیون: {str(e)}", "critical")
            current_time = datetime.now(tehran_tz).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.submission_logs.append(f"{current_time}: خطای بحرانی اتوماسیون: {str(e)}")
            # در اینجا نباید raise کرد تا لاگ‌ها و نتیجه ناموفق برگردانده شود
            return {"success": False, "logs": self.logs, "submission_logs": self.submission_logs, "error": str(e)}
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("Browser closed")
                self.add_log("مرورگر بسته شد", "info")

