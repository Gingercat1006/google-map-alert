import asyncio
import os
import requests
import json
import re 
from playwright.async_api import async_playwright

# ================= 設定エリア =================
TARGET_URL = "https://www.google.com/maps/place/%E3%81%8F%E3%82%89%E5%AF%BF%E5%8F%B8+%E5%AF%9D%E5%B1%8B%E5%B7%9D%E6%89%93%E4%B8%8A%E5%BA%97/@34.758988,135.6562656,17z/data=!3m1!4b1!4m5!3m4!1s0x60011ee0b8a31271:0x692c89b1427ba689!8m2!3d34.758988!4d135.6562656?hl=ja"

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
SAVE_FILE = "last_review.txt"
# ==============================================

def send_line_message(text):
    if not CHANNEL_ACCESS_TOKEN:
        print("LINE設定なし")
        return
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    data = {"messages": [{"type": "text", "text": text}]}
    try:
        requests.post(url, headers=headers, data=json.dumps(data))
        print("LINEに通知を送りました")
    except Exception as e:
        print(f"LINE送信エラー: {e}")

def normalize_text(text):
    text = re.sub(r'\d+\s*(分|時間|日|週間|か?ヶ?月|年)前', '', text)
    text = re.sub(r'(新規|先月|先週|昨日|今日)', '', text)
    text = re.sub(r'\s+', '', text) 
    return text

async def get_latest_review():
    async with async_playwright() as p:
        print("\n=== GitHub実行開始 ===")
        
        # ★重要：GitHubサーバー用設定
        # 1. headless=True (画面なし)
        # 2. 画面サイズ固定
        # 3. User-Agent偽装
        browser = await p.chromium.launch(headless=True)
        
        context = await browser.new_context(
            locale="ja-JP",
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("1. URLへ移動中...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)

        # ★★★ リロード処理（簡易版対策） ★★★
        print("2. 簡易版回避のためリロードします...")
        await page.reload(wait_until="domcontentloaded")
        print("   リロード完了。読み込み待ち...")
        await page.wait_for_timeout(5000)
        # ★★★★★★★★★★★★★★★★★★★★

        # ポップアップ対策（Escキー）
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(1000)

        # ---------------------------------------------------------
        # クチコミ画面へ移動
        # ---------------------------------------------------------
        print("クチコミ画面への移動を試みます...")
        
        try:
            # 「733件のクチコミ」リンクを狙う
            count_link = page.locator("button, a").filter(has_text=re.compile(r"\d+\s*件のクチコミ")).first
            
            if await count_link.count() > 0:
                print("★件数リンクを発見！クリックします")
                await count_link.click()
            else:
                print("件数リンクが見つかりません。タブを探します...")
                await page.locator('button[role="tab"][aria-label*="クチコミ"]').click()
            
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"移動失敗（次に進みます）: {e}")

        # ---------------------------------------------------------
        # 並べ替え
        # ---------------------------------------------------------
        print("「並べ替え」ボタンを探します...")
        try:
            sort_btn = page.locator('button[data-value="並べ替え"]').first
            
            if await sort_btn.count() > 0:
                print("並べ替えボタンをクリック")
                await sort_btn.click()
                await page.wait_for_timeout(1000)
                
                print("「新しい順」を選択...")
                await page.locator('[data-value="新しい順"], [role="menuitemradio"]').filter(has_text="新しい順").first.click()
                await page.wait_for_timeout(3000)
            else:
                print("⚠️並べ替えボタンなし（デフォルト順で取得）")
        except:
            pass

        # ---------------------------------------------------------
        # 取得
        # ---------------------------------------------------------
        print("リストを読み込んでいます...")
        try:
            await page.mouse.move(100, 300)
            await page.mouse.wheel(0, 1000)
            await page.wait_for_timeout(2000)
        except:
            pass

        reviews = page.locator('div[data-review-id]')
        count = await reviews.count()
        print(f"取得できた口コミ数: {count}件")

        if count > 0:
            raw_text = await reviews.first.inner_text()
            # ログには最初の50文字だけ出す
            print(f"【最新口コミ】: {raw_text[:50].replace('\n', ' ')}...")
            
            current_signature = normalize_text(raw_text[:150]) 
            last_signature = ""
            if os.path.exists(SAVE_FILE):
                with open(SAVE_FILE, "r", encoding="utf-8") as f:
                    last_signature = f.read().strip()

            if current_signature != last_signature:
                if len(current_signature) > 5:
                    print("★新しい投稿です！通知します")
                    msg = f"【クチコミ検知】\n{raw_text[:200]}..."
                    send_line_message(msg)
                    with open(SAVE_FILE, "w", encoding="utf-8") as f:
                        f.write(current_signature)
            else:
                print("前回と同じでした")
        else:
            print("❌まだ口コミが取得できません。画面を確認してください。")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_latest_review())