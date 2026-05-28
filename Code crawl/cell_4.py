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

# Ẩn cảnh báo không cần thiết từ pandas
warnings.filterwarnings("ignore", category=FutureWarning)

# --- CẤU HÌNH SERVICE ACCOUNT & GOOGLE SHEETS ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SA_KEY_FILE    = "sa-key.json"  # đường dẫn tới JSON key của Service Account
SPREADSHEET_ID = "10Lz4-X1asek_hl-1iuC9T2rYV61gOWZ_sT22zn6J4Vc"
SHEET_NAME     = "4.1_báo_cáo_tài_chính(Bảng_cân_đối_kế_toán)"

# ---- MAPPING CỘT ANH → VIỆT ----
COLUMN_MAPPING = {
    'CP': 'mã chứng khoán',
}

def authorize_service_account() -> Credentials:
    """
    Khởi tạo Credentials từ Service Account JSON
    """
    creds = Credentials.from_service_account_file(
        SA_KEY_FILE,
        scopes=SCOPES
    )
    return creds


def fetch_balance_sheet(period: str = "quarter") -> pd.DataFrame:
    """
    Lấy báo cáo Bảng cân đối (Balance Sheet) theo quý của VN100,
    lọc chỉ năm từ 2023 trở đi.
    Trả về một pandas.DataFrame.
    """
    symbols = Listing().symbols_by_group("VN100")
    api = Vnstock()
    frames = []

    for idx, symbol in enumerate(symbols, start=1):
        print(f"🔄 ({idx}/{len(symbols)}) Đang xử lý: {symbol}")
        retries = 0
        while retries < 3:
            try:
                df = api.stock(symbol=symbol, source="VCI") \
                        .finance.balance_sheet(period=period, lang="vi", dropna=True)
                if df is not None and not df.empty:
                    # Chuyển report_date sang datetime và lọc năm >= 2023
                    if "report_date" in df.columns:
                        df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
                        df = df[df["report_date"].dt.year >= 2023]
                    elif "year_report" in df.columns:
                        df = df[df["year_report"] >= 2023]

                    if not df.empty:
                        df = df.reset_index(drop=True)
                        # df["symbol"] = symbol
                        print(f"✅ {symbol}: {len(df)} dòng sau khi lọc năm >= 2023")
                        frames.append(df)
                    else:
                        print(f"⚠️ {symbol}: Không có dữ liệu sau khi lọc năm >= 2023")
                else:
                    print(f"⚠️ {symbol}: Không có dữ liệu balance sheet")
                break

            except Exception as e:
                retries += 1
                print(f"❌ Lỗi với {symbol} (attempt {retries}): {e}")
                if "VCI" in str(e):
                    print("⏳ Đợi 60s rồi thử lại...")
                    time.sleep(60)
                else:
                    break

        time.sleep(1.5)  # giảm tốc độ request

    if not frames:
        return pd.DataFrame()

    # Gộp dữ liệu và thực hiện rename cột
    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.rename(columns=COLUMN_MAPPING)
    return df_all


def sanitize_cell(val):
    # NaN hoặc Inf → None (JSON null)
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return None
    # pandas NA
    try:
        import pandas as pd
        if pd.isna(val):
            return None
    except:
        pass
    # datetime → ISO string
    if isinstance(val, (datetime, date, pd.Timestamp)):
        return val.isoformat()
    # mọi thứ khác giữ nguyên
    return val


def update_sheet(df: pd.DataFrame, creds):
    # 1) Xử lý từng ô
    header = df.columns.tolist()
    rows = df.to_dict(orient='records')
    values = [header]
    for row in rows:
        values.append([sanitize_cell(row[col]) for col in header])

    # 2) Kết nối gspread
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

    # 3) Clear + Update
    ws.clear()
    ws.update(range_name="A1", values=values)
    print(f"📈 Đã cập nhật {len(values)-1} dòng lên '{SHEET_NAME}'")


def main():
    # 1. Auth với Service Account
    creds = authorize_service_account()

    # 2. Fetch dữ liệu balance sheet
    df = fetch_balance_sheet(period="quarter")
    if df.empty:
        print("❌ Không có dữ liệu balance sheet nào từ 2023 trở đi.")
        return

    # 3. Cập nhật lên Google Sheets
    update_sheet(df, creds)

if __name__ == "__main__":
    main()