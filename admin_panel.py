from datetime import timedelta, datetime, time as datetime_time
from time import sleep
import streamlit as st
import json
import os
import uuid
import pandas as pd

# --- Configuration ---
USERS_FILE = "users.json"  # Ensure this matches the bot's USERS_FILE
ADMIN_PASSWORD = "0000"  # Change this in a production environment!

def load_users_data():
    """Loads user and token data from the JSON file."""
    if not os.path.exists(USERS_FILE):
        return {"users": [], "tokens": [], "activity_log": {}}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "users" not in data: data["users"] = []
            if "tokens" not in data: data["tokens"] = []
            if "activity_log" not in data: data["activity_log"] = {}
            return data
    except json.JSONDecodeError:
        st.error(f"Error decoding JSON from {USERS_FILE}.")
        return {"users": [], "tokens": [], "activity_log": {}}
    except Exception as e:
        st.error(f"Error loading data from {USERS_FILE}: {e}")
        return {"users": [], "tokens": [], "activity_log": {}}

def save_users_data(data):
    """Saves user and token data to the JSON file."""
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        st.error(f"Error saving data to {USERS_FILE}: {e}")

def find_user_by_telegram_id(telegram_id_to_find):
    """Finds a user by their Telegram ID."""
    data = load_users_data()
    telegram_id_str = str(telegram_id_to_find)
    for user in data.get("users", []):
        if str(user.get("telegram_id")) == telegram_id_str:
            return user
    return None

def find_users_by_fields(**kwargs):
    """Finds users matching multiple search criteria (case-insensitive)."""
    data = load_users_data()
    users_list = data.get("users", [])
    if not kwargs: return users_list
    
    results = []
    for user in users_list:
        match = True
        for field, value in kwargs.items():
            if value:
                user_field_value = str(user.get(field, "")).lower()
                search_value = str(value).lower()
                if search_value not in user_field_value:
                    match = False
                    break
        if match:
            results.append(user)
    return results

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
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "used_by_telegram_id": None,
        "used_at": None
    }
    return token_data

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
        st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs(["کاربران", "توکن‌ها", "تولید توکن", "تنظیمات و راهنما"])

    with tab1:
        st.subheader("📊 مدیریت کاربران")
        all_data = load_users_data()
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
                            
                            new_full_name = st.text_input("نام کامل:", value=user_to_edit.get("full_name", ""))
                            new_broker_user = st.text_input("نام کاربری کارگزاری:", value=user_to_edit.get("brokerage_username", ""))
                            new_broker_type = st.selectbox("نوع کارگزاری:", ["agah", "mofid"], index=["agah", "mofid"].index(user_to_edit.get("brokerage_type", "agah")))
                            new_sub_type = st.selectbox("نوع اشتراک:", ["free", "premium"], index=["free", "premium"].index(user_to_edit.get("subscription_type", "free")))
                            
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
                                
                                all_data["users"][user_to_edit_index]["full_name"] = new_full_name
                                all_data["users"][user_to_edit_index]["brokerage_username"] = new_broker_user
                                all_data["users"][user_to_edit_index]["brokerage_type"] = new_broker_type
                                all_data["users"][user_to_edit_index]["subscription_type"] = new_sub_type
                                all_data["users"][user_to_edit_index]["expiry_date"] = updated_expiry_str
                                all_data["users"][user_to_edit_index]["token"] = new_token_val
                                
                                save_users_data(all_data)
                                placeholder = st.empty()
                                placeholder.success(f"اطلاعات حساب کاربری با ID {selected_user_id_str} با موفقیت به‌روزرسانی شد.")
                                sleep(3)  # نمایش پیام به مدت 3 ثانیه
                                placeholder.empty()  # پاک کردن پیام
                                st.rerun()
                    else:
                        st.error("کاربر انتخاب شده برای ویرایش یافت نشد.")
            else:
                st.info("برای ویرایش، ابتدا یک کاربر را جستجو و انتخاب کنید.")

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
                value=datetime_time(23, 59, 59)  # Fixed: Use datetime_time
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
                
                all_data = load_users_data()
                all_data["tokens"].append(new_token_data)
                save_users_data(all_data)
                
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