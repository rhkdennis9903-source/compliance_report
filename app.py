import streamlit as st
import os
import google.generativeai as genai
from dotenv import load_dotenv
import PyPDF2
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# =========================================================
# Config
# =========================================================
st.set_page_config(
    page_title="AI 文案法規合規性檢測助手 (雲端連線版)",
    page_icon="⚖️",
    layout="wide"
)

# 🔴 請將你的 PDF 檔案 ID 貼在這裡
# 從 Google Drive 連結抓取: https://drive.google.com/file/d/【就是這一串】/view
DRIVE_FILE_ID = "10rpQHKAzc2VnHPV9YGnVGoJy78Gr7lXk" 

# =========================================================
# Helper Functions: Google Drive
# =========================================================
@st.cache_data(ttl=3600) # 快取 1 小時，避免每次按按鈕都重新下載 PDF
def load_pdf_from_drive_api(file_id):
    """
    使用 Service Account 從 Google Drive 下載 PDF 並提取文字
    """
    if not file_id or "請將" in file_id:
        return None, "請先在程式碼中設定正確的 DRIVE_FILE_ID"

    try:
        # 1. 取得憑證 (從 Streamlit Secrets)
        if "gcp_service_account" not in st.secrets:
            return None, "找不到 Secrets 設定"
            
        creds_dict = dict(st.secrets["gcp_service_account"])
        # 修正私鑰換行問題
        if "\\n" in creds_dict["private_key"]:
             creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )

        # 2. 建立 Drive API 服務
        service = build('drive', 'v3', credentials=creds)

        # 3. 下載檔案
        request = service.files().get_media(fileId=file_id)
        file_stream = BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        # 4. 解析 PDF
        file_stream.seek(0) # 回到檔案開頭
        reader = PyPDF2.PdfReader(file_stream)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
            
        return text, None

    except Exception as e:
        return None, f"讀取雲端 PDF 失敗: {str(e)}"

def extract_text_from_uploaded_file(uploaded_file):
    """(保留) 從使用者手動上傳的檔案中提取文字"""
    if uploaded_file is None: return ""
    try:
        if uploaded_file.type == "application/pdf":
            reader = PyPDF2.PdfReader(uploaded_file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        elif uploaded_file.type == "text/plain":
            return uploaded_file.getvalue().decode("utf-8")
        return ""
    except Exception as e:
        return ""

def analyze_compliance(api_key, ad_copy, reference_data):
    """Gemini 分析邏輯"""
    if not api_key: return "請輸入 API Key"

    genai.configure(api_key=api_key)
    # 優先使用最新的推理模型
    model_name = "gemini-3-pro-preview" 
    
    system_instruction = """
    你是一位精通台灣法規的「首席合規長」。你的任務是依據【違規資料庫】與【台灣法規】審查文案。
    比對原則：
    1. 若文案出現與【違規資料庫】相似的詞彙或邏輯，視為極高風險。
    2. 嚴格審查「療效」、「誇大」、「保證」等概念。
    """
    
    try:
        model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
        prompt = f"""
        請分析以下文案的合規性：

        ### 1. 核心判例標準（來自雲端資料庫）：
        {reference_data}

        ### 2. 待審文案：
        {ad_copy}

        ---
        請輸出 Markdown 報告：
        1. **風險評級**
        2. **違規熱點與解釋** (請明確指出違反資料庫中哪一條)
        3. **修改建議**
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 分析錯誤: {e}"

# =========================================================
# Sidebar
# =========================================================
with st.sidebar:
    st.header("⚙️ 設定")
    
    # API Key 處理
    env_api_key = os.getenv("GOOGLE_API_KEY")
    if "GOOGLE_API_KEY" in st.secrets:
        env_api_key = st.secrets["GOOGLE_API_KEY"]

    api_key = st.text_input("Google Gemini API Key", value=env_api_key if env_api_key else "", type="password")
    
    st.markdown("---")
    st.subheader("📡 資料庫狀態")
    
    # 自動讀取雲端 PDF
    with st.spinner("正在連線 Google Drive 讀取法規資料庫..."):
        cloud_db_text, error_msg = load_pdf_from_drive_api(DRIVE_FILE_ID)
    
    if cloud_db_text:
        st.success(f"✅ 雲端資料庫已連線\n(字數: {len(cloud_db_text)})")
    else:
        st.error(f"❌ 雲端連線失敗\n{error_msg}")
        st.caption("請檢查 FILE_ID 或共用權限")

# =========================================================
# Main UI
# =========================================================
st.title("🛡️ 文案合規快篩 (Cloud Database)")
st.caption("法規資料庫由 Google Drive 自動同步，無需手動上傳。")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. 審核依據")
    if cloud_db_text:
        st.info("💡 系統已自動載入最新的「雲端違規案例資料庫」。")
        with st.expander("查看目前資料庫內容前 500 字"):
            st.text(cloud_db_text[:500] + "...")
    else:
        st.warning("雲端讀取失敗，請手動上傳備用檔案：")
        uploaded_db = st.file_uploader("手動上傳資料庫 (PDF)", type=["pdf"])
        if uploaded_db:
            cloud_db_text = extract_text_from_uploaded_file(uploaded_db)

with col2:
    st.subheader("2. 輸入文案")
    tab_text, tab_file = st.tabs(["貼上文字", "上傳檔案"])
    
    ad_text = ""
    with tab_text:
        raw_text = st.text_area("直接貼上文案", height=200)
        if raw_text: ad_text = raw_text
        
    with tab_file:
        up_file = st.file_uploader("上傳文案檔案", type=["pdf", "txt"])
        if up_file: ad_text = extract_text_from_uploaded_file(up_file)

st.markdown("---")

if st.button("🚀 執行合規分析", type="primary", use_container_width=True):
    if not api_key:
        st.warning("缺少 API Key")
    elif not ad_text:
        st.warning("請輸入文案內容")
    elif not cloud_db_text:
        st.warning("資料庫未載入，無法分析")
    else:
        with st.spinner("Gemini 3 Pro 正在交叉比對雲端資料庫..."):
            result = analyze_compliance(api_key, ad_text, cloud_db_text)
            st.markdown("### 分析報告")
            st.markdown(result)
