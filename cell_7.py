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

# Chỉ wrap khi stdout có attribute `buffer` (console thật)
import sys, io
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Ẩn cảnh báo không cần thiết từ pandas
warnings.filterwarnings("ignore", category=FutureWarning)

# --- CẤU HÌNH SERVICE ACCOUNT & GOOGLE SHEETS ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SA_KEY_FILE    = "sa-key.json"
SPREADSHEET_ID = "10Lz4-X1asek_hl-1iuC9T2rYV61gOWZ_sT22zn6J4Vc"
SHEET_NAME     = "5_sự_kiện"

# ---- MAPPING CỘT ANH → VIỆT ----
COLUMN_MAPPING = {
    'id': 'mã sự kiện',
    'event_title': 'tiêu đề sự kiện',
    'en__event_title': 'tiêu đề sự kiện (tiếng Anh)',
    'public_date': 'ngày công bố',
    'issue_date': 'ngày thực hiện',
    'source_url': 'liên kết nguồn',
    'event_list_code': 'mã loại sự kiện',
    'ratio': 'tỷ lệ',
    'value': 'giá trị',
    'record_date': 'ngày chốt quyền',
    'exright_date': 'ngày không hưởng quyền',
    'event_list_name': 'tên loại sự kiện',
    'en__event_list_name': 'tên loại sự kiện (tiếng Anh)',
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


# DANH SÁCH MÃ VN100
vn100_symbols = Listing().symbols_by_group("VN100")


def get_events(symbol: str) -> pd.DataFrame | None:
    """
    Lấy các sự kiện của 1 mã qua Company.events(), có retry.
    """
    def _fetch():
        df = Company(symbol).events()
        return df

    df = safe_fetch(_fetch)
    if df is not None and not df.empty:
        df['symbol'] = symbol
        print(f"✅ {symbol}: {len(df)} sự kiện")
        return df
    print(f"⚠️ {symbol}: Không có dữ liệu sự kiện hay lỗi")
    return None


def update_sheet(df: pd.DataFrame, creds: Credentials):
    """
    Đổi tên cột, sanitize và cập nhật lên Google Sheets
    """
    # 1) Lọc và rename cột
    df = df.rename(columns=COLUMN_MAPPING)

    # 2) Chuẩn hóa từng ô
    header = df.columns.tolist()
    records = df.to_dict(orient="records")
    values = [header]
    for rec in records:
        values.append([sanitize_cell(rec[col]) for col in header])

    # 3) Kết nối và cập nhật sheet
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
    event_list = []
    for sym in vn100_symbols:
        df_ev = get_events(sym)
        if df_ev is not None:
            event_list.append(df_ev)
        time.sleep(1)

    if not event_list:
        print("❌ Không thu được dữ liệu sự kiện nào.")
        return

    events_df = pd.concat(event_list, ignore_index=True)
    # chuyển kiểu ngày để filter mới nếu cần (2023)
    events_df['record_date'] = pd.to_datetime(events_df['record_date'], errors='coerce')
    events_df['issue_date']  = pd.to_datetime(events_df['issue_date'],  errors='coerce')
    events_df = events_df[ (events_df['record_date'] >= '2023-01-01') |
                           (events_df['issue_date']  >= '2023-01-01') ]

    print(events_df.head())
    update_sheet(events_df, creds)


if __name__ == "__main__":
    main()