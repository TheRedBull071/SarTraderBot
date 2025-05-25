#salam salam va kheili salam ** Dual Push**
import os
from dotenv import load_dotenv
import base64
import io
import logging
from filelock import FileLock, Timeout
import asyncio
import json
from time import sleep
import uuid # For generating unique tokens
from datetime import datetime, time as dt_time, timedelta
from typing import List
from PIL import Image # Still needed if we have other images, but not for Mofid CAPTCHA
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InputFile,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from telegram.ext import MessageHandler, CallbackQueryHandler
from telegram.ext.filters import Text
from telegram.error import BadRequest # For managing errors related to message deletion
from mofid_module import MofidBroker # Import Mofid broker module
from selenium.webdriver.common.by import By # For closing forms (if applicable to Mofid)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

from uuid import uuid4
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from logging import getLogger
from typing import List

import mysql.connector
from mysql.connector import Error
from mysql.connector import pooling
from datetime import datetime

import os 
import asyncio 
from telegram import InputFile 
from telegram.error import BadRequest 


logger = getLogger(__name__)

load_dotenv()
# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


# Define conversation states
(
    MAIN_MENU,
    BROKER_SELECTION, # Will be simplified for Mofid-only bot
    # LOGIN_USERNAME, # Implicit
    # LOGIN_PASSWORD, # Implicit, combined into LOGIN_ENTER_BROKERAGE_PASSWORD
    # LOGIN_CAPTCHA, # Removed for Mofid
    STOCK_SELECTION,
    ORDER_ACTION,
    ORDER_PRICE_TYPE,
    ORDER_CUSTOM_PRICE,
    ORDER_SEND_METHOD,
    ORDER_SCHEDULE_TIME,
    ORDER_QUANTITY,
    ORDER_CONFIRMATION,
    VIEW_DETAILS,
    POST_ORDER_CHOICE,
    REGISTER_PROMPT,
    REGISTER_FULL_NAME,
    REGISTER_BROKERAGE_USERNAME,
    REGISTER_BROKERAGE_TYPE, # Will default/confirm Mofid
    REGISTER_HAS_TOKEN,
    REGISTER_TOKEN_INPUT,
    LOGIN_CONFIRM_DETAILS,
    LOGIN_ENTER_BROKERAGE_PASSWORD, # Key state for Mofid login
    # LOGIN_ENTER_TOKEN, # This was for Agah premium, Mofid will use password
    EXPIRED_ACCOUNT_OPTIONS,
    LOGIN_ENTER_NEW_TOKEN_FOR_EXPIRED,
    ATTEMPT_MOFID_LOGIN, # New state for actual login attempt
    AWAITING_NEW_BROKERAGE_USERNAME,
) = range(24) # Adjusted range




EMOJI = {
    "success": "✅", "error": "❌", "warning": "⚠️", "info": "ℹ️",
    "clock": "⏰", "money": "💰", "trade": "💹", "login": "🔐",
    "buy": "🟢", "sell": "🔴", "loading": "⏳", "done": "🎯",
    "report": "📊", "time": "🕒", "price": "🏷️", "alert": "🚨",
    "admin": "👨‍💼", "tutorial": "📚", "start": "🚀", "logout": "🚪",
    "new_order": "🔄", "form_close": "📄", "cleanup": "🧹", "details": "📜",
    "register": "📝", "free": "🆓", "premium": "💎", "token": "🔑",
    "confirm": "👍", "password": "🔑", "ratelimit": "🚦", "block": "🚫"
}

#USERS_FILE = "users.json" # Shared user data file

MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW_MINUTES = 10
LOGIN_COOLDOWN_MINUTES = 15
MIN_SECONDS_BETWEEN_ORDERS = 10 # This can be adjusted based on Mofid's behavior





#Database connection details

from mysql.connector import pooling

dbconfig = {
    "host": os.environ.get("MYSQLHOST"),
    "port": int(os.environ.get("MYSQLPORT", 3306)),
    "user": os.environ.get("MYSQLUSER"),
    "password": os.environ.get("MYSQLPASSWORD"),
    "database": os.environ.get("MYSQLDATABASE")
}
connection_pool = pooling.MySQLConnectionPool(pool_name="mypool", pool_size=5, **dbconfig)

def get_db_connection():
    try:
        return connection_pool.get_connection()
    except Error as e:
        logger.error(f"Error getting connection from pool: {e}")
        return None


# --- User Data Management (Identical to telegramBotV7.py) ---
def load_users_data():
    connection = get_db_connection()
    if not connection:
        logger.error("Cannot load users data: No database connection")
        return {"users": [], "tokens": [], "activity_log": {}}

    try:
        cursor = connection.cursor(dictionary=True)

        # خواندن کاربران با تمام فیلدها
        cursor.execute("""
            SELECT telegram_id, telegram_name, registration_date, brokerage_type, full_name, 
                   brokerage_username, subscription_type, token, expiry_date, brokerage_password, 
                   real_name, national_id, phone_number, email 
            FROM users
        """)
        users = cursor.fetchall()

        # خواندن توکن‌ها
        cursor.execute("SELECT * FROM tokens")
        tokens = cursor.fetchall()

        # خواندن لاگ‌های فعالیت
        cursor.execute("""
            SELECT telegram_id, login_attempts_count, first_attempt_timestamp, 
                   cooldown_until, last_order_submission_timestamp 
            FROM activity_log
        """)
        activity_logs = cursor.fetchall()
        activity_log = {}
        for log in activity_logs:
            telegram_id = str(log["telegram_id"])
            activity_log[telegram_id] = {
                "login_attempts": {
                    "count": log["login_attempts_count"],
                    "first_attempt_timestamp": log["first_attempt_timestamp"].isoformat() if log["first_attempt_timestamp"] else None,
                    "cooldown_until": log["cooldown_until"].isoformat() if log["cooldown_until"] else None
                },
                "last_order_submission_timestamp": log["last_order_submission_timestamp"].isoformat() if log["last_order_submission_timestamp"] else None
            }

        return {"users": users, "tokens": tokens, "activity_log": activity_log}

    except Error as e:
        logger.error(f"Error loading users data from MySQL: {e}")
        return {"users": [], "tokens": [], "activity_log": {}}
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def save_users_data(data):
    connection = get_db_connection()
    if not connection:
        logger.error("Cannot save users data: No database connection")
        raise Exception("Could not connect to MySQL database")

    try:
        cursor = connection.cursor()

        # ذخیره یا به‌روزرسانی کاربران
        for user in data.get("users", []):
            cursor.execute("""
                INSERT INTO users (telegram_id, telegram_name, registration_date, brokerage_type, full_name, 
                                   brokerage_username, subscription_type, token, expiry_date, brokerage_password, 
                                   real_name, national_id, phone_number, email)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    telegram_name = VALUES(telegram_name),
                    registration_date = VALUES(registration_date),
                    brokerage_type = VALUES(brokerage_type),
                    full_name = VALUES(full_name),
                    brokerage_username = VALUES(brokerage_username),
                    subscription_type = VALUES(subscription_type),
                    token = VALUES(token),
                    expiry_date = VALUES(expiry_date),
                    brokerage_password = VALUES(brokerage_password),
                    real_name = VALUES(real_name),
                    national_id = VALUES(national_id),
                    phone_number = VALUES(phone_number),
                    email = VALUES(email)
            """, (
                user.get("telegram_id"),
                user.get("telegram_name"),
                user.get("registration_date"),
                user.get("brokerage_type"),
                user.get("full_name"),
                user.get("brokerage_username"),
                user.get("subscription_type"),
                user.get("token"),
                user.get("expiry_date"),
                user.get("brokerage_password"),
                user.get("real_name"),
                user.get("national_id"),
                user.get("phone_number"),
                user.get("email")
            ))

        # ذخیره یا به‌روزرسانی توکن‌ها
        for token in data.get("tokens", []):
            cursor.execute("""
                INSERT INTO tokens (token, is_used, used_by_telegram_id, used_at, telegram_id, 
                                    brokerage_username, subscription_type, expiry_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    is_used = VALUES(is_used),
                    used_by_telegram_id = VALUES(used_by_telegram_id),
                    used_at = VALUES(used_at),
                    telegram_id = VALUES(telegram_id),
                    brokerage_username = VALUES(brokerage_username),
                    subscription_type = VALUES(subscription_type),
                    expiry_date = VALUES(expiry_date)
            """, (
                token.get("token"),
                token.get("is_used"),
                token.get("used_by_telegram_id"),
                token.get("used_at"),
                token.get("telegram_id"),
                token.get("brokerage_username"),
                token.get("subscription_type"),
                token.get("expiry_date")
            ))

        # ذخیره یا به‌روزرسانی لاگ‌های فعالیت
        for telegram_id, activity in data.get("activity_log", {}).items():
            login_attempts = activity.get("login_attempts", {})
            cursor.execute("""
                INSERT INTO activity_log (telegram_id, login_attempts_count, first_attempt_timestamp, 
                                          cooldown_until, last_order_submission_timestamp)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    login_attempts_count = VALUES(login_attempts_count),
                    first_attempt_timestamp = VALUES(first_attempt_timestamp),
                    cooldown_until = VALUES(cooldown_until),
                    last_order_submission_timestamp = VALUES(last_order_submission_timestamp)
            """, (
                telegram_id,
                login_attempts.get("count", 0),
                login_attempts.get("first_attempt_timestamp"),
                login_attempts.get("cooldown_until"),
                activity.get("last_order_submission_timestamp")
            ))

        connection.commit()
        logger.info("User data successfully saved to MySQL")
    except Error as e:
        logger.error(f"Error saving user data to MySQL: {e}")
        raise
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def find_user_by_telegram_id(telegram_id):
    connection = get_db_connection()
    if not connection:
        logger.error("Cannot find user: No database connection")
        return None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM users WHERE telegram_id = %s
        """, (telegram_id,))
        user = cursor.fetchone()
        return user
    except Error as e:
        logger.error(f"Error finding user by telegram_id {telegram_id}: {e}")
        return None
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def is_brokerage_username_in_use(brokerage_username_to_check: str, brokerage_type_to_check: str = "mofid") -> bool:
    connection = get_db_connection()
    if not connection:
        logger.error("Cannot check brokerage username: No database connection")
        return False

    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM users
            WHERE LOWER(brokerage_username) = LOWER(%s) AND brokerage_type = %s
        """, (brokerage_username_to_check, brokerage_type_to_check))
        count = cursor.fetchone()[0]
        return count > 0
    except Error as e:
        logger.error(f"Error checking brokerage username: {e}")
        return False
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()



def is_subscription_active(user):
    if not user or "expiry_date" not in user or not user["expiry_date"]:
        print(f"User {user.get('telegram_id')} has no expiry_date or it's empty")
        return False
    try:
        expiry_date = user["expiry_date"]  # این یک شیء datetime است
        now = datetime.now()
        print(f"Current time: {now}, Expiry date: {expiry_date}")
        return now < expiry_date
    except Exception as e:
        print(f"Error checking subscription for user {user.get('telegram_id')}: {e}")
        return False

def get_time_remaining(user):
    if not user or "expiry_date" not in user or not user["expiry_date"]:
        return "نامشخص"
    try:
        expiry_date = user["expiry_date"]  # این یک شیء datetime است
        time_left = expiry_date - datetime.now()
        if time_left.total_seconds() <= 0:
            return "منقضی شده"
        days = time_left.days
        hours, rem = divmod(time_left.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        return f"{days} روز، {hours} ساعت، {minutes} دقیقه"
    except Exception:
        return "نامشخص"



def validate_premium_token(token_string, telegram_id, brokerage_username_for_validation):
    connection = get_db_connection()
    if not connection:
        logger.error("Cannot validate token: No database connection")
        return {"valid": False, "message": "خطای اتصال به پایگاه داده"}

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tokens WHERE token = %s", (token_string,))
        token_data = cursor.fetchone()

        if not token_data:
            return {"valid": False, "message": "توکن نامعتبر یا پیدا نشد."}

        if token_data.get("is_used", False):
            logger.warning(f"Attempt to use already used token {token_string} by Telegram ID {telegram_id}")
            return {"valid": False, "message": "این توکن قبلا استفاده شده است."}

        token_bound_telegram_id = token_data.get("telegram_id")
        if token_bound_telegram_id and str(token_bound_telegram_id) != str(telegram_id):
            logger.warning(f"Token {token_string} (for Telegram ID {token_bound_telegram_id}) attempted by {telegram_id}")
            return {"valid": False, "message": "این توکن برای شناسه تلگرام شما صادر نشده است."}

        token_bound_brokerage_username = token_data.get("brokerage_username")
        if token_bound_brokerage_username and brokerage_username_for_validation.lower() != token_bound_brokerage_username.lower():
            logger.warning(f"Token {token_string} (for brokerage {token_bound_brokerage_username}) attempted with brokerage {brokerage_username_for_validation} by {telegram_id}")
            return {"valid": False, "message": f"این توکن برای نام کاربری کارگزاری '{brokerage_username_for_validation}' معتبر نیست."}

        if "expiry_date" in token_data and token_data["expiry_date"]:
            if datetime.now() >= token_data["expiry_date"]:
                logger.warning(f"Attempted to use expired token: {token_string}")
                return {"valid": False, "message": "توکن منقضی شده است."}

        return {"valid": True, "token_data": token_data}
    except Error as e:
        logger.error(f"Error validating token {token_string}: {e}")
        return {"valid": False, "message": "خطا در بررسی توکن"}
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def calculate_premium_expiry(subscription_type):
    now = datetime.now()
    if subscription_type == "روزانه": return now + timedelta(days=1)
    elif subscription_type == "هفتگی": return now + timedelta(weeks=1)
    elif subscription_type == "ماهانه": return now + timedelta(days=30)
    else:
        logger.warning(f"Unknown sub type for expiry: {subscription_type}. Defaulting to 1 day.")
        return now + timedelta(days=1)

# --- Rate Limiting (Identical to telegramBotV7.py) ---
def check_login_rate_limit(user_id: int) -> tuple[bool, str]:
    user_id_str = str(user_id)
    now = datetime.now()
    activity_data = load_users_data().get("activity_log", {})
    user_login_activity = activity_data.get(user_id_str, {}).get("login_attempts", {})
    cooldown_until_str = user_login_activity.get("cooldown_until")
    if cooldown_until_str:
        cooldown_until = datetime.fromisoformat(cooldown_until_str)
        if now < cooldown_until:
            rem_cooldown = cooldown_until - now
            return True, f"{EMOJI['ratelimit']} محدودیت ورود. لطفاً پس از {int(rem_cooldown.total_seconds() // 60)} دقیقه تلاش کنید."
    return False, ""

def record_failed_login_attempt(user_id: int):
    user_id_str = str(user_id)
    now = datetime.now()
    connection = get_db_connection()
    if not connection:
        logger.error("Cannot record failed login attempt: No database connection")
        return

    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT login_attempts_count, first_attempt_timestamp
            FROM activity_log
            WHERE telegram_id = %s
        """, (user_id_str,))
        result = cursor.fetchone()

        if result:
            count, first_attempt_ts = result
            if first_attempt_ts and now - first_attempt_ts < timedelta(minutes=LOGIN_ATTEMPT_WINDOW_MINUTES):
                count += 1
            else:
                count = 1
                first_attempt_ts = now
        else:
            count = 1
            first_attempt_ts = now

        cooldown_until = None
        if count >= MAX_LOGIN_ATTEMPTS:
            cooldown_until = now + timedelta(minutes=LOGIN_COOLDOWN_MINUTES)
            count = 0
            first_attempt_ts = None
            logger.warning(f"User {user_id_str} rate-limited for login. Cooldown until: {cooldown_until}")

        cursor.execute("""
            INSERT INTO activity_log (telegram_id, login_attempts_count, first_attempt_timestamp, cooldown_until)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                login_attempts_count = %s,
                first_attempt_timestamp = %s,
                cooldown_until = %s
        """, (user_id_str, count, first_attempt_ts, cooldown_until, count, first_attempt_ts, cooldown_until))

        connection.commit()
    except Error as e:
        logger.error(f"Error recording failed login attempt for user {user_id}: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def reset_login_attempts(user_id: int):
    user_id_str = str(user_id)
    connection = get_db_connection()
    if not connection:
        logger.error("Cannot reset login attempts: No database connection")
        return

    try:
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE activity_log
            SET login_attempts_count = 0, first_attempt_timestamp = NULL, cooldown_until = NULL
            WHERE telegram_id = %s
        """, (user_id_str,))
        connection.commit()
        logger.info(f"Login attempts reset for user {user_id_str}")
    except Error as e:
        logger.error(f"Error resetting login attempts for user {user_id}: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def check_order_submission_rate_limit(user_id: int) -> tuple[bool, str]:
    user_id_str = str(user_id)
    now = datetime.now()
    activity_data = load_users_data().get("activity_log", {})
    last_sub_ts_str = activity_data.get(user_id_str, {}).get("last_order_submission_timestamp")
    if last_sub_ts_str:
        last_sub_ts = datetime.fromisoformat(last_sub_ts_str)
        if now - last_sub_ts < timedelta(seconds=MIN_SECONDS_BETWEEN_ORDERS):
            wait_time = MIN_SECONDS_BETWEEN_ORDERS - (now - last_sub_ts).total_seconds()
            return True, f"{EMOJI['ratelimit']} ثبت سفارش سریع. لطفاً {int(wait_time) + 1} ثانیه دیگر تلاش کنید."
    return False, ""

def record_order_submission(user_id: int):
    user_id_str = str(user_id)
    now = datetime.now()
    connection = get_db_connection()
    if not connection:
        logger.error("Cannot record order submission: No database connection")
        return

    try:
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO activity_log (telegram_id, last_order_submission_timestamp)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE last_order_submission_timestamp = %s
        """, (user_id_str, now, now))
        connection.commit()
    except Error as e:
        logger.error(f"Error recording order submission for user {user_id}: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


class MofidBrokerSession:
    def __init__(self, user_id):
        self.user_id = user_id
        self.bot = MofidBroker()
        self.is_logged_in = False
        self.order_details = {}
        self.logs = []
        self.order_detail_message_ids = []  
        self.active_orders = set()
        self.credentials = {}
        self.user_data = None
        self.last_activity_time = datetime.now()  # Initialize last activity time
        self.inactivity_timeout_task = None

    def update_activity(self):
        """Update the last activity timestamp."""
        self.last_activity_time = datetime.now()
        logger.info(f"Updated activity time for user {self.user_id} to {self.last_activity_time}")

    async def check_inactivity(self, context: ContextTypes.DEFAULT_TYPE):
        """Check for inactivity and close browser if 5 minutes have passed and no scheduled orders are pending."""
        while self.is_logged_in:
            now = datetime.now()
            inactivity_duration = (now - self.last_activity_time).total_seconds()
            
            # Check if there are pending scheduled orders
            has_pending_orders = bool(self.active_orders)
            
            # Check if there's a scheduled order that hasn't been executed yet
            if self.order_details.get("send_method") in ["زمان‌دار", "سرخطی"] and self.order_details.get("scheduled_time_str_for_module"):
                try:
                    scheduled_time_str = self.order_details["scheduled_time_str_for_module"]
                    scheduled_time = datetime.strptime(scheduled_time_str, "%H:%M:%S.%f").time()
                    current_time = now.time()
                    # Convert times to seconds for comparison
                    scheduled_seconds = scheduled_time.hour * 3600 + scheduled_time.minute * 60 + scheduled_time.second + (scheduled_time.microsecond / 1_000_000)
                    current_seconds = current_time.hour * 3600 + current_time.minute * 60 + current_time.second + (current_time.microsecond / 1_000_000)
                    
                    # If the scheduled time has passed, clear the scheduled order details
                    if current_seconds >= scheduled_seconds:
                        logger.info(f"Scheduled order time {scheduled_time_str} for user {self.user_id} has passed. Clearing scheduled order details.")
                        self.order_details.pop("scheduled_time_str_for_module", None)
                        self.order_details.pop("send_method", None)
                        if self.order_details.get("stock") in self.active_orders:
                            self.active_orders.remove(self.order_details["stock"])
                        has_pending_orders = False
                    else:
                        has_pending_orders = True
                        logger.debug(f"Pending scheduled order for user {self.user_id} at {scheduled_time_str}. Keeping browser open.")
                except ValueError as e:
                    logger.error(f"Invalid scheduled time format for user {self.user_id}: {e}")
                    # Clear invalid scheduled time to avoid blocking
                    self.order_details.pop("scheduled_time_str_for_module", None)
                    self.order_details.pop("send_method", None)
                    if self.order_details.get("stock") in self.active_orders:
                        self.active_orders.remove(self.order_details["stock"])
                    has_pending_orders = False
            
            # Log the state for debugging
            logger.debug(f"User {self.user_id}: inactivity_duration={inactivity_duration:.1f}s, has_pending_orders={has_pending_orders}")
            
            # Only close browser if inactive for 5 minutes AND no pending orders
            if inactivity_duration >= 300 and not has_pending_orders:  # 5 minutes = 300 seconds
                logger.info(f"User {self.user_id} inactive for 5 minutes with no pending orders. Closing browser.")
                self.safe_quit()
                try:
                    await context.bot.send_message(
                        chat_id=self.user_id,
                        text=f"{EMOJI['logout']} به دلیل عدم فعالیت به مدت 5 دقیقه و نبود سفارش زمان‌بندی شده، از حساب کارگزاری مفید خارج شدید.\n برای شروع مجدد روی /start کلیک کنید."
                    )
                except Exception as e:
                    logger.error(f"Failed to send inactivity logout message to user {self.user_id}: {e}")
                break
            elif has_pending_orders:
                logger.debug(f"User {self.user_id} has pending orders: {self.active_orders}. Keeping browser open.")
            
            await asyncio.sleep(30)  # Check every 30 seconds to reduce load

    def add_log(self, message, status="info"):
        log_entry = {"time": datetime.now().strftime("%H:%M:%S.%f")[:-3], "message": message, "status": status}
        self.logs.append(log_entry)
        # logger.info(f"User {self.user_id} Log: {message}") # Optional: also log to main logger
        return log_entry

    def safe_quit(self):
        """Safely quit the WebDriver for Mofid."""
        if self.bot and self.bot.driver:
            try:
                self.bot.driver.quit()
                logger.info(f"Mofid WebDriver quit for user {self.user_id}")
            except Exception as e:
                logger.error(f"Error quitting Mofid WebDriver for user {self.user_id}: {e}")
            self.bot.driver = None
        self.is_logged_in = False
        # self.stocks_in_watchlist.clear() # Mofid module doesn't use a watchlist in the same way

    # --- Wrappers for MofidBroker methods to standardize return types or add logging ---
    async def mofid_login(self, username, password):
        """Wrapper for MofidBroker's login_to_website."""
        try:
            success = self.bot.login_to_website(username, password)
            if success:
                self.is_logged_in = True
                return {"success": True, "message": "ورود به کارگزاری مفید موفقیت آمیز بود."}
            else:
                return {"success": False, "message": "خطا در ورود به کارگزاری مفید. اطلاعات صحیح نیست یا مشکلی رخ داده."}
        except Exception as e:
            logger.error(f"Mofid login error for user {self.user_id}: {e}")
            error_message = str(e)
            # Check if the error is the specific broker message
            if "نام کاربری یا کلمه عبور نادرست است" in error_message:
                return {"success": False, "message": "نام کاربری یا کلمه عبور نادرست است. لطفاً اطلاعات خود را بررسی کنید."}
            return {"success": False, "message": f"نام کاربری یا کلمه عبور نادرست است. لطفاً اطلاعات خود را بررسی کنید. "}
    async def mofid_search_stock(self, stock_name):
        """Wrapper for MofidBroker's search_stock."""
        if not self.is_logged_in:
            return {"success": False, "message": "ابتدا باید وارد حساب کارگزاری شوید."}
        try:
            success = self.bot.search_stock(stock_name)
            if success:
                return {"success": True, "message": f"نماد '{stock_name}' با موفقیت پیدا و انتخاب شد."}
            else:
                return {"success": False, "message": f"خطا در جستجو یا انتخاب نماد '{stock_name}'."}
        except Exception as e:
            logger.error(f"Mofid search_stock error for user {self.user_id}, stock {stock_name}: {e}")
            return {"success": False, "message": f"خطا در جستجوی نماد '{stock_name}': {str(e)}"}

    async def mofid_place_order(self, stock_name, action, quantity, price_option, custom_price=None, send_option="now", scheduled_time_str=None):
        """Wrapper for MofidBroker's place_order."""
        if not self.is_logged_in:
            return {"success": False, "message": "ابتدا باید وارد حساب کارگزاری شوید.", "submission_logs": [], "click_count": 0}

        # Parameter mapping
        mofid_action = "buy" if action == "خرید" else "sell"
        mofid_price_option = price_option
        if price_option == "higher": mofid_price_option = "max"
        if price_option == "lower": mofid_price_option = "min"
        mofid_send_option = "now"
        if send_option == "زمان‌دار" or send_option == "سرخطی":
            mofid_send_option = "schedule"
            if not scheduled_time_str and send_option == "سرخطی":
                default_serkhati_dt_time = dt_time(8, 44, 50, 0)
                scheduled_time_str = default_serkhati_dt_time.strftime('%H:%M:%S.%f')[:-3]

        order_submission_logs = []
        try:
            # result_from_broker شامل click_count خواهد بود
            result_from_broker = self.bot.place_order(
                action=mofid_action,
                quantity=quantity,
                price_option=mofid_price_option,
                custom_price=custom_price,
                send_option=mofid_send_option,
                scheduled_time_str=scheduled_time_str
            )

            # استخراج click_count و سایر موارد لازم
            click_count_val = result_from_broker.get("click_count", 0)
            submission_logs_val = result_from_broker.get("submission_logs", [])

            if result_from_broker["success"]:
                final_message = "سفارش با موفقیت در هسته معاملات ثبت گردید."
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                order_submission_logs.append(f"{current_time}: نتیجه: {final_message}")
                order_submission_logs.extend(submission_logs_val)
                return {"success": True, "message": final_message, "submission_logs": order_submission_logs, "click_count": click_count_val}
            else:
                final_message = "ارسال سفارش ناموفق بود."
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                order_submission_logs.append(f"{current_time}: نتیجه: {final_message}")
                order_submission_logs.extend(submission_logs_val)
                return {"success": False, "message": final_message, "submission_logs": order_submission_logs, "click_count": click_count_val}

        except Exception as e:
            logger.error(f"Mofid place_order error for user {self.user_id}: {e}")
            error_message = f"خطا در ارسال سفارش به مفید: {str(e)}"
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            order_submission_logs.append(f"{current_time}: خطا: {error_message}")
            return {"success": False, "message": error_message, "submission_logs": order_submission_logs, "click_count": 0}

async def schedule_order_detail_cleanup(context: ContextTypes.DEFAULT_TYPE, session: MofidBrokerSession, chat_id: int):
    # """Schedules the cleanup of order detail messages, excluding the final summary message."""
    # await asyncio.sleep(20)  # Wait for 10 seconds
    # logger.info(f"Initiating cleanup for user {chat_id}. Messages to delete: {session.order_detail_message_ids}")
    # if session.order_detail_message_ids:
    #     deleted_count = 0
    #     messages_to_delete = session.order_detail_message_ids[1:] if len(session.order_detail_message_ids) > 1 else []
    #     for msg_id in list(messages_to_delete):
    #         try:
    #             await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
    #             if msg_id in session.order_detail_message_ids:
    #                 session.order_detail_message_ids.remove(msg_id)
    #             deleted_count += 1
    #         except BadRequest as e:
    #             logger.error(f"Error deleting message {msg_id} for user {chat_id}: {e}")
    #             if "message to delete not found" in str(e).lower() or "message can't be deleted" in str(e).lower():
    #                 if msg_id in session.order_detail_message_ids:
    #                     session.order_detail_message_ids.remove(msg_id)
    #         except Exception as e:
    #             logger.error(f"Unexpected error deleting message {msg_id} for user {chat_id}: {e}")
    #     logger.info(f"Deleted {deleted_count} order detail messages for user {chat_id}.")
    #     if deleted_count > 0:
    #         cleanup_info_msg = await context.bot.send_message(
    #             chat_id=chat_id,
    #             text=f"{EMOJI['cleanup']} جزئیات سفارش برای تمیز نگه داشتن چت پاک شدند.",
    #             #reply_markup=InlineKeyboardMarkup([
    #                 #[InlineKeyboardButton(f"{EMOJI['details']} نمایش مجدد جزئیات سفارش", callback_data="reshow_details")]
    #             #])
    #         )
    pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if "session" not in context.user_data or not isinstance(context.user_data["session"], MofidBrokerSession):
        logger.info(f"New MofidBrokerSession for user {user_id}.")
        context.user_data["session"] = MofidBrokerSession(user_id)
    session = context.user_data["session"]
    session.update_activity()

    if session.inactivity_timeout_task:  # Cancel any existing inactivity task
        session.inactivity_timeout_task.cancel()

    session.order_details = {}
    session.order_detail_message_ids = []
    session.active_orders = set()
    session.credentials = {}
    if session.is_logged_in:  # If there was an active selenium session, try to close it.
        session.safe_quit()

    user_data_from_db = find_user_by_telegram_id(user_id)
    
    if user_data_from_db and user_data_from_db.get("brokerage_type") != "mofid":
        welcome_text = (
            f"{EMOJI['warning']} حساب شما برای کارگزاری دیگری ثبت شده است.\n"
            f"این ربات مخصوص کارگزاری **مفید** می‌باشد.\n"
            f"برای استفاده از ربات کارگزاری مفید، لطفاً با یک حساب کاربری مفید ثبت نام کنید یا با پشتیبانی تماس بگیرید."
        )
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['register']} ثبت نام جدید (برای مفید)", callback_data="force_register_mofid")],
            [InlineKeyboardButton("📩 پیام به پشتیبانی", url="https://t.me/SarTraderBot_Support")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text(text=welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
        elif update.callback_query:
            # اگر از callback_query آمده، سعی می‌کنیم پیام قبلی را ویرایش کنیم
            try:
                await update.callback_query.edit_message_text(text=welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
            except BadRequest: # اگر ویرایش ممکن نبود (مثلا پیام خیلی قدیمی است)، پیام جدید ارسال می‌کنیم
                await context.bot.send_message(chat_id=user_id, text=welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
        logger.info(f"User {user_id} redirected to register for Mofid (was registered for another broker)")
        return MAIN_MENU

    session.user_data = user_data_from_db

    if user_data_from_db:
        if is_subscription_active(user_data_from_db):
            time_left = get_time_remaining(user_data_from_db)
            welcome_text = f"{EMOJI['trade']} {user_data_from_db.get('full_name', 'کاربر')} عزیز، به ربات معاملاتی *کارگزاری مفید* خوش آمدید.!\nزمان باقیمانده اشتراک: *{time_left}*"
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI['start']} شروع معاملات", callback_data="menu_start_mofid")],
                [InlineKeyboardButton(f"{EMOJI['tutorial']} راهنمای ربات", callback_data="menu_tutorial_mofid")], # تغییر callback_data
                [InlineKeyboardButton(f"{EMOJI['admin']} ارتباط با پشتیبانی", url="https://t.me/SarTraderBot_Support")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if update.message:
                await update.message.reply_text(text=welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
            elif update.callback_query:
                try:
                    await update.callback_query.edit_message_text(text=welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
                except BadRequest:
                     await context.bot.send_message(chat_id=user_id, text=welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
            logger.info(f"User {user_id} with active subscription directed to main menu")
            return MAIN_MENU
        else:
            logger.info(f"User {user_id} has expired subscription, directing to EXPIRED_ACCOUNT_OPTIONS")
            # اطمینان از اینکه handle_expired_account_options با query یا update مناسب فراخوانی می‌شود
            if update.callback_query:
                 await handle_expired_account_options(update, context) # ارسال کل آپدیت
            else:
                # اگر آپدیت از نوع پیام است، یک آپدیت ساختگی برای query ایجاد نمی‌کنیم
                # بلکه مستقیما handle_expired_account_options را با آپدیت پیام فراخوانی می‌کنیم
                # یا منطق نمایش پیام انقضا را مستقیما اینجا پیاده‌سازی می‌کنیم
                await context.bot.send_message(chat_id=user_id, text=f"{EMOJI['warning']} اشتراک شما منقضی شده است.")
                await handle_expired_account_options(update, context) # ارسال کل آپدیت

            return EXPIRED_ACCOUNT_OPTIONS
    else:
        welcome_text = f"""
🌟 **به ربات معاملاتی هوشمند کارگزاری مفید خوش آمدید!** 🌟

این ربات برای **اتوماسیون معاملات در کارگزاری مفید** طراحی شده و به شما کمک می‌کند با **دقت میلی‌ثانیه‌ای** سفارشات خرید و فروش را ثبت کنید.

🎯 **ویژگی‌های کلیدی:**
• **ورود امن:** با نام کاربری و رمز عبور کارگزاری مفید.
• **سفارشات متنوع:** فوری، زمان‌دار، و سرخطی با قیمت دلخواه.
• **سرعت بالا:** ثبت سفارش در صف‌های خرید/فروش.
• **اشتراک‌ها:** ۳ روز رایگان یا پریمیوم (روزانه، هفتگی، ماهانه).

⚠️ **نکات مهم:**
• پس از ثبت سفارش، حساب کارگزاری مفید خود را بررسی کنید.
• برای مشکلات، با پشتیبانی تماس بگیرید.

🚀 **چگونه شروع کنیم؟**
برای استفاده، **باید ابتدا حساب کاربری در ربات** ایجاد کنید.
**روی "ایجاد حساب برای کارگزاری مفید" کلیک کنید!**
"""
        keyboard = [[InlineKeyboardButton(f"{EMOJI['register']} ایجاد حساب (مفید)", callback_data="register_yes_mofid")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text(text=welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
        elif update.callback_query:
            try:
                await update.callback_query.edit_message_text(text=welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
            except BadRequest:
                await context.bot.send_message(chat_id=user_id, text=welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
        logger.info(f"New user {user_id} directed to registration prompt")
        return REGISTER_PROMPT



async def show_tutorial_mofid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    # اطمینان از اینکه query وجود دارد قبل از استفاده
    if not query:
        logger.warning("show_tutorial_mofid called without a callback query.")
        # اگر query وجود ندارد، نمی‌توانیم پیام را ویرایش کنیم یا پاسخ دهیم.
        # شاید بهتر باشد یک پیام جدید ارسال کنیم اگر chat_id در دسترس است.
        if update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{EMOJI['error']} خطایی در نمایش راهنما رخ داد. لطفا از منوی اصلی دوباره تلاش کنید.")
        return MAIN_MENU # یا ConversationHandler.END

    await query.answer() # پاسخ به callback query برای جلوگیری از تایم اوت در کلاینت تلگرام
    
    session = context.user_data.get("session") # استفاده از .get برای جلوگیری از KeyError
    if not session:
        logger.error(f"Session not found for user {update.effective_user.id} in show_tutorial_mofid")
        await query.edit_message_text(f"{EMOJI['error']} خطای داخلی رخ داده است. لطفا با /start مجددا تلاش کنید.")
        return ConversationHandler.END
        
    session.update_activity()

    tutorial_text = f"""
{EMOJI['tutorial']} *آموزش استفاده از ربات معاملاتی مفید*

📌 *مراحل ثبت سفارش:*
1️⃣ *ورود به حساب:*
   • وارد کردن نام کاربری و رمز عبور مفید
   • تأیید ورود به سیستم

2️⃣ *انتخاب نماد:*
   • جستجو و انتخاب نماد مورد نظر
   • مثال: وبملت، فولاد، خودرو

3️⃣ *تنظیم سفارش:*
   • انتخاب خرید یا فروش
   • تعیین قیمت (بالاترین/پایین‌ترین/دلخواه)
   • انتخاب روش ارسال:
     - فوری (ارسال بلافاصله)
     - زمان‌دار (در زمان مشخص)
     - سرخطی (ابتدای بازار)
   • تعیین تعداد سهام

4️⃣ *تأیید و ارسال:*
   • بررسی جزئیات سفارش
   • تأیید نهایی و ارسال به کارگزاری

⚡️ *ویژگی‌های خاص:*
• *دقت زمانی:* ارسال با دقت میلی‌ثانیه
• *سفارش سرخطی:* ثبت خودکار در شروع بازار
• *ارسال زمان‌دار:* تنظیم دقیق زمان ارسال

⚠️ *نکات مهم:*
• پس از هر سفارش، حساب کارگزاری را چک کنید
• در سفارش‌های سریع، احتمال ثبت چند سفارش وجود دارد
• مسئولیت صحت اطلاعات و سفارشات با کاربر است

{EMOJI['alert']} *برای شروع معاملات، روی دکمه زیر کلیک کنید:*
"""
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['start']} شروع معاملات در مفید", callback_data="menu_start_mofid")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main_action")],
    ]
    try:
        await query.edit_message_text(
            text=tutorial_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        session.add_log("راهنمای استفاده با موفقیت نمایش داده شد", "success")
    except BadRequest as e:
        # اگر پیام ویرایش نشد (مثلا چون محتوا یکسان است یا پیام خیلی قدیمی است)
        logger.warning(f"Could not edit message for tutorial: {e}. Sending as new message if possible.")
        session.add_log(f"خطا در ویرایش پیام راهنما: {str(e)}", "warning")
        # تلاش برای ارسال پیام جدید به عنوان جایگزین
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id, # استفاده از chat_id پیام اصلی
                text=tutorial_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            session.add_log("راهنما به صورت پیام جدید ارسال شد (پس از خطای ویرایش)", "info")
        except Exception as e2:
            logger.error(f"Failed to send tutorial as new message after edit failure: {e2}")
            session.add_log(f"خطا در ارسال پیام جدید راهنما (پس از خطای ویرایش): {str(e2)}", "error")
            # اگر ارسال پیام جدید هم با خطا مواجه شد، به کاربر اطلاع می‌دهیم
            # این حالت نادر است اما برای کامل بودن در نظر گرفته شده
            await query.message.reply_text(f"{EMOJI['error']} متاسفانه در نمایش راهنما مشکلی پیش آمد. لطفا دوباره امتحان کنید.")
            
    except Exception as e: # سایر خطاهای احتمالی
        logger.error(f"Unexpected error in show_tutorial_mofid: {e}")
        session.add_log(f"خطای غیرمنتظره در نمایش راهنما: {str(e)}", "error")
        await query.message.reply_text(f"{EMOJI['error']} یک خطای پیش‌بینی نشده در نمایش راهنما رخ داد.")

    return MAIN_MENU


async def get_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    session.user_data["full_name"] = update.message.text 
    session.add_log(f"نام ثبت شد: {session.user_data['full_name']}", "info")
    await update.message.reply_text(f"{EMOJI['register']} لطفا نام کاربری خود در **کارگزاری مفید** را وارد کنید: \n \n[این نام کاربری است که برای ورود به سامانه ایزی تریدر استفاده می کنید (کد ملی ، شماره همراه و یا شناسه دیگر )]")
    return REGISTER_BROKERAGE_USERNAME

async def get_brokerage_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    brokerage_username_input = update.message.text.strip()
    
    session.user_data["brokerage_username"] = brokerage_username_input 
    
    # Check for free trial uniqueness for this Mofid username
    if is_brokerage_username_in_use(brokerage_username_input, "mofid"):
        data = load_users_data()
        associated_user_is_current_user = False
        for usr in data.get("users", []):
            if usr.get("brokerage_username", "").lower() == brokerage_username_input.lower() and \
               usr.get("brokerage_type") == "mofid" and \
               str(usr.get("telegram_id")) == str(session.user_id):
                associated_user_is_current_user = True
                break
        
        if not associated_user_is_current_user:
            logger.warning(f"Registration attempt by {session.user_id} with already used Mofid brokerage username '{brokerage_username_input}'.")
            await update.message.reply_text(
                f"{EMOJI['block']} این نام کاربری کارگزاری مفید قبلاً در سیستم ثبت شده و با یک حساب تلگرام دیگر مرتبط است. "
                f"امکان ایجاد حساب رایگان جدید با این نام کاربری کارگزاری وجود ندارد.\n\n"
                f"اگر فکر می‌کنید خطایی رخ داده یا می‌خواهید از توکن پریمیوم استفاده کنید، با پشتیبانی بات تماس بگیرید یا مجدداً با /start تلاش کنید و گزینه توکن را انتخاب نمایید.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END 

    session.add_log(f"نام کاربری کارگزاری مفید: {brokerage_username_input}", "info")
    
    # Set brokerage type to Mofid
    session.user_data["brokerage_type"] = "mofid"
    session.add_log(f"نوع کارگزاری: مفید (ثابت)", "info")

    # Ask for subscription type (free or premium)
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['token']} توکن فعال‌سازی پریمیوم دارم", callback_data="has_token_yes")],
        [InlineKeyboardButton(f"{EMOJI['free']} حساب رایگان (۳ روز) برای مفید", callback_data="has_token_no")],
    ]
    await update.message.reply_text(
        f"{EMOJI['register']} آیا توکن فعال‌سازی پریمیوم برای ربات دارید؟",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return REGISTER_HAS_TOKEN
async def has_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity() 

    if query.data == "has_token_yes":
        await query.edit_message_text(f"{EMOJI['token']} لطفا توکن فعال‌سازی خود را وارد کنید:")
        return REGISTER_TOKEN_INPUT
    else: # User chooses free account for Mofid
        if is_brokerage_username_in_use(session.user_data["brokerage_username"], "mofid"):
            data = load_users_data()
            associated_user_is_current_user = False
            for usr in data.get("users", []):
                if usr.get("brokerage_username", "").lower() == session.user_data["brokerage_username"].lower() and \
                   usr.get("brokerage_type") == "mofid" and \
                   str(usr.get("telegram_id")) == str(session.user_id):
                    associated_user_is_current_user = True
                    break
            if not associated_user_is_current_user:
                logger.warning(f"Free trial for Mofid denied for {session.user_id} (brokerage '{session.user_data['brokerage_username']}' already in use by another TG ID for Mofid).")
                await query.edit_message_text(
                    f"{EMOJI['block']} این نام کاربری کارگزاری مفید قبلاً توسط حساب تلگرام دیگری برای دریافت دوره رایگان استفاده شده است. "
                    f"هر نام کاربری کارگزاری تنها یکبار می‌تواند از دوره رایگان استفاده کند.\n\n"
                    f"لطفا با استفاده از توکن پریمیوم ثبت نام کنید یا با پشتیبانی بات تماس بگیرید.",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END

        session.user_data["subscription_type"] = "free"
        session.user_data["token"] = None # No token string for free trial
        session.user_data["expiry_date"] = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        session.add_log("کاربر حساب رایگان (مفید) را انتخاب کرد", "info")

        all_data = load_users_data()
        all_data["users"] = [u for u in all_data["users"] if str(u.get("telegram_id")) != str(session.user_id)]
        all_data["users"].append(session.user_data) 
        save_users_data(all_data)
        session.add_log("اطلاعات کاربر جدید (رایگان مفید) ذخیره شد", "success")

        await query.edit_message_text(
            f"{EMOJI['success']} ثبت‌نام رایگان برای کارگزاری مفید موفق! حساب شما ۳ روز فعال شد.\n"
            f"انقضا: *{session.user_data['expiry_date']}*\n\n"
            f"با /start شروع کنید.", parse_mode="Markdown")
        return ConversationHandler.END

async def get_token_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity() 
    token_string = update.message.text.strip()
    brokerage_username_entered_this_session = session.user_data.get("brokerage_username")

    if not brokerage_username_entered_this_session:
        logger.error(f"Brokerage username missing in session during token input for Mofid user {session.user_id}")
        await update.message.reply_text(f"{EMOJI['error']} خطای داخلی. لطفا با /start مجددا تلاش کنید.")
        return ConversationHandler.END

    validation_result = validate_premium_token(
        token_string,
        session.user_id, 
        brokerage_username_entered_this_session 
    )

    if validation_result["valid"]:
        token_data = validation_result["token_data"]
        session.user_data["subscription_type"] = "premium"
        session.user_data["token"] = token_string # Store the token itself
        session.user_data["expiry_date"] = calculate_premium_expiry(
            token_data.get("subscription_type", "ماهانه") 
        ).strftime("%Y-%m-%d %H:%M:%S")
        session.add_log(f"توکن پریمیوم معتبر: {token_string}", "success")

        all_data = load_users_data()
        for t_entry in all_data.get("tokens", []):
            if t_entry.get("token") == token_string:
                t_entry["is_used"] = True
                t_entry["used_by_telegram_id"] = session.user_id
                t_entry["used_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        
        all_data["users"] = [u for u in all_data["users"] if str(u.get("telegram_id")) != str(session.user_id)]
        all_data["users"].append(session.user_data) 
        save_users_data(all_data)
        session.add_log("کاربر پریمیوم (مفید) ذخیره شد و توکن استفاده شد", "success")

        await update.message.reply_text(
            f"{EMOJI['success']} توکن فعال شد! حساب پریمیوم شما برای ربات مفید فعال است.\n"
            f"انقضا: *{session.user_data['expiry_date']}*\n\n"
            f"با /start شروع کنید.", parse_mode="Markdown")
        return ConversationHandler.END
    else:
        logger.info(f"Token نامعتبر '{token_string}' توسط کاربر مفید {session.user_id}. دلیل: {validation_result['message']}")
        keyboard = [
    [InlineKeyboardButton(f"{EMOJI['token']} تلاش مجدد توکن", callback_data="retry_token_input_mofid")],
    [InlineKeyboardButton(f"{EMOJI['free']} استفاده از حساب رایگان (مفید)", callback_data="has_token_no")],
    [InlineKeyboardButton(f"{EMOJI['admin']} ارتباط با پشتیبانی بات", url="https://t.me/SarTraderBot_Support")],
    [InlineKeyboardButton("❌ انصراف از ثبت‌نام", callback_data="cancel_registration_mofid")],
]
        await update.message.reply_text(
            f"{EMOJI['error']} {validation_result['message']}\nچه کاری میخواهید انجام دهید؟",
            reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True
        )
        return REGISTER_HAS_TOKEN

async def retry_token_input_mofid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(f"{EMOJI['token']} لطفا توکن فعال‌سازی خود را مجددا وارد کنید:")
    return REGISTER_TOKEN_INPUT


async def send_message_with_retry(bot, chat_id, text, parse_mode=None, reply_markup=None, disable_web_page_preview=None, max_retries=3, retry_delay=1):
    for attempt in range(max_retries):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview
            )
            logger.info(f"Message sent successfully to chat {chat_id} on attempt {attempt + 1}")
            return True
        except Exception as e:
            logger.warning(f"Failed to send message to chat {chat_id} on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            continue
    logger.error(f"Failed to send message to chat {chat_id} after {max_retries} attempts")
    return False

async def handle_expired_account_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    session = context.user_data["session"]
    session.update_activity()
    user_data = session.user_data

    logger.info(f"Handling expired account options for user {session.user_id}")

    if query and query.data == "enter_new_token_expired":
        await query.answer()
        await query.edit_message_text(f"{EMOJI['token']} لطفا توکن فعال‌سازی جدید خود را وارد کنید:")
        logger.info(f"User {session.user_id} selected to enter new token")
        return LOGIN_ENTER_NEW_TOKEN_FOR_EXPIRED
    elif query and query.data == "show_subscription_guide":
        return await show_subscription_guide(update, context)

    welcome_text = f"{EMOJI['warning']} حساب شما برای ربات مفید منقضی شده است."
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['token']} وارد کردن توکن جدید", callback_data="enter_new_token_expired")],
        [InlineKeyboardButton(f"{EMOJI['tutorial']} آموزش تهیه اشتراک بات", callback_data="show_subscription_guide")],
        [InlineKeyboardButton("📩 پیام به پشتیبانی جهت تهیه توکن", url="https://t.me/SarTraderBot_Support")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.answer()
        await query.edit_message_text(text=welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text=welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    logger.info(f"Sent main expired account message to user {session.user_id}")

    return EXPIRED_ACCOUNT_OPTIONS

async def get_new_token_for_expired(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    user_data_from_session = session.user_data 

    if not user_data_from_session or is_subscription_active(user_data_from_session):
         await update.message.reply_text(f"{EMOJI['error']} وضعیت حساب تغییر کرده. با /start شروع کنید.")
         return ConversationHandler.END

    token_string = update.message.text.strip()
    registered_brokerage_username = user_data_from_session.get("brokerage_username")
    if not registered_brokerage_username:
        logger.error(f"Mofid user {session.user_id} (expired) trying to apply new token but has no brokerage_username in record.")
        await update.message.reply_text(f"{EMOJI['error']} خطای داخلی: اطلاعات کارگزاری شما یافت نشد. با پشتیبانی بات تماس بگیرید.")
        return ConversationHandler.END

    validation_result = validate_premium_token(
        token_string,
        session.user_id,
        registered_brokerage_username
    )

    if validation_result["valid"]:
        token_data = validation_result["token_data"]
        all_data = load_users_data()
        user_updated = False
        for user_db in all_data["users"]:
            if str(user_db.get("telegram_id")) == str(session.user_id):
                user_db["subscription_type"] = "premium"
                user_db["token"] = token_string
                user_db["expiry_date"] = calculate_premium_expiry(
                    token_data.get("subscription_type", "ماهانه")
                ).strftime("%Y-%m-%d %H:%M:%S")
                user_updated = True
                break
        
        if user_updated:
            for t_entry in all_data.get("tokens", []):
                if t_entry.get("token") == token_string:
                    t_entry["is_used"] = True
                    t_entry["used_by_telegram_id"] = session.user_id
                    t_entry["used_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    break
            save_users_data(all_data)
            session.user_data = find_user_by_telegram_id(session.user_id) # Reload updated data
            session.add_log(f"توکن جدید برای کاربر مفید منقضی شده فعال شد: {token_string}", "success")
            await update.message.reply_text(
                f"{EMOJI['success']} توکن جدید فعال شد! حساب پریمیوم شما برای ربات مفید فعال است.\n"
                f"انقضا: *{session.user_data['expiry_date']}*\n\n"
                f"با /start شروع کنید.", parse_mode="Markdown")
            return ConversationHandler.END
        else:
            await update.message.reply_text(f"{EMOJI['error']} خطای داخلی در به‌روزرسانی. با پشتیبانی بات تماس بگیرید.")
            return ConversationHandler.END
    else:
        keyboard = [
             [InlineKeyboardButton(f"{EMOJI['token']} تلاش مجدد", callback_data="enter_new_token_expired")], # This callback should lead back to asking for token
             [InlineKeyboardButton(f"{EMOJI['admin']} ارتباط با پشتیبانی بات", url="https://t.me/SarTraderBot_Support")],
        ]
        await update.message.reply_text(f"{EMOJI['error']} {validation_result['message']}", reply_markup=InlineKeyboardMarkup(keyboard))
        return EXPIRED_ACCOUNT_OPTIONS # Stay in this state to allow retry or contact




async def show_admin_contact_mofid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    admin_text = f"""
{EMOJI['admin']} *اطلاعات تماس با پشتیبانی ربات مفید*

برای ارتباط با پشتیبانی می‌توانید از راه‌های زیر اقدام کنید:
👨‍💼 *آیدی تلگرام:* [پشتیبانی بات](https://t.me/SarTraderBot_Support)
📧 *ایمیل* : ناموجود

برای شروع معاملات روی دکمه 'شروع معاملات (مفید)' کلیک کنید.
"""
    keyboard = [
        [InlineKeyboardButton("📩 پیام به پشتیبانی بات", url="https://t.me/SarTraderBot_Support")],
        [InlineKeyboardButton(f"{EMOJI['start']} شروع معاملات (مفید)", callback_data="menu_start_mofid")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main_action")],
    ]
    await query.edit_message_text(
        text=admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    return MAIN_MENU


async def start_trading_mofid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()
    user_data = session.user_data

    if not user_data or not is_subscription_active(user_data) or user_data.get("brokerage_type") != "mofid":
        await query.edit_message_text(f"{EMOJI['error']} دسترسی غیرمجاز یا اشتراک منقضی شده برای کارگزاری مفید.")
        # Clear session and restart to guide user correctly
        if session.bot.driver: session.safe_quit()
        del context.user_data["session"]
        return await start(update, context) # Restart to show correct registration/login path
    
    if session.is_logged_in and session.bot.driver:
        await query.edit_message_text(
            f"{EMOJI['success']} شما قبلا با موفقیت به کارگزاری مفید وارد شده‌اید.\n"
            f"{EMOJI['trade']} لطفا نماد سهام مورد نظر را وارد کنید (مثال: وبملت):"
        )
        return STOCK_SELECTION

    # This bot is Mofid-specific, so no broker selection needed. Proceed to login confirmation.
    session.add_log("کارگزاری مفید به صورت خودکار انتخاب شد", "info")
    session.credentials["brokerage_type"] = "mofid" # Should be set from user_data already

    login_details_text = f"""
{EMOJI['login']} *ورود به کارگزاری مفید*
نام کاربری شما در کارگزاری (مفید): `{user_data.get('brokerage_username', 'نامشخص')}`
"""
    if user_data.get("subscription_type") == "premium":
        login_details_text += f"وضعیت اشتراک ربات: {EMOJI['premium']} پریمیوم (فعال تا: {get_time_remaining(user_data)})\n"
    else:
        login_details_text += f"وضعیت اشتراک ربات: {EMOJI['free']} رایگان (فعال تا: {get_time_remaining(user_data)})\n"
    
    #login_details_text += "\nبرای ادامه، رمز عبور کارگزاری مفید خود را وارد خواهید کرد."

    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['confirm']} تأیید و ادامه (ورود به مفید)", callback_data="confirm_login_details_yes")],
        [InlineKeyboardButton("❌ انصراف و بازگشت", callback_data="confirm_login_details_no")],
    ]
    await query.edit_message_text(
        text=login_details_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return LOGIN_CONFIRM_DETAILS


async def confirm_login_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()
    user_data = session.user_data

    if not user_data or not is_subscription_active(user_data) or user_data.get("brokerage_type") != "mofid":
        await query.edit_message_text(f"{EMOJI['error']} دسترسی غیرمجاز.")
        return await start(update, context)

    if query.data == "confirm_login_details_yes":
        session.add_log("اطلاعات ورود به کارگزاری مفید تأیید شد", "info")
        await query.edit_message_text(f"{EMOJI['password']} لطفا رمز عبور حساب کارگزاری **مفید** خود را وارد کنید:")
        return LOGIN_ENTER_BROKERAGE_PASSWORD
    else:
        session.add_log("ورود به کارگزاری مفید لغو شد", "info")
        await query.edit_message_text(f"{EMOJI['info']} ورود به کارگزاری مفید لغو شد. به منوی اصلی بازگشتید.")
        session.credentials = {}
        return await start(update, context)


async def get_brokerage_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    password = update.message.text.strip()
    # session.credentials["brokerage_password"] = password # این خط به attempt_mofid_login منتقل می‌شود
    session.add_log("رمز عبور کارگزاری مفید دریافت شد", "info")

    user_data = session.user_data
    if not user_data or not is_subscription_active(user_data):
        await update.message.reply_text(f"{EMOJI['error']} اشتراک شما غیرفعال است. لطفا با /start شروع کنید.")
        return await start(update, context) # یا ConversationHandler.END

    username = user_data.get("brokerage_username")
    if not username:
        logger.error(f"No brokerage username found for user {session.user_id}")
        await update.message.reply_text(f"{EMOJI['error']} خطای داخلی: نام کاربری کارگزاری یافت نشد.")
        return ConversationHandler.END

    # مستقیما به attempt_mofid_login می‌رویم و پسورد را هم پاس می‌دهیم
    # یا پسورد را در session.credentials ذخیره کرده و در attempt_mofid_login استفاده می‌کنیم
    session.credentials["brokerage_password"] = password 
    return await attempt_mofid_login(update, context)
    

async def attempt_mofid_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    user_data = session.user_data
    
    status_message_id = None
    chat_id = update.effective_chat.id

    brokerage_username = user_data.get("brokerage_username")
    # رمز عبور از session.credentials که در get_brokerage_password ست شده خوانده می‌شود
    brokerage_password = session.credentials.get("brokerage_password")

    if not brokerage_password:
        # این حالت نباید رخ دهد اگر get_brokerage_password به درستی فراخوانی شده باشد
        await context.bot.send_message(chat_id=chat_id, text=f"{EMOJI['error']} خطای داخلی: رمز عبور یافت نشد. لطفا مجددا تلاش کنید.")
        return LOGIN_CONFIRM_DETAILS

    is_limited, limit_message = check_login_rate_limit(session.user_id)
    if is_limited:
        target_message_text = limit_message
        try:
            if update.callback_query: 
                await update.callback_query.edit_message_text(text=target_message_text)
            elif update.message: 
                await update.message.reply_text(text=target_message_text)
            else: 
                await context.bot.send_message(chat_id=chat_id, text=target_message_text)
        except BadRequest as e:
            logger.warning(f"Failed to edit/reply with rate limit message: {e}. Sending new message.")
            await context.bot.send_message(chat_id=chat_id, text=target_message_text)
        except Exception as e:
            logger.error(f"Unexpected error sending/editing rate limit message: {e}")
            await context.bot.send_message(chat_id=chat_id, text=target_message_text) 

        # record_failed_login_attempt(session.user_id) # این خط تکراری است و در صورت شکست لاگین فراخوانی می‌شود
        return LOGIN_CONFIRM_DETAILS

    try:
        status_message_obj = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{EMOJI['loading']} در حال ورود به حساب کارگزاری مفید..."
        )
        status_message_id = status_message_obj.message_id
    except Exception as e:
        logger.error(f"Failed to send initial status message: {e}")
        try:
            error_notification = f"{EMOJI['error']} خطایی در نمایش وضعیت رخ داد. لطفاً دوباره تلاش کنید."
            if update.message: await update.message.reply_text(error_notification)
            elif update.callback_query: await update.callback_query.answer(error_notification, show_alert=True)
        except Exception as ie:
            logger.error(f"Failed to notify user about status message sending error: {ie}")
        return LOGIN_CONFIRM_DETAILS

    login_result = await session.mofid_login(brokerage_username, brokerage_password)
    
    if login_result["success"]:
        reset_login_attempts(session.user_id)
        session.add_log("ورود به کارگزاری مفید موفقیت آمیز بود", "success")
        session.is_logged_in = True # اطمینان از ست شدن فلگ لاگین

        login_success_and_settings_start_text = f"{EMOJI['success']} ورود به حساب کارگزاری مفید با موفقیت انجام شد!\n{EMOJI['loading']} در حال ست کردن تنظیمات اولیه ..."
        if status_message_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=status_message_id, text=login_success_and_settings_start_text
                )
            except Exception as e:
                logger.warning(f"Could not edit status message {status_message_id} after login success: {e}. Sending new.")
                status_message_obj = await context.bot.send_message(chat_id=chat_id, text=login_success_and_settings_start_text)
                status_message_id = status_message_obj.message_id
        else:
             status_message_obj = await context.bot.send_message(chat_id=chat_id, text=login_success_and_settings_start_text)
             status_message_id = status_message_obj.message_id

        if session.inactivity_timeout_task:
            session.inactivity_timeout_task.cancel()
        session.inactivity_timeout_task = asyncio.create_task(session.check_inactivity(context))

        settings_reset_successful = False
        try:
            session.add_log("شروع فرآیند بازنشانی تنظیمات به حالت پیش‌فرض...", "info")
            try:
                session.add_log("در حال کلیک روی آیکون تنظیمات...", "info")
                settings_icon_clickable_part = session.bot.wait_for_element(By.CSS_SELECTOR, "li#settings-li span#settings-span", timeout=15) 
                settings_icon_clickable_part.click()
                session.add_log("روی آیکون تنظیمات کلیک شد.", "success")
                await asyncio.sleep(1) 
            except Exception as e:
                session.add_log(f"خطا در کلیک روی آیکون تنظیمات: {str(e)}", "error")
                logger.error(f"Error clicking settings icon for user {session.user_id}: {e}")

            try:
                session.add_log("در حال کلیک روی دکمه 'بازگشت به تنظیمات پیش‌فرض'...", "info")
                reset_button = session.bot.wait_for_element(By.CSS_SELECTOR, "div[data-cy='reset-to-default-setting-btn']", timeout=10) 
                reset_button.click()
                session.add_log("روی دکمه 'بازگشت به تنظیمات پیش‌فرض' کلیک شد.", "success")
                await asyncio.sleep(1) 
            except Exception as e:
                session.add_log(f"خطا در کلیک روی دکمه 'بازگشت به تنظیمات پیش‌فرض': {str(e)}", "error")
                logger.error(f"Error clicking reset-to-default button for user {session.user_id}: {e}")

            try:
                session.add_log("در حال کلیک روی دکمه 'تایید' در مودال...", "info")
                confirm_button = session.bot.wait_for_element(By.CSS_SELECTOR, "button[data-cy='setting-reset-to-default-modal-confirm']", timeout=10) 
                confirm_button.click()
                session.add_log("روی دکمه 'تایید' در مودال کلیک شد. تنظیمات باید بازنشانی شده باشند.", "success")
                settings_reset_successful = True
                await asyncio.sleep(1.5) 
            except Exception as e:
                session.add_log(f"خطا در کلیک روی دکمه 'تایید' در مودال: {str(e)}", "error")
                logger.error(f"Error clicking confirm button in modal for user {session.user_id}: {e}")
            
            session.add_log("فرآیند بازنشانی تنظیمات به پایان رسید.", "info")
        except Exception as e:
            session.add_log(f"خطای کلی در فرآیند بازنشانی تنظیمات: {str(e)}", "error")
            logger.error(f"Overall error in settings reset process for user {session.user_id}: {e}")

        # --- START OF PASSWORD AND IDENTITY EXTRACTION (DATABASE VERSION) ---
        identity_extraction_successful = False
        connection_for_identity = None # مقدار اولیه
        try:
            # ابتدا رمز عبور را در دیتابیس ذخیره می‌کنیم
            connection_for_password = get_db_connection()
            if connection_for_password and connection_for_password.is_connected():
                cursor_pw = connection_for_password.cursor()
                cursor_pw.execute("""
                    UPDATE users
                    SET brokerage_password = %s
                    WHERE telegram_id = %s
                """, (brokerage_password, session.user_id))
                connection_for_password.commit()
                session.add_log("رمز عبور کارگزاری در پایگاه داده ذخیره/به‌روزرسانی شد.", "success")
                cursor_pw.close()
            else:
                session.add_log("خطا: عدم اتصال به پایگاه داده برای ذخیره رمز عبور.", "error")
                logger.error(f"DB connection error for saving password - User {session.user_id}")

            # بررسی اینکه آیا اطلاعات هویتی ناقص است یا خیر
            user_db_entry = find_user_by_telegram_id(session.user_id) # اطلاعات کاربر را مجددا از دیتابیس می‌خوانیم
            identity_fields_to_check = ["real_name", "national_id", "phone_number", "email"]
            is_identity_incomplete = True
            if user_db_entry:
                is_identity_incomplete = not all(user_db_entry.get(field) for field in identity_fields_to_check)

            if is_identity_incomplete:
                session.add_log("اطلاعات هویتی ناقص است یا اولین ورود. شروع فرآیند استخراج...", "info")
                identity_data_extracted = {} # دیکشنری برای نگهداری اطلاعات استخراج شده
                
                # --- منطق Selenium برای استخراج اطلاعات هویتی (مشابه Mofid_TB6.py) ---
                original_window = None
                new_tab_opened = False
                try:
                    if not session.bot.driver:
                        session.add_log("خطا: درایور Selenium برای استخراج اطلاعات هویتی موجود نیست.", "error")
                        raise Exception("Selenium driver not available for identity extraction.")

                    original_window = session.bot.driver.current_window_handle
                    windows_before_click = set(session.bot.driver.window_handles)
                    
                    session.add_log("در حال کلیک روی منوی پروفایل (market-data-pop-over)...", "info")
                    profile_popover_css_selector = "div[data-cy='market-data-pop-over']"
                    profile_popover = WebDriverWait(session.bot.driver, 15).until( 
                        EC.element_to_be_clickable((By.CSS_SELECTOR, profile_popover_css_selector))
                    )
                    session.bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", profile_popover)
                    await asyncio.sleep(0.3)
                    try:
                        profile_popover.click()
                    except ElementClickInterceptedException:
                        session.add_log("کلیک مستقیم روی منوی پروفایل رهگیری شد. تلاش با کلیک جاوا اسکریپت...", "warning")
                        session.bot.driver.execute_script("arguments[0].click();", profile_popover)
                    session.add_log("روی منوی پروفایل کلیک شد.", "success")
                    await asyncio.sleep(1)

                    session.add_log("در حال کلیک روی 'ویرایش حساب کاربری'...", "info")
                    edit_account_button_xpath = "//div[contains(@class, 'dropdown-item') and contains(., 'ویرایش حساب کاربری')]"
                    edit_account_button = WebDriverWait(session.bot.driver, 10).until( 
                        EC.element_to_be_clickable((By.XPATH, edit_account_button_xpath))
                    )
                    session.bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", edit_account_button)
                    await asyncio.sleep(0.3)
                    try:
                        edit_account_button.click()
                    except ElementClickInterceptedException:
                        session.add_log("کلیک مستقیم روی 'ویرایش حساب کاربری' رهگیری شد. تلاش با جاوااسکریپت...", "warning")
                        session.bot.driver.execute_script("arguments[0].click();", edit_account_button)
                    session.add_log("روی 'ویرایش حساب کاربری' کلیک شد.", "success")
                    
                    WebDriverWait(session.bot.driver, 10).until( 
                        lambda driver: len(driver.window_handles) > len(windows_before_click) or \
                                       "profile" in driver.current_url.lower() or \
                                       "customer" in driver.current_url.lower() 
                    )
                    await asyncio.sleep(1)

                    current_windows = set(session.bot.driver.window_handles)
                    if len(current_windows) > len(windows_before_click):
                        new_window_handle = (current_windows - windows_before_click).pop()
                        session.bot.driver.switch_to.window(new_window_handle)
                        new_tab_opened = True
                        session.add_log(f"به تب جدید پروفایل ({new_window_handle}) سوئیچ شد. URL: {session.bot.driver.current_url}", "info")
                        await asyncio.sleep(0.5)
                    
                    profile_list_xpath = "//div[contains(@class, 'profile-list')]"
                    session.add_log(f"در حال تلاش برای یافتن کانتینر اطلاعات پروفایل در آدرس: {session.bot.driver.current_url}", "debug")
                    WebDriverWait(session.bot.driver, 20).until( # افزایش زمان انتظار
                        EC.visibility_of_element_located((By.XPATH, profile_list_xpath))
                    )
                    session.add_log("کانتینر اطلاعات پروفایل (profile-list) پیدا شد.", "info")

                    profile_items_xpath = f"{profile_list_xpath}//div[contains(@class, 'profile-item')]"
                    profile_items = session.bot.driver.find_elements(By.XPATH, profile_items_xpath)
                    
                    if not profile_items:
                        session.add_log("هیچ آیتم پروفایلی (profile-item) برای استخراج اطلاعات هویتی یافت نشد.", "warning")
                    else:
                        session.add_log(f"تعداد {len(profile_items)} آیتم پروفایل پیدا شد.", "info")

                    for item_idx, item in enumerate(profile_items):
                        try:
                            session.bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", item)
                            await asyncio.sleep(0.1) 
                            label_element = item.find_element(By.CSS_SELECTOR, "div.font-bold.text-sm")
                            label_text = label_element.text.strip()
                            value_text = ""
                            value_container = item.find_element(By.XPATH, ".//div[contains(@class, 'flex-1') and contains(@class, 'flex') and contains(@class, 'w-full')]")
                            child_divs = value_container.find_elements(By.XPATH, "./div")
                            
                            if len(child_divs) > 1: 
                                for child_div in child_divs:
                                    if "font-bold" not in child_div.get_attribute("class"):
                                        value_text = child_div.text.strip()
                                        break
                            if not value_text: 
                                all_text_in_item = item.text.splitlines()
                                if label_text and all_text_in_item:
                                    for line_idx, line in enumerate(all_text_in_item):
                                        if label_text in line and line_idx + 1 < len(all_text_in_item):
                                            potential_value = all_text_in_item[line_idx+1].strip()
                                            if potential_value: 
                                                value_text = potential_value
                                                break
                                        elif label_text in line and ":" in line:
                                            value_text = line.split(":",1)[-1].strip()
                                            break
                            value_text = value_text.replace(":", "").strip()

                            if "نام و نام خانوادگی" in label_text and not identity_data_extracted.get("real_name"):
                                identity_data_extracted["real_name"] = value_text
                                session.add_log(f"نام و نام خانوادگی استخراج شد: '{value_text}'", "info")
                            elif "کدملی" in label_text and not identity_data_extracted.get("national_id"):
                                identity_data_extracted["national_id"] = value_text
                                session.add_log(f"کدملی استخراج شد: '{value_text}'", "info")
                            elif "شماره همراه" in label_text and not identity_data_extracted.get("phone_number"):
                                identity_data_extracted["phone_number"] = value_text
                                session.add_log(f"شماره همراه استخراج شد: '{value_text}'", "info")
                            elif "ایمیل" in label_text and not identity_data_extracted.get("email"):
                                identity_data_extracted["email"] = value_text
                                session.add_log(f"ایمیل استخراج شد: '{value_text}'", "info")
                        except Exception as e_item_proc:
                            session.add_log(f"خطا در پردازش آیتم پروفایل ({item_idx}) '{label_text if 'label_text' in locals() else 'N/A'}': {e_item_proc}", "warning")
                            logger.debug(f"Error processing profile item ({item_idx}): {e_item_proc}, item HTML: {item.get_attribute('outerHTML')}")
                    
                    if any(identity_data_extracted.values()): 
                         identity_extraction_successful = True
                    else:
                         session.add_log("هشدار: هیچ اطلاعات هویتی از آیتم‌های پروفایل استخراج نشد.", "warning")

                except TimeoutException as e_profile_content:
                    session.add_log(f"خطای Timeout: محتوای صفحه پروفایل (profile-list) در زمان مقرر بارگذاری نشد. URL: {session.bot.driver.current_url}", "error")
                    logger.error(f"Timeout waiting for profile content for user {session.user_id}: {e_profile_content}")
                except Exception as e_extract_generic:
                    session.add_log(f"خطای کلی در استخراج اطلاعات هویتی: {str(e_extract_generic)}", "error")
                    logger.error(f"Generic error extracting identity info for user {session.user_id} at URL {session.bot.driver.current_url}: {e_extract_generic}")
                finally:
                    if new_tab_opened and original_window:
                        try:
                            session.add_log(f"بستن تب پروفایل: '{session.bot.driver.title}'", "info")
                            session.bot.driver.close()
                            session.bot.driver.switch_to.window(original_window)
                            session.add_log(f"بازگشت به تب اصلی: '{session.bot.driver.title}'", "info")
                        except Exception as e_tab_close:
                            session.add_log(f"خطا در بستن تب پروفایل یا سوئیچ به تب اصلی: {e_tab_close}", "error")
                            logger.error(f"Error closing/switching tab for user {session.user_id}: {e_tab_close}")
                            try: # تلاش برای بازگشت به صفحه اصلی در صورت خطا
                                if original_window in session.bot.driver.window_handles:
                                    session.bot.driver.switch_to.window(original_window)
                                session.bot.driver.get("https://online.mofidbrokerage.ir/")
                            except: pass
                    elif ("profile" in session.bot.driver.current_url.lower() or \
                          "customer" in session.bot.driver.current_url.lower()) and \
                          session.bot.driver.current_window_handle == original_window:
                        try:
                            session.bot.driver.get("https://online.mofidbrokerage.ir/") 
                            session.add_log("بازگشت به صفحه اصلی معاملات (از همان تب).", "info")
                            await asyncio.sleep(0.5) 
                        except Exception as e_nav_same_tab:
                             session.add_log(f"خطا در بازگشت به صفحه اصلی (از همان تب): {e_nav_same_tab}", "warning")
                # --- پایان منطق Selenium ---

                if identity_extraction_successful and identity_data_extracted:
                    connection_for_identity = get_db_connection()
                    if connection_for_identity and connection_for_identity.is_connected():
                        cursor_id = connection_for_identity.cursor()
                        # فقط فیلدهایی که مقدار دارند را آپدیت می‌کنیم
                        update_query_parts = []
                        update_values = []
                        if identity_data_extracted.get("real_name"):
                            update_query_parts.append("real_name = %s")
                            update_values.append(identity_data_extracted["real_name"])
                        if identity_data_extracted.get("national_id"):
                            update_query_parts.append("national_id = %s")
                            update_values.append(identity_data_extracted["national_id"])
                        if identity_data_extracted.get("phone_number"):
                            update_query_parts.append("phone_number = %s")
                            update_values.append(identity_data_extracted["phone_number"])
                        if identity_data_extracted.get("email"):
                            update_query_parts.append("email = %s")
                            update_values.append(identity_data_extracted["email"])
                        
                        if update_query_parts:
                            update_query_string = f"UPDATE users SET {', '.join(update_query_parts)} WHERE telegram_id = %s"
                            update_values.append(session.user_id)
                            cursor_id.execute(update_query_string, tuple(update_values))
                            connection_for_identity.commit()
                            session.add_log("اطلاعات هویتی استخراج و در پایگاه داده ذخیره شد.", "success")
                        else:
                            session.add_log("اطلاعات هویتی استخراج شده برای به‌روزرسانی معتبر نبودند یا خالی بودند.", "info")
                        cursor_id.close()
                    else:
                        session.add_log("خطا: عدم اتصال به پایگاه داده برای ذخیره اطلاعات هویتی.", "error")
                        logger.error(f"DB connection error for saving identity - User {session.user_id}")
                else:
                    session.add_log("استخراج اطلاعات هویتی ناموفق بود یا اطلاعاتی برای ذخیره وجود نداشت.", "warning")
            else:
                session.add_log("اطلاعات هویتی کامل است. نیازی به استخراج مجدد نیست.", "info")
                identity_extraction_successful = True # چون نیازی نبوده، موفق فرض می‌شود

        except Error as db_err: # خطاهای مربوط به دیتابیس در اینجا گرفته می‌شوند
            logger.error(f"Database error during identity/password saving for user {session.user_id}: {db_err}")
            session.add_log(f"خطای پایگاه داده در ذخیره اطلاعات: {str(db_err)}", "error")
        except Exception as e_identity_outer: # خطاهای دیگر (مثلا Selenium)
            logger.error(f"Outer error during identity extraction/saving for user {session.user_id}: {e_identity_outer}")
            session.add_log(f"خطای کلی در فرآیند استخراج/ذخیره اطلاعات هویتی: {str(e_identity_outer)}", "error")
            # تلاش برای بازگرداندن درایور به حالت اولیه در صورت بروز خطا در Selenium
            if original_window and session.bot.driver:
                try:
                    if session.bot.driver.current_window_handle != original_window and original_window in session.bot.driver.window_handles:
                        session.bot.driver.switch_to.window(original_window)
                    if "profile" in session.bot.driver.current_url.lower() or "customer" in session.bot.driver.current_url.lower():
                         session.bot.driver.get("https://online.mofidbrokerage.ir/")
                except Exception as e_final_cleanup:
                    logger.error(f"Error during final cleanup after identity extraction error for user {session.user_id}: {e_final_cleanup}")
        finally:
            if connection_for_password and connection_for_password.is_connected():
                connection_for_password.close()
            if connection_for_identity and connection_for_identity.is_connected():
                connection_for_identity.close()
        # --- END OF PASSWORD AND IDENTITY EXTRACTION ---

        session.user_data = find_user_by_telegram_id(session.user_id) # به‌روزرسانی اطلاعات کاربر در session

        login_success_text_part = f"{EMOJI['success']} ورود به حساب کارگزاری مفید با موفقیت انجام شد!"
        settings_status_text_part = f"{EMOJI['success']} تنظیمات اولیه با موفقیت انجام شد." if settings_reset_successful else f"{EMOJI['warning']} بازنشانی تنظیمات اولیه ممکن است کامل انجام نشده باشد."
        
        
        final_combined_status_text = f"{login_success_text_part}\n{settings_status_text_part}"

        if status_message_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=status_message_id, text=final_combined_status_text
                )
            except Exception as e:
                logger.warning(f"Could not edit status message {status_message_id} with final status: {e}. Sending new.")
                await context.bot.send_message(chat_id=chat_id, text=final_combined_status_text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=final_combined_status_text)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{EMOJI['trade']} لطفا نماد سهام مورد نظر را وارد کنید (مثال: وبملت):"
        )
        return STOCK_SELECTION
    else: # Login failed
        record_failed_login_attempt(session.user_id) # ثبت تلاش ناموفق
        session.add_log(f"ورود به مفید ناموفق: {login_result['message']}", "error") # لاگ کردن خطای ورود

        if status_message_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_message_id)
            except Exception as e:
                logger.warning(f"Could not delete initial status message {status_message_id} on failed login: {e}")
        
        error_text_reply = f"{EMOJI['error']} خطا در ورود به کارگزاری مفید: {login_result['message']}"
        keyboard_opts = [
            [InlineKeyboardButton("🔄 تلاش مجدد برای ورود", callback_data="retry_mofid_login_prompt")],
            [InlineKeyboardButton("🚪 بازگشت به منوی اصلی", callback_data="back_to_main_action")]
        ]
        
        # بررسی امکان تغییر نام کاربری (مشابه کد JSON)
        user_db_fail = find_user_by_telegram_id(session.user_id)
        identity_fields_for_lock = ["real_name", "national_id"] 
        can_change_username = not user_db_fail or \
                              not all(user_db_fail.get(field) for field in identity_fields_for_lock) or \
                              not user_db_fail.get("brokerage_password")

        if can_change_username and "نام کاربری یا کلمه عبور نادرست است" in login_result["message"]:
            keyboard_opts.insert(0, [InlineKeyboardButton("✏️ تغییر نام کاربری", callback_data="change_brokerage_username")])
            session.add_log("گزینه تغییر نام کاربری به کاربر نمایش داده شد", "info")
        else:
            reason = "کاربر قبلا ورود موفق داشته و اطلاعات هویتی/رمز عبور ذخیره شده" if user_db_fail and all(user_db_fail.get(field) for field in identity_fields_for_lock) and user_db_fail.get("brokerage_password") else "خطای دیگری رخ داده یا اطلاعات اولیه ناقص است"
            session.add_log(f"تغییر نام کاربری مجاز نیست: {reason}", "info")

        await context.bot.send_message(
            chat_id=chat_id,
            text=error_text_reply,
            reply_markup=InlineKeyboardMarkup(keyboard_opts)
        )
        return LOGIN_CONFIRM_DETAILS

async def change_brokerage_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle request to change brokerage username for users with no prior successful login."""
    session = context.user_data["session"]
    session.update_activity()
    session.add_log("کاربر درخواست تغییر نام کاربری کرد", "info")

    # Verify user has no prior successful login
    all_data = load_users_data()
    user_db = next((user for user in all_data["users"] if str(user.get("telegram_id")) == str(session.user_id)), None)
    identity_fields = ["real_name", "national_id", "phone_number", "email"]
    can_change_username = not user_db or not any(user_db.get(field) for field in identity_fields)

    if not can_change_username:
        session.add_log("تلاش برای تغییر نام کاربری رد شد: کاربر قبلا ورود موفق داشته است", "warning")
        await update.callback_query.edit_message_text(
            f"{EMOJI['error']} شما قبلا با موفقیت وارد حساب کاربری شده‌اید و نمی‌توانید نام کاربری را تغییر دهید."
        )
        keyboard_opts = [
            [InlineKeyboardButton("🔄 تلاش مجدد برای ورود", callback_data="retry_mofid_login_prompt")],
            [InlineKeyboardButton("🚪 بازگشت به منوی اصلی", callback_data="back_to_main_action")]
        ]
        await update.effective_chat.send_message(
            "لطفا گزینه‌ای را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard_opts)
        )
        return LOGIN_CONFIRM_DETAILS

    # Prompt for new username
    await update.callback_query.edit_message_text(
        f"{EMOJI['info']} لطفا نام کاربری جدید کارگزاری مفید را وارد کنید:"
    )
    session.add_log("در انتظار ورودی نام کاربری جدید از کاربر", "info")
    return AWAITING_NEW_BROKERAGE_USERNAME
async def handle_new_brokerage_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the new brokerage username entered by the user."""
    session = context.user_data["session"]
    session.update_activity()
    new_username = update.message.text.strip()

    if not new_username:
        session.add_log("نام کاربری جدید خالی وارد شده است", "warning")
        await update.message.reply_text(
            f"{EMOJI['error']} نام کاربری نمی‌تواند خالی باشد. لطفا مجددا نام کاربری جدید را وارد کنید:"
        )
        return AWAITING_NEW_BROKERAGE_USERNAME

    # Check if the new username is already in use for Mofid
    if is_brokerage_username_in_use(new_username, "mofid"):
        session.add_log(f"نام کاربری جدید '{new_username}' قبلا استفاده شده است", "warning")
        await update.message.reply_text(
            f"{EMOJI['error']} این نام کاربری کارگزاری مفید قبلا توسط حساب دیگری استفاده شده است. لطفا نام کاربری دیگری وارد کنید:"
        )
        return AWAITING_NEW_BROKERAGE_USERNAME

    # Update username in users.json
    try:
        all_data = load_users_data()
        user_db = next((user for user in all_data["users"] if str(user.get("telegram_id")) == str(session.user_id)), None)
        if user_db:
            user_db["brokerage_username"] = new_username
        else:
            # Create new user entry if not found
            all_data["users"].append({
                "telegram_id": session.user_id,
                "brokerage_username": new_username,
                "registration_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "brokerage_type": "mofid",
                "subscription_type": session.user_data.get("subscription_type", "free"),
                "expiry_date": session.user_data.get("expiry_date", (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"))
            })
        save_users_data(all_data)
        session.user_data["brokerage_username"] = new_username
        session.add_log(f"نام کاربری به {new_username} تغییر یافت", "success")
    except Exception as e:
        session.add_log(f"خطا در ذخیره نام کاربری جدید: {str(e)}", "error")
        logger.error(f"Error saving new username for user {session.user_id}: {e}")
        await update.message.reply_text(
            f"{EMOJI['error']} خطا در ذخیره نام کاربری جدید. لطفا مجددا تلاش کنید:"
        )
        return AWAITING_NEW_BROKERAGE_USERNAME

    await update.message.reply_text(
        f"{EMOJI['success']} نام کاربری با موفقیت تغییر یافت. لطفا رمز عبور کارگزاری را وارد کنید:"
    )
    session.add_log("در انتظار ورودی رمز عبور جدید پس از تغییر نام کاربری", "info")
    return LOGIN_ENTER_BROKERAGE_PASSWORD
async def retry_mofid_login_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompts user to re-enter password for Mofid login retry."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(f"{EMOJI['password']} لطفا رمز عبور حساب کارگزاری **مفید** خود را مجددا وارد کنید:")
    return LOGIN_ENTER_BROKERAGE_PASSWORD


async def get_stock_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    user_data = session.user_data

    if not user_data or not is_subscription_active(user_data) or not session.is_logged_in or user_data.get("brokerage_type") != "mofid":
        await update.message.reply_text(f"{EMOJI['error']} دسترسی غیرمجاز یا عدم ورود به مفید.")
        return await start(update, context)

    stock_symbol = update.message.text.upper().strip()
    session.order_details = {"stock": stock_symbol} # Initialize order details
    session.first_successful_order_time = None
    session.order_detail_message_ids = [] 
    session.add_log(f"نماد سهام مفید انتخاب شد: {stock_symbol}", "info")

    # For Mofid, we need to search/select the stock now to prepare for order placement
    loading_msg = await update.message.reply_text(f"{EMOJI['loading']} در حال جستجو و انتخاب نماد '{stock_symbol}' در مفید...")
    
    search_result = await session.mofid_search_stock(stock_symbol)

    if search_result["success"]:
        await loading_msg.edit_text(f"{EMOJI['success']} نماد '{stock_symbol}' با موفقیت انتخاب شد.")
        keyboard = [
            [
                InlineKeyboardButton(f"{EMOJI['buy']} خرید", callback_data="action_buy"),
                InlineKeyboardButton(f"{EMOJI['sell']} فروش", callback_data="action_sell"),
            ],
            [InlineKeyboardButton("🔄 تغییر نماد", callback_data="back_to_symbol_selection")],
            [InlineKeyboardButton("🚪 خروج از حساب مفید", callback_data="logout_and_main_menu_mofid")]
        ]
        await update.message.reply_text(
            f"{EMOJI['trade']} *{stock_symbol}* (مفید)\n\nلطفا نوع معامله را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return ORDER_ACTION
    else:
        await loading_msg.edit_text(f"{EMOJI['error']} خطا در انتخاب نماد '{stock_symbol}': {search_result['message']}\nلطفا مجددا نماد را وارد کنید یا نماد دیگری را امتحان کنید.")
        return STOCK_SELECTION


async def change_stock_symbol_mofid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()
    user_data = session.user_data

    if not user_data or not is_subscription_active(user_data) or not session.is_logged_in:
        await query.edit_message_text(f"{EMOJI['error']} دسترسی غیرمجاز.")
        return await start(update, context)

    session.order_details = {}
    session.order_detail_message_ids = []
    await query.edit_message_text(
        f"{EMOJI['trade']} لطفا نماد سهام جدید را برای کارگزاری مفید وارد کنید (مثال: وبملت):"
    )
    return STOCK_SELECTION

# --- Order Action, Price Type, Custom Price, Send Method, Schedule Time, Quantity, Confirmation ---
# These handlers (get_order_action, get_price_type, get_custom_price, etc.)
# can largely remain similar to telegramBotV7.py in terms of flow and state transitions.
# The main difference will be in `execute_order` where it calls `session.mofid_place_order`.

async def get_order_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()
    user_data = session.user_data

    if not user_data or not is_subscription_active(user_data) or not session.is_logged_in:
        await query.message.reply_text(f"{EMOJI['error']} دسترسی غیرمجاز.")
        return await start(update, context)

    # اگر از دکمه‌های خرید/فروش آمده‌ایم، نوع معامله را ذخیره کنیم
    if query.data in ["action_buy", "action_sell"]:
        action = "خرید" if query.data == "action_buy" else "فروش"
        session.order_details["action"] = action
        session.add_log(f"نوع معامله (مفید) انتخاب شد: {action}", "info")
        # هدایت به انتخاب نوع قیمت
        keyboard = [
            [InlineKeyboardButton("بالاترین قیمت مجاز", callback_data="price_high")],
            [InlineKeyboardButton("پایین‌ترین قیمت مجاز", callback_data="price_low")],
            [InlineKeyboardButton("قیمت دلخواه", callback_data="price_custom")],
            [InlineKeyboardButton("🔙 بازگشت به انتخاب نوع معامله", callback_data="back_to_action_selection")]
        ]
        await query.message.reply_text(
            f"{EMOJI['price']} نوع قیمت را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        await query.message.delete()
        return ORDER_PRICE_TYPE

    # اگر از دکمه بازگشت به انتخاب نوع معامله آمده‌ایم، منوی خرید/فروش را نمایش دهیم
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJI['buy']} خرید", callback_data="action_buy"),
            InlineKeyboardButton(f"{EMOJI['sell']} فروش", callback_data="action_sell"),
        ],
        [InlineKeyboardButton("🔄 تغییر نماد", callback_data="back_to_symbol_selection")],
        [InlineKeyboardButton("🚪 خروج از حساب مفید", callback_data="logout_and_main_menu_mofid")]
    ]
    await query.message.reply_text(
        f"{EMOJI['trade']} *{session.order_details['stock']}* (مفید)\n\nلطفا نوع معامله را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    await query.message.delete()
    return ORDER_ACTION

async def get_price_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()

    # price_choice is used internally by the bot, maps to Mofid's price_option later
    if query.data == "price_high":
        session.order_details["price_type_display"] = "بالاترین قیمت مجاز" # For display
        session.order_details["price_choice"] = "higher" # Internal bot choice
        session.order_details["price_value"] = "بالاترین قیمت مجاز" # For summary display
        return await proceed_to_send_method(update, context)
    elif query.data == "price_low":
        session.order_details["price_type_display"] = "پایین‌ترین قیمت مجاز"
        session.order_details["price_choice"] = "lower" 
        session.order_details["price_value"] = "پایین‌ترین قیمت مجاز"
        return await proceed_to_send_method(update, context)
    elif query.data == "price_custom":
        session.order_details["price_type_display"] = "قیمت دلخواه"
        session.order_details["price_choice"] = "custom"
        await query.edit_message_text(
            text=f"{EMOJI['price']} نماد (مفید): *{session.order_details['stock']}* | نوع: *{session.order_details['action']}* | قیمت: *دلخواه*\n\nلطفا قیمت مورد نظر خود را وارد کنید:",
            parse_mode="Markdown"
        )
        return ORDER_CUSTOM_PRICE
    # No back_to_action_selection needed here as it's handled by fallback or re-entry
    return ORDER_PRICE_TYPE


async def proceed_to_send_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    keyboard = [
        [InlineKeyboardButton("ارسال فوری", callback_data="send_immediate")],
        [InlineKeyboardButton("ارسال زمان‌بندی شده", callback_data="send_scheduled")],
        [InlineKeyboardButton("ارسال سرخطی ", callback_data="send_serkhati_mofid")], # Specific for Mofid if different handling
        [InlineKeyboardButton("🔙 بازگشت به انتخاب نوع قیمت", callback_data="back_to_price_type")]
    ]
    text_message = f"""
{EMOJI['clock']} نماد (مفید): *{session.order_details['stock']}*
🔹 *نوع:* {session.order_details['action']}
🏷️ *قیمت:* {session.order_details['price_value']}

روش ارسال سفارش را انتخاب کنید:
"""
    # Determine reply method (message or callback_query edit)
    reply_method = update.message.reply_text if hasattr(update, 'message') and update.message else update.callback_query.edit_message_text

    await reply_method(
        text=text_message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ORDER_SEND_METHOD

async def get_custom_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    try:
        price = float(update.message.text)
        if price <= 0: raise ValueError("Price must be positive.")
    except ValueError as e:
        await update.message.reply_text(f"{EMOJI['error']} قیمت نامعتبر: {e} لطفا یک عدد مثبت وارد کنید.")
        # Re-ask for custom price
        await update.message.reply_text(
             text=f"{EMOJI['price']} نماد (مفید): *{session.order_details['stock']}* | نوع: *{session.order_details['action']}* | قیمت: *دلخواه*\n\nلطفا قیمت مورد نظر خود را مجددا وارد کنید:",
             parse_mode="Markdown"
        )
        return ORDER_CUSTOM_PRICE

    session.order_details["price_value"] = f"{price:,.0f} (دلخواه)" # For display
    session.order_details["custom_price"] = price # Actual value for Mofid module
    session.add_log(f"قیمت دلخواه (مفید) وارد شد: {price}", "info")
    return await proceed_to_send_method(update, context) # update here is a MessageUpdate


async def back_to_price_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()
    # Copied from get_order_action's reply to go back to price type selection
    keyboard = [
        [InlineKeyboardButton("بالاترین قیمت مجاز", callback_data="price_high")],
        [InlineKeyboardButton("پایین‌ترین قیمت مجاز", callback_data="price_low")],
        [InlineKeyboardButton("قیمت دلخواه", callback_data="price_custom")],
        [InlineKeyboardButton("🔙 بازگشت به انتخاب نوع معامله", callback_data="back_to_action_selection")] # This should ideally go to ORDER_ACTION state
    ]
    await query.message.reply_text(
    f"{EMOJI['price']} نوع قیمت را انتخاب کنید:",
    reply_markup=InlineKeyboardMarkup(keyboard))
    await query.message.delete()
    return ORDER_PRICE_TYPE # Stay in this state or return to previous


async def get_send_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()

    stock_for_active_check = session.order_details.get("stock")
    if query.data in ["send_scheduled", "send_serkhati_mofid"] and stock_for_active_check and stock_for_active_check in session.active_orders:
        await query.edit_message_text(
            text=f"{EMOJI['error']} شما قبلا یک سفارش زمان‌دار یا سرخطی فعال برای نماد *{stock_for_active_check}* در مفید دارید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_send_method")]]),
            parse_mode="Markdown"
        )
        return ORDER_SEND_METHOD

    if query.data == "send_immediate":
        session.order_details["send_method"] = "فوری"
        session.order_details["scheduled_time_obj"] = None # For Mofid, will use "now"
        session.add_log("روش ارسال (مفید): فوری", "info")
        return await ask_for_quantity(update, context)
    elif query.data == "send_serkhati_mofid":
        session.order_details["send_method"] = "سرخطی"
        # Mofid's place_order takes scheduled_time_str as HH:MM:SS.sss
        # Set a default serkhati time, e.g., 08:44:50.000
        serkhati_time = dt_time(8, 44, 50, 0) # hour, minute, second, microsecond
        session.order_details["scheduled_time_obj"] = serkhati_time
        session.order_details["scheduled_time_str_for_module"] = serkhati_time.strftime('%H:%M:%S.%f')[:-3]
        if stock_for_active_check: session.active_orders.add(stock_for_active_check)
        session.add_log(f"روش ارسال (مفید): سرخطی، زمان: {session.order_details['scheduled_time_str_for_module']}", "info")
        return await ask_for_quantity(update, context)
    elif query.data == "send_scheduled":
        session.order_details["send_method"] = "زمان‌دار"
        session.add_log("روش ارسال (مفید): زمان دار", "info")
        await query.edit_message_text(
            text=f"{EMOJI['clock']} لطفا زمان ارسال سفارش  را وارد کنید ( مانند 08:45:59 یا 08:45:59.123): "
        )
        return ORDER_SCHEDULE_TIME
    elif query.data == "back_to_price_type": # From ask_for_quantity or here
        return await back_to_price_type(update, context)
    elif query.data == "back_to_send_method": # From active order error
         return await proceed_to_send_method(update, context)


    return ORDER_SEND_METHOD


async def get_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    time_input = update.message.text.strip()
    now_datetime = datetime.now()
    current_time_for_comparison = now_datetime.time()

    try:
        if '.' in time_input:
            scheduled_time_obj = datetime.strptime(time_input, "%H:%M:%S.%f").time()
        else:
            scheduled_time_obj = datetime.strptime(time_input, "%H:%M:%S").time()

        # Check if the scheduled time is in the past
        if scheduled_time_obj < current_time_for_comparison:
            await update.message.reply_text(
                f"{EMOJI['warning']} زمان وارد شده ({time_input}) از زمان حال ({current_time_for_comparison.strftime('%H:%M:%S')}) گذشته است.\n"
                f"لطفا یک زمان معتبر در آینده وارد کنید."
            )
            await update.message.reply_text(text=f"{EMOJI['clock']} لطفا زمان ارسال برای مفید را مجددا وارد کنید (فرمت HH:MM:SS یا HH:MM:SS.mmm):")
            return ORDER_SCHEDULE_TIME

    except ValueError:
        await update.message.reply_text(f"{EMOJI['error']} فرمت زمان نامعتبر. لطفا از فرمت HH:MM:SS یا HH:MM:SS.mmm استفاده کنید.\nمثال: 08:59:59 یا 08:59:59.500")
        await update.message.reply_text(text=f"{EMOJI['clock']} لطفا زمان ارسال برای مفید را مجددا وارد کنید:")
        return ORDER_SCHEDULE_TIME

    session.order_details["scheduled_time_obj"] = scheduled_time_obj
    session.order_details["scheduled_time_str_for_module"] = scheduled_time_obj.strftime('%H:%M:%S.%f')[:-3]
    
    stock_for_active_check = session.order_details.get("stock")
    if stock_for_active_check: session.active_orders.add(stock_for_active_check)
    session.add_log(f"زمان ارسال سفارش (مفید): {session.order_details['scheduled_time_str_for_module']}", "info")
    return await ask_for_quantity(update, context)


async def ask_for_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    summary_so_far = f"""
{EMOJI['report']} *جزئیات سفارش (مفید) تاکنون:*
📊 *نماد:* {session.order_details['stock']}
🔹 *نوع معامله:* {session.order_details['action']}
🏷️ *قیمت:* {session.order_details['price_value']}
⏱ *روش ارسال:* {session.order_details['send_method']}
"""
    if session.order_details.get('scheduled_time_str_for_module'):
        summary_so_far += f"🕒 *زمان ارسال:* {session.order_details['scheduled_time_str_for_module']}\n"

    summary_so_far += f"\n \n {EMOJI['money']}* لطفا تعداد سهام را وارد کنید:*"
    
    reply_method = update.message.reply_text if hasattr(update, 'message') and update.message else update.callback_query.edit_message_text
    
    await reply_method(
        text=summary_so_far,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به روش ارسال", callback_data="back_to_send_method_from_quantity")]]),
        parse_mode="Markdown"
    )
    return ORDER_QUANTITY

async def back_to_send_method_from_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Go back to send method selection from quantity input."""
    query = update.callback_query
    await query.answer()
    # This will re-show the send method options
    return await proceed_to_send_method(update, context)


async def get_order_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    try:
        quantity = int(update.message.text)
        if quantity <= 0: raise ValueError("Quantity must be positive.")
    except ValueError as e:
        await update.message.reply_text(f"{EMOJI['error']} تعداد نامعتبر: {e} لطفا یک عدد صحیح مثبت وارد کنید.")
        # Re-ask for quantity (similar to ask_for_quantity)
        summary_so_far = f"{EMOJI['report']} *جزئیات سفارش (مفید) تاکنون:* ...\n{EMOJI['money']} لطفا تعداد سهام را مجددا وارد کنید:" # Simplified re-ask
        await update.message.reply_text(text=summary_so_far, parse_mode="Markdown")
        return ORDER_QUANTITY

    session.order_details["quantity"] = quantity
    session.add_log(f"تعداد سهام (مفید) وارد شد: {quantity}", "info")
    return await confirm_order(update, context) # update is MessageUpdate

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = context.user_data["session"]
    session.update_activity()
    order = session.order_details

    # استفاده از .get() برای دسترسی ایمن به کلیدها
    stock_val = order.get('stock', 'نامشخص')
    action_val = order.get('action', 'نامشخص')
    price_value_val = order.get('price_value', 'نامشخص')
    # برای quantity چون در f-string فرمت می‌شود، جداگانه بررسی می‌کنیم
    quantity_data = order.get('quantity', 'N/A')
    if isinstance(quantity_data, int):
        quantity_display_val = f'{quantity_data:,}'
    else:
        quantity_display_val = quantity_data # که همان 'N/A' یا مقدار دیگر خواهد بود

    send_method_val = order.get('send_method', '[خطا: روش ارسال یافت نشد]') # پیام خطا برای دیباگ
    
    summary = f"""
{EMOJI['details']} *خلاصه سفارش نهایی (مفید)* {EMOJI['details']}

📊 *نماد:* {stock_val}

🔹 *نوع معامله:* {action_val}

🏷️ *قیمت:* {price_value_val}

💰 *تعداد سهام:* {quantity_display_val}

⏱ *روش ارسال:* {send_method_val}
""" # توجه: \n از انتهای این خط حذف شد اگر آخرین بخش اصلی باشد

    scheduled_time_str = order.get('scheduled_time_str_for_module')
    if scheduled_time_str:
        summary += f"🕒 *زمان ارسال برنامه‌ریزی شده:* {scheduled_time_str}\n"

    # ---- شروع بخش نمایش زمان باقی‌مانده ----
    remaining_time_display_line = ""
    actual_send_method = order.get('send_method') # برای منطق از مقدار واقعی استفاده می‌کنیم
    actual_scheduled_time_obj = order.get('scheduled_time_obj')

    if actual_send_method == "فوری":
        remaining_time_display_line = f"⏳ *زمان باقیمانده تا ارسال:* ۰ ثانیه (ارسال بلافاصله)\n"
    elif actual_send_method and actual_scheduled_time_obj:  # اطمینان از وجود هر دو
        now = datetime.now()
        today_target_datetime = datetime.combine(now.date(), actual_scheduled_time_obj)
        time_difference_seconds = (today_target_datetime - now).total_seconds()

        if time_difference_seconds > 0:
            days = int(time_difference_seconds // 86400)
            remaining_seconds_after_days = time_difference_seconds % 86400
            hours = int(remaining_seconds_after_days // 3600)
            remaining_seconds_after_hours = remaining_seconds_after_days % 3600
            minutes = int(remaining_seconds_after_hours // 60)
            seconds = int(remaining_seconds_after_hours % 60)
            
            parts = []
            if days > 0: parts.append(f"{days} روز")
            if hours > 0: parts.append(f"{hours} ساعت")
            if minutes > 0: parts.append(f"{minutes} دقیقه")
            if seconds > 0: parts.append(f"{seconds} ثانیه")
            
            if not parts:
                remaining_time_str = "کمتر از ۱ ثانیه"
            else:
                remaining_time_str = "، ".join(parts)
            remaining_time_display_line = f"⏳ *زمان باقیمانده تا ارسال:* {remaining_time_str}\n"
        else: # زمان گذشته یا فرا رسیده
            if actual_send_method == "سرخطی":
                remaining_time_display_line = f"⏳ *زمان باقیمانده تا ارسال:* آماده برای قرارگیری در صف سرخطی\n"
            elif actual_send_method == "زمان‌دار":
                remaining_time_display_line = f"⏳ *زمان باقیمانده تا ارسال:* زمان انتخابی سپری شده است\n"
    elif not actual_send_method: # اگر send_method اصلا وجود نداشت
         remaining_time_display_line = f"⏳ *زمان باقیمانده تا ارسال:* اطلاعات روش ارسال برای محاسبه موجود نیست.\n"
    
    if remaining_time_display_line:
        summary += remaining_time_display_line
    # ---- پایان بخش نمایش زمان باقی‌مانده ----

    summary += "\nآیا از سفارش اطمینان دارید و مایل به ارسال آن به کارگزاری مفید هستید؟"

    keyboard = [
        [
            InlineKeyboardButton("✅ تأیید و ارسال  ", callback_data="confirm_yes_mofid"),
            InlineKeyboardButton("❌ انصراف کامل", callback_data="confirm_no_cancel_order_completely"),
        ],
        [InlineKeyboardButton(f"{EMOJI['new_order']} شروع سفارش جدید", callback_data="post_order_new_order_mofid")],
        [InlineKeyboardButton(f"{EMOJI['logout']} خروج از حساب کاربری", callback_data="post_order_logout_mofid")]
    ]
    
    reply_method = update.message.reply_text if hasattr(update, 'message') and update.message else update.callback_query.edit_message_text
    await reply_method(
        text=summary,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ORDER_CONFIRMATION

async def execute_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()
    user_data = session.user_data

    if not user_data or not is_subscription_active(user_data) or not session.is_logged_in or user_data.get("brokerage_type") != "mofid":
        await query.edit_message_text(f"{EMOJI['error']} دسترسی غیرمجاز یا عدم ورود به مفید.")
        return await start(update, context)

    if query.data == "confirm_no_cancel_order_completely":
        return await confirm_no_cancel_order_completely(update, context)
    
    is_limited, limit_message = check_order_submission_rate_limit(session.user_id)
    if is_limited:
        await query.edit_message_text(limit_message)
        return ORDER_CONFIRMATION

    order = session.order_details
    
    loading_text = f"{EMOJI['loading']} در حال آماده سازی برای ارسال سفارش به مفید..."
    if order.get('scheduled_time_str_for_module') and order['send_method'] != "فوری":
        loading_text = (
            f"{EMOJI['clock']} سفارش برای نماد *{order['stock']}* در زمان *{order['scheduled_time_str_for_module']}* تنظیم شد.\n"
            f"ربات تا آن زمان منتظر مانده و سپس اقدام به ارسال سفارش خواهد کرد."
        )
    
    # Keep the message ID of the "loading" message to delete it later.
    loading_message_id_to_delete = None
    try:
        # Attempt to edit the message that triggered this handler (e.g., the confirmation message)
        await query.edit_message_text(text=loading_text, parse_mode="Markdown")
        loading_message_id_to_delete = query.message.message_id
    except BadRequest as e:
        logger.warning(f"Could not edit original message to loading text: {e}. Sending new loading message.")
        # If editing fails (e.g., message too old), send a new one.
        new_loading_msg = await context.bot.send_message(chat_id=session.user_id, text=loading_text, parse_mode="Markdown")
        loading_message_id_to_delete = new_loading_msg.message_id


    result = await session.mofid_place_order(
        stock_name=order['stock'],
        action=order['action'],
        quantity=order['quantity'],
        price_option=order['price_choice'],
        custom_price=order.get('custom_price'),
        send_option=order['send_method'],
        scheduled_time_str=order.get('scheduled_time_str_for_module')
    )
    
    session.update_activity()
    logger.info(f"Reset inactivity timer for user {session.user_id} after executing order at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}.")

    record_order_submission(session.user_id)

    send_method_for_summary = order.get('send_method', 'نامشخص')
    scheduled_time_for_summary = order.get('scheduled_time_str_for_module', None)

    if order.get("stock") in session.active_orders:
        session.active_orders.remove(order["stock"])
    session.order_details.pop("scheduled_time_str_for_module", None)
    logger.info(f"Cleared scheduled order details for user {session.user_id} after execution.")

    session.first_successful_order_time = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    # processed_submission_logs = result.get("submission_logs", []) # Raw logs if needed for other purposes

    summary_text = f"""
{EMOJI['done']} *خلاصه نهایی سفارشات* {EMOJI['done']}

📊 *نماد:* {order['stock']} 
🔹 *نوع:* {order['action']}
🏷️ *قیمت:* {order['price_value']} 
� *تعداد:* {order['quantity']:,}
⏱ *روش ارسال:* {send_method_for_summary}
"""
    if scheduled_time_for_summary:
        summary_text += f"🕒 *زمان برنامه‌ریزی شده:* {scheduled_time_for_summary}\n"
    
    summary_text += f"✅ *زمان تقریبی پردازش/شروع ارسال:* {session.first_successful_order_time}\n"

    # Updated order status messages
    if result["success"]:
        session.add_log(f"سفارش مفید با موفقیت پردازش شد: {result.get('message', 'موفق')}", "success")
        summary_text += f"\n{EMOJI['success']} *وضعیت سفارش:* سفارشات بصورت کامل ارسال شدند."
    else:
        session.add_log(f"خطا در ارسال سفارش مفید: {result.get('message', 'ناموفق')}", "error")
        summary_text += f"\n{EMOJI['error']} *وضعیت سفارش:* خطا در ارسال سفارشات."
        # Optionally include more details from result if available and safe to show
        # error_detail = result.get('message', 'جزئیات بیشتر در لاگ‌های سرور موجود است.')
        # summary_text += f" ({error_detail})"


    summary_text += f"\n\n{EMOJI['warning']} *توجه بسیار مهم:* لطفاً حتماً و فوراً به حساب کاربری خود در سامانه کارگزاری مفید مراجعه کرده و از ثبت صحیح، تعداد نهایی و وضعیت سفارش(های) خود اطمینان کامل حاصل کنید. مسئولیت نهایی سفارشات با شماست. {EMOJI['warning']}"

    actual_click_count = result.get("click_count", 0)
    if actual_click_count > 0 :
        summary_text += f"\n📜 *تعداد کل سفارشات ارسالی در بازه زمانی ارسال (کلیک‌های متوالی):* {actual_click_count}"

    # session.order_details["execution_details"] = [summary_text] # Storing summary if needed for other logic

    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['details']} دریافت تاریخچه سفارشات (اکسل)", callback_data="reshow_details")],
        [InlineKeyboardButton(f"{EMOJI['new_order']} شروع سفارش جدید", callback_data="post_order_new_order_mofid")],
        [InlineKeyboardButton(f"{EMOJI['logout']} خروج از حساب کارگزاری", callback_data="post_order_logout_mofid")],
    ]
    
    # Delete the "loading" message before sending the final summary.
    if loading_message_id_to_delete:
        try:
            await context.bot.delete_message(chat_id=session.user_id, message_id=loading_message_id_to_delete)
        except BadRequest as e:
            logger.warning(f"Could not delete loading message (ID: {loading_message_id_to_delete}): {e}")

    # Send the final summary as a new message. This ensures it's always sent.
    await context.bot.send_message(
        chat_id=session.user_id,
        text=f"{summary_text}\n\nبرای ادامه یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    
    # Automatic message cleanup is disabled.
    # asyncio.create_task(schedule_order_detail_cleanup(context, session, session.user_id))

    return POST_ORDER_CHOICE
async def confirm_no_cancel_order_completely(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()
    if session.order_details.get("stock") in session.active_orders:
        session.active_orders.remove(session.order_details["stock"])
    session.order_details = {}  # This clears scheduled_time_str_for_module
    session.first_successful_order_time = None
    session.order_detail_message_ids = []
    await query.edit_message_text(f"{EMOJI['info']} سفارش   لغو شد. بازگشت به منوی اصلی.")
    session.update_activity()  # Add this to reset inactivity timer on cancellation
    return await start(update, context)


async def back_to_quantity_from_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()
    if "quantity" in session.order_details: del session.order_details["quantity"]
    # This will re-ask for quantity
    return await ask_for_quantity(update, context)


async def _send_paginated_details(context: ContextTypes.DEFAULT_TYPE, session: MofidBrokerSession, chat_id: int, logs: List[str]):
    """Send execution details with pagination, preserving exact log format from submission_logs."""
    for i, log in enumerate(logs, 1):
        # Log is already in the format "YYYY-MM-DD HH:MM:SS.sss: message" from submission_logs
        formatted_log = log.strip()
        message_text = f"{EMOJI['details']} *جزئیات اجرا ({i}/{len(logs)})*\n`{formatted_log}`"
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode="Markdown"
        )
        session.order_detail_message_ids.append(msg.message_id)
        await asyncio.sleep(0.3)  # Delay to avoid rate limits
async def handle_view_details(update: Update, context: ContextTypes.DEFAULT_TYPE, reshow: bool = False) -> int:
    """
    Handles user choice for viewing details.
    The primary mechanism for "viewing details" is now the Excel file sent by `reshow_order_details`.
    Paginated log display and automatic cleanup are removed.
    This function mainly ensures the user is active and presents options.
    """
    query = update.callback_query
    await query.answer()

    session = context.user_data["session"]
    session.update_activity()
    user_data = session.user_data

    if not user_data or not is_subscription_active(user_data):
        await query.edit_message_text(
            f"{EMOJI['error']} شما اجازه دسترسی به این بخش را ندارید. لطفا ابتدا ثبت‌نام کرده و یا اشتراک خود را تمدید کنید."
        )
        return await start(update, context)

    # If the callback is "reshow_details", it's handled by the `reshow_order_details` function directly.
    # This function, if reached through a different path or as a state fallback,
    # will just ensure options are presented.
    if query.data == "reshow_details":
        logger.info(f"handle_view_details called with reshow_details, deferring to reshow_order_details logic.")
        return await reshow_order_details(update, context)

    # Present options if this state is reached.
    post_order_keyboard = [
        [InlineKeyboardButton(f"{EMOJI['details']} دریافت تاریخچه سفارشات (اکسل)", callback_data="reshow_details")],
        [InlineKeyboardButton(f"{EMOJI['new_order']} شروع سفارش جدید", callback_data="post_order_new_order_mofid")],
        [InlineKeyboardButton(f"{EMOJI['logout']} خروج از حساب کارگزاری", callback_data="post_order_logout_mofid")],
    ]
    
    message_text_to_edit = query.message.text
    # If the current message is not the final summary, provide a generic prompt.
    # This check might need to be more robust depending on possible message texts.
    if "خلاصه نهایی سفارش" not in message_text_to_edit :
         message_text_to_edit = f"{EMOJI['info']} لطفاً گزینه بعدی خود را انتخاب کنید:"

    try:
        await query.edit_message_text(
            text=message_text_to_edit,
            reply_markup=InlineKeyboardMarkup(post_order_keyboard),
            parse_mode="Markdown"
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning(f"Could not edit message in handle_view_details: {e}. Sending new options message.")
            await context.bot.send_message(
                chat_id=session.user_id,
                text=f"{EMOJI['info']} لطفاً گزینه بعدی خود را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(post_order_keyboard)
            )

    logger.info("Paginated log display and automatic message cleanup are removed from handle_view_details.")
    return POST_ORDER_CHOICE



async def reshow_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the 'دریافت تاریخچه سفارشات (اکسل)' button by fetching and sending the order history Excel."""
    query = update.callback_query
    await query.answer()

    session = context.user_data["session"]
    session.update_activity()
    user_data = session.user_data

    if not user_data or not is_subscription_active(user_data):
        await context.bot.send_message(
            chat_id=session.user_id,
            text=f"{EMOJI['error']} شما اجازه دسترسی به این بخش را ندارید. "
            f"لطفا ابتدا ثبت‌نام کرده و یا اشتراک خود را تمدید کنید."
        )
        try: # Attempt to edit the original message as well, if possible
            await query.edit_message_text(
                f"{EMOJI['error']} شما اجازه دسترسی به این بخش را ندارید. "
                f"لطفا ابتدا ثبت‌نام کرده و یا اشتراک خود را تمدید کنید."
            )
        except BadRequest: pass # If edit fails, new message is already sent
        return await start(update, context)

    if not session.is_logged_in:
        await context.bot.send_message(
            chat_id=session.user_id,
            text=f"{EMOJI['error']} شما وارد حساب کارگزاری مفید نشده‌اید. لطفاً ابتدا با دستور /start وارد شوید."
        )
        try: # Attempt to edit the original message
            await query.edit_message_text(
                f"{EMOJI['error']} شما وارد حساب کارگزاری مفید نشده‌اید. لطفاً ابتدا با دستور /start وارد شوید."
            )
        except BadRequest: pass
        return await start(update, context)

    # Message cleanup is disabled, so no need to clear session.order_detail_message_ids here.

    stock_name = session.order_details.get("stock")
    order_action_persian = session.order_details.get("action")

    if not stock_name or not order_action_persian:
        err_msg_no_details = f"{EMOJI['error']} اطلاعات سفارش (نماد یا نوع معامله) برای دریافت تاریخچه یافت نشد."
        await context.bot.send_message(chat_id=session.user_id, text=err_msg_no_details)
        session.add_log(err_msg_no_details, "error")
        
        post_order_keyboard_err = [
            [InlineKeyboardButton(f"{EMOJI['new_order']} شروع سفارش جدید", callback_data="post_order_new_order_mofid")],
            [InlineKeyboardButton(f"{EMOJI['logout']} خروج از حساب کارگزاری", callback_data="post_order_logout_mofid")],
        ]
        await context.bot.send_message(
            chat_id=session.user_id,
            text="لطفا یک گزینه را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(post_order_keyboard_err)
        )
        return POST_ORDER_CHOICE

    loading_msg_text = f"{EMOJI['loading']} در حال آماده‌سازی و دریافت تاریخچه سفارشات برای نماد **'{stock_name}'** ({order_action_persian}) از کارگزاری مفید...\nاین عملیات ممکن است چند لحظه طول بکشد."
    
    # Send loading message as a new message to avoid issues with editing old/complex messages
    status_msg = await context.bot.send_message(chat_id=session.user_id, text=loading_msg_text, parse_mode="Markdown")
    
    downloaded_excel_path = None
    try:
        loop = asyncio.get_event_loop()
        downloaded_excel_path = await loop.run_in_executor(
            None,
            session.bot.get_order_history_excel,
            stock_name,
            order_action_persian
        )

        if downloaded_excel_path and os.path.exists(downloaded_excel_path):
            session.add_log(f"فایل تاریخچه سفارشات '{os.path.basename(downloaded_excel_path)}' با موفقیت در سرور دریافت شد.", "success")
            file_name_for_user = f"Mofid_OrderHistory_{stock_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            # Updated caption for the Excel file
            excel_caption = (
                f"{EMOJI['details']} فایل تاریخچه سفارشات کارگزاری مفید برای نماد **{stock_name}** (عملیات: {order_action_persian}).\n"
                f"این فایل، تاریخچه سفارشات شما را از سامانه کارگزاری نمایش می‌دهد و حاوی جزئیات ۱۰ تلاش آخر برای ارسال سفارشات پیاپی برای نماد مربوطه می‌باشد. "
                f"لطفاً محتوای آن را برای اطمینان از صحت و کامل بودن اطلاعات بررسی نمایید."
            )

            try:
                with open(downloaded_excel_path, 'rb') as excel_file:
                    await context.bot.send_document(
                        chat_id=session.user_id,
                        document=InputFile(excel_file, filename=file_name_for_user),
                        caption=excel_caption,
                        parse_mode="Markdown"
                    )
                session.add_log(f"فایل اکسل تاریخچه سفارشات ({file_name_for_user}) با موفقیت برای کاربر ارسال شد.", "success")
                # Edit the status_msg (loading message) to success
                await context.bot.edit_message_text(
                    chat_id=session.user_id,
                    message_id=status_msg.message_id,
                    text=f"{EMOJI['success']} فایل تاریخچه سفارشات با موفقیت ارسال شد."
                )
            except Exception as send_err:
                logger.error(f"Error sending Excel document to user {session.user_id}: {send_err}")
                session.add_log(f"خطا در ارسال فایل اکسل به کاربر: {send_err}", "error")
                await context.bot.edit_message_text(
                    chat_id=session.user_id,
                    message_id=status_msg.message_id,
                    text=f"{EMOJI['error']} خطا در ارسال فایل تاریخچه سفارشات به شما. {send_err}"
                )
            finally:
                try:
                    os.remove(downloaded_excel_path)
                    logger.info(f"Temporary Excel file {downloaded_excel_path} deleted.")
                    session.add_log(f"فایل اکسل موقت از سرور حذف شد: {os.path.basename(downloaded_excel_path)}", "info")
                except OSError as e:
                    logger.error(f"Error deleting temporary Excel file {downloaded_excel_path}: {e}")
                    session.add_log(f"خطا در حذف فایل اکسل موقت از سرور: {e}", "error")
        else:
            msg_fail = f"{EMOJI['error']} دریافت گزارش تاریخچه سفارشات برای نماد '{stock_name}' ناموفق بود. لطفاً مطمئن شوید نماد و نوع سفارش صحیح است و مجدداً تلاش کنید یا لاگ‌های سرور را بررسی نمایید."
            await context.bot.edit_message_text(chat_id=session.user_id, message_id=status_msg.message_id, text=msg_fail)
            session.add_log(msg_fail, "error")

    except Exception as e:
        logger.error(f"Critical error in reshow_order_details (fetching/sending Excel) for user {session.user_id}: {e}", exc_info=True)
        detailed_error_msg = f"{EMOJI['error']} یک خطای پیش‌بینی نشده در هنگام پردازش درخواست تاریخچه سفارشات رخ داد. لطفاً دقایقی دیگر مجددا تلاش کنید."
        try:
            await context.bot.edit_message_text(chat_id=session.user_id, message_id=status_msg.message_id, text=detailed_error_msg)
        except BadRequest: # If editing status_msg fails, send a new error message
            await context.bot.send_message(chat_id=session.user_id, text=detailed_error_msg)
        session.add_log(f"خطای بحرانی و غیرمنتظره در reshow_order_details: {str(e)}", "critical")

    # Send the final warning message
    final_warning = f"""
{EMOJI['alert']} *توجه بسیار مهم*
لطفاً به حساب کاربری خود در کارگزاری مراجعه کنید و از ثبت صحیح سفارش و تعداد آن اطمینان حاصل نمایید. ممکن است به دلیل سرعت بالای ارسال، چندین سفارش در هسته معاملاتی ثبت شده باشد. مسئولیت نهایی سفارشات با شماست.
"""
    await context.bot.send_message(
        chat_id=session.user_id,
        text=final_warning,
        parse_mode="Markdown"
    )

    post_order_keyboard = [
        [InlineKeyboardButton(f"{EMOJI['details']} دریافت مجدد تاریخچه (اکسل)", callback_data="reshow_details")],
        [InlineKeyboardButton(f"{EMOJI['new_order']} شروع سفارش جدید", callback_data="post_order_new_order_mofid")],
        [InlineKeyboardButton(f"{EMOJI['logout']} خروج از حساب کارگزاری", callback_data="post_order_logout_mofid")],
    ]
    
    # Send a new message for options, ensuring it's always visible after the process.
    await context.bot.send_message(
        chat_id=session.user_id,
        text=f"{EMOJI['info']} لطفاً گزینه بعدی خود را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(post_order_keyboard)
    )
    
    # Automatic message cleanup is disabled.
    # asyncio.create_task(schedule_order_detail_cleanup(context, session, session.user_id))

    return POST_ORDER_CHOICE
�

async def handle_post_order_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()

    try: await query.edit_message_reply_markup(reply_markup=None)
    except Exception: pass

    if query.data == "post_order_new_order_mofid":
        # Mofid module doesn't specify closing forms, assume it's handled or not needed.
        session.order_details = {}
        session.first_successful_order_time = None
        session.order_detail_message_ids = []

        if not session.is_logged_in:
            await query.message.reply_text(f"{EMOJI['error']} شما وارد حساب کارگزاری مفید نشده‌اید. لطفاً ابتدا وارد شوید.")
            return await start_trading_mofid(update, context) # Back to Mofid trading start

        await query.message.reply_text(
            f"{EMOJI['trade']} لطفا نماد سهام جدید را برای مفید وارد کنید (مثال: وبملت):"
        )
        return STOCK_SELECTION

    elif query.data in ["post_order_logout_mofid", "logout_and_main_menu_mofid"]:
        if session.inactivity_timeout_task:
            session.inactivity_timeout_task.cancel()
        session.safe_quit() # Calls MofidBrokerSession's safe_quit
        session.is_logged_in = False
        session.credentials = {}
        session.order_details = {}
        session.order_detail_message_ids = []  # Clear message IDs
        session.active_orders.clear()  # Clear active orders
        await query.message.reply_text(f"{EMOJI['logout']} شما با موفقیت از حساب کارگزاری مفید خارج شدید. \n برای شروع مجدد روی /start کلیک کنید.")
        return await start(update, context) # To main menu
    return POST_ORDER_CHOICE


async def back_to_main_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    # Potentially clean up session's selenium driver if any action implies full stop
    # session = context.user_data.get("session")
    # if session and session.is_logged_in:
    #     # Decide if navigating to main menu should also log out of selenium
    #     # For now, let start() handle session cleanup if needed
    return await start(update, context)


async def restart_full_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data.get("session")
    if session:
        session.safe_quit()
        del context.user_data["session"] 
    await query.edit_message_text("در حال شروع مجدد ربات مفید...")
    return await start(update, context)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update for Mofid Bot:", exc_info=context.error)
    if update and update.effective_chat:
        try:
            await update.effective_chat.send_message(
                f"{EMOJI['error']} یک خطای پیش‌بینی نشده رخ داد. لطفا دقایقی دیگر مجددا تلاش کنید (/start) یا با پشتیبانی تماس بگیرید."
            )
        except Exception as e:
            logger.error(f"Error sending error message to user: {e}")
    # Optionally, perform more detailed error handling or session cleanup
    # session = context.user_data.get("session")
    # if session:
    #     session.safe_quit() # Example cleanup
    # return ConversationHandler.END # Or a specific error state
async def cancel_registration_mofid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data.get("session")
    if session:
        session.user_data = {}
    await query.edit_message_text(f"{EMOJI['info']} ثبت‌نام لغو شد. برای شروع مجدد از /start استفاده کنید.")
    return ConversationHandler.END

async def back_to_symbol_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data.get("session")
    if session and "order_details" in session.__dict__:
        session.order_details.pop("symbol", None)  # Clear previous symbol
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['logout']} خروج از حساب کاربری", callback_data="logout_and_main_menu_mofid")],
    ]
    await query.message.reply_text(
        f"{EMOJI['trade']} لطفا نماد مورد نظر خود را وارد کنید (مثال: وبملت)",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return STOCK_SELECTION
async def force_register_mofid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles when a user registered for another broker wants to register for Mofid."""
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()
    session.user_data = { 
        "telegram_id": session.user_id,
        "telegram_name": update.effective_user.full_name,
        "registration_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "brokerage_type": "mofid" # Pre-set for Mofid registration
    }
    await query.edit_message_text(f"{EMOJI['register']} ثبت نام جدید برای کارگزاری مفید.\nلطفا نام و نام خانوادگی خود را(به زبان فارسی) وارد کنید:")
    return REGISTER_FULL_NAME
async def register_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()
    session.user_data = {
        "telegram_id": session.user_id,
        "telegram_name": update.effective_user.full_name,
        "registration_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "brokerage_type": "mofid"
    }
    await query.edit_message_text(f"{EMOJI['register']} لطفا نام و نام خانوادگی خود را (به زبان فارسی) وارد کنید:")
    logger.info(f"User {session.user_id} prompted to enter full name for registration")
    return REGISTER_FULL_NAME


async def show_subscription_guide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = context.user_data["session"]
    session.update_activity()
    user_data = session.user_data

    # فرم اطلاعات کاربری
    user_info_form = f"""
{EMOJI['info']} *فرم اطلاعات کاربری جهت تمدید اشتراک سرتریدر بات*

```
🆔 شناسه تلگرام: {session.user_id}
👤 نام و نام خانوادگی: {user_data.get('full_name', 'نامشخص')}
🏦 کارگزاری: {user_data.get('brokerage_type', 'مفید')}
```

لطفاً با لمس فرم بالا، اطلاعات را کپی کرده و همراه با فیش واریزی به پشتیبانی ارسال کنید.
"""
    success = await send_message_with_retry(
        context.bot,
        chat_id=session.user_id,
        text=user_info_form,
        parse_mode="Markdown"
    )
    if success:
        session.add_log("پیام فرم اطلاعات کاربری برای کاربر منقضی‌شده ارسال شد", "info")
    else:
        session.add_log("خطا در ارسال فرم اطلاعات کاربری", "error")

    await asyncio.sleep(0.5)

    # راهنمای خرید توکن
    token_purchase_info = f"""
{EMOJI['money']} *راهنمای خرید توکن و تمدید اشتراک سرتریدر بات*

🔸 *توکن روزانه:* ۲۰۰,۰۰۰ تومان  
🔸 *توکن هفتگی:* ۳۰۰,۰۰۰ تومان  
🔸 *توکن ماهانه:* ۸۰۰,۰۰۰ تومان  

📌 *شماره کارت جهت واریز:*  
`6219861939396965`  
*بانک سامان - به نام محمد امین مقدسی*  
(با لمس شماره کارت، به‌صورت خودکار کپی می‌شود)

📸 *دستورالعمل:*  
لطفاً تصویر فیش واریزی متناسب با توکن درخواستی را به همراه فرم اطلاعات کاربری (ارسال‌شده در پیام قبلی) به پشتیبانی ارسال کنید. توکن شما در کمتر از ۱۰ دقیقه صادر خواهد شد .
با کلیک روی /start مجدد شروع کنید.
🙏 *با سپاس، تیم پشتیبانی سرتریدر بات*
"""
    success = await send_message_with_retry(
        context.bot,
        chat_id=session.user_id,
        text=token_purchase_info,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    if success:
        session.add_log("پیام راهنمای خرید توکن برای کاربر منقضی‌شده ارسال شد", "info")
    else:
        session.add_log("خطا در ارسال راهنمای خرید توکن", "error")

    # آماده‌سازی منوی گزینه‌های حساب منقضی‌شده
    welcome_text = f"{EMOJI['warning']} حساب شما برای ربات مفید منقضی شده است."
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['token']} وارد کردن توکن جدید", callback_data="enter_new_token_expired")],
        [InlineKeyboardButton(f"{EMOJI['tutorial']} آموزش تهیه اشتراک بات", callback_data="show_subscription_guide")],
        [InlineKeyboardButton("📩 پیام به پشتیبانی جهت تهیه توکن", url="https://t.me/SarTraderBot_Support")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # بررسی پیام فعلی برای جلوگیری از خطای "Message is not modified"
    try:
        current_message = query.message
        current_text = current_message.text
        current_reply_markup = current_message.reply_markup

        # اگر متن و کیبورد فعلی با جدید یکسان باشند، از ویرایش صرف‌نظر می‌کنیم
        if current_text == welcome_text and current_reply_markup == reply_markup:
            session.add_log("پیام فعلی نیازی به ویرایش ندارد", "info")
        else:
            await query.edit_message_text(
                text=welcome_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            session.add_log("منوی گزینه‌های حساب منقضی‌شده ویرایش شد", "info")
    except BadRequest as e:
        if "Message is not modified" in str(e):
            session.add_log("پیام فعلی نیازی به ویرایش ندارد (خطای BadRequest)", "info")
        else:
            session.add_log(f"خطا در ویرایش پیام: {str(e)}", "error")
            # در صورت خطای دیگر، پیام را به‌صورت جدید ارسال می‌کنیم
            await context.bot.send_message(
                chat_id=session.user_id,
                text=welcome_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            session.add_log("منوی گزینه‌های حساب منقضی‌شده به‌صورت پیام جدید ارسال شد", "info")
    except Exception as e:
        session.add_log(f"خطای غیرمنتظره در ویرایش پیام: {str(e)}", "error")
        # در صورت خطای غیرمنتظره، پیام را به‌صورت جدید ارسال می‌کنیم
        await context.bot.send_message(
            chat_id=session.user_id,
            text=welcome_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        session.add_log("منوی گزینه‌های حساب منقضی‌شده به‌صورت پیام جدید ارسال شد", "info")

    return EXPIRED_ACCOUNT_OPTIONS




def main() -> None:
    bot_token = os.environ.get("MOFID_BOT_TOKEN")
    if not bot_token:
        logger.critical("MOFID_BOT_TOKEN not found in .env file. Exiting.")
        return

    application = Application.builder().token(bot_token).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(show_tutorial_mofid, pattern="menu_tutorial_mofid"), # تغییر پترن
                CallbackQueryHandler(start_trading_mofid, pattern="menu_start_mofid"),
                CallbackQueryHandler(show_admin_contact_mofid, pattern="^menu_admin_mofid$"), # اگر این هم مشکل دارد، ^ و $ را بردارید
                CallbackQueryHandler(restart_full_process, pattern="^restart_full_process$"),
                CallbackQueryHandler(force_register_mofid, pattern="^force_register_mofid$"),
            ],
            REGISTER_PROMPT: [CallbackQueryHandler(register_prompt, pattern="^register_yes_mofid$")],
            REGISTER_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_full_name)],
            REGISTER_BROKERAGE_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_brokerage_username)],
            REGISTER_HAS_TOKEN: [
                CallbackQueryHandler(has_token, pattern="^has_token_"),
                CallbackQueryHandler(retry_token_input_mofid, pattern="^retry_token_input_mofid$"),
                CallbackQueryHandler(cancel_registration_mofid, pattern="^cancel_registration_mofid$")
            ],
            REGISTER_TOKEN_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_token_input)],
            EXPIRED_ACCOUNT_OPTIONS: [
                CallbackQueryHandler(handle_expired_account_options, pattern="^enter_new_token_expired$"),
                CallbackQueryHandler(show_subscription_guide, pattern="^show_subscription_guide$"),
                CallbackQueryHandler(handle_expired_account_options, pattern=".*"),
            ],
            LOGIN_ENTER_NEW_TOKEN_FOR_EXPIRED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_token_for_expired),
                CallbackQueryHandler(handle_expired_account_options, pattern="^enter_new_token_expired$"),
            ],
            AWAITING_NEW_BROKERAGE_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_brokerage_username)
            ],
            LOGIN_CONFIRM_DETAILS: [
                CallbackQueryHandler(change_brokerage_username, pattern="^change_brokerage_username$"),
                CallbackQueryHandler(retry_mofid_login_prompt, pattern="^retry_mofid_login_prompt$"),
                CallbackQueryHandler(back_to_main_action, pattern="^back_to_main_action$"),
                CallbackQueryHandler(confirm_login_details, pattern="^confirm_login_details_"),
            ],
            LOGIN_ENTER_BROKERAGE_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_brokerage_password)],
            STOCK_SELECTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_stock_symbol),
                CallbackQueryHandler(change_stock_symbol_mofid, pattern="^change_stock_symbol_mofid$"),
                CallbackQueryHandler(handle_post_order_choice, pattern="^logout_and_main_menu_mofid$"),
                CallbackQueryHandler(back_to_symbol_selection, pattern="^back_to_symbol_selection$"),
            ],
            ORDER_ACTION: [
                CallbackQueryHandler(get_order_action, pattern="^action_(buy|sell)$"),
                CallbackQueryHandler(back_to_symbol_selection, pattern="^back_to_symbol_selection$"),
                CallbackQueryHandler(handle_post_order_choice, pattern="^logout_and_main_menu_mofid$"),
            ],
            ORDER_PRICE_TYPE: [
                CallbackQueryHandler(get_price_type, pattern="^price_(high|low|custom)$"),
                CallbackQueryHandler(get_order_action, pattern="^back_to_action_selection$"),
                CallbackQueryHandler(back_to_price_type, pattern="^back_to_price_type$"),
            ],
            ORDER_CUSTOM_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_custom_price)],
            ORDER_SEND_METHOD: [
                CallbackQueryHandler(get_send_method, pattern="^send_(immediate|scheduled|serkhati_mofid)$"),
                CallbackQueryHandler(back_to_price_type, pattern="^back_to_price_type$"),
                CallbackQueryHandler(get_send_method, pattern="^back_to_send_method$"),
                CallbackQueryHandler(back_to_send_method_from_quantity, pattern="^back_to_send_method_from_quantity$"),
            ],
            ORDER_SCHEDULE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_schedule_time)],
            ORDER_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_order_quantity),
                CallbackQueryHandler(back_to_send_method_from_quantity, pattern="^back_to_send_method_from_quantity$"),
            ],
            ORDER_CONFIRMATION: [
                CallbackQueryHandler(execute_order, pattern="^confirm_yes_mofid$"),
                CallbackQueryHandler(confirm_no_cancel_order_completely, pattern="^confirm_no_cancel_order_completely$"),
                CallbackQueryHandler(handle_post_order_choice, pattern="^post_order_(new_order_mofid|logout_mofid)$"),
                CallbackQueryHandler(back_to_quantity_from_confirm, pattern="^back_to_quantity_from_confirm$"),
            ],
            VIEW_DETAILS: [],
            POST_ORDER_CHOICE: [
                CallbackQueryHandler(handle_post_order_choice, pattern="^post_order_"),
                CallbackQueryHandler(reshow_order_details, pattern="^reshow_details$") 
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(back_to_main_action, pattern="^back_to_main_action$"),
        ],
    )
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    logger.info("Mofid Telegram Bot started successfully.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
