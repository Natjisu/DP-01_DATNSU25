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
SA_KEY_FILE    = "sa-key.json"  
SPREADSHEET_ID = "10Lz4-X1asek_hl-1iuC9T2rYV61gOWZ_sT22zn6J4Vc"
SHEET_NAME     = "4.3_báo_cáo_tài_chính(Báo_cáo_lưu_chuyển_tiền_tệ)"

# ---- MAPPING CỘT ANH → VIỆT ----
COLUMN_MAPPING = {
    'ticker': 'mã chứng khoán',
    'yearReport': 'năm báo cáo',
    'lengthReport': 'kỳ báo cáo',
    'Net Profit/Loss before tax': 'lợi nhuận/lỗ trước thuế',
    'Depreciation and Amortisation': 'khấu hao và phân bổ',
    'Provision for credit losses': 'dự phòng rủi ro tín dụng',
    'Unrealized foreign exchange gain/loss': 'lãi/lỗ tỷ giá chưa thực hiện',
    'Profit/Loss from disposal of fixed assets': 'lãi/lỗ từ thanh lý tài sản cố định',
    'Profit/Loss from investing activities': 'lãi/lỗ từ hoạt động đầu tư',
    'Interest Expense': 'chi phí lãi vay',
    'Operating profit before changes in working capital': 'lợi nhuận hoạt động trước thay đổi vốn lưu động',
    'Increase/Decrease in receivables': 'tăng/giảm khoản phải thu',
    'Increase/Decrease in inventories': 'tăng/giảm hàng tồn kho',
    'Increase/Decrease in payables': 'tăng/giảm khoản phải trả',
    'Increase/Decrease in prepaid expenses': 'tăng/giảm chi phí trả trước',
    'Interest paid': 'lãi vay đã trả',
    'Business Income Tax paid': 'thuế TNDN đã nộp',
    'Other receipts from operating activities': 'các khoản thu khác từ hoạt động kinh doanh',
    'Other payments on operating activities': 'các khoản chi khác từ hoạt động kinh doanh',
    'Net cash inflows/outflows from operating activities': 'luồng tiền thuần từ hoạt động kinh doanh',
    'Purchase of fixed assets': 'chi mua tài sản cố định',
    'Proceeds from disposal of fixed assets': 'thu từ thanh lý tài sản cố định',
    'Loans granted, purchases of debt instruments (Bn. VND)': 'cho vay, mua công cụ nợ',
    'Collection of loans, proceeds from sales of debts instruments (Bn. VND)': 'thu hồi khoản cho vay, bán công cụ nợ',
    'Investment in other entities': 'đầu tư vào các đơn vị khác',
    'Proceeds from divestment in other entities': 'thu từ thoái vốn ở các đơn vị khác',
    'Gain on Dividend': 'lãi từ cổ tức',
    'Net Cash Flows from Investing Activities': 'luồng tiền thuần từ hoạt động đầu tư',
    'Increase in charter captial': 'tăng vốn điều lệ',
    'Proceeds from borrowings': 'thu từ vay nợ',
    'Repayment of borrowings': 'trả nợ gốc vay',
    'Finance lease principal payments': 'thanh toán gốc thuê tài chính',
    'Dividends paid': 'chi trả cổ tức',
    'Cash flows from financial activities': 'luồng tiền thuần từ hoạt động tài chính',
    'Net increase/decrease in cash and cash equivalents': 'tăng/giảm thuần tiền và tương đương tiền',
    'Cash and cash equivalents': 'tiền và tương đương tiền đầu kỳ',
    'Foreign exchange differences Adjustment': 'điều chỉnh chênh lệch tỷ giá',
    'Cash and Cash Equivalents at the end of period': 'tiền và tương đương tiền cuối kỳ',
    'Profits from other activities': 'lợi nhuận từ các hoạt động khác',
    'Net Cash Flows from Operating Activities before BIT': 'luồng tiền từ hoạt động kinh doanh trước thuế TNDN',
    'Payment from reserves': 'chi từ quỹ dự phòng',
    'Payments for share repurchases': 'chi mua lại cổ phiếu',
    'Interest income and dividends': 'thu nhập từ lãi và cổ tức',
    '_Increase/Decrease in receivables': 'tăng/giảm khoản phải thu (dự phòng)',
    '_Increase/Decrease in payables': 'tăng/giảm khoản phải trả (dự phòng)',
    'Dividends received': 'cổ tức đã nhận'
}


def authorize_service_account() -> Credentials:
    """
    Khởi tạo Credentials từ Service Account JSON
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


def get_cash_flow(symbol: str, period: str = 'quarter') -> pd.DataFrame | None:
    """
    Lấy báo cáo lưu chuyển tiền tệ (Cash Flow) theo kỳ của 1 mã,
    dùng safe_fetch để retry, trả về DataFrame hoặc None nếu không lấy được.
    """
    def _fetch():
        stock = Vnstock().stock(symbol=symbol, source='VCI')
        return stock.finance.cash_flow(period=period, dropna=True)

    df = safe_fetch(_fetch)
    if df is None or df.empty:
        print(f"⚠️ {symbol}: Không có dữ liệu cash flow hoặc lỗi")
        return None

    df = df.reset_index(drop=True)
    df['ticker']      = symbol
    print(f"✅ {symbol}: {len(df)} dòng")
    return df


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
    # 1) Đổi tên cột sang tiếng Việt
    df = df.rename(columns=COLUMN_MAPPING)

    # 2) Chuẩn bị values
    header = df.columns.tolist()
    records = df.to_dict(orient='records')
    values = [header]
    for rec in records:
        row = [sanitize_cell(rec[col]) for col in header]
        values.append(row)

    # 3) Kết nối gspread và update
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

    # 1. Lấy danh sách mã VN100
    symbols = Listing().symbols_by_group("VN100")

    # 2. Thu thập cash flow với retry
    cashflow_list = []
    for idx, sym in enumerate(symbols, 1):
        print(f"🔄 ({idx}/{len(symbols)}) Đang xử lý: {sym}")
        df_cf = get_cash_flow(sym, period='quarter')
        if df_cf is not None:
            cashflow_list.append(df_cf)
        time.sleep(2)

    # 3. Gộp, đổi tên và cập nhật lên Sheets
    if cashflow_list:
        cashflow_df = pd.concat(cashflow_list, ignore_index=True)
        update_sheet(cashflow_df, creds)
    else:
        print("❌ Không thu được dữ liệu cash flow nào.")


if __name__ == "__main__":
    main()