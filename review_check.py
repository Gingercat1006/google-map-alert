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

# ★診断用：画面にあるボタンの文字を全部表示する関数
async def debug_print_buttons(page, step_name):
    print(f"\n--- 【診断】{step_name} の時点で見えているボタン ---")
    try:
        # 画面上のボタン要素をすべて取得
        buttons = page.locator("button")
        count = await buttons.count()
        print(f"ボタンの数: {count}個")
        
        # 上位20個だけテキストを表示してみる
        for i in range(min(count, 20)):
            text = await buttons.nth(i).inner_text()
            aria = await buttons.nth(i).get_attribute("aria-label") or ""
            # 改行を消してきれいに表示
            clean_text = text.replace('\n', ' ').strip()
            if clean_text or aria:
                print(f"[{i}] テキスト: '{clean_text}' / ラベル: '{aria}'")
    except Exception as e:
        print(f"診断エラー: {e}")
    print("--------------------------------------------------\n")

async def get_latest_review():
    async with async_playwright() as p:
        print("ブラウザを起動します...")
        browser = await p.chromium.launch(headless=True)
        # 画面サイズをPC最大サイズに固定
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
                print("邪魔な同意ポップアップを消します...")
                await consent_button.first.click()
                await page.wait_for_timeout(3000)
        except:
            pass 

        # ★診断1：トップページの状態
        await debug_print_buttons(page, "トップページ")

        # 1. クチコミタブクリック
        try:
            print("「クチコミ」タブを探しています...")
            # より確実なセレクタ：aria-labelに「クチコミ」を含む、かつrole="tab"
            tab_btn = page.locator('button[role="tab"][aria-label*="クチコミ"], button[role="tab"][aria-label*="Reviews"]')
            
            if await tab_btn.count() > 0:
                await tab_btn.first.click()
                print("OK: クチコミタブをクリックしました")
                await page.wait_for_timeout(5000)
            else:
                # 見つからない場合、テキストで探すバックアップ
                print("role=tabで見つからないため、テキスト検索します...")
                await page.get_by_text(re.compile(r"(クチコミ|Reviews)")).first.click()
                print("OK: テキスト検索でクリックしました")
                await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"【失敗】クチコミタブ操作エラー: {e}")

        # ★診断2：クチコミタブを押した後
        await debug_print_buttons(page, "クチコミタブクリック後")

        # 2. 並べ替え
        try:
            print("並べ替えを試みます...")
            # 「並べ替え」または「Sort」を含むボタン
            sort_btn = page.locator('button[aria-label*="並べ替え"], button[aria-label*="Sort"]')
            
            if await sort_btn.count() > 0:
                print("「並べ替え」ボタンが見つかりました。クリックします。")
                await sort_btn.first.click()
                await page.wait_for_timeout(2000)
                
                # メニューから「新しい順」
                newest_option = page.locator('[role="menuitemradio"]').filter(has_text=re.compile(r"(新しい順|Newest)"))
                if await newest_option.count() > 0:
                    await newest_option.first.click()
                    print("OK: 「新しい順」を選択しました")
                else:
                    # メニュー内のテキスト検索
                    await page.get_by_text(re.compile(r"(新しい順|Newest)")).click()
                    print("OK: 「新しい順」を選択しました（テキスト）")
            else:
                print("並べ替えボタンが見つかりません。直接ボタンを探します...")
                # タイプB：「新しい順」などが直接出ている場合
                direct_btn = page.locator('button').filter(has_text=re.compile(r"(新しい順|Newest|最新)")).first
                if await direct_btn.count() > 0:
                    await direct_btn.click()
                    print("OK: 「最新」ボタンを直接クリックしました")
                else:
                    print("【重要】並べ替えに関するボタンが一切見つかりませんでした")

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