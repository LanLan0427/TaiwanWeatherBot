import requests
from google import genai
import os
import sys
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

# ================= 設定區 =================
# 從 GitHub Secrets 讀取金鑰，安全又方便
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NASA_API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")
# ==========================================

# --- 功能 1: 嘗試從 API 抓取 (正門) ---
def get_nasa_from_api():
    print("🚀 嘗試連線 NASA API (正門)...")
    url = f"https://api.nasa.gov/planetary/apod?api_key={NASA_API_KEY}"
    
    # 設定重試策略 (避免網路瞬斷)
    retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            print("✅ API 連線成功！")
            return resp.json()
    except Exception as e:
        print(f"⚠️ API 連線失敗: {e}")
    return None

# --- 功能 2: 嘗試從網頁爬取 (窗戶 - B計畫) ---
def get_nasa_from_website():
    print("🪟 API 失敗，改由爬蟲抓取 NASA 官網 (B計畫)...")
    url = "https://apod.nasa.gov/apod/astropix.html"
    
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200: return None
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # 抓圖片 (通常在 IMG 標籤裡)
        img_tag = soup.find("img")
        if not img_tag: return None
        img_url = "https://apod.nasa.gov/apod/" + img_tag["src"]
        
        # 抓標題 (通常在 center > b 裡)
        title = "NASA Unknown Star"
        center_tags = soup.find_all("center")
        if len(center_tags) >= 2:
            title_tag = center_tags[1].find("b")
            if title_tag: title = title_tag.text.strip()

        print("✅ 網頁爬取成功！")
        return {
            "title": title,
            "url": img_url,
            "hdurl": img_url,
            "explanation": "（從網頁抓取，無原文解釋，請 AI 自由發揮）",
            "date": time.strftime("%Y-%m-%d"),
            "media_type": "image"
        }
    except Exception as e:
        print(f"❌ 爬蟲也失敗: {e}")
        return None

# --- 功能 3: 呼叫 Gemini (含寬鬆解析) ---
def get_ai_content_v2(title, explanation):
    print("🧠 呼叫 gemini-3-flash-preview...")
    
    prompt_context = f"原文解說：{explanation}"
    if "無原文解釋" in explanation:
        prompt_context = "原文無法讀取，請你根據標題和圖片主題，發揮想像力寫作。"

    prompt = f"""
    標題：{title}
    {prompt_context}

    請產出兩段內容 (繁體中文)：
    1. 【宇宙日記】：用第一人稱寫一段短日記(50字內)，描述看到這景象的感性心情，帶點孤獨或浪漫。
    2. 【天文科普】：用「白話文」簡單解釋這張照片是什麼(星雲?黑洞?彗星?)，以及它有什麼特別之處(100字內)。

    格式：
    日記：(內容)
    科普：(內容)
    """
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-3-flash-preview", 
            contents=prompt
        )
        text = response.text
        print(f"🤖 AI 原始回覆 (Debug):\n{text}")

        # === 🟢 超強段落解析邏輯 (State Machine) ===
        diary_lines = []
        knowledge_lines = []
        current_mode = None # 目前正在讀取哪個區塊 (diary / knowledge)

        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line: continue # 跳過空行

            # 1. 偵測標頭：如果是「日記」開頭
            if "日記" in line and ("：" in line or ":" in line):
                current_mode = "diary"
                # 如果同一行就有字 (例如: "日記：今天...")，把標頭去掉後留下來
                content = line.replace("：", ":").split(":", 1)[1].strip()
                if content: diary_lines.append(content)
                continue

            # 2. 偵測標頭：如果是「科普」開頭
            elif "科普" in line and ("：" in line or ":" in line):
                current_mode = "knowledge"
                content = line.replace("：", ":").split(":", 1)[1].strip()
                if content: knowledge_lines.append(content)
                continue

            # 3. 根據目前的模式，把內容加進去
            if current_mode == "diary":
                diary_lines.append(line)
            elif current_mode == "knowledge":
                knowledge_lines.append(line)

        # 把抓到的多行內容接起來
        diary = " ".join(diary_lines) if diary_lines else "（AI 正在看著星空發呆...）"
        knowledge = " ".join(knowledge_lines) if knowledge_lines else "（數據訊號干擾...）"
        
        return diary, knowledge

    except Exception as e:
        print(f"⚠️ AI 生成失敗: {e}")
        return "AI 休息中...", "暫無資料"

# --- 功能 4: 發送 Discord 卡片 ---
def send_discord(data, diary, knowledge):
    print("📡 發送 Discord...")
    
    date_str = data.get('date', '')
    if len(date_str) >= 10:
        short_date = date_str.replace("-", "")[2:] 
        perm_link = f"https://apod.nasa.gov/apod/ap{short_date}.html"
    else:
        perm_link = "https://apod.nasa.gov/apod/astropix.html"

    embed = {
        "title": f"🌌 {data.get('title')}",
        "url": perm_link,
        "description": f"**📖 航行日誌**\n> {diary}", # 使用引用符號
        "color": 3447003, # 深藍色
        "fields": [
            {
                "name": "🔭 天文小知識",
                "value": knowledge,
                "inline": False
            },
            {
                "name": "🔗 相關連結",
                "value": f"[前往 NASA 官網]({perm_link}) | [下載高畫質原圖]({data.get('hdurl', data.get('url'))})",
                "inline": False
            }
        ],
        "image": {
            "url": data.get('url')
        },
        "footer": {
            "text": f"📅 {data.get('date')} • Powered by NASA & Gemini"
        }
    }

    try:
        requests.post(WEBHOOK_URL, json={"embeds": [embed]})
        print("✅ Discord 發送成功！")
    except Exception as e:
        print(f"❌ Discord 發送失敗: {e}")

# --- 主程式 ---
if __name__ == "__main__":
    if not WEBHOOK_URL or not GEMINI_API_KEY:
        print("❌ 錯誤：請檢查 GitHub Secrets 是否設定正確")
        sys.exit(1)

    # 1. 先試 API，不行就試爬蟲
    nasa_data = get_nasa_from_api()
    if not nasa_data:
        nasa_data = get_nasa_from_website()
    
    # 2. 如果有拿到資料，就叫 AI寫作並發送
    if nasa_data:
        # 檢查是不是圖片 (影片無法顯示在 Embed image)
        if "image" in nasa_data.get('media_type', 'image'):
            d, k = get_ai_content_v2(nasa_data['title'], nasa_data.get('explanation', '無原文解釋'))
            send_discord(nasa_data, d, k)
        else:
            print(f"⚠️ 今天 NASA 給的是影片，跳過不發圖。")
    else:
        print("❌ 最終嘗試失敗：NASA API 和 官網都無法讀取。")
        sys.exit(1)
