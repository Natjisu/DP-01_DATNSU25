import time
import random
import pandas as pd
import numpy as np
import warnings
from vnstock.explorer.vci import Company
from vnstock import Listing
from google.oauth2.service_account import Credentials
import gspread
from datetime import date, datetime
import sys
import io

# --- FORCE UTF-8 FOR SCHEDULED TASKS / WINDOWS CONSOLES ---
try:
    import sys, os
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
except Exception:
    pass
# ----------------------------------------------------------

# Chỉ wrap stdout khi chạy console thật (có buffer)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Ẩn cảnh báo không cần thiết từ pandas
warnings.filterwarnings("ignore", category=FutureWarning)

# --- CẤU HÌNH SERVICE ACCOUNT & GOOGLE SHEETS ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SA_KEY_FILE    = "sa-key.json"  # path tới JSON key của Service Account
SPREADSHEET_ID = "10Lz4-X1asek_hl-1iuC9T2rYV61gOWZ_sT22zn6J4Vc"
SHEET_NAME     = "6_tin_tức"

# ---- MAPPING CỘT ANH → VIỆT ----
COLUMN_MAPPING = {
    'id': 'mã tin tức',
    'news_title': 'tiêu đề tin tức',
    'news_image_url': 'liên kết hình ảnh',
    'news_source_link': 'liên kết nguồn tin',
    'public_date': 'ngày công bố',
    'lang_code': 'mã ngôn ngữ',
    'news_id': 'mã định danh tin',
    'news_short_content': 'nội dung tóm tắt',
    'news_full_content': 'nội dung chi tiết',
    'close_price': 'giá đóng cửa',
    'ref_price': 'giá tham chiếu',
    'floor': 'giá sàn',
    'ceiling': 'giá trần',
    'price_change_pct': 'tỷ lệ thay đổi giá',
    'symbol': 'mã chứng khoán'
}


def authorize_service_account() -> Credentials:
    """
    Khởi tạo Credentials từ Service Account JSON
    """
    return Credentials.from_service_account_file(
        SA_KEY_FILE,
        scopes=SCOPES
    )


def sanitize_cell(val):
    """
    Thay NaN/Inf thành None, datetime → ISO string, giữ nguyên các giá trị khác
    """
    if val is None:
        return None
    if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
        return None
    try:
        if pd.isna(val):
            return None
    except:
        pass
    if isinstance(val, (datetime, date, pd.Timestamp)):
        return val.isoformat()
    return val


def safe_fetch(fetch_fn, max_retries=3, initial_wait=2):
    """
    Thực thi fetch_fn() với retry/back‑off khi gặp lỗi.
    fetch_fn: callable không tham số.
    """
    wait = initial_wait
    for attempt in range(1, max_retries+1):
        try:
            return fetch_fn()
        except Exception as e:
            print(f"⚠️ Attempt {attempt}/{max_retries} lỗi: {e}")
            if attempt == max_retries:
                print("❌ Đã vượt quá số lần retry, bỏ qua.")
                return None
            sleep_t = wait + random.uniform(0, 1)
            print(f"⏳ Đợi {sleep_t:.1f}s rồi thử lại…")
            time.sleep(sleep_t)
            wait *= 2


# 1. Lấy danh sách mã VN100
vn100_symbols = Listing().symbols_by_group("VN100")


def get_news(symbol: str) -> pd.DataFrame | None:
    """
    Lấy tin tức (news) cho từng mã, có retry.
    """
    def _fetch():
        df = Company(symbol).news()
        return df

    df = safe_fetch(_fetch)
    if df is not None and not df.empty:
        df['symbol'] = symbol
        return df
    print(f"⚠️ {symbol}: Không có tin hoặc lỗi")
    return None


def update_sheet(df: pd.DataFrame, creds: Credentials):
    """
    Xử lý và cập nhật DataFrame lên Google Sheets
    - Xoá cột toàn None
    - Đổi tên cột
    - Sanitize từng ô
    """
    # 1) Chuẩn hoá giá trị rỗng thành NaN
    df = df.replace(r'^\s*$', np.nan, regex=True) \
        .replace(['None', 'NaN', 'nan'], np.nan)

    # 2) Xoá cột toàn NaN
    df = df.dropna(axis=1, how='all')


    # 2) Đổi tên cột
    df = df.rename(columns=COLUMN_MAPPING)

    # 3) Sanitize từng ô
    header = df.columns.tolist()
    records = df.to_dict(orient="records")
    values = [header]
    for rec in records:
        values.append([sanitize_cell(rec.get(col)) for col in header])

    # 4) Kết nối và cập nhật sheet
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(
            title=SHEET_NAME,
            rows=str(len(values)+5),
            cols=str(len(header)+2)
        )
    ws.clear()
    ws.update(range_name="A1", values=values)
    print(f"📈 Đã cập nhật {len(values)-1} dòng lên sheet '{SHEET_NAME}'")


def main():
    creds = authorize_service_account()
    news_list = []
    total = len(vn100_symbols)

    # 2. Lặp qua các mã và gom dữ liệu với progress log
    for idx, sym in enumerate(vn100_symbols, start=1):
        print(f"🔄 ({idx}/{total}) Đang xử lý: {sym}")
        df = get_news(sym)
        if df is not None:
            print(f"✅ {sym}: {len(df)} bản tin")
            news_list.append(df)
        else:
            print(f"⚠️ {sym}: Không có tin")
        time.sleep(1)

    if not news_list:
        print("❌ Không thu được dữ liệu news nào.")
        return

    # 3. Gộp dữ liệu và lọc từ 2023
    news_df = pd.concat(news_list, ignore_index=True)
    news_df['public_date'] = pd.to_datetime(news_df['public_date'], unit='ms', errors='coerce')
    news_df = news_df[news_df['public_date'] >= '2023-01-01']

    print(news_df.head())
    update_sheet(news_df, creds)


if __name__ == "__main__":
    main()