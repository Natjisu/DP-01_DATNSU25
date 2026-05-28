import time
import random
import warnings
from datetime import date

import pandas as pd
import numpy as np
from vnstock import Listing
from google.oauth2.service_account import Credentials
import gspread

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
SA_KEY_FILE    = "sa-key.json"
SPREADSHEET_ID = "10Lz4-X1asek_hl-1iuC9T2rYV61gOWZ_sT22zn6J4Vc"
SHEET_NAME     = "1_danh_sách_mã_VN100"

# ---- MAPPING CỘT ANH → VIỆT ----
COLUMN_MAPPING = {
    'symbol': 'mã chứng khoán',
    'organ_name': 'tên công ty',
}

def authorize_service_account():
    creds = Credentials.from_service_account_file(
        SA_KEY_FILE,
        scopes=SCOPES
    )
    return creds

def safe_fetch(fetch_fn, max_retries=3, initial_wait=2):
    wait = initial_wait
    for attempt in range(1, max_retries + 1):
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
            
def fetch_symbols() -> pd.DataFrame:
    """
    Lấy danh sách mã cổ phiếu trong rổ VN100,
    rồi merge với thông tin tên công ty và đổi tên cột sang tiếng Việt.
    """
    # 1. Lấy Series chứa các symbol trong nhóm VN100
    symbols_series = safe_fetch(lambda: Listing().symbols_by_group('VN100'))
    if symbols_series is None or symbols_series.empty:
        return pd.DataFrame()

    symbols = symbols_series.tolist()

    # 2. Lấy DataFrame toàn bộ mã niêm yết
    df_all = safe_fetch(lambda: Listing().all_symbols())
    if df_all is None or df_all.empty:
        return pd.DataFrame({'symbol': symbols})

    # 3. Nếu cần, đổi tên cột 'ticker' thành 'symbol'
    if 'ticker' in df_all.columns:
        df_all = df_all.rename(columns={'ticker': 'symbol'})

    # 4. Lọc chỉ những cổ phiếu trong rổ VN100
    df = df_all[df_all['symbol'].isin(symbols)].copy()

    # 5. Đổi tên cột sang tiếng Việt theo mapping đã khai báo
    df = df.rename(columns=COLUMN_MAPPING)

    # 6. Đặt cột 'mã chứng khoán' lên đầu
    cols = ['mã chứng khoán'] + [c for c in df.columns if c != 'mã chứng khoán']
    df = df[cols]

    return df


def update_sheet(df: pd.DataFrame, creds):
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(
            title=SHEET_NAME,
            rows=str(len(df) + 10),
            cols=str(len(df.columns) + 2)
        )

    ws.clear()
    header = df.columns.tolist()
    values = [header] + df.values.tolist()
    ws.update(range_name="A1", values=values)
    print(f"📈 Đã cập nhật {len(df)} dòng lên sheet '{SHEET_NAME}'.")

def main():
    creds = authorize_service_account()
    df = fetch_symbols()
    if df.empty:
        print("❌ Không có dữ liệu để cập nhật.")
    else:
        update_sheet(df, creds)

if __name__ == "__main__":
    main()