# コントリビューションガイド / Contributing

このプロジェクトは **Issue ドリブン** で開発します。
すべての変更は Issue から始まり、Pull Request で Issue を閉じます。

*English summary is at the bottom.*

## 開発の流れ (Issue ドリブン)

1. **Issue を立てる**
   - 変更はまず Issue から。バグ・機能要望・用語修正のテンプレートがあります
     ([New issue](https://github.com/konpuku/tableau-workbook-documenter/issues/new/choose))。
   - 既存 Issue と重複していないか検索してください。
2. **担当・方針を確認する**
   - 大きな変更は、実装前に Issue 上で方針を合意してから着手すると手戻りが減ります。
3. **ブランチを作る**
   - `main` から分岐し、`<種別>/<Issue番号>-<短い説明>` の形式で命名します。
     - 例: `fix/12-encoding`, `feat/45-lineage-tooltip`, `docs/7-readme`
4. **実装 + テスト**
   - ツール本体は **Python 標準ライブラリのみ** で書きます (依存を増やさない)。
   - 挙動を変えたら **テストを追加/更新** します (`tests/`)。
   - ローカルで通す:
     ```bash
     python -m pip install -r requirements-dev.txt
     python -m pytest tests/
     ```
5. **Pull Request を出す**
   - PR 本文に **`Closes #<Issue番号>`** を必ず書きます (マージで Issue が自動クローズ)。
   - PR テンプレートのチェックリストを埋めます。
   - **CI (GitHub Actions) が緑になること** がマージの条件です。
6. **レビュー → マージ**
   - レビュー後にマージ。マージで Issue が閉じます。

## コーディング規約

- **標準ライブラリのみ**: ツール本体 (`app/twbdoc/`) に外部依存を追加しない。
- **中間モデルで分離**: `parsers/` (XML → モデル) と `renderers/` (モデル → 出力) を分ける。
- **用語は Tableau 公式ヘルプの表記に統一** (日英とも)。訳語は `app/twbdoc/i18n.py` で一元管理。
- **起動スクリプトのエンコーディング**:
  - `.ps1` は **UTF-8 BOM 付き** (Windows PowerShell 5.1 の文字化け対策)
  - `.bat` は **BOM なし** (cmd.exe の 1 行目誤認識対策)
  - `tests/test_scripts.py` がこれを検査します。
- コミットメッセージは `feat:` / `fix:` / `docs:` / `chore:` などの接頭辞を推奨。

## ラベル運用

ラベルは `.github/labels.yml` で管理し、`main` への push で自動同期されます
(`.github/workflows/labels.yml`)。ラベルを増減したいときは `labels.yml` を PR で編集してください。

- 種別: `bug` / `enhancement` / `docs` / `i18n` / `question`
- 領域: `area: parser` / `area: renderer` / `area: html` / `area: sampler` / `area: distribution` / `area: ci`
- 運用: `good first issue` / `help wanted` / `needs-repro` / `wontfix` / `duplicate`

## Claude Code に Issue を任せる

Issue や PR のコメント、または Issue 本文に **`@claude`** と書くと、Claude Code が
内容を読んで実装 PR の作成やコメント対応を行います
(`.github/workflows/claude.yml`)。

- 例: Issue に「`@claude` この不具合を再現して修正 PR を出してください」とコメント。
- **事前準備 (管理者が 1 回だけ)**: リポジトリの
  **Settings > Secrets and variables > Actions** で `ANTHROPIC_API_KEY` を登録してください。
  (Claude の [GitHub App](https://github.com/apps/claude) を使う場合は
  [公式ドキュメント](https://docs.claude.com/en/docs/claude-code/github-actions) を参照)
- Claude が出す PR も通常どおり **CI と人によるレビュー** を通ります。エージェントの変更を
  無条件に信頼せず、必ずレビューしてください。

## 外部アセットの追従

参照している外部アセットの更新は `.github/workflows/upstream-check.yml`(週次 + 手動実行)で追従します。

- **更新検知**: `tableau/hyper-db`(hyperapi)と `tableau/tableau-document-schemas`(XSD 定義)の
  新リリースを検知し、更新があれば `[upstream] …` という Issue を自動起票します
  (同一タイトルの重複は作りません)。→ あとは通常の issue ドリブンで対応。
- **追従検証**: 最新の `tableauhyperapi` を入れてテストを実行し、壊れていれば Issue を自動起票します。
- **Actions の更新**: `.github/dependabot.yml` がワークフローの Action バージョンを週次で最新化します。

手動で今すぐ確認したいときは、Actions タブから **Upstream check** を `Run workflow` で実行できます。

---

## English summary

This project follows an **issue-driven** workflow: every change starts from an
issue and is closed by a pull request.

1. **Open an issue** using a template (bug / feature / terminology).
2. **Branch** from `main` as `<type>/<issue-number>-<short-desc>` (e.g. `fix/12-encoding`).
3. **Implement + test.** The core uses the **Python standard library only**. Add/update tests:
   ```bash
   python -m pip install -r requirements-dev.txt
   python -m pytest tests/
   ```
4. **Open a PR** with `Closes #<issue>` in the body and fill in the checklist. **CI must be green** to merge.
5. **Review → merge** (the issue auto-closes).

Conventions: stdlib only; keep `parsers/` and `renderers/` separated by an intermediate model;
match official Tableau terminology (managed in `app/twbdoc/i18n.py`); `.ps1` files are
UTF-8 **with** BOM, `.bat` files **without** BOM (checked by `tests/test_scripts.py`).

Labels live in `.github/labels.yml` and sync on push to `main`.

Mention **`@claude`** in an issue or PR comment to have Claude Code work on it
(requires an `ANTHROPIC_API_KEY` repo secret). Claude's PRs still go through CI and human review.
