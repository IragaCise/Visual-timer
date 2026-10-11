# Visual Bar Timer v2.5 — macOS アプリ化キット

このZIPは**完成済みのMacアプリではなく、Mac上で完成品を自動生成するためのプロジェクト**です。
この作業環境（Linux）ではmacOS用のPyInstallerビルドを実施できないため、完成品の動作を保証できません。

## できあがるアプリ

- `Visual Bar Timer.app`（Pythonランタイムを含む単独実行形式）
- MacにPythonやpipをインストールする必要なし（**ビルド後の利用時**）
- ドラッグしてアプリケーションフォルダへ移動して利用
- 終了音：Mac標準の音 + 任意の音楽ファイル（`afplay`で再生）
- 設定：`~/.visual_bar_timer.json` に保存され、アプリを移動しても保持
- Intel Mac と Apple Silicon のそれぞれの版を生成

## Windows PC だけでMac用アプリを生成する

1. GitHub で新しいリポジトリを作る（プロジェクト名は自由）。
2. このフォルダの全ファイル（隠しフォルダ `.github/workflows` を含む）をアップロードする。GitHub Desktop の **Add Existing Repository** → **Publish repository** を使うと比較的簡単です。
3. リポジトリの **Actions** タブ → **Mac アプリを作成** → **Run workflow** を押す。
4. 完了後、ビルドのページ下部の **Artifacts** から次のいずれかをダウンロードする。
   - `VisualBarTimer-macOS-AppleSilicon` — M1/M2/M3/M4などのMac向け
   - `VisualBarTimer-macOS-Intel` — Intel Mac向け
5. Artifactsから落ちてきたZIPを開き、その中のさらにZIPを展開すると `Visual Bar Timer.app` が出ます（GitHub ArtifactsがZIPをもう一層付けるため）。

プライベートリポジトリの場合、GitHub Actionsの利用枠・料金が適用されることがあります。

## Macが使えるときの簡単ビルド

ターミナルで、このフォルダに移動して `bash build_mac.sh` と入力します。
初回のみネット接続が必要です。Python 3 と tkinter が既にMac上にある環境でビルドします。

生成物は `output/VisualBarTimer-macOS-<arch>.zip` です。

## macOSの初回起動と署名について

生成物にはDeveloper ID署名およびAppleの公証（notarization）がありません。
macOSのGatekeeperによって初回起動がブロックされる場合があります。
この場合は提供元を確認したうえで、**システム設定 → プライバシーとセキュリティ → このまま開く** の手順が必要なことがあります。
参照: https://support.apple.com/ja-jp/102445

配布先で『コピーしてダブルクリックするだけ』を完全に保証するには、Apple Developer IDによる署名・公証が別途必要です。

## 内容

- `visual_bar_timer.py` — 動作確認済みWindows v2.5相当のPythonソース（Mac向けタイトル調整）
- `build_mac.sh` — Pythonを同梱した.appと配布用ZIPを生成
- `make_iconset.sh` — Mac用アプリアイコンを作成
- `.github/workflows/build-mac.yml` — GitHubのMac環境で2種類を自動作成
- `assets/icon.png` — アプリアイコンの元画像

## 検証状況

Linuxでソースの構文とZIP構成を確認済み。Macの実機・CIでのビルドと起動確認は未実施です。
