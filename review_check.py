import asyncio
import os
import requests
import json
import re 
from playwright.async_api import async_playwright

# ================= 設定エリア =================
TARGET_URL = "https://www.google.com/maps/place/%E3%81%8F%E3%82%89%E5%AF%BF%E5%8F%B8+%E5%AF%9D%E5%B1%8B%E5%B7%9D%E6%89%93%E4%B8%8A%E5%BA%97/@34.758988,135.6562656,17z/data=!3m1!4b1!4m6!3m5!1s0x60011ee0b8a31271:0x692c89b1427ba689!8m2!3d34.758988!4d135.6562656!16s%2Fg%2F1tptqj6v?entry=ttu&hl=ja"

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("LINE_USER_ID")
SAVE_FILE = "last_review.txt"
# ==============================================

def send_line_message(text):
    if not CHANNEL_ACCESS_TOKEN:
        print("LINE設定が見つかりません")
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
        print("ブラウザを起動します...")
        browser = await p.chromium.launch(headless=True)
        # PC画面サイズ固定
        context = await browser.new_context(
            locale="ja-JP", 
            timezone_id="Asia/Tokyo",
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"URLにアクセス中...")
        try:
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
        except:
            print("【エラー】ページにアクセスできませんでした")
            await browser.close()
            return

        # 同意ポップアップ対策
        try:
            consent_button = page.locator('button', has_text=re.compile(r"(すべて同意|Accept all)"))
            if await consent_button.count() > 0:
                print("同意ポップアップを消します...")
                await consent_button.first.click()
                await page.wait_for_timeout(3000)
        except:
            pass 

        # 1. クチコミタブクリック（★ここを修正：部分一致OKにする）
        try:
            print("「クチコミ」タブを探しています...")
            
            # 戦略A: aria-label に "クチコミ" が含まれるボタン (完全一致ではなく部分一致 '*=')
            tab_btn = page.locator('button[aria-label*="クチコミ"], button[aria-label*="Reviews"]')
            
            if await tab_btn.count() > 0:
                await tab_btn.first.click()
                print("OK: クチコミタブ（aria-label部分一致）をクリックしました")
            else:
                # 戦略B: ボタンの中に「クチコミ」という文字がある場合
                print("ラベルで見つからないため、テキストを含むボタンを探します...")
                text_btn = page.locator('button').filter(has_text=re.compile(r"(クチコミ|Reviews)")).first
                if await text_btn.count() > 0:
                    await text_btn.click()
                    print("OK: テキストを含むボタンをクリックしました")
                else:
                    # 戦略C: 「500件」のような件数リンクをクリック（これが一番確実な場合が多い）
                    print("ボタンが見つからないため、件数リンクを探します...")
                    count_link = page.locator(':text-matches("(\\d+)\\s*(件の)?(クチコミ|Reviews)")').first
                    await count_link.click()
                    print("OK: 件数リンクをクリックしました")
            
            await page.wait_for_timeout(5000)

        except Exception as e:
            print(f"【失敗】クチコミタブ操作エラー: {e}")

        # 2. 並べ替え
        try:
            print("並べ替えを試みます...")
            
            # パターンA: 並べ替えボタン
            sort_btn = page.locator('button[aria-label*="並べ替え"], button[aria-label*="Sort"]')
            
            if await sort_btn.count() > 0:
                print("「並べ替え」ボタンが見つかりました。クリックします。")
                await sort_btn.first.click()
                await page.wait_for_timeout(2000)
                
                # メニューから「新しい順」
                newest_option = page.locator('[role="menuitemradio"], div[role="menuitem"]').filter(has_text=re.compile(r"(新しい順|Newest)"))
                if await newest_option.count() > 0:
                    await newest_option.first.click()
                    print("OK: メニューから「新しい順」を選択しました")
                else:
                    # テキストクリック（バックアップ）
                    await page.get_by_text(re.compile(r"(新しい順|Newest)")).first.click()
                    print("OK: テキストで「新しい順」を選択しました")

            else:
                print("並べ替えボタンなし。直接「最新」ボタンを探します...")
                # パターンB: 直接ボタン (新しい順、最新、Newest)
                direct_btn = page.locator('button').filter(has_text=re.compile(r"(^新しい順$|^Newest$|^最新$)")).first
                
                if await direct_btn.count() > 0:
                    await direct_btn.click()
                    print("OK: 「最新」ボタンを直接クリックしました")
                else:
                    print("【注意】並べ替えボタンが見つかりませんでした。デフォルト順の可能性があります。")

            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"【失敗】並べ替えエラー: {e}")

        # 3. 取得と判定
        reviews = page.locator('div[data-review-id]')
        count = await reviews.count()
        print(f"見つかった口コミの数: {count}件")

        if count > 0:
            raw_text = await reviews.first.inner_text()
            preview_text = raw_text[:50].replace('\n', ' ')
            print(f"【最新の口コミ内容】: {preview_text}...")

            current_signature = normalize_text(raw_text[:150]) 
            last_signature = ""
            if os.path.exists(SAVE_FILE):
                with open(SAVE_FILE, "r", encoding="utf-8") as f:
                    last_signature = f.read().strip()

            if current_signature != last_signature:
                if len(current_signature) > 5:
                    print("★判定: 新しい投稿です！通知を送ります。")
                    msg = f"【新しいクチコミ】\n{raw_text[:200]}..."
                    send_line_message(msg)
                    with open(SAVE_FILE, "w", encoding="utf-8") as f:
                        f.write(current_signature)
            else:
                print("★判定: 前回と同じでした")
        else:
            print("【エラー】口コミ要素が見つかりませんでした")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_latest_review())