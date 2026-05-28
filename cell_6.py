import time
import pandas as pd
import numpy as np
import warnings
from vnstock import Vnstock, Listing
from google.oauth2.service_account import Credentials
import gspread
from datetime import date, datetime
import random

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

# Ẩn cảnh báo không cần thiết từ pandas
warnings.filterwarnings("ignore", category=FutureWarning)

# --- CẤU HÌNH SERVICE ACCOUNT & GOOGLE SHEETS ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SA_KEY_FILE    = "sa-key.json"  # đường dẫn tới JSON key của Service Account
SPREADSHEET_ID = "10Lz4-X1asek_hl-1iuC9T2rYV61gOWZ_sT22zn6J4Vc"
SHEET_NAME     = "4.2_báo_cáo_tài_chính(Báo_cáo_kết_quả_kinh_doanh)"

# ---- MAPPING CỘT ANH → VIỆT ----
COLUMN_MAPPING = {
    'CP': 'mã chứng khoán',
}

def authorize_service_account() -> Credentials:
    """
    Khởi tạo Credentials từ Service Account JSON
    """
    return Credentials.from_service_account_file(
        SA_KEY_FILE,
        scopes=SCOPES
    )


def safe_fetch(fetch_fn, max_retries=5, initial_wait=5):
    """
    fetch_fn: callable không tham số, trả về DataFrame hoặc raise Exception
    max_retries: số lần thử tối đa
    initial_wait: thời gian chờ ban đầu (giây)
    """
    wait = initial_wait
    for attempt in range(1, max_retries+1):
        try:
            return fetch_fn()
        except Exception as e:
            print(f"⚠️ Attempt {attempt}/{max_retries} lỗi: {e}")
            if attempt == max_retries:
                print(f"❌ Bỏ qua sau {max_retries} lần thử.")
                return None
            sleep_t = wait + random.uniform(0, 2)
            print(f"⏳ Đợi {sleep_t:.1f}s rồi thử lại…")
            time.sleep(sleep_t)
            wait *= 2


def get_income_statement(symbol: str, period: str = 'quarter') -> pd.DataFrame | None:
    """
    Lấy báo cáo kết quả kinh doanh với retry/back‑off khi gặp lỗi
    """
    def fetch():
        return Vnstock() \
            .stock(symbol=symbol, source='VCI') \
            .finance.income_statement(period=period, lang='vi', dropna=True)

    df = safe_fetch(fetch)
    if df is not None and not df.empty:
        df = df.reset_index(drop=True)
        # df['symbol'] = symbol
        print(f"✅ {symbol}: {len(df)} dòng")
        return df

    print(f"⚠️ {symbol}: Không có dữ liệu sau retry.")
    return None


def sanitize_cell(val):
    """
    Chuyển NaN/Inf thành None, datetime thành ISO string, giữ nguyên các giá trị khác
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


def update_sheet(df: pd.DataFrame, creds: Credentials):
    """
    Xử lý từng ô rồi cập nhật toàn bộ DataFrame lên Google Sheets
    """
    header = df.columns.tolist()
    records = df.to_dict(orient='records')
    values = [header]
    for rec in records:
        values.append([sanitize_cell(rec[col]) for col in header])

    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(
            title=SHEET_NAME,
            rows=str(len(values) + 5),
            cols=str(len(header) + 2)
        )
    ws.clear()
    ws.update(range_name="A1", values=values)
    print(f"📈 Đã cập nhật {len(values)-1} dòng lên '{SHEET_NAME}'")


def main():
    creds = authorize_service_account()
    symbols = Listing().symbols_by_group("VN100")
    income_list = []
    for idx, sym in enumerate(symbols, 1):
        print(f"🔄 ({idx}/{len(symbols)}) Đang xử lý: {sym}")
        df_inc = get_income_statement(sym)
        if df_inc is not None:
            income_list.append(df_inc)
        time.sleep(2)

    if income_list:
        income_df = pd.concat(income_list, ignore_index=True)
        # Thực hiện rename các cột trước khi update lên Sheets
        income_df = income_df.rename(columns=COLUMN_MAPPING)
        update_sheet(income_df, creds)
    else:
        print("❌ Không thu được dữ liệu income statement nào.")

if __name__ == "__main__":
    main()