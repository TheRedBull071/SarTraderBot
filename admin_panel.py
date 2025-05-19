from datetime import timedelta, datetime, time as datetime_time
from time import sleep
import streamlit as st
import json
import os
import uuid
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

import mysql.connector
from mysql.connector import Error

# --- Configuration ---
ADMIN_PASSWORD = "0000"  # Change this in a production environment!

# MySQL Database Configuration
DB_CONFIG = {
    "host": os.environ.get("MYSQLHOST"),
    "port": int(os.environ.get("MYSQLPORT", 3306)),
    "user": os.environ.get("MYSQLUSER"),
    "password": os.environ.get("MYSQLPASSWORD"),
    "database": os.environ.get("MYSQLDATABASE")
}
def get_db_connection():
    """Establishes a connection to the MySQL database."""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        st.error(f"Error connecting to MySQL database: {e}")
        return None
    return None

# فرض بر این است که سایر وارد کردن‌ها و تنظیمات اولیه فایل شما در اینجا وجود دارد
# import ها و DB_CONFIG و get_db_connection و سایر توابع بدون تغییر باقی می‌مانند

def load_users_data():
    """Loads user, token, and activity log data from the MySQL database."""
    data = {"users": [], "tokens": [], "activity_log": {}}
    connection = get_db_connection()
    if not connection:
        return data
    
    try:
        cursor = connection.cursor(dictionary=True)
        
        # Load users (این بخش بدون تغییر است)
        cursor.execute("""
            SELECT telegram_id, telegram_name, registration_date, brokerage_type,
                   full_name, brokerage_username, subscription_type, token,
                   expiry_date, brokerage_password, real_name, national_id,
                   phone_number, email
            FROM users
        """)
        users = cursor.fetchall()
        data["users"] = [
            {
                "telegram_id": str(u["telegram_id"]),
                "telegram_name": u["telegram_name"],
                "registration_date": u["registration_date"].strftime("%Y-%m-%d %H:%M:%S") if u["registration_date"] else None,
                "brokerage_type": u["brokerage_type"],
                "full_name": u["full_name"],
                "brokerage_username": u["brokerage_username"],
                "subscription_type": u["subscription_type"],
                "token": u["token"],
                "expiry_date": u["expiry_date"].strftime("%Y-%m-%d %H:%M:%S") if u["expiry_date"] else None,
                "brokerage_password": u["brokerage_password"],
                "real_name": u["real_name"],
                "national_id": u["national_id"],
                "phone_number": u["phone_number"],
                "email": u["email"]
            } for u in users
        ]
        
        # Load tokens (این بخش بدون تغییر است، با فرض اینکه مشکلات قبلی حل شده)
        cursor.execute("""
            SELECT token, telegram_id, brokerage_username, subscription_type,
                   expiry_date, is_used, used_by_telegram_id, used_at
            FROM tokens
        """)
        tokens_from_db = cursor.fetchall()
        data["tokens"] = [
            {
                "token": t["token"],
                "telegram_id": str(t["telegram_id"]) if t["telegram_id"] else None,
                "brokerage_username": t["brokerage_username"],
                "subscription_type": t["subscription_type"],
                "expiry_date": t["expiry_date"].strftime("%Y-%m-%d %H:%M:%S") if t["expiry_date"] else None,
                "is_used": t["is_used"],
                "used_by_telegram_id": str(t["used_by_telegram_id"]) if t.get("used_by_telegram_id") else None,
                "used_at": t["used_at"].strftime("%Y-%m-%d %H:%M:%S") if t.get("used_at") else None
            } for t in tokens_from_db
        ]
        
        # Load activity log
        # تغییر: ستون 'timestamp' از کوئری SELECT حذف شد (و همچنین action از پاسخ قبلی)
        cursor.execute("SELECT telegram_id FROM activity_log") # فقط telegram_id را می‌خوانیم اگر timestamp هم نباشد
        logs = cursor.fetchall()
        data["activity_log"] = {}
        for log_entry in logs:
            # تغییر: کلید 'timestamp' از دیکشنری حذف شد (و همچنین action)
            # اگر ستون action وجود دارد و میخواهید نگه دارید، آن را باقی بگذارید
            data["activity_log"][str(log_entry["telegram_id"])] = {
                # "action": log_entry.get("action"), # اگر ستون action در دیتابیس شما وجود دارد
                # "timestamp": log_entry.get("timestamp").strftime("%Y-%m-%d %H:%M:%S") if log_entry.get("timestamp") else None # این خط حذف یا کامنت شد
            }
            # اگر میخواهید یک مقدار پیشفرض برای timestamp بگذارید (مثلا None)
            # data["activity_log"][str(log_entry["telegram_id"])]["timestamp"] = None
        
    except Error as e:
        st.error(f"Error loading data from database: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
    
    return data

def save_users_data(data):
    """Saves user, token, and activity log data to the MySQL database."""
    connection = get_db_connection()
    if not connection:
        return
    
    try:
        cursor = connection.cursor()
        
        # Clear existing data
        cursor.execute("DELETE FROM users") 
        cursor.execute("DELETE FROM tokens")
        cursor.execute("DELETE FROM activity_log")
        
        # Save users
        for user in data.get("users", []):
            cursor.execute("""
                INSERT INTO users (telegram_id, telegram_name, registration_date, brokerage_type,
                                  full_name, brokerage_username, subscription_type, token,
                                  expiry_date, brokerage_password, real_name, national_id,
                                  phone_number, email)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user.get("telegram_id"), user.get("telegram_name"), user.get("registration_date"),
                user.get("brokerage_type"), user.get("full_name"), user.get("brokerage_username"),
                user.get("subscription_type"), user.get("token"), user.get("expiry_date"),
                user.get("brokerage_password"), user.get("real_name"), user.get("national_id"),
                user.get("phone_number"), user.get("email")
            ))
        
        # Save tokens (corrected)
        for token_item in data.get("tokens", []):
            cursor.execute("""
                INSERT INTO tokens (token, telegram_id, brokerage_username, subscription_type,
                                   expiry_date, is_used, used_by_telegram_id, used_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                token_item.get("token"),
                token_item.get("telegram_id"),
                token_item.get("brokerage_username"),
                token_item.get("subscription_type"),
                token_item.get("expiry_date"),
                token_item.get("is_used"),
                token_item.get("used_by_telegram_id"),
                token_item.get("used_at")
            ))
        
        # Save activity log
        for telegram_id, log_data in data.get("activity_log", {}).items():
            cursor.execute("""
                INSERT INTO activity_log (telegram_id)
                VALUES (%s)
            """, (telegram_id,))
        
        connection.commit()
    except Error as e:
        st.error(f"Error saving data to database: {e}")
        if connection:
            connection.rollback()
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


def generate_token_entry(telegram_id, subscription_type, expiry_date_str, brokerage_username):
    """
    Generates a token entry dictionary.
    Does NOT save it; saving is handled by the calling function.
    """
    new_token_val = str(uuid.uuid4())
    token_data = {
        "token": new_token_val,
        "telegram_id": telegram_id if telegram_id else None,
        "brokerage_username": brokerage_username.strip() if brokerage_username else None,
        "subscription_type": subscription_type,
        "expiry_date": expiry_date_str,
        "is_used": False,
        # MODIFICATION: Removed 'created_at' key-value pair
        # "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "used_by_telegram_id": None,
        "used_at": None
    }
    return token_data

# The rest of your admin_panel.py code (find_user_by_telegram_id, find_users_by_fields, Streamlit layout, etc.)
# remains unchanged by this specific fix. You would paste these modified functions
# back into your existing admin_panel.py file, replacing the original ones.


def find_user_by_telegram_id(telegram_id_to_find):
    """Finds a user by their Telegram ID."""
    connection = get_db_connection()
    if not connection:
        return None
    
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT telegram_id, telegram_name, registration_date, brokerage_type,
                   full_name, brokerage_username, subscription_type, token,
                   expiry_date, brokerage_password, real_name, national_id,
                   phone_number, email
            FROM users
            WHERE telegram_id = %s
        """, (str(telegram_id_to_find),))
        user = cursor.fetchone()
        
        if user:
            return {
                "telegram_id": str(user["telegram_id"]),
                "telegram_name": user["telegram_name"],
                "registration_date": user["registration_date"].strftime("%Y-%m-%d %H:%M:%S") if user["registration_date"] else None,
                "brokerage_type": user["brokerage_type"],
                "full_name": user["full_name"],
                "brokerage_username": user["brokerage_username"],
                "subscription_type": user["subscription_type"],
                "token": user["token"],
                "expiry_date": user["expiry_date"].strftime("%Y-%m-%d %H:%M:%S") if user["expiry_date"] else None,
                "brokerage_password": user["brokerage_password"],
                "real_name": user["real_name"],
                "national_id": user["national_id"],
                "phone_number": user["phone_number"],
                "email": user["email"]
            }
        return None
    except Error as e:
        st.error(f"Error finding user: {e}")
        return None
    finally:
        cursor.close()
        connection.close()
def find_users_by_fields(**kwargs):
    """Finds users matching multiple search criteria (case-insensitive)."""
    connection = get_db_connection()
    if not connection:
        return []
    
    try:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT telegram_id, telegram_name, registration_date, brokerage_type,
                   full_name, brokerage_username, subscription_type, token,
                   expiry_date, brokerage_password, real_name, national_id,
                   phone_number, email
            FROM users
        """
        params = []
        if kwargs:
            conditions = []
            for field, value in kwargs.items():
                if value:
                    conditions.append(f"LOWER({field}) LIKE %s")
                    params.append(f"%{str(value).lower()}%")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        cursor.execute(query, params)
        users = cursor.fetchall()
        
        return [
            {
                "telegram_id": str(u["telegram_id"]),
                "telegram_name": u["telegram_name"],
                "registration_date": u["registration_date"].strftime("%Y-%m-%d %H:%M:%S") if u["registration_date"] else None,
                "brokerage_type": u["brokerage_type"],
                "full_name": u["full_name"],
                "brokerage_username": u["brokerage_username"],
                "subscription_type": u["subscription_type"],
                "token": u["token"],
                "expiry_date": u["expiry_date"].strftime("%Y-%m-%d %H:%M:%S") if u["expiry_date"] else None,
                "brokerage_password": u["brokerage_password"],
                "real_name": u["real_name"],
                "national_id": u["national_id"],
                "phone_number": u["phone_number"],
                "email": u["email"]
            } for u in users
        ]
    except Error as e:
        st.error(f"Error searching users: {e}")
        return []
    finally:
        cursor.close()
        connection.close()

# --- Streamlit App Layout ---
st.set_page_config(page_title="پنل مدیریت ربات", layout="wide", page_icon="🤖")
st.markdown("""
    <style>
    body, .stApp {
        direction: rtl;
        text-align: right;
        font-family: 'Vazir', sans-serif;
    }
    .css-1v3fvcr, .css-18ni7ap, .stTextInput > div > input {
        direction: rtl !important;
        text-align: right !important;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("""<link href="https://cdn.jsdelivr.net/gh/rastikerdar/vazir-font@v30.1.0/dist/font-face.css" rel="stylesheet" type="text/css" />""", unsafe_allow_html=True)

# --- Admin Login ---
if 'admin_logged_in' not in st.session_state:
    st.session_state['admin_logged_in'] = False

if not st.session_state['admin_logged_in']:
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        with st.form("admin_login_form"):
            st.markdown("<h2 style='text-align: center;'>ورود ادمین</h2>", unsafe_allow_html=True)
            password_input = st.text_input("رمز عبور:", type="password", key="admin_pass")
            login_button = st.form_submit_button("ورود")
            if login_button:
                if password_input == ADMIN_PASSWORD:
                    st.session_state['admin_logged_in'] = True
                    st.rerun()
                else:
                    st.error("رمز عبور اشتباه است.")
else:
    st.sidebar.title("پنل مدیریت")
    if st.sidebar.button("خروج"):
        st.session_state['admin_logged_in'] = False
        st.session_state.pop('all_data', None)  # پاک کردن داده‌های کش‌شده
        st.rerun()

    # دکمه تازه‌سازی داده‌ها
    if st.sidebar.button("تازه‌سازی داده‌ها"):
        st.session_state.pop('all_data', None)  # پاک کردن داده‌های قبلی
        st.rerun()

    # بارگذاری داده‌ها
    if 'all_data' not in st.session_state:
        st.session_state['all_data'] = load_users_data()

    all_data = st.session_state['all_data']

    tab1, tab2, tab3, tab4 = st.tabs(["کاربران", "توکن‌ها", "تولید توکن", "تنظیمات و راهنما"])

    with tab1:
        st.subheader("📊 مدیریت کاربران")
        users_list = all_data.get("users", [])

        if not users_list:
            st.info("هیچ کاربری ثبت نشده است.")
        else:
            with st.expander("🔍 جستجو و فیلتر کاربران", expanded=False):
                search_telegram_id = st.text_input("ID تلگرام کاربر:")
                search_name = st.text_input("نام کاربر (یا بخشی از آن):")
                search_broker_user = st.text_input("نام کاربری کارگزاری:")
                
                filtered_users = users_list
                if search_telegram_id:
                    filtered_users = [u for u in filtered_users if str(u.get("telegram_id", "")) == search_telegram_id]
                if search_name:
                    filtered_users = [u for u in filtered_users if search_name.lower() in u.get("full_name", "").lower()]
                if search_broker_user:
                    filtered_users = [u for u in filtered_users if search_broker_user.lower() in u.get("brokerage_username", "").lower()]
                
                st.dataframe(pd.DataFrame(filtered_users), height=300, use_container_width=True)

            st.markdown("---")
            st.markdown("#### ویرایش کاربر")
            if filtered_users:
                user_ids_for_selection = [str(u.get("telegram_id", "ID نامشخص")) for u in filtered_users]
                if not user_ids_for_selection:
                    st.warning("ابتدا یک کاربر را از طریق جستجو انتخاب کنید.")
                else:
                    selected_user_id_str = st.selectbox(
                        "انتخاب کاربر برای ویرایش (بر اساس ID تلگرام):",
                        options=user_ids_for_selection,
                        key="edit_user_select"
                    )
                    
                    user_to_edit_index = -1
                    for i, u_data in enumerate(all_data["users"]):
                        if str(u_data.get("telegram_id")) == selected_user_id_str:
                            user_to_edit_index = i
                            break
                    
                    if user_to_edit_index != -1:
                        user_to_edit = all_data["users"][user_to_edit_index]
                        with st.form(f"edit_form_{user_to_edit.get('telegram_id', 'new')}"):
                            st.text(f"ویرایش کاربر: {user_to_edit.get('full_name', '')} (ID: {user_to_edit.get('telegram_id')})")
                            
                            new_telegram_name = st.text_input("نام تلگرام:", value=user_to_edit.get("telegram_name", ""))
                            new_full_name = st.text_input("نام کامل:", value=user_to_edit.get("full_name", ""))
                            new_real_name = st.text_input("نام واقعی:", value=user_to_edit.get("real_name", ""))
                            new_broker_user = st.text_input("نام کاربری کارگزاری:", value=user_to_edit.get("brokerage_username", ""))
                            new_broker_password = st.text_input("رمز عبور کارگزاری:", value=user_to_edit.get("brokerage_password", ""), type="password")
                            new_broker_type = st.selectbox("نوع کارگزاری:", ["agah", "mofid"], index=["agah", "mofid"].index(user_to_edit.get("brokerage_type", "agah")))
                            new_sub_type = st.selectbox("نوع اشتراک:", ["free", "premium"], index=["free", "premium"].index(user_to_edit.get("subscription_type", "free")))
                            new_national_id = st.text_input("کدملی:", value=user_to_edit.get("national_id", ""))
                            new_phone_number = st.text_input("شماره تلفن:", value=user_to_edit.get("phone_number", ""))
                            new_email = st.text_input("ایمیل:", value=user_to_edit.get("email", ""))
                            
                            current_expiry_dt = datetime.now()
                            if user_to_edit.get("expiry_date"):
                                try:
                                    current_expiry_dt = datetime.strptime(user_to_edit["expiry_date"], "%Y-%m-%d %H:%M:%S")
                                except ValueError:
                                    st.warning("فرمت تاریخ انقضای قبلی نامعتبر بود.")

                            new_expiry_date = st.date_input("تاریخ انقضای جدید:", value=current_expiry_dt.date())
                            new_expiry_time = st.time_input("زمان انقضای جدید:", value=current_expiry_dt.time())
                            
                            new_token_val = st.text_input("توکن مرتبط (اختیاری):", value=user_to_edit.get("token", ""))

                            if st.form_submit_button("ذخیره تغییرات کاربر"):
                                updated_expiry_str = datetime.combine(new_expiry_date, new_expiry_time).strftime("%Y-%m-%d %H:%M:%S")
                                
                                all_data["users"][user_to_edit_index]["telegram_name"] = new_telegram_name
                                all_data["users"][user_to_edit_index]["full_name"] = new_full_name
                                all_data["users"][user_to_edit_index]["real_name"] = new_real_name
                                all_data["users"][user_to_edit_index]["brokerage_username"] = new_broker_user
                                all_data["users"][user_to_edit_index]["brokerage_password"] = new_broker_password
                                all_data["users"][user_to_edit_index]["brokerage_type"] = new_broker_type
                                all_data["users"][user_to_edit_index]["subscription_type"] = new_sub_type
                                all_data["users"][user_to_edit_index]["national_id"] = new_national_id
                                all_data["users"][user_to_edit_index]["phone_number"] = new_phone_number
                                all_data["users"][user_to_edit_index]["email"] = new_email
                                all_data["users"][user_to_edit_index]["expiry_date"] = updated_expiry_str
                                all_data["users"][user_to_edit_index]["token"] = new_token_val
                                
                                save_users_data(all_data)
                                # به‌روزرسانی داده‌ها در session_state
                                st.session_state['all_data'] = load_users_data()
                                placeholder = st.empty()
                                placeholder.success(f"اطلاعات حساب کاربری با ID {selected_user_id_str} با موفقیت به‌روزرسانی شد.")
                                sleep(3)  # نمایش پیام به مدت 3 ثانیه
                                placeholder.empty()  # پاک کردن پیام
                                st.rerun()
                    else:
                        st.error("کاربر انتخاب شده برای ویرایش یافت نشد.")
            else:
                st.info("برای ویرایش، ابتدا یک کاربر را جستجو و انتخاب کنید.")



    with tab2:
        st.subheader("🔑 مدیریت توکن‌ها")
        tokens_list = all_data.get("tokens", [])

        if not tokens_list:
            st.info("هیچ توکنی ثبت نشده است.")
        else:
            with st.expander("🔍 جستجو و فیلتر توکن‌ها", expanded=False):
                search_token = st.text_input("توکن (یا بخشی از آن):")
                search_token_telegram_id = st.text_input("ID تلگرام مرتبط:")
                search_token_sub_type = st.selectbox("نوع اشتراک:", ["همه", "روزانه", "هفتگی", "ماهانه"], index=0)
                search_token_status = st.selectbox("وضعیت توکن:", ["همه", "استفاده شده", "استفاده نشده"], index=0)
                
                filtered_tokens = tokens_list
                if search_token:
                    filtered_tokens = [t for t in filtered_tokens if search_token.lower() in t.get("token", "").lower()]
                if search_token_telegram_id:
                    filtered_tokens = [t for t in filtered_tokens if str(t.get("telegram_id", "")) == search_token_telegram_id]
                if search_token_sub_type != "همه":
                    filtered_tokens = [t for t in filtered_tokens if t.get("subscription_type", "") == search_token_sub_type]
                if search_token_status != "همه":
                    is_used = search_token_status == "استفاده شده"
                    filtered_tokens = [t for t in filtered_tokens if t.get("is_used", False) == is_used]
                
                # نمایش داده‌ها در جدول
                st.dataframe(
                    pd.DataFrame([
                        {
                            "توکن": t.get("token", ""),
                            "ID تلگرام": t.get("telegram_id", ""),
                            "نام کاربری کارگزاری": t.get("brokerage_username", ""),
                            "نوع اشتراک": t.get("subscription_type", ""),
                            "تاریخ انقضا": t.get("expiry_date", ""),
                            "وضعیت": "استفاده شده" if t.get("is_used", False) else "استفاده نشده",
                            "استفاده شده توسط": t.get("used_by_telegram_id", ""),
                            "تاریخ استفاده": t.get("used_at", "")
                        } for t in filtered_tokens
                    ]),
                    height=300,
                    use_container_width=True
                )

    with tab3:
        st.subheader("🛠️ تولید توکن جدید")
        with st.form("generate_token_form_main"):
            st.markdown("##### اطلاعات اتصال توکن (اختیاری)")
            token_telegram_id = st.text_input(
                "ID تلگرام کاربر هدف:",
                help="اگر خالی بماند، توکن برای هر کاربری قابل استفاده است (اولین نفر)."
            ).strip()
            
            token_brokerage_username_input = st.text_input(
                "نام کاربری کارگزاری هدف:",
                help="اگر خالی بماند، توکن به نام کاربری خاصی محدود نمی‌شود (مگر اینکه ID تلگرام بالا پر شده باشد و کاربر آن ID، نام کاربری کارگزاری ثبت کرده باشد)."
            ).strip()

            suggested_brokerage_username = ""
            if token_telegram_id:
                user_for_token = find_user_by_telegram_id(token_telegram_id)
                if user_for_token and user_for_token.get("brokerage_username"):
                    suggested_brokerage_username = user_for_token.get("brokerage_username")
                    st.info(f"نام کاربری کارگزاری پیشنهادی برای ID {token_telegram_id}: {suggested_brokerage_username}")
                    if not token_brokerage_username_input:
                        token_brokerage_username_input = suggested_brokerage_username

            st.markdown("##### مشخصات اشتراک توکن")
            token_sub_type = st.selectbox("نوع اشتراک:", ["روزانه", "هفتگی", "ماهانه"], key="token_sub_type_gen")
            
            now = datetime.now()
            if token_sub_type == "روزانه": default_duration = timedelta(days=1)
            elif token_sub_type == "هفتگی": default_duration = timedelta(weeks=1)
            else: default_duration = timedelta(days=30)
            
            token_self_expiry_date = st.date_input(
                "تاریخ انقضای خود توکن (تا این تاریخ قابل فعالسازی است):",
                value=now + timedelta(days=90)
            )
            token_self_expiry_time = st.time_input(
                "زمان انقضای خود توکن:",
                value=datetime_time(23, 59, 59)
            )

            if st.form_submit_button("تولید و ذخیره توکن", type="primary"):
                token_self_expiry_datetime_str = datetime.combine(
                    token_self_expiry_date, token_self_expiry_time
                ).strftime("%Y-%m-%d %H:%M:%S")

                new_token_data = generate_token_entry(
                    telegram_id=token_telegram_id,
                    subscription_type=token_sub_type,
                    expiry_date_str=token_self_expiry_datetime_str,
                    brokerage_username=token_brokerage_username_input
                )
                
                all_data["tokens"].append(new_token_data)
                save_users_data(all_data)
                
                # به‌روزرسانی داده‌ها در session_state
                st.session_state['all_data'] = load_users_data()
                
                st.success("✅ توکن با موفقیت تولید و ذخیره شد!")
                st.code(new_token_data["token"], language=None)
                st.caption(f"این توکن از نوع '{token_sub_type}' است و تا تاریخ {token_self_expiry_datetime_str} قابل فعالسازی است.")
                if token_telegram_id:
                    st.caption(f"این توکن به ID تلگرام: {token_telegram_id} متصل است.")
                if token_brokerage_username_input:
                    st.caption(f"این توکن به نام کاربری کارگزاری: {token_brokerage_username_input} متصل است.")
                if not token_telegram_id and not token_brokerage_username_input:
                    st.warning("توجه: این توکن به هیچ کاربر یا نام کاربری کارگزاری خاصی متصل نشده است. اولین کاربری که آن را وارد کند، از آن استفاده خواهد کرد.")    
        
    
    
        with tab4:
            st.subheader("💡 راهنما و تنظیمات")
            st.markdown("""
            **توضیحات:**
            - **مدیریت کاربران:** مشاهده، جستجو و ویرایش اطلاعات کاربران ثبت‌شده در ربات.
            - **توکن‌های موجود:** لیست تمام توکن‌های تولید شده، وضعیت استفاده و اطلاعات مربوط به آن‌ها.
            - **تولید توکن جدید:** ایجاد توکن‌های اشتراک برای کاربران.
                - **ID تلگرام کاربر هدف (اختیاری):** اگر می‌خواهید توکن فقط توسط یک کاربر خاص قابل استفاده باشد، ID تلگرام او را وارد کنید. ربات هنگام فعال‌سازی، این ID را با ID کاربر فعلی تطبیق می‌دهد.
                - **نام کاربری کارگزاری هدف (اختیاری):** اگر می‌خواهید توکن فقط برای یک نام کاربری کارگزاری خاص قابل استفاده باشد، آن را وارد کنید. ربات هنگام فعال‌سازی، این نام کاربری را با نام کاربری کارگزاری که کاربر در ربات ثبت کرده، تطبیق می‌دهد.
                - **نوع اشتراک:** مدت زمانی که اشتراک کاربر پس از فعال‌سازی این توکن معتبر خواهد بود (مثلاً روزانه، هفتگی، ماهانه).
                - **تاریخ و زمان انقضای خود توکن:** تاریخی که خود توکن تا آن زمان برای *فعال‌سازی* معتبر است. پس از این تاریخ، توکن دیگر قابل استفاده نخواهد بود، حتی اگر مصرف نشده باشد. این با تاریخ انقضای اشتراک کاربر پس از فعال‌سازی متفاوت است.

            **نکات امنیتی برای توکن‌ها:**
            1.  **اتصال قوی:** برای امنیت بیشتر، هنگام تولید توکن، هم ID تلگرام و هم نام کاربری کارگزاری کاربر هدف را وارد کنید. این کار باعث می‌شود توکن فقط توسط آن کاربر خاص و برای آن حساب کارگزاری خاص قابل استفاده باشد.
            2.  **توکن‌های عمومی:** اگر ID تلگرام و نام کاربری کارگزاری را خالی بگذارید، توکن تولید شده عمومی خواهد بود و اولین کاربری که آن را در ربات وارد کند، می‌تواند از آن استفاده نماید (به شرط تطابق با نام کاربری کارگزاری که کاربر در ربات ثبت کرده، اگر توکن به نام کاربری خاصی محدود شده باشد).
            3.  **یکبار مصرف بودن:** هر توکن پس از یکبار استفاده موفق، غیرفعال می‌شود.
            4.  **انقضای خود توکن:** توکن‌ها دارای تاریخ انقضای خود هستند و پس از آن تاریخ دیگر قابل فعال‌سازی نیستند.

            **جلوگیری از سوءاستفاده از دوره رایگان:**
            - ربات تلاش می‌کند با بررسی نام کاربری کارگزاری، از ثبت‌نام‌های متعدد برای دریافت دوره رایگان با یک حساب کارگزاری جلوگیری کند. اگر یک نام کاربری کارگزاری قبلاً توسط یک ID تلگرام دیگر برای دوره رایگان استفاده شده باشد، ثبت‌نام رایگان جدید با آن نام کاربری مسدود خواهد شد.
            """)

            st.markdown("---")
            #st.warning(f"مسیر فایل کاربران و توکن‌ها: `{os.path.abspath(USERS_FILE)}`")