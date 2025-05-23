#!/usr/bin/env python3
# coding: utf-8
# ファイル名: Dlsite_Eromanga_Auto_Post.py

import os
import re
import requests
from bs4 import BeautifulSoup
import collections
import collections.abc
collections.Iterable = collections.abc.Iterable

from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods import posts, media
from wordpress_xmlrpc.compat import xmlrpc_client

print("🧪 Running Dlsite_Eromanga_Auto_Post.py")

# 環境変数読み込み
AFFILIATE_ID = os.environ.get('AFFILIATE_ID')
WP_URL       = os.environ.get('WP_URL')
WP_USER      = os.environ.get('WP_USER')
WP_PASS      = os.environ.get('WP_PASS')

# DLsite商品一覧を取得
def fetch_dlsite_items(limit=100):
    url = (
        'https://www.dlsite.com/maniax/fsr/=/language/jp/sex_category[0]/male/'
        'work_category[0]/doujin/order[0]/trend/work_type[0]/MNG/work_type_name[0]/マンガ/'
        'options_and_or/and/options[0]/JPN/options[1]/NM/options_name[0]/日本語作品/'
        'options_name[1]/言語不問作品/per_page/100/page/1/show_type/3/lang_options[0]/日本語/'
        'lang_options[1]/言語不要'
    )
    print(f"🔍 Fetching URL: {url}")
    resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    items = soup.select('li.search_result_img_box_inner') or []
    print(f"🔎 Retrieved {len(items)} items from list page")
    return items[:limit]

# 個別ページ解析
def parse_item(el):
    a = el.select_one('dd.work_name a')
    title = a.get_text(strip=True)
    href = a['href']
    detail_url = href if href.startswith('http') else 'https://www.dlsite.com' + href

    resp = requests.get(detail_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    resp.raise_for_status()
    dsoup = BeautifulSoup(resp.text, 'html.parser')

    # 説明HTML
    intro = dsoup.find('div', id='intro-title')
    desc  = dsoup.find('div', itemprop='description', class_='work_parts_container')
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

    # 画像URL取得
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
    print(f"📷 Image URL: {main_img}")

    return {
        'title': title,
        'product_id': re.search(r'/product_id/(RJ\d+)\.html', detail_url).group(1),
        'detail_url': detail_url,
        'description_html': description_html,
        'tags': tags,
        'main_image_url': main_img
    }

# 画像アップロード
def upload_image(client, url, label):
    if not url:
        print(f"⚠️ {label}なし")
        return None
    resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    resp.raise_for_status()
    data = {
        'name': os.path.basename(url),
        'type': resp.headers.get('Content-Type', 'image/jpeg'),
        'bits': xmlrpc_client.Binary(resp.content)
    }
    result = client.call(media.UploadFile(data))
    print(f"✅ Uploaded {label}: {result.get('id')}")
    return result.get('id')

# 投稿本文生成
def make_content(item, img_url):
    link = f"https://dlaf.jp/maniax/dlaf/=/t/n/link/work/aid/{AFFILIATE_ID}/id/{item['product_id']}.html"
    parts = []
    parts.append(f"<p><a href='{img_url}' target='_blank'><img src='{img_url}'/></a></p>")
    parts.append(f"<p><a href='{link}'>{item['title']}</a></p>")
    parts.append(item['description_html'])
    return '\n'.join(parts)

# 既存タイトル取得
def get_existing(client):
    posts_list = client.call(posts.GetPosts({'number': 100, 'post_status': 'publish'}))
    return {p.title for p in posts_list}

# メイン処理
if __name__ == '__main__':
    cli = Client(WP_URL, WP_USER, WP_PASS)
    exist = get_existing(cli)
    items = [parse_item(el) for el in fetch_dlsite_items()]
    for it in items:
        if it['title'] in exist:
            continue
        img_id = upload_image(cli, it['main_image_url'], 'featured')
        post = WordPressPost()
        post.title = it['title']
        post.thumbnail = img_id
        post.terms_names = {'post_tag': it['tags']}
        post.content = make_content(it, it['main_image_url'])
        post.post_status = 'publish'
        cli.call(posts.NewPost(post))
        print(f"✅ Posted: {it['title']}")
