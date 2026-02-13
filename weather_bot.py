import requests
from google import genai  # 🟢 改用新版 SDK
import os
import sys
from dotenv import load_dotenv

# 載入 .env 檔案
load_dotenv()

# ================= 設定區 =================
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CWA_API_KEY = os.environ.get("CWA_API_KEY")
# ==========================================

# Line Bot 設定
LINE_TOKEN = os.environ.get("LINE_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

# 1. 檢查鑰匙有沒有帶到 (除錯關鍵)
if not CWA_API_KEY:
    print("❌ 嚴重錯誤：找不到 CWA_API_KEY！")
    print("請檢查你的 .github/workflows/xxx.yml 裡面，env: 底下有沒有寫 CWA_API_KEY")
    sys.exit(1)

# 📍 定義區域與縣市對照表
REGION_MAP = {
    "北部地區": ["基隆市", "臺北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣"],
    "中部地區": ["臺中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣"],
    "南部地區": ["臺南市", "高雄市", "屏東縣"],
    "東部地區": ["宜蘭縣", "花蓮縣", "臺東縣"],
    "外島地區": ["澎湖縣", "金門縣", "連江縣"]
}

def get_taiwan_weather_data():
    print("📡 正在抓取氣象局資料...")
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={CWA_API_KEY}&format=JSON"
    
    try:
        response = requests.get(url, timeout=10)
        
        # 🟢 除錯重點：如果狀態碼不是 200，印出原因
        if response.status_code != 200: 
            print(f"❌ 氣象局拒絕連線 (Code: {response.status_code})")
            print(f"回傳內容: {response.text}") # 看看它到底說什麼
            return None, None, None
            
        data = response.json()
        location_list = data['records']['location']
        
        weather_data = {} 
        raw_data_list = [] 
        
        for location in location_list:
            city = location['locationName']
            wx = location['weatherElement'][0]['time'][0]['parameter']['parameterName']
            pop = location['weatherElement'][1]['time'][0]['parameter']['parameterName']
            min_t = location['weatherElement'][2]['time'][0]['parameter']['parameterName']
            max_t = location['weatherElement'][4]['time'][0]['parameter']['parameterName']
            
            pop_val = int(pop)
            if pop_val >= 60: icon = "🌧️"
            elif pop_val >= 30: icon = "☂️"
            elif "晴" in wx: icon = "☀️"
            else: icon = "☁️"
            
            display_line = f"**{city}**\n└ {icon} {min_t}-{max_t}°C | 降雨 {pop}%"
            # 🟢 [關鍵修改] 這裡把資料分兩份：
            # 1. "display": 專門給 Discord 用的字串 (保留 **粗體** 格式)
            # 2. 其他欄位 (city, min_t, etc): 給 Line Flex Message 用 (乾淨的數據，方便重新排版)
            weather_data[city] = {
                "display": display_line,  # 給 Discord 吃這行
                "city": city,             # 以下給 Line 吃
                "icon": icon,
                "min_t": min_t,
                "max_t": max_t,
                "pop": pop_val
            }
            raw_data_list.append(f"{city}: {wx}, 氣溫{min_t}-{max_t}, 降雨{pop}%")

        start_time = location_list[0]['weatherElement'][0]['time'][0]['startTime']
        end_time = location_list[0]['weatherElement'][0]['time'][0]['endTime']
        time_range = f"{start_time} ~ {end_time}"
        
        return weather_data, raw_data_list, time_range

    except Exception as e:
        print(f"❌ 抓取資料發生例外: {e}")
        return None, None, None

def get_ai_comment(raw_data_list):
    print("☕ 呼叫 gemini-3-flash-preview...")
    weather_text = "\n".join(raw_data_list)
    
    prompt = f"""
    你是個講話「輕鬆幽默」且「點到為止」的氣象播報員。
    以下是台灣最新的天氣預報數據：
    {weather_text}

    請產出氣象評論 (150字內，繁體中文)，請包含：
    1. 【今日重點】：平舖直敘天氣狀況。
    2. 【天氣觀察】：選一個地區簡單描述生活共鳴。
    3. 【貼心叮嚀】：穿搭或生活建議。
    """
    
    try:
        # 🟢 改用新版 client 寫法
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-3-flash-preview", 
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"❌ AI 錯誤: {e}")
        return "🐭 AI 氣象鼠正在啃瓜子，暫時無法提供評論..."

def send_webhook(weather_data, ai_comment, time_range):
    print("🚀 正在組裝 Discord 卡片...")
    
    embed = {
        "title": "🌤️ 全台氣象播報",
        "description": f"📅 **預報時間**\n{time_range}",
        "color": 15105570,
        "fields": [],
        "footer": {
            "text": "Powered by CWA & Gemini AI"
        }
    }
    
    for region_name, cities in REGION_MAP.items():
        region_content = ""
        for city in cities:
            if city in weather_data:
                # 🟢 [Discord 專用] 這裡只拿 "display" 那一格
                # 所以 Discord 收到的還是原本的格式 (含粗體)，完全不受 Line 改版的影響
                region_content += weather_data[city]["display"] + "\n"
        
        if region_content:
            embed["fields"].append({
                "name": f"🔹 {region_name}",
                "value": region_content,
                "inline": True
            })

    embed["fields"].append({
        "name": "🐭 Ai氣象鼠點評",
        "value": f">>> {ai_comment}",
        "inline": False
    })

    data = {"content": "", "embeds": [embed]}
    
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("✅ 發送完成！")
    except Exception as e:
        print(f"❌ Discord 發送失敗: {e}")

def generate_flex_message(weather_data, ai_comment, time_range):
    """產生 Line Flex Message JSON"""
    contents = []

    # 1. 標題區塊
    header = {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {"type": "text", "text": "🌤️ 全台氣象播報", "weight": "bold", "size": "xl", "color": "#ffffff"},
            {"type": "text", "text": f"📅 {time_range}", "size": "xs", "color": "#eeeeee", "margin": "sm"}
        ],
        "backgroundColor": "#00B900", # Line Green
        "paddingAll": "lg"
    }

    # 2. 內容區塊 (分區顯示)
    body_contents = []
    
    for region_name, cities_list in REGION_MAP.items():
        # 區域標題
        body_contents.append({
            "type": "box",
            "layout": "vertical",
            "margin": "lg",
            "contents": [
                {"type": "text", "text": region_name, "weight": "bold", "color": "#1DB446", "size": "sm"},
                {"type": "separator", "margin": "sm"}
            ]
        })

        # 城市列表
        for city in cities_list:
            if city in weather_data:
                d = weather_data[city]
                pop_color = "#ff3333" if d['pop'] >= 50 else "#666666"
                
                row = {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "sm",
                    "contents": [
                        {"type": "text", "text": d['city'], "size": "sm", "flex": 2, "color": "#333333"},
                        {"type": "text", "text": d['icon'], "size": "sm", "flex": 1, "align": "center"},
                        {"type": "text", "text": f"{d['min_t']}-{d['max_t']}°", "size": "sm", "flex": 2, "align": "center", "color": "#333333"},
                        {"type": "text", "text": f"☂️{d['pop']}%", "size": "sm", "flex": 2, "align": "end", "color": pop_color}
                    ]
                }
                body_contents.append(row)

    # 3. AI 點評區塊 in Footer
    footer = {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {"type": "separator", "margin": "md"},
            {"type": "text", "text": "🐭 Ai氣象鼠點評", "weight": "bold", "size": "sm", "margin": "md", "color": "#555555"},
            {"type": "text", "text": ai_comment, "size": "xs", "color": "#777777", "wrap": True, "margin": "sm"}
        ],
        "backgroundColor": "#f8f8f8",
        "paddingAll": "md"
    }

    # 組合 Flex Message
    flex_message = {
        "type": "flex",
        "altText": f"🌤️ 全台氣象播報 ({time_range})",
        "contents": {
            "type": "bubble",
            "header": header,
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": body_contents
            },
            "footer": footer
        }
    }
    return flex_message

def send_line_message(weather_data, ai_comment, time_range):
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
    flex_payload = generate_flex_message(weather_data, ai_comment, time_range)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    
    payload = {
        "to": "",  # 會在迴圈中設定
        "messages": [flex_payload]
    }

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
    w_data, raw_list, t_range = get_taiwan_weather_data()
    if w_data:
        comment = get_ai_comment(raw_list)
        comment = get_ai_comment(raw_list)
        if WEBHOOK_URL:
            send_webhook(w_data, comment, t_range)
        send_line_message(w_data, comment, t_range)
