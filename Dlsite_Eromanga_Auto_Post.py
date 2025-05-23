#!/usr/bin/env python3
# coding: utf-8
# ファイル名: Dlsite_Eromanga_Auto_Post.py

import os
import re
import requests
from bs4 import BeautifulSoup
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods import posts, media
from wordpress_xmlrpc.compat import xmlrpc_client
import collections.abc
collections.Iterable = collections.abc.Iterable

print("🧪 Running Dlsite_Eromanga_Auto_Post.py with sample images")

# 環境変数読み込み
AFFILIATE_ID = os.environ.get('AFFILIATE_ID')
WP_URL       = os.environ.get('WP_URL')
WP_USER      = os.environ.get('WP_USER')
WP_PASS      = os.environ.get('WP_PASS')

# 商品一覧取得
def fetch_dlsite_items(limit=100):
    url = (
        'https://www.dlsite.com/maniax/fsr/=/language/jp/sex_category[0]/male/'
        'work_category[0]/doujin/order/release_d/work_type[0]/MNG/'
        'options_and_or/and/options[0]/JPN/options[1]/NM/per_page/100/'
        'lang_options[0]/日本語/lang_options[1]/言語不要'
    )
    resp = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    items = soup.select('li.search_result_img_box_inner')
    print(f"🔎 Retrieved {len(items)} items from list page")
    return items[:limit]

# 個別ページ解析
def parse_item(el):
    a = el.select_one('dd.work_name a')
    title = a.get_text(strip=True)
    href = a['href']
    detail_url = href if href.startswith('http') else 'https://www.dlsite.com' + href
    resp = requests.get(detail_url, headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
    resp.raise_for_status()
    dsoup = BeautifulSoup(resp.text, 'html.parser')

    # 説明HTML
    intro = dsoup.find('div', id='intro-title')
    desc = dsoup.find('div', itemprop='description', class_='work_parts_container')
    description_html = ''
    if intro:
        description_html += str(intro)
    if desc:
        description_html += str(desc)

    # タグ取得
    tags = []
    for label in ['サークル名', '作者', 'イラスト', 'シナリオ', 'ジャンル']:
        th = dsoup.find('th', string=label)
        if not th:
            continue
        td = th.find_next_sibling('td')
        if label == 'ジャンル':
            for a_genre in td.select('div.main_genre a'):
                tags.append(a_genre.get_text(strip=True))
        else:
            for a_tag in td.select('a'):
                tags.append(a_tag.get_text(strip=True))

    # サンプル画像URL取得
    sample_divs = dsoup.select('div.product-slider-data div[data-src]')
    sample_images = []
    for sd in sample_divs:
        src = sd.get('data-src', '')
        if src.startswith('//'):
            src = 'https:' + src
        sample_images.append(src)

    # メイン画像URL取得
    og = dsoup.find('meta', property='og:image')
    if og and og.get('content'):
        main_img = og['content']
    else:
        img_tag = dsoup.select_one('div#work_image_main img') or dsoup.find('img', id='main')
        if img_tag:
            src = img_tag.get('data-original') or img_tag.get('src') or ''
            main_img = ('https:' + src) if src.startswith('//') else src
        else:
            main_img = ''
    print(f"📷 Main Image URL: {main_img}")

    product_id = re.search(r'/product_id/(RJ\d+)\.html', detail_url).group(1)
    return {
        'title': title,
        'product_id': product_id,
        'detail_url': detail_url,
        'description_html': description_html,
        'tags': tags,
        'main_image_url': main_img,
        'sample_images': sample_images
    }

# 画像アップロード
def upload_image(client, url, label):
    if not url:
        print(f"⚠️ {label}なし")
        return None
    resp = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
    resp.raise_for_status()
    data = {
        'name': os.path.basename(url),
        'type': resp.headers.get('Content-Type'),
        'bits': xmlrpc_client.Binary(resp.content)
    }
    result = client.call(media.UploadFile(data))
    print(f"✅ Uploaded {label}: id={result.get('id')}")
    return result.get('id')

# 投稿本文生成 (画像とサンプル画像にアフィリエイトリンクを付与)
def make_content(item, img_url):
    link = f"https://dlaf.jp/maniax/dlaf/=/t/n/link/work/aid/{AFFILIATE_ID}/id/{item['product_id']}.html"
    parts = []
    parts.append(f"<p><a rel='noopener sponsored' href='{link}' target='_blank'><img src='{img_url}' alt='{item['title']}'/></a></p>")
    parts.append(f"<p><a rel='noopener sponsored' href='{link}' target='_blank'>{item['title']}</a></p>")
    parts.append(item['description_html'])
    for sip in item.get('sample_images', []):
        parts.append(f"<p><img src='{sip}' alt='sample image'/></p>")
    parts.append(f"<p><a rel='noopener sponsored' href='{link}' target='_blank'>{item['title']}</a></p>")
    return "\n".join(parts)

# 既存タイトル取得
def get_existing(client):
    posts_list = client.call(posts.GetPosts({'number':100,'post_status':'publish'}))
    return {p.title for p in posts_list}

# メイン処理: 新しいアイテムを1件だけ投稿
def main():
    client = Client(WP_URL, WP_USER, WP_PASS)
    published = get_existing(client)
    items = fetch_dlsite_items()
    for el in items:
        it = parse_item(el)
        if it['title'] in published:
            continue
        img_id = upload_image(client, it['main_image_url'], 'featured')
        post = WordPressPost()
        post.title = it['title']
        if img_id:
            post.thumbnail = img_id
        post.terms_names = {'post_tag': it['tags']}
        post.content = make_content(it, it['main_image_url'])
        post.post_status = 'publish'
        client.call(posts.NewPost(post))
        print(f"✅ Posted: {it['title']}")
        break

if __name__ == '__main__':
    main()
