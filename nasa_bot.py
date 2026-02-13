import requests
from google import genai
import os
import sys
import time
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# 載入 .env 檔案
load_dotenv()

# ================= 設定區 =================
# 從 GitHub Secrets 讀取金鑰，安全又方便
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NASA_API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")

# Line Bot 設定
LINE_TOKEN = os.environ.get("LINE_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
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
        # print(f"🤖 AI 原始回覆 (Debug):\n{text}")
        # print("======== (End of AI Response) ========")

        # === 🟢 超強段落解析邏輯 (State Machine) ===
        diary_lines = []
        knowledge_lines = []
        current_mode = None # 目前正在讀取哪個區塊 (diary / knowledge)

        # === 🟢 超強段落解析邏輯 (Regex Version) ===
        import re
        
        # 移除可能的 Markdown 標記 (如 **日記：**, ### 日記)
        clean_text = re.sub(r'[\*\#]', '', text)
        
        diary_match = re.search(r'日記[:：](.*?)(?=科普[:：]|$)', clean_text, re.DOTALL)
        knowledge_match = re.search(r'科普[:：](.*?)(?=$)', clean_text, re.DOTALL)

        diary = diary_match.group(1).strip() if diary_match else "（AI 正在看著星空發呆...）"
        knowledge = knowledge_match.group(1).strip() if knowledge_match else "（數據訊號干擾...）"
        
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

def generate_flex_message(data, diary, knowledge):
    """產生 NASA 宇宙日報 Flex Message JSON"""
    
    # 0. 準備資料
    title = data.get('title', 'NASA Unknown Star')
    date = data.get('date', 'Unknown Date')
    image_url = data.get('url')
    hd_url = data.get('hdurl', image_url)
    
    # 確保圖片 URL 是 HTTPS (Flex Message Hero 圖片必須是 HTTPS)
    if not image_url or not image_url.startswith("https"):
        image_url = "https://apod.nasa.gov/apod/calendar/allyears/2024/0101.jpg" # 預設圖
    
    # 1. 標題區塊 (Header)
    header = {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {"type": "text", "text": "🌌 NASA 宇宙日報", "weight": "bold", "size": "sm", "color": "#A9A9A9"},
            {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": "#FFFFFF", "wrap": True, "margin": "md"},
            {"type": "text", "text": f"📅 {date}", "size": "xs", "color": "#D3D3D3", "margin": "sm"}
        ],
        "paddingAll": "lg"
    }

    # 2. 英雄圖片 (Hero)
    hero = {
        "type": "image",
        "url": image_url,
        "size": "full",
        "aspectRatio": "20:13",
        "aspectMode": "cover",
        "action": {
            "type": "uri",
            "uri": hd_url
        }
    }

    # 3. 內容區塊 (Body)
    body = {
        "type": "box",
        "layout": "vertical",
        "contents": [
            # 📖 航行日誌
            {"type": "text", "text": "📖 航行日誌", "weight": "bold", "size": "sm", "color": "#8A2BE2"}, # BlueViolet
            {"type": "text", "text": diary, "size": "sm", "color": "#555555", "wrap": True, "margin": "sm", "lineSpacing": "4px"},
            
            {"type": "separator", "margin": "lg"},
            
            # 🔭 天文小知識
            {"type": "text", "text": "🔭 天文小知識", "weight": "bold", "size": "sm", "color": "#4169E1", "margin": "lg"}, # RoyalBlue
            {"type": "text", "text": knowledge, "size": "sm", "color": "#555555", "wrap": True, "margin": "sm", "lineSpacing": "4px"}
        ],
        "paddingAll": "lg",
        "backgroundColor": "#F8F8FF" # GhostWhite 微微的藍白
    }

    # 4. 底部按鈕 (Footer)
    footer = {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {
                "type": "button",
                "action": {
                    "type": "uri",
                    "label": "👉 下載高清大圖",
                    "uri": hd_url
                },
                "style": "secondary",
                "color": "#4169E1",
                "height": "sm"
            },
            {
                "type": "button",
                "action": {
                    "type": "uri",
                    "label": "🔗 前往 NASA 官網",
                    "uri": "https://apod.nasa.gov/apod/astropix.html"
                },
                "margin": "sm",
                "height": "sm",
                "style": "link"
            },
            {"type": "text", "text": "Powered by NASA & Gemini AI", "size": "xxs", "color": "#aaaaaa", "align": "center", "margin": "md"}
        ],
        "paddingAll": "lg"
    }

    # 5. 組合樣式 (Bubble)
    # Styles 設定 header 為深色背景
    styles = {
        "header": {
            "backgroundColor": "#191970" # MidnightBlue
        }
    }

    flex_message = {
        "type": "flex",
        "altText": f"🌌 NASA 宇宙日報: {title}",
        "contents": {
            "type": "bubble",
            "header": header,
            "hero": hero,
            "body": body,
            "footer": footer,
            "styles": styles
        }
    }
    return flex_message

def send_line_message(data, diary, knowledge):
    # 檢查 Token 是否存在
    if not LINE_TOKEN:
        print("⚠️ 未設定 LINE_TOKEN，跳過 LINE 發送。")
        return

    # 檢查是否有 User ID 或 API URL
    subscriber_api_url = os.getenv("SUBSCRIBER_API_URL")
    if not LINE_USER_ID and not subscriber_api_url:
        print("⚠️ 未設定 LINE_USER_ID 且無 SUBSCRIBER_API_URL，跳過 LINE 發送。")
        return

    print("🚀 正在發送 Line Flex Message...")
    
    # 產生 Flex Message payload
    flex_payload = generate_flex_message(data, diary, knowledge)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }

    payload = {
        "to": "", # 會在迴圈中設定
        "messages": [flex_payload]
    }

    # 支援發送給多個使用者或群組 (以逗號分隔)
    # 取得訂閱者列表 (合併 .env 與 GAS API)
    user_ids = set()
    
    # 1. 從 .env 讀取
    if LINE_USER_ID:
        for uid in LINE_USER_ID.split(","):
            if uid.strip():
                user_ids.add(uid.strip())

    # 2. 從 GAS API 讀取 (自動訂閱)
    subscriber_api_url = os.getenv("SUBSCRIBER_API_URL")
    if subscriber_api_url:
        try:
            print(f"📡 正在從 GAS API 取得訂閱者列表...")
            resp = requests.get(subscriber_api_url)
            if resp.status_code == 200:
                api_ids = resp.json()
                print(f"✅ 取得 {len(api_ids)} 個訂閱者: {api_ids}")
                for uid in api_ids:
                    user_ids.add(uid)
            else:
                print(f"⚠️ GAS API 回傳錯誤: {resp.status_code}")
        except Exception as e:
            print(f"⚠️ 讀取訂閱者 API 失敗: {e}")
    
    if not user_ids:
        print("⚠️ 無任何訂閱者 ID (LINE_USER_ID 未設定且 API 無回傳)")
        return

    for uid in user_ids:
        payload["to"] = uid
        try:
            response = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
            if response.status_code == 200:
                print(f"✅ Line 發送成功！(Target: {uid})")
            else:
                print(f"❌ Line 發送失敗 (Target: {uid}): {response.status_code} {response.text}")
        except Exception as e:
            print(f"❌ Line 發送例外 (Target: {uid}): {e}")

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
            if WEBHOOK_URL:
                send_discord(nasa_data, d, k)
            send_line_message(nasa_data, d, k)
        else:
            print(f"⚠️ 今天 NASA 給的是影片，跳過不發圖。")
    else:
        print("❌ 最終嘗試失敗：NASA API 和 官網都無法讀取。")
        sys.exit(1)
