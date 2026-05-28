import time
import random
import warnings
from datetime import date, datetime

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

# Ẩn cảnh báo FutureWarning của pandas
warnings.filterwarnings("ignore", category=FutureWarning)

# --- CẤU HÌNH SERVICE ACCOUNT & GOOGLE SHEETS ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SA_KEY_FILE    = "sa-key.json"
SPREADSHEET_ID = "10Lz4-X1asek_hl-1iuC9T2rYV61gOWZ_sT22zn6J4Vc"
SHEET_NAME     = "3_giá_cổ_phiếu_VN100"

# --- MAPPING CỘT ANH → VIỆT (đã loại bỏ 'time') ---
COLUMN_MAPPING = {
    'open': 'giá mở cửa',
    'high': 'giá cao nhất',
    'low': 'giá thấp nhất',
    'close': 'giá đóng cửa',
    'volume': 'khối lượng giao dịch',
    'symbol': 'mã chứng khoán'
}

def authorize_service_account():
    """
    Khởi tạo Credentials từ Service Account JSON và trả về đối tượng Credentials.
    """
    return Credentials.from_service_account_file(
        SA_KEY_FILE,
        scopes=SCOPES
    )

def safe_fetch(fetch_fn, max_retries=3, initial_wait=2):
    """
    Thực thi fetch_fn() với retry/back‑off khi gặp lỗi.
    fetch_fn: callable không tham số, trả về DataFrame hoặc raise.
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


def fetch_price_history() -> pd.DataFrame:
    symbols   = Listing().symbols_by_group("VN100")
    api       = Vnstock()
    today     = date.today().isoformat()
    all_frames = []

    for symbol in symbols:
        def _get_history():
            return (api.stock(symbol=symbol, source="VCI")
                       .quote
                       .history(start="2023-01-01", end=today, interval="1D"))

        df = safe_fetch(_get_history)
        if df is None:
            print(f"⚠️ Bỏ qua {symbol} do lỗi không hồi phục")
            continue
        if df.empty:
            print(f"⚠️ {symbol}: Không có dữ liệu giá")
            continue

        # ---- CHỈ CẦN 3 DÒNG NÀY ----
        df.rename(columns={'time': 'thời gian'}, inplace=True)
        df['thời gian'] = pd.to_datetime(df['thời gian']).dt.date
        df['symbol']    = symbol
        # --------------------------------

        print(f"✅ {symbol}: {len(df)} dòng giá (đến {today})")
        all_frames.append(df)
        time.sleep(1.5)

    if not all_frames:
        return pd.DataFrame()

    full_df = pd.concat(all_frames, ignore_index=True)
    full_df.rename(columns=COLUMN_MAPPING, inplace=True)   # map giá/volume
    return full_df

def sanitize_cell(val):
    """
    Chuyển NaN/Inf thành None, pd.Timestamp/date/datetime → ISO string,
    giữ nguyên các giá trị khác (int, float, str…).
    """
    if val is None:
        return None
    # số float NaN/Inf
    if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
        return None
    # pandas NA
    try:
        if pd.isna(val):
            return None
    except:
        pass
    # datetime types → ISO string
    if isinstance(val, (pd.Timestamp, datetime, date)):
        return val.isoformat()
    return val

def update_sheet(df: pd.DataFrame, creds):
    """
    Ghi đè toàn bộ DataFrame lên Google Sheet,
    đảm bảo mọi cell đều JSON‑serializable bằng sanitize_cell().
    """
    # Không cần loop dt.strftime nữa, chúng ta sanitize cell sau
    header = df.columns.tolist()
    records = df.to_dict(orient='records')

    # Build values, convert mỗi ô qua sanitize_cell
    values = [header]
    for rec in records:
        row = []
        for col in header:
            val = rec.get(col)
            # sanitize_cell sẽ chuyển pd.Timestamp → ISO string, NaN/Inf → None
            row.append(sanitize_cell(val))
        values.append(row)

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
    print(f"📈 Đã cập nhật {len(values)-1} dòng lên sheet '{SHEET_NAME}'")

def main():
    creds = authorize_service_account()
    df = fetch_price_history()
    if df.empty:
        print("❌ Không có dữ liệu giá để cập nhật.")
    else:
        update_sheet(df, creds)

if __name__ == "__main__":
    main()