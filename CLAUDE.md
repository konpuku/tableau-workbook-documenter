# CLAUDE.md

Claude Code や貢献者がこのリポジトリで作業するための要点。詳細な運用は `CONTRIBUTING.md` を参照。

## このプロジェクト

Tableau ワークブック (`.twbx` / `.twb`) を解析し、設計書 (HTML / Markdown) を自動生成する
CLI ツール。企業の Windows 環境を想定し、**生成 AI・インターネット接続・外部ライブラリなしで動作**する
(ツール本体は Python 標準ライブラリのみ)。日本語 / 英語出力に対応。

## 開発コマンド

```bash
# 依存 (開発時のみ。ツール本体は標準ライブラリのみ)
python -m pip install -r requirements-dev.txt

# テスト
python -m pytest tests/                       # 全テスト
python -m pytest tests/ --cov=twbdoc          # カバレッジ付き
python -m pytest tests/test_parsers.py -q     # 個別ファイル

# ツール実行 (app/ から)
cd app && python -m twbdoc path/to/book.twbx
python -m twbdoc book.twbx --lang en          # 英語出力
python -m twbdoc book.twbx --no-sample        # サンプル値取得を無効化
```

CI (`.github/workflows/ci.yml`) は ubuntu / windows × Python 3.10・3.12 で `pytest` を実行。
**変更は CI が緑になってからマージ**する。

## アーキテクチャ

パーサーとレンダラーを **中間モデル (`app/twbdoc/model.py` のイミュータブル dataclass)** で分離。

```
app/twbdoc/
├── cli.py            # コマンドライン処理
├── loader.py         # twbx/twb → XML
├── model.py          # 中間モデル (dataclass)
├── i18n.py           # 日英の訳語を一元管理
├── sampler.py        # サンプル値取得 (hyper/csv/xlsx)
├── health.py         # 健康診断 (保守リスクの機械チェック)
├── parsers/          # XML → モデル (章ごとに分割)
└── renderers/        # モデル → Markdown / HTML (章ごとに分割)
```

新しい章や要素を足すときは、原則 **parsers に解析を、renderers に出力を** 追加し、
両者を model 経由でつなぐ。

## 守るべき規約

- **標準ライブラリのみ**: `app/twbdoc/` に外部依存を追加しない。
- **用語は Tableau 公式ヘルプ表記**に統一 (日英)。文言は `i18n.py` に集約し、直書きしない。
- **スクリプトのエンコーディング**: `.ps1` は UTF-8 **BOM 付き**、`.bat` は **BOM なし**。
  `tests/test_scripts.py` が検査する。
- **挙動を変えたら必ずテストを追加/更新**する (`tests/`)。
- 生成物 (設計書・`app/python/`・`dist/`) はコミットしない (`.gitignore` 済み)。

## Issue ドリブン

変更は Issue から始め、PR 本文に `Closes #<Issue番号>` を書いてマージで閉じる。
ブランチ名は `<種別>/<Issue番号>-<短い説明>` (例: `fix/12-encoding`)。
