# twb_doc_generator

*[English](README.en.md)*

Tableau ワークブック (.twbx / .twb) を解析し、設計書 (HTML / Markdown) を自動生成するツールです。

- 完全にローカルで動作します。生成 AI・インターネット接続・追加ライブラリは一切不要です (Python 標準ライブラリのみ)
- 企業の Windows 環境を想定し、bat / PowerShell / Python だけで動作します。Python 未導入の PC 向けの同梱配布にも対応しています
- 日本語と英語に対応しています。実行環境の表示言語を自動判定して出力を切り替え、用語は Tableau 公式ヘルプの表記に統一しています

## 出力言語

Windows の表示言語から自動判定します (日本語環境なら日本語、それ以外は英語)。
明示的に指定する場合:

```powershell
python -m twbdoc book.twbx --lang en     # 英語で出力
python -m twbdoc book.twbx --lang ja     # 日本語で出力
$env:TWBDOC_LANG = 'en'                  # 環境変数でも指定可 (bat 起動時の画面表示にも反映)
```

## 必要環境

- Windows 10/11
- Python 3.10 以上。**Python 未導入の PC でも、後述の「同梱 Python のセットアップ」を行えば動作します**

## 使い方

### 1. ドラッグ&ドロップ

推奨の方法です。`.twbx` または `.twb` ファイルを **`generate_doc.bat` にドラッグ&ドロップ**します。
入力ファイルと同じフォルダに以下の構成で生成されます (`yyyymmdd` は実行日):

```text
<ファイル名>_Documentation_yyyymmdd\
├── <ファイル名>_Documentation.html    # ブラウザで開ける設計書 (推奨。図・目次ジャンプ・ツールチップ対応)
├── <ファイル名>_Documentation.md      # Markdown 版 (VS Code / GitHub 向け)
└── images\
    ├── <ダッシュボード名>.png          # プレビュー画像 (ワークブック内蔵サムネイル)
    └── layout_<ダッシュボード名>.svg   # レイアウト簡略図 (位置・サイズ比率を再現)
```

HTML 版はダブルクリックでブラウザ表示でき、VS Code などがなくても Mermaid 図・
画像・目次ジャンプ・計算式ツールチップが動きます (mermaid.js 同梱、オフライン完結)。
画像も HTML 内に埋め込み済みのため、HTML ファイル単体で共有できます。

プレビュー画像はワークブック保存時に Tableau が埋め込むサムネイル (約 192px) です。
サムネイルを持たないワークブック (保存時の設定による) では PNG なしで生成されます。
レイアウト簡略図はどのワークブックでも twb の定義から生成されます。

### 2. ダブルクリックで一括処理

`generate_doc.bat` をダブルクリックすると、このフォルダと親フォルダにある
`.twbx` / `.twb` を全て処理します。

### 3. コマンドライン

```powershell
cd twb_doc_generator\app
python -m twbdoc "C:\path\to\ワークブック.twbx"
python -m twbdoc book1.twbx book2.twb --output C:\docs  # 複数指定・出力先指定
```

終了コード: `0` = 成功 / `1` = 解析エラー / `2` = 入力エラー / `3` = Python 未検出 (bat/ps1) /
`4` = 同梱 Python の標準ライブラリを読み込めない (bat/ps1。下記「ファイル暗号化ソフトを使っている環境で」を参照)

## 同梱 Python で Python 未導入の PC に配布する

### 方法 1: ビルド済み zip をダウンロード

最も簡単な方法です。[Releases](https://github.com/konpuku/tableau-workbook-documenter/releases) から
Python 同梱版の zip をダウンロードし、展開して配布するだけです。
利用者側でのインストール・ダウンロード・管理者権限は一切不要です。
zip には設計書生成 (`generate_doc.bat`) に加えて、Live CI (`live_ci.bat`) と
Tableau Agent スキルのインストーラー (`install_skill.bat`) も入っています。

| アセット | 内容 | サイズ目安 |
| --- | --- | --- |
| `...-with-python-hyperapi-win64.zip` | Python + tableauhyperapi 同梱 (.hyper のサンプル値取得対応) | 約 83MB |
| `...-with-python-win64.zip` | Python のみ同梱 | 約 12MB |

### 方法 2: 管理者がセットアップして配布

ネットワークに接続できる PC で 1 回だけ以下を実行すると、
インストール不要の Python (python.org の embeddable 版) が `app\python` に配置されます。

```powershell
cd twb_doc_generator\app
.\setup_python.ps1                  # Python 本体のみ
.\setup_python.ps1 -WithHyperApi    # + .hyper のサンプル値取得対応 (約 +225MB)
```

セットアップ後は **ツールのフォルダごとコピーして配布**するだけです。
配布用の zip を自分で作る場合は `.\build_distribution.ps1 [-WithHyperApi]` を実行すると
`dist\` に配布用 zip が生成されます。

いずれの方法も再配布は合法です (Python は PSF License、tableauhyperapi は Apache-2.0)。

### ファイル暗号化ソフトを使っている環境で

社内の情報漏洩対策ソフト (ファイル暗号化・DRM) が `.zip` や `.txt` を暗号化する設定になっていると、
同梱 Python が起動できなくなることがあります
(`Fatal Python error: Failed to import encodings module`)。

本ツールでは対策として、同梱 Python から**暗号化対象になりやすい拡張子を排除**しています。

- 標準ライブラリは `pythonXXX.zip` ではなく `python\Lib\` フォルダへ展開して同梱
- ライセンス等の `.txt` は `.dat` にリネーム (中身はテキストのまま。メモ帳等で読めます)

それでも起動できない場合 (終了コード `4`)、`.pyc` や `.dll` まで暗号化対象になっている可能性があります。
**IT 管理者に、ツールのフォルダを暗号化・DRM の対象外にするようご相談ください。**

## Live CI: Tableau Studio の編集をリアルタイムに検査する

Tableau Desktop 2026.3.1 以降の **Tableau Studio** で開いているワークブックを、
**保存しなくても** 数秒ごとに読み取り、設計書と CI チェック結果を自動更新します。
人が編集しても、Tableau Agent (Studio 内のエージェント) が編集しても同じように追従します。

### 準備

1. Tableau Desktop で **ヘルプ > 設定とパフォーマンス > External Client API Access** をオンにして再起動
2. Python 3.10 以上 (または同梱 Python)

### 監視を始める

`live_ci.bat` をダブルクリックすると、ブラウザでダッシュボード (http://127.0.0.1:8765/) が開きます。

- **検出**: エラー / 警告 / 情報の件数と一覧。直前の編集で増えたものに「新規」バッジ
- **変更履歴**: 計算フィールド・シート・ダッシュボード等の追加 / 削除 / 変更と、検出の新規 / 解消
- **設計書**: 最新の設計書 HTML

ワークブックの隣の `<名前>.twbdoc/` に `spec.md` / `spec.html` / `findings.json` / `history.jsonl`
を書き出します (未保存のワークブックはカレントフォルダの `twbdoc_live/`)。
`spec.md` をワークブックと一緒に Git 管理すると、変更が差分として残ります。

```bash
cd app
python -m twbdoc watch                  # Studio で開いているワークブックを監視
python -m twbdoc watch book.twbx        # 保存済みファイルを監視 (Studio なし)
python -m twbdoc watch --open --port 8765 --doc-interval 5 --out ./ci
```

Tableau は変更イベントを提供しないため、`GET /v0/workbook` を 2 秒ごと、
ワークブック全体の XML (`GET /v0/workbook/document`) を構成変化時と最大 5 秒ごとに取得します。
通信は 127.0.0.1 のみ・読み取り専用で、ワークブックを変更することはありません。

### CI チェック (check)

```bash
python -m twbdoc check book.twbx                         # テキスト表示
python -m twbdoc check book.twbx --format json -o r.json # JSON (機械可読)
python -m twbdoc check --studio --format md              # 編集中のワークブックを検査
python -m twbdoc check *.twbx --fail-on warning          # 警告以上で終了コード 5
```

終了コード: 0 = 合格 / 1 = 解析エラー / 2 = 入力エラー / 5 = `--fail-on` 以上の検出あり /
6 = Tableau Studio に接続できない。GitHub Actions などの CI にもそのまま組み込めます。

| ルール | 重要度 | 内容 |
|---|---|---|
| `invalid-field` | エラー | シェルフ上の無効なフィールド (Studio の診断 API、`--studio` / watch のみ) |
| `broken-reference` | 警告 | 計算式がワークブック内に存在しないフィールドを参照 |
| `unused-calc` / `unused-parameter` | 警告 | どこからも参照されない計算フィールド / パラメーター |
| `duplicate-formula` | 警告 | 同一の計算式 |
| `extract-row-limit` | 警告 | 抽出に行数制限 |
| `orphan-worksheet` / `unused-datasource` | 情報 | ダッシュボード未配置のシート / 未使用データソース |
| `deep-dependency` / `comment-coverage` | 情報 | 深い依存チェーン / コメント記載率 |
| `default-sheet-name` | 情報 | 「シート 1」など既定名のまま |
| `placeholder-calc-name` | 情報 | 「(コピー)」「計算1」など仮の名前の計算フィールド |
| `uncommented-complex-calc` | 情報 | コメントのない長い計算式 |

ワークブックと同じフォルダ (または親フォルダ) の `.twbdoc.json` でルールを調整できます。

```json
{
  "rules": { "orphan-worksheet": "off", "default-sheet-name": "warning" },
  "ignore": ["unused-calc:3f2a9c1b0d", { "rule": "unused-calc", "target": "検証用フラグ" }],
  "fail_on": "warning"
}
```

### Tableau Agent スキル (検出 → 修正提案 → 承認後に修正)

`install_skill.bat` をダブルクリックすると、
`ドキュメント\My Tableau Repository\Tableau Agent\skills\twbdoc-ci` にスキルが入ります。
その後、Tableau Agent のチャットで `/reload-skills` を実行します。
スキルはインストール時に見つけた Python (同梱 Python を優先) で動くため、
Python 未導入の PC でも配布用 zip のまま使えます。「CI チェックして」と頼むと、
エージェントが検出を説明し、修正案 (シート名の変更、計算式へのコメント追加、参照の修正など) を示し、
**承認したものだけ** Tableau MCP のツールで適用して再チェックします。
計算フィールドの削除は API が無いため、手順の案内にとどめます。

## 出力される設計書の内容

| 章 | 内容 |
| --- | --- |
| 目次 | 章・節へのリンク付き目次 (GitHub / VS Code のプレビューでジャンプ可能) |
| 1. ワークブック概要 | バージョン・作成ビルド・各要素の個数 |
| 2. データソースと前処理 | 接続一覧 (ファイル/サーバー)、データモデル図 (Mermaid 統合図 1 枚: 枠=論理テーブル、点線=リレーションシップ、実線=結合、内枠=ユニオン、キー項目を型付き表示)、リレーションシップ・結合・ユニオンの条件テーブル、フィールド設定の変更 (名前変更・型変更・非表示・地理的役割)、データソースフィルター・抽出フィルター、ライブ/抽出の別。リレーションシップ・結合の定義が残っていないワークブック (抽出専用など) ではテーブル+列一覧の構成図を表示 |
| 3. ダッシュボード構成 | プレビュー画像 (ワークブック内蔵サムネイル)、サイズ、レイアウト構成 (インデント付きリスト + レイアウト簡略図 SVG)。固定サイズのダッシュボードは Tableau の「位置/サイズ」パネルと同じピクセル表記 |
| 4. ダッシュボードアクション | ハイライト / フィルター / URL / セット / パラメーターの各アクション。実行タイミング・ソース (除外シート含む)・ターゲット・対象フィールド |
| 5. ワークシート一覧 | タイトル・使用データソース・使用計算フィールド・使用パラメーター・配置先ダッシュボード |
| 6. フィルター | 共通フィルター (コンテキスト) とワークシートごとのフィルター。対象フィールドと適用内容 (「A、B のみ保持」「X 〜 Y の範囲のみ保持」「C を除外」など) |
| 7. パラメーター | データ型・現在値・許容値 (範囲 / リスト / 自由入力) |
| 8. 計算フィールド | リネージュ (依存関係の Mermaid 図 + 各フィールド詳細へのリンク)、データ型・ロール・GUI コメント・式内コメント (`//`, `/* */`)・参照フィールド・利用先ワークシート・数式 (内部 ID は表示名に自動置換)。未使用フィールドには ⚠ を表示 |
| 9. 表計算設定 | ピルごとの設定 (シート別: 対象ピル・集計・表計算の種類・次を使用して計算) とフィールド既定の設定。「特定のディメンション」は計算順序付きで表示 |
| 10. 別名 | フィールドごとの「元の値 → 別名」対応表 |
| 11. 書式設定 | フォント名・サイズ・色などの GUI 設定 (ワークブック / ワークシート / ダッシュボード別) |
| 12. 健康診断 | 保守リスクの機械チェック: 未使用の計算フィールド/パラメーター、重複した計算式、抽出の行数制限 (⚠ 警告)、ダッシュボード未配置シート、未使用データソース、深い依存チェーン、コメント記載率 (ℹ 情報)。警告数は 1 章の概要にも表示 |
| 13. テーブル別フィールド一覧 (参考) | 全フィールドの名前・型と、実データからサンプリングした代表値 (下記参照) |

## フィールドのサンプル値 (13 章)

twbx に同梱されたデータから、フィールドごとに重複を除いた代表値 (最大 5 件) を取得して表示します。
ビジネスユーザーからの「このフィールドに何が入っているか見たい」という質問に設計書だけで答えられます。

| twbx 内のデータ形式 | 取得可否 |
| --- | --- |
| .csv / .txt | ○ (標準ライブラリのみで可) |
| .xlsx | ○ (標準ライブラリのみで可) |
| .hyper (Tableau 抽出) | ○ ただし `pip install tableauhyperapi` が必要 (未導入時は注記を表示) |
| .xls (旧 Excel 形式) | × 非対応 |

- 取得できないフィールドは「(取得不可)」と表示されます (非表示フィールドは抽出データに含まれないため取得不可になります)
- サンプリングしたくない場合 (機密データなど) は `--no-sample` オプションを付けてください

出力は UTF-8 (BOM 付き) のため、メモ帳や Excel でも文字化けしません。
Mermaid 図は GitHub / VS Code などで図として表示されます (非対応ビューアではコードのまま表示)。
リネージュ図には各計算フィールド詳細へのリンク一覧を併記しており、
セキュリティ設定が緩いビューアでは図中のノードをクリックしても移動できます。
GitHub や VS Code の標準プレビューではクリックが効かないため、リンク一覧をお使いください。

## 構成

```text
twb_doc_generator/
├── generate_doc.bat      # 起動用 (ダブルクリック / D&D)。ユーザーが触るのはこれだけ
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

## 開発時のテスト実行

```powershell
pip install pytest pytest-cov   # 開発環境のみ
python -m pytest tests/ --cov=twbdoc
```

## 用語

用語は日英とも Tableau 公式ヘルプの表記に合わせています
(例:「次を使用して計算」/ Compute Using、「合計に対する割合」/ Percent of Total、
「URL に移動」/ Go to URL、「数値 (整数)」/ Number (whole))。
設計書の記述と Tableau Desktop の画面表示が一致するため、対応付けが容易です。

## 参考

- [Tableau Document Schemas (公式 XSD)](https://github.com/tableau/tableau-document-schemas)
- [Tableau ヘルプ (日本語)](https://help.tableau.com/current/pro/desktop/ja-jp/default.htm)
- [Tableau Help (English)](https://help.tableau.com/current/pro/desktop/en-us/default.htm)
