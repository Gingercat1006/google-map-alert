import asyncio
import os
import requests
import json
import re 
from playwright.async_api import async_playwright

# ================= 設定エリア =================
TARGET_URL = "https://www.google.com/maps/place/%E3%81%8F%E3%82%89%E5%AF%BF%E5%8F%B8+%E5%AF%9D%E5%B1%8B%E5%B7%9D%E6%89%93%E4%B8%8A%E5%BA%97/@34.758988,135.6562656,17z/data=!3m1!4b1!4m6!3m5!1s0x60011ee0b8a31271:0x692c89b1427ba689!8m2!3d34.758988!4d135.6562656!16s%2Fg%2F1tptqj6v?entry=ttu"

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("LINE_USER_ID")
SAVE_FILE = "last_review.txt"
# ==============================================

def send_line_message(text):
    if not CHANNEL_ACCESS_TOKEN:
        print("LINE設定が見つかりません")
        return

    # ★全員送信用のURL
    url = "https://api.line.me/v2/bot/message/broadcast"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    
    data = {
        "messages": [{"type": "text", "text": text}]
    }
    
    try:
        # ★ここで1回だけ全員に送る（これで完了！）
        requests.post(url, headers=headers, data=json.dumps(data))
        print("LINEに通知を送りました（全員宛）")
    except Exception as e:
        print(f"LINE送信エラー: {e}")

    # ★注意：ここに書いてあった「2回目の送信処理」は完全に消しました！
    # これがあると「全員に2回」届いてしまいます。

# -----------------------------------------------------------
# 以下は変更なし（そのままコピーしてください）
# -----------------------------------------------------------
def normalize_text(text):
    text = re.sub(r'\d+\s*(分|時間|日|週間|か?ヶ?月|年)前', '', text)
    text = re.sub(r'(新規|先月|先週|昨日|今日)', '', text)
    text = re.sub(r'\s+', '', text) 
    return text

async def get_latest_review():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="ja-JP", 
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("ページにアクセス中...")
        try:
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        except:
            print("アクセス不可")
            await browser.close()
            return

        await page.wait_for_timeout(5000)

        try:
            await page.locator('button[role="tab"]', has_text="クチコミ").click()
            await page.wait_for_timeout(2000)
        except:
            pass 

        try:
            await page.locator("button", has_text="並べ替え").click()
            await page.wait_for_timeout(2000)
        except:
            pass

        try:
            if await page.locator('[role="menuitemradio"]', has_text="新しい順").count() > 0:
                await page.locator('[role="menuitemradio"]', has_text="新しい順").first.click()
            else:
                await page.get_by_text("新しい順").click()
            
            await page.wait_for_timeout(3000)
        except:
            pass

        reviews = page.locator('div[data-review-id]')
        if await reviews.count() > 0:
            raw_text = await reviews.first.inner_text()
            current_signature = normalize_text(raw_text[:150]) 
            last_signature = ""
            if os.path.exists(SAVE_FILE):
                with open(SAVE_FILE, "r", encoding="utf-8") as f:
                    last_signature = f.read().strip()

            print(f"今回: {current_signature[:30]}...")
            print(f"前回: {last_signature[:30]}...")

            if current_signature != last_signature:
                if len(current_signature) > 5:
                    print("新しい投稿あり")
                    msg = f"【新しいクチコミ】\n{raw_text[:200]}..."
                    send_line_message(msg)
                    with open(SAVE_FILE, "w", encoding="utf-8") as f:
                        f.write(current_signature)
            else:
                print("変更なし")
        else:
            print("クチコミ取得失敗")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_latest_review())