# twb_doc_generator — Tableau ワークブック設計書自動生成ツール

Tableau ワークブック (.twbx / .twb) を解析し、設計書 (Markdown) を自動生成します。

- **完全ローカル動作**: 生成 AI・インターネット接続・追加ライブラリは一切不要 (Python 標準ライブラリのみ)
- **企業の Windows 環境を想定**: bat / PowerShell / Python だけで動作。Python 未導入の PC 向けに同梱配布にも対応

## 必要環境

- Windows 10/11
- Python 3.10 以上 — **Python 未導入の PC でも「同梱 Python のセットアップ」(後述) を行えば動作します**

## 使い方

### 1. ドラッグ&ドロップ (推奨)

`.twbx` または `.twb` ファイルを **`generate_doc.bat` にドラッグ&ドロップ**します。
入力ファイルと同じフォルダに `<ファイル名>_設計書.md` が生成されます。

### 2. ダブルクリック (一括処理)

`generate_doc.bat` をダブルクリックすると、このフォルダと親フォルダにある
`.twbx` / `.twb` を全て処理します。

### 3. コマンドライン

```powershell
cd twb_doc_generator\app
python -m twbdoc "C:\path\to\ワークブック.twbx"
python -m twbdoc book1.twbx book2.twb --output C:\docs  # 複数指定・出力先指定
```

終了コード: `0` = 成功 / `1` = 解析エラー / `2` = 入力エラー / `3` = Python 未検出 (bat/ps1)

## Python 未導入の PC への配布 (同梱 Python)

管理者・IT 担当者が **ネットワークに接続できる PC で 1 回だけ**以下を実行すると、
インストール不要の Python (python.org の embeddable 版、約 25MB) が `app\python` に配置されます。

```powershell
cd twb_doc_generator\app
.\setup_python.ps1                  # Python 本体のみ
.\setup_python.ps1 -WithHyperApi    # + .hyper のサンプル値取得対応 (約 +225MB)
```

セットアップ後は **ツールのフォルダごとコピーして配布**するだけで、
配布先の PC に Python が入っていなくても動作します (インストール・管理者権限は不要)。
`-WithHyperApi` を付けると tableauhyperapi (Apache-2.0 ライセンス) が同梱され、
Tableau 抽出 (.hyper) からのサンプル値取得がオフライン PC でも有効になります。

## 出力される設計書の内容

| 章 | 内容 |
| --- | --- |
| 1. ワークブック概要 | バージョン・作成ビルド・各要素の個数 |
| 2. データソースと前処理 | 接続一覧 (ファイル/サーバー)、データモデル図 (Mermaid 統合図 1 枚: 枠=論理テーブル、点線=リレーションシップ、実線=結合、内枠=ユニオン、キー項目を型付き表示)、リレーションシップ・結合・ユニオンの条件テーブル、フィールド設定の変更 (名前変更・型変更・非表示・地理的役割)、データソースフィルタ・抽出フィルタ、ライブ/抽出の別 |
| 3. ダッシュボード構成 | サイズ、レイアウト構成 (インデント付きリスト + Mermaid 図、位置・サイズの % 表記) |
| 4. ワークシート一覧 | タイトル・使用データソース・使用計算フィールド・使用パラメーター・配置先ダッシュボード |
| 5. フィルター | 共通フィルター (コンテキスト) とワークシートごとのフィルター。対象フィールドと適用内容 (「A、B のみ保持」「X 〜 Y の範囲のみ保持」「C を除外」など) |
| 6. パラメーター | データ型・現在値・許容値 (範囲 / リスト / 自由入力) |
| 7. 計算フィールド | リネージュ (依存関係の Mermaid 図)、データ型・ロール・GUI コメント・式内コメント (`//`, `/* */`)・参照フィールド・利用先ワークシート・数式 (内部 ID は表示名に自動置換)。未使用フィールドには ⚠ を表示 |
| 8. 別名一覧 | フィールドごとの「元の値 → 別名」対応表 |
| 9. 書式設定 | フォント名・サイズ・色などの GUI 設定 (ワークブック / ワークシート / ダッシュボード別) |
| 10. テーブル別フィールド一覧 (参考) | 全フィールドの名前・型と、実データからサンプリングした代表値 (下記参照) |

## フィールドのサンプル値 (10 章)

twbx に同梱されたデータから、フィールドごとに重複を除いた代表値 (最大 5 件) を取得して表示します。
ビジネスユーザーからの「このフィールドに何が入っているか見たい」という質問に設計書だけで答えられます。

| twbx 内のデータ形式 | 取得可否 |
| --- | --- |
| .csv / .txt | ○ (標準ライブラリのみで可) |
| .xlsx | ○ (標準ライブラリのみで可) |
| .hyper (Tableau 抽出) | ○ ただし `pip install tableauhyperapi` が必要 (未導入時は注記を表示) |
| .xls (旧 Excel 形式) | × 非対応 |

- 取得できないフィールドは「(取得不可)」と表示されます (非表示フィールドは抽出データに含まれないため取得不可になります)
- サンプリングを行いたくない場合 (機密データなど) は `--no-sample` オプションを付けてください

出力は UTF-8 (BOM 付き) のため、メモ帳や Excel でも文字化けしません。
Mermaid 図は GitHub / VSCode などで図として表示されます (非対応ビューアではコードのまま表示)。

## 構成

```text
twb_doc_generator/
├── generate_doc.bat      # 起動用 (ダブルクリック / D&D) — ユーザーが触るのはこれだけ
├── app/                  # ツール本体 (ユーザーが開く必要はありません)
│   ├── generate_doc.ps1  # Python 検出・呼び出し
│   ├── setup_python.ps1  # 同梱 Python のセットアップ (管理者向け・1 回だけ)
│   ├── python/           # 同梱 Python (setup_python.ps1 実行後に生成)
│   └── twbdoc/           # Python パッケージ
│       ├── cli.py        # コマンドライン処理
│       ├── loader.py     # twbx/twb → XML 読み込み
│       ├── model.py      # 中間モデル (イミュータブル dataclass)
│       ├── sampler.py    # サンプル値取得 (hyper/csv/xlsx)
│       ├── parsers/      # XML → モデル (章ごとに分割)
│       └── renderers/    # モデル → Markdown
└── tests/                # pytest (開発時のみ使用)
```

パーサーとレンダラーは中間モデルで分離されているため、
将来のダッシュボード画像埋め込み (`Dashboard.image_path`、レンダラー実装済み) や
HTML など別形式の出力も追加しやすい構造です。

## 開発 (テスト実行)

```powershell
pip install pytest pytest-cov   # 開発環境のみ
python -m pytest tests/ --cov=twbdoc
```

## 参考

- [Tableau Document Schemas (公式 XSD)](https://github.com/tableau/tableau-document-schemas)
