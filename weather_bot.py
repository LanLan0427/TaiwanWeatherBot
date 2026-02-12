import requests
from google import genai  # 🟢 改用新版 SDK
import os
import sys

# ================= 設定區 =================
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CWA_API_KEY = os.environ.get("CWA_API_KEY")
# ==========================================

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
            weather_data[city] = display_line
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
                region_content += weather_data[city] + "\n"
        
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

if __name__ == "__main__":
    w_data, raw_list, t_range = get_taiwan_weather_data()
    if w_data:
        comment = get_ai_comment(raw_list)
        send_webhook(w_data, comment, t_range)

