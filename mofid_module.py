# ماژول ورژن 1
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


tehran_tz = pytz.timezone('Asia/Tehran')

# Set up logging for debugging and tracking
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MofidBroker:
    def __init__(self):
        self.driver = None
        self.logs = []
        self.submission_logs = []

    def setup_driver(self, headless=True):  # Changed default to True for headless
        """Initialize and return a Chrome WebDriver with optimized settings for headless operation."""
        try:
            chrome_options = Options()
            # --- Essential Headless Mode Options ---
            chrome_options.add_argument("--headless")  # Run Chrome in headless mode
            chrome_options.add_argument("--no-sandbox") # Bypass OS security model, REQUIRED for headless Linux
            chrome_options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems

            # --- Performance & Resource Optimization Options ---
            chrome_options.add_argument("--disable-gpu")  # Disable GPU hardware acceleration (often not needed for headless)
            chrome_options.add_argument("--disable-extensions")  # Disable extensions
            chrome_options.add_argument("--disable-infobars")  # Disable infobars
            chrome_options.add_argument("--disable-popup-blocking") # Disable pop-up blocking
            chrome_options.add_argument("--disable-notifications") # Disable notifications
            chrome_options.add_argument("--disable-logging") # Disable logging
            chrome_options.add_argument("--log-level=3") # Suppress console logs
            chrome_options.add_argument("--silent") # Suppress console logs (alternative)
            chrome_options.add_argument("--blink-settings=imagesEnabled=false") # Disable images
            # chrome_options.add_argument("--disable-javascript") # Uncomment if JavaScript is not strictly needed for the target site

            # --- Stability & Compatibility Options ---
            chrome_options.add_argument("--window-size=1920,1080") # Specify window size, can be important for some sites even in headless
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"]) # Hide "Chrome is being controlled by automated test software"
            chrome_options.add_argument("--disable-blink-features=AutomationControlled") # Further attempt to hide automation

            # --- Network Optimization (Optional - can sometimes cause issues) ---
            # chrome_options.add_argument('--dns-prefetch-disable')
            # chrome_options.add_argument('--disable-setuid-sandbox') # Use with caution

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
            return True
        except WebDriverException as e:
            print(f"Error setting up WebDriver: {e}")
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
        and super-fast burst submit with 100ms rate limiting.
        """
        try:
            # اگر می‌خواهید لاگ‌ها برای هر بار فراخوانی place_order جدا باشند، آنها را اینجا پاک کنید
            # self.logs = [] 
            # self.submission_logs = []
            self.add_log(f"شروع فرآیند سفارش: {action.capitalize()} برای تعداد {quantity}", "info")

            action = action.strip().lower()
            if action not in ['buy', 'sell']:
                self.add_log(f"عملیات نامعتبر: {action}. باید 'buy' یا 'sell' باشد.", "error")
                raise ValueError("Action must be 'buy' or 'sell'")

            logger.info(f"Locating {action} button")
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
                    quantity_input = self.wait_for_element(By.CSS_SELECTOR, selector, timeout=2)
                    self.add_log(f"فیلد تعداد با سلکتور '{selector}' پیدا شد", "info")
                    break
                except TimeoutException:
                    self.add_log(f"فیلد تعداد با سلکتور '{selector}' پیدا نشد (تلاش {idx+1}/{len(selectors)})", "warning")
            
            if not quantity_input:
                self.add_log("خطا: فیلد تعداد پیدا نشد پس از تمام تلاش‌ها", "error")
                raise TimeoutException("Quantity input field not found after all attempts")

            try:
                quantity_input.clear()
                time.sleep(0.1) # انتظار برای اطمینان از پاک شدن
                quantity_input.send_keys(str(quantity))
                time.sleep(0.2) # انتظار برای پردازش ورودی
                self.add_log(f"تعداد {quantity} با موفقیت وارد شد", "info")
            except Exception as e:
                self.add_log(f"خطا در وارد کردن تعداد: {str(e)}", "error")
                raise

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
                    price_input_selector = "input[id*='price'], input[data-cy*='price']"
                    price_input = self.wait_for_element(By.CSS_SELECTOR, price_input_selector)

                price_input.clear()
                time.sleep(0.1)
                price_input.send_keys(str(custom_price))
                self.add_log(f"قیمت سفارشی '{custom_price}' وارد شد", "info")

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
                    scheduled_time_obj = datetime.strptime(scheduled_time_str, "%H:%M:%S.%f").time()
                except (ValueError, TypeError) as e:
                    logger.error(f"فرمت زمان برنامه‌ریزی شده نامعتبر است: {scheduled_time_str}. فرمت مورد انتظار: HH:MM:SS.sss - {e}")
                    self.add_log(f"خطا: فرمت زمان برنامه‌ریزی شده نامعتبر: {scheduled_time_str}", "error")
                    raise ValueError(f"Invalid scheduled time format: {e}")

                naive_target_datetime = datetime.combine(now_system.date(), scheduled_time_obj)
                target_datetime = tehran_tz.localize(naive_target_datetime)

                if target_datetime < now_system:
                    if (now_system - target_datetime).total_seconds() > 300: 
                        logger.error(f"زمان برنامه‌ریزی شده {target_datetime.strftime('%H:%M:%S.%f')} برای امروز به طور قابل توجهی گذشته است (زمان فعلی: {now_system.strftime('%H:%M:%S.%f')}).")
                        self.add_log(f"خطا: زمان برنامه‌ریزی شده {target_datetime.strftime('%H:%M:%S.%f')} برای امروز گذشته است.", "error")
                        raise ValueError("Scheduled time for today has already significantly passed.")
                    logger.warning(f"زمان برنامه‌ریزی شده {target_datetime.strftime('%H:%M:%S.%f')} برای امروز کمی گذشته است (زمان فعلی: {now_system.strftime('%H:%M:%S.%f')}). بلافاصله ادامه می‌دهیم.")
                    self.add_log(f"هشدار: زمان برنامه‌ریزی شده {target_datetime.strftime('%H:%M:%S.%f')} کمی گذشته، ادامه فوری.", "warning")
                else:
                    self.add_log(f"بات در حال انتظار برای زمان برنامه‌ریزی شده (ساعت تهران): {target_datetime.strftime('%H:%M:%S.%f')}", "info")
                    logger.info(f"Waiting for scheduled time (Tehran clock): {target_datetime.strftime('%H:%M:%S.%f')}")

                    while True:
                        current_system_time = datetime.now(tehran_tz)
                        remaining_seconds = (target_datetime - current_system_time).total_seconds()
                        
                        if remaining_seconds <= 0: 
                            break
                        
                        if remaining_seconds > 0.02: 
                            time.sleep(max(0.0001, min(0.01, remaining_seconds / 2.0)))
                        elif remaining_seconds > 0.0001: 
                            time.sleep(0.00001) 
                        
                logger.info(f"زمان برنامه‌ریزی شده {target_datetime.strftime('%H:%M:%S.%f')} فرا رسید. شروع ارسال سریع.")
                self.add_log(f"زمان برنامه‌ریزی شده فرا رسید. شروع ارسال سریع در {datetime.now(tehran_tz).strftime('%H:%M:%S.%f')}", "info")

            # --- شروع حلقه ارسال سریع سفارش ---
            logger.info(f"Locating {action} submit button for burst")
            submit_selector = f"button.btn-sm.btn-{'success' if action == 'buy' else 'danger'}"
            try:
                submit_button = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, submit_selector))
                )
            except TimeoutException:
                self.add_log(f"انتخابگر اصلی دکمه ارسال {action} ناموفق بود، تلاش با XPath.", "warning")
                submit_selector_xpath = f"//button[contains(@class, 'btn-sm') and (contains(., 'ارسال خرید') or contains(., 'ارسال فروش')) and contains(@class, 'btn-{'success' if action == 'buy' else 'danger'}')]"
                submit_button = self.wait_for_element(By.XPATH, submit_selector_xpath)
            
            WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(submit_button))
            self.add_log("دکمه ارسال برای حلقه سریع آماده است.", "info")

            start_burst_time = time.perf_counter()
            burst_duration_seconds = 20  # مدت زمان ارسال سریع (مثلا 20 ثانیه)
            min_interval_seconds = 0.001 # حداقل فاصله زمانی 1 میلی‌ثانیه
            last_click_time = 0 # زمان آخرین کلیک موفق

            success_message_keyword = "هسته معاملات ثبت گردید" 
            click_count = 0
            order_successful = False

            self.add_log(f"شروع حلقه ارسال سریع در {datetime.now(tehran_tz).strftime('%H:%M:%S.%f')} با محدودیت نرخ {min_interval_seconds*1000:.0f}ms", "info")

            while (time.perf_counter() - start_burst_time) < burst_duration_seconds:
                current_loop_time = time.perf_counter()

                # بررسی محدودیت نرخ ارسال
                if last_click_time > 0: # اگر اولین کلیک نیست
                    time_since_last_click = current_loop_time - last_click_time
                    if time_since_last_click < min_interval_seconds:
                        sleep_duration = min_interval_seconds - time_since_last_click
                        if sleep_duration > 0: # فقط اگر نیاز به خوابیدن باشد
                           # logger.debug(f"Rate limit: sleeping for {sleep_duration:.4f}s") # برای دیباگ
                           time.sleep(sleep_duration)
                        # current_loop_time را بعد از sleep به‌روزرسانی می‌کنیم تا محاسبات بعدی دقیق‌تر باشند
                        current_loop_time = time.perf_counter()


                try:
                    # کلیک با جاوااسکریپت برای سرعت بیشتر
                    self.driver.execute_script("arguments[0].click();", submit_button)
                    last_click_time = time.perf_counter() # ثبت زمان کلیک موفق
                    click_count += 1
                    current_click_log_time = datetime.now(tehran_tz).strftime("%H:%M:%S.%f")[:-3]
                    self.submission_logs.append(f"{current_click_log_time}: تلاش {click_count} برای ارسال سفارش")
                except Exception as e:
                    current_error_time = datetime.now(tehran_tz).strftime("%H:%M:%S.%f")[:-3]
                    self.submission_logs.append(f"{current_error_time}: خطا در کلیک (تلاش {click_count}): {str(e)}")
                    # اگر کلیک با خطا مواجه شد، شاید بهتر باشد کمی صبر کنیم یا به تلاش بعدی برویم
                    # time.sleep(0.001) # تاخیر بسیار کوتاه در صورت بروز خطا در کلیک
                    continue # ادامه به تلاش بعدی در حلقه while

                # بررسی پیام موفقیت با تناوب (مثلا هر 3 کلیک یا اولین کلیک)
                if click_count == 1 or click_count % 3 == 0:
                    try:
                        message_elements = self.driver.find_elements(By.CSS_SELECTOR, "span[data-cy='notify-message']")
                        if message_elements:
                            message_text = message_elements[-1].text.strip() 
                            if message_text: 
                                msg_time = datetime.now(tehran_tz).strftime("%H:%M:%S.%f")[:-3]
                                self.submission_logs.append(f"{msg_time}: پیام کارگزار: {message_text}")
                                self.add_log(f"پیام اعلان دریافت شد: {message_text}", "info")
                                
                                if success_message_keyword in message_text:
                                    logger.info(f"پیام موفقیت‌آمیز '{success_message_keyword}' دریافت شد، توقف ارسال.")
                                    self.add_log(f"پیام موفقیت‌آمیز '{success_message_keyword}' دریافت شد.", "success")
                                    order_successful = True
                                    break 
                    except Exception: 
                        pass
            
            self.add_log(f"پایان حلقه ارسال سریع. کل کلیک‌ها: {click_count}. زمان سپری شده: {time.perf_counter() - start_burst_time:.3f} ثانیه.", "info")

            if not order_successful:
                logger.info("بررسی نهایی برای پیام پس از اتمام زمان انفجار")
                try:
                    time.sleep(0.5) # فرصت برای نمایش پیام
                    message_elements = self.driver.find_elements(By.CSS_SELECTOR, "span[data-cy='notify-message']")
                    if message_elements:
                        final_message = message_elements[-1].text.strip()
                        if final_message:
                            msg_time = datetime.now(tehran_tz).strftime("%H:%M:%S.%f")[:-3]
                            self.submission_logs.append(f"{msg_time}: پیام نهایی کارگزار (پس از انفجار): {final_message}")
                            self.add_log(f"پیام نهایی پس از انفجار: {final_message}", "info")
                            if success_message_keyword in final_message:
                                order_successful = True
                                self.add_log("موفقیت در بررسی نهایی تأیید شد.", "success")
                            else:
                                self.add_log(f"عدم موفقیت بر اساس پیام نهایی: {final_message}", "warning")
                    else:
                        self.add_log("هیچ پیام نهایی پس از انفجار یافت نشد.", "warning")
                        self.submission_logs.append(f"{datetime.now(tehran_tz).strftime('%H:%M:%S.%f')[:-3]}: هیچ پیام نهایی کارگزار (پس از انفجار) یافت نشد")
                except Exception as e:
                    self.add_log(f"خطا در بررسی پیام نهایی: {str(e)}", "warning")
                    self.submission_logs.append(f"{datetime.now(tehran_tz).strftime('%H:%M:%S.%f')[:-3]}: خطا در بررسی پیام نهایی: {str(e)}")

            logger.info("Order placement process completed within place_order.")
            self.add_log("فرآیند ارسال سفارش در place_order تکمیل شد", "info")
            return {"success": order_successful, "logs": self.logs, "submission_logs": self.submission_logs}

        except TimeoutException as e:
            logger.error(f"Timeout waiting for element during order placement: {e}")
            self.add_log(f"خطای وقفه زمانی در ارسال سفارش: {str(e)}", "error")
            current_time = datetime.now(tehran_tz).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.submission_logs.append(f"{current_time}: خطای وقفه زمانی: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"An error occurred during order placement: {e}")
            self.add_log(f"خطا در ارسال سفارش: {str(e)}", "error")
            current_time = datetime.now(tehran_tz).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.submission_logs.append(f"{current_time}: خطا در ارسال سفارش: {str(e)}")
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

