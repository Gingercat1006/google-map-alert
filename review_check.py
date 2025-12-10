import asyncio
import os
import requests
import json
import re 
from playwright.async_api import async_playwright

# ================= 設定エリア =================
# URLの最後に "&hl=ja" を追加
TARGET_URL = "https://www.google.com/maps/place/%E3%81%8F%E3%82%89%E5%AF%BF%E5%8F%B8+%E5%AF%9D%E5%B1%8B%E5%B7%9D%E6%89%93%E4%B8%8A%E5%BA%97/@34.758988,135.6562656,17z/data=!3m1!4b1!4m6!3m5!1s0x60011ee0b8a31271:0x692c89b1427ba689!8m2!3d34.758988!4d135.6562656!16s%2Fg%2F1tptqj6v?entry=ttu&hl=ja"

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("LINE_USER_ID")
SAVE_FILE = "last_review.txt"
# ==============================================

def send_line_message(text):
    if not CHANNEL_ACCESS_TOKEN:
        print("LINE設定が見つかりません")
        return

    # 全員送信（Broadcast）
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    data = {
        "messages": [{"type": "text", "text": text}]
    }
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
        # 画面サイズを大きめに固定
        context = await browser.new_context(
            locale="ja-JP", 
            timezone_id="Asia/Tokyo",
            viewport={"width": 1920, "height": 1080} 
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
                print("邪魔な同意ポップアップを消します...")
                await consent_button.first.click()
                await page.wait_for_timeout(3000)
        except:
            pass 

        # 1. クチコミタブ
        try:
            print("「クチコミ」タブを探しています...")
            # あらゆるパターンでタブを探す
            tab_btn = page.locator('button[role="tab"], button[aria-label*="クチコミ"], button:has-text("クチコミ"), button:has-text("Reviews")')
            
            # 複数のタブが見つかることがあるので、確実に「クチコミ」っぽいものを特定
            target_tab = tab_btn.filter(has_text=re.compile(r"(クチコミ|Reviews)")).first
            
            await target_tab.click()
            print("OK: クチコミタブをクリックしました")
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"【失敗】クチコミタブが見つかりません: {e}")
            await browser.close()
            return

        # 2. 並べ替え処理（パターンAとBの両対応）
        sorted_flag = False
        try:
            print("並べ替えを試みます...")
            
            # --- パターンA: 「並べ替え」ボタンがある場合 ---
            sort_btn = page.locator('button[aria-label*="並べ替え"], button[aria-label*="Sort"], button:has-text("並べ替え")')
            if await sort_btn.count() > 0:
                print("タイプA: 「並べ替え」ボタンが見つかりました。クリックします。")
                await sort_btn.first.click()
                await page.wait_for_timeout(2000)
                
                # メニューから「新しい順」を選ぶ
                newest_option = page.locator('[role="menuitemradio"], [role="menuitem"]').filter(has_text=re.compile(r"(新しい順|Newest)"))
                if await newest_option.count() > 0:
                    await newest_option.first.click()
                    print("OK: メニューから「新しい順」を選択しました")
                    sorted_flag = True
                else:
                    print("メニュー内に「新しい順」が見つかりませんでした")

            # --- パターンB: 「並べ替え」がなく、直接「最新」ボタンがある場合 ---
            if not sorted_flag:
                print("タイプAで失敗したため、タイプB（直接ボタン）を探します...")
                # 「最新」「新しい順」「Newest」という文字を持つボタンを探す
                direct_newest_btn = page.locator('button').filter(has_text=re.compile(r"(^最新$|新しい順|Newest)")).first
                
                if await direct_newest_btn.count() > 0:
                    await direct_newest_btn.click()
                    print("OK: 「最新」ボタンを直接クリックしました")
                    sorted_flag = True
                else:
                    print("タイプBのボタンも見つかりませんでした")

            await page.wait_for_timeout(5000) # リスト更新待ち

        except Exception as e:
            print(f"【失敗】並べ替え操作中にエラー: {e}")

        # 3. 取得と判定
        # data-review-id を持つdivを探す
        reviews = page.locator('div[data-review-id]')
        count = await reviews.count()
        print(f"見つかった口コミの数: {count}件")

        if count > 0:
            raw_text = await reviews.first.inner_text()
            
            # ログ確認用
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
                print("★判定: 前回と同じでした（通知なし）")
        else:
            print("【エラー】口コミ要素が見つかりませんでした。")
            print("考えられる原因: 並べ替えボタンが押せていないか、ページの読み込みが遅い可能性があります。")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_latest_review())