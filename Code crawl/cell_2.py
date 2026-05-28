import time
import random
import warnings
from datetime import date

import pandas as pd
import numpy as np
from vnstock import Vnstock, Listing
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
SHEET_NAME     = "2_thông_tin_doanh_nghiệp"

# ---- MAPPING CỘT ANH → VIỆT ----
COLUMN_MAPPING = {
    'symbol': 'mã chứng khoán',
    'organ_short_name': 'tên viết tắt công ty',
    'organ_name': 'tên đầy đủ công ty',
    'product_grp_id': 'mã nhóm sản phẩm',
    'id': 'mã định danh',
    'issue_share': 'số lượng cổ phiếu lưu hành',
    'history': 'lịch sử phát triển',
    'company_profile': 'hồ sơ công ty',
    'icb_name3': 'ngành cấp 3',
    'icb_name2': 'ngành cấp 2',
    'icb_name4': 'ngành cấp 4',
    'financial_ratio_issue_share': 'tỷ lệ cổ phiếu tài chính',
    'charter_capital': 'vốn điều lệ'
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

def fetch_company_info() -> pd.DataFrame:
    symbols = Listing().symbols_by_group("VN100")
    api = Vnstock()
    rows = []

    for idx, symbol in enumerate(symbols, 1):
        def _get_one():
            df = api.stock(symbol=symbol, source="VCI").company.overview()
            return df.iloc[0].to_dict()

        info = safe_fetch(_get_one)
        if info:
            info['symbol'] = symbol
            rows.append(info)
            print(f"✅ Lấy {symbol} thành công")
            time.sleep(1)
        else:
            print(f"⚠️ Bỏ qua {symbol} do lỗi không hồi phục")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # **1.** Di chuyển cột symbol lên đầu
    cols = ['symbol'] + [c for c in df.columns if c != 'symbol']
    df = df[cols]

    # **2.** Sau đó mới rename theo mapping
    df = df.rename(columns=COLUMN_MAPPING)

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
    df = fetch_company_info()
    if df.empty:
        print("❌ Không có dữ liệu để cập nhật.")
    else:
        update_sheet(df, creds)

if __name__ == "__main__":
    main()