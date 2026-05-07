# 🔗 いちカズ

> シンプルで軽量なURL短縮サービス。

![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite)

---

## ✨ 特徴

- **URL短縮** — 長いURLを6文字のランダムコードに短縮
- **クリック計測** — アクセス数・最終アクセス日時を記録
- **アクセスログ** — IPアドレス・UA・リファラーを保存
- **統計ページ** — 各短縮URLのクリック数を確認
- **管理画面** — 全URL一覧・詳細ログをBasic認証で保護

---

## 🛠️ 技術スタック

| カテゴリ | 技術 |
|---|---|
| バックエンド | FastAPI |
| データベース | SQLite + SQLAlchemy |
| テンプレート | Jinja2 |

---

## 📁 ディレクトリ構成

```
ichikazu/
├── app/
│   ├── main.py          # APIエンドポイント
│   ├── models.py        # DBモデル
│   ├── database.py      # DB接続
│   ├── templates/       # HTMLテンプレート
│   └── static/          # CSS・JS
├── data/                # SQLiteデータベース（gitignore対象）
├── requirements.txt
└── .env.example         # 環境変数テンプレート
```

---

## 🚀 セットアップ

```bash
# 1. クローン
git clone https://github.com/masafykun/ichikazu.git
cd ichikazu

# 2. 仮想環境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. 環境変数
cp .env.example .env
# .env の ADMIN_PASS を任意の強いパスワードに変更

# 4. 起動
uvicorn app.main:app --reload --port 8000
```

---

## 🔑 環境変数

`.env.example` をコピーして `.env` を作成してください。

| 変数名 | 説明 |
|---|---|
| `ADMIN_USER` | 管理画面のユーザー名（デフォルト: `admin`） |
| `ADMIN_PASS` | 管理画面のパスワード（必ず変更してください） |

---

## 📜 ライセンス

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

このプロジェクトは **MIT ライセンス** のもとで公開しています。
使用・参考にした際はできる限り作者へのクレジット表記をお願いします。

```
© 2025 masafykun (https://github.com/masafykun)
```
