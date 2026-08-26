<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="preview/logo-dark.png">
  <img src="preview/logo-light.png" width="360" alt="Yui Codex Pet">
</picture>

**Claude Code** と **Codex** の動きをそのまま映すデスクトップペット。

[English](README.md) · [한국어](README.ko.md) · **日本語** · [简体中文](README.zh-CN.md)

</div>

デスクトップに小さなキャラクターが住みつき、コーディングエージェントが今なにをしているかを
見せてくれる — **Claude Code** も **Codex** も。エージェントが作業を始めれば一緒に働き、手を止めて返事を待って
いれば、こちらを向いて待つ。失敗すれば、ウィンドウを切り替えなくても部屋の向こうから見て取れる。

ウィンドウは透過で常に最前面にあるので、作業を隠さずその上に乗る。Windows 上の
**PySide6**（Qt）で描画し、状態を運ぶフックは WSL で動く。

<p align="center">
  <img src="preview/overlay-states.gif" width="420" alt="作業中・待機・エラーに反応するペット"/>
</p>
<p align="center"><sub>実際の画面。<b>作業中</b>はプロジェクト名と経過時間、<b>待機</b>はオレンジ、<b>エラー</b>は赤。セッションが複数あるときは <code>≡ N</code> が出る。</sub></p>
<p align="center">
  <img src="preview/all-states.gif" width="240" alt="アニメーション状態"/>
  &nbsp;
  <img src="preview/16-directions.gif" width="240" alt="16方向の視線"/>
  <br><sub>9 つのアニメーション状態と 16 方向の視線。</sub>
</p>

---

## 何を映すのか

Claude Code はフックで自分の状態を小さなファイルに書く。Codex は設定が一切要らない —
Codex が自分で残しているログをオーバーレイが直接読むからだ。どちらにせよオーバーレイが
ポーリングし、対応するアニメーションを再生する。

| エージェントが | ペットは | |
|---|---|:---:|
| 何もしていない、セッションがない | くつろぐ | <img src="preview/states/00-idle.png" width="90"/> |
| 作業中 | 黙々と働く | <img src="preview/states/07-active-work.png" width="90"/> |
| 入力を待っている | こちらを向いて待つ | <img src="preview/states/06-waiting.png" width="90"/> |
| 見直して締めくくっている | ざっと目を通す | <img src="preview/states/08-review.png" width="90"/> |
| エラーを踏んだ | 反応する | <img src="preview/states/05-failed.png" width="90"/> |
| 作業を切り替えた | 横切って走る | <img src="preview/states/01-running-right.png" width="90"/> |
| 挨拶するとき | 手を振る | <img src="preview/states/03-waving.png" width="90"/> |

セッションを 4 つ開いてもペットは 1 匹だ。オーバーレイが
`待機 > 失敗 > 作業中 > 完了 > idle` の順で並べ替え、いちばん急ぐものを見せる。隅にセッション数が出る。

## 5 人

右クリックで切り替える。素材があるキャラクターだけがメニューに出る。

<p align="center">
  <img src="preview/roster.png" width="720" alt="5 匹を並べたシート"/>
</p>

| | ペット | アイデンティティ | パッケージ |
|:---:|---|---|---|
| <img src="preview/pets/yui-idle.png" width="80"/> | **平沢唯** | 右利きのギブソン・レスポール | `pets/yui/` |
| <img src="preview/pets/mio-idle.png" width="80"/> | **秋山澪** | 左利きのサンバースト・ジャズベース | `pets/mio/` |
| <img src="preview/pets/ritsu-idle.png" width="80"/> | **田井中律** | スティックとメロウイエローの Hipgig | `pets/ritsu/` |
| <img src="preview/pets/tsumugi-idle.png" width="80"/> | **琴吹紬** | KORG TRITON Extreme 76 鍵 | `pets/tsumugi/` |
| <img src="preview/pets/azusa-idle.png" width="80"/> | **中野梓** | キャンディアップルレッドのフェンダー・ムスタング | `pets/azusa/` |

<details>
<summary><b>キャラクターごとの 9 状態すべて</b></summary>
<p align="center">
  <img src="preview/pets/yui-all-states.gif" width="240" alt="唯、9 状態"/>
  <img src="preview/pets/mio-all-states.gif" width="240" alt="澪、9 状態"/>
  <img src="preview/pets/ritsu-all-states.gif" width="240" alt="律、9 状態"/>
  <img src="preview/pets/tsumugi-all-states.gif" width="240" alt="紬、9 状態"/>
  <img src="preview/pets/azusa-all-states.gif" width="240" alt="梓、9 状態"/>
</p>
<p align="center"><sub>idle · running-right · running-left · waving · jumping · failed · waiting · active-work · review</sub></p>
</details>

`pet.json` マニフェストはパッケージ形式を読めるように置いてある。スプライトシートは無い。
[自分で描く](#自分で描く)を参照。

## ほかにできること

何も起きていなければ画面を横切って歩き回り、不規則な間隔でまばたきをする。開いている
ウィンドウの上辺に登ってその上を歩き、画面の壁をよじ登る。つかんで引けば引いた方向へ走り、
動かしたまま放せば弧を描いて飛び、画面の端で跳ね返る。

マウスが近づくと見てくる。カーソルが入ったとき、クリックしたとき、状態が変わったときに
3〜5 秒。ずっと見ているわけではなく、入力中はこちらから見つめない。

右クリックメニューから手を振る・ジャンプ・壁を登る・ポモドーロ（25 分集中・5 分休憩）・
ペットの切り替え・音楽プレイヤーを呼べる。残りは設定ウィンドウにある。言語、サイズ、透明度、
クリック時の動作、自律行動のオンオフ、セリフと音声、音楽フォルダ、作業表示の設定。
タスクトレイにも常駐し、クリック透過を戻せる経路はそのトレイだけだ。

自分のフォルダの音源をプレイヤーウィンドウで再生する。検索・シャッフルと、歌・インスト・
BGM のフィルタがあり、ペットが喋る間は音量が下がる。

画面の文言とペットのセリフを韓国語・English・日本語から選ぶ。再起動なしでその場で切り替わる。

吹き出しには作業のタイトルと 1 行の詳細が入る。`privacyMode` が既定で有効なので、会話の
中身ではなくどのツールを使ったかで語る。実際の文面を見たければ `config.json` で切る。
`showJapanese` を有効にすると、韓国語の下に日本語が 1 行付く。

全画面アプリが前面に来ると自分から隠れ、終われば戻ってくる。


## 仕組み

```
Claude Code フック ──▶ sessions/<source>/<session_id>.json   (小さな PetState ファイル)
                                │   (セッションごとに自分のぶんを書く)
                                ▼
                     オーバーレイがポーリングし優先度で集約
                (waiting > failed > working > done > idle)
                                ▼
                        ペットのアニメーション + 吹き出し
```

```
PetState = {source, session_id, phase, title, detail, transcript, ts, expires_at?}
phase    = idle | working | waiting | done | failed
```


## インストール

```bash
./install.sh          # オーバーレイを配置し、Claude Code のフックを登録する
./install.sh --dry-run
```

Windows 側に Python と PySide6 が、WSL 側にフックが要る。`settings.json` にすでにあるフックは
そのまま残し、`--uninstall` で全部戻せる。詳細は `overlay/README.md` にある。

## 自分のスクリプトから動かす

同梱の `yui` CLI が同じ `PetState` を書く。長く走るジョブを包めば、ペットがその状態を映す。

```bash
yui start "学習"                     # 作業中に切り替わる
yui done  "学習" "3 エポック完了"      # 緑のチェック、そのあと手を振る
yui fail  "ビルド" "テスト失敗"        # 赤
yui wait  "判断が要る"                # オレンジ、こちらを向く
yui clear                           # idle に戻す

# コマンドを包んでもいい。終了コードが完了・失敗を決め、そのまま返る
yui run -t "学習" -- python train.py
```

呼び出す側はそれぞれ `sessions/cli/<id>.json` に書く。CLI のジョブ 1 つと Claude Code の
セッション 3 つが、互いを踏まずに共存する。

## ペットの切り替え

ペットを右クリックして **펫 바꾸기**（*Change pet*）を選ぶ。選んだ値は `config.json` に残る。

```jsonc
{ "pet": "" }        // "" = 配置フォルダ直下の既定シート
{ "pet": "ritsu" }   // = pets/ritsu/spritesheet.webp
```

オーバーレイは配置された `pets/*/` を走査し、マニフェストとシートが揃っているフォルダを探す。

```text
~/.yui-pet/
├── spritesheet.webp        ← 既定のペット、配置フォルダ直下
├── config.json
└── pets/
    ├── mio/{pet.json, spritesheet.webp}
    ├── ritsu/{pet.json, spritesheet.webp}
    └── …
```

マニフェストは 5 つのフィールドだ。

```json
{
  "id": "ritsu",
  "displayName": "Tainaka Ritsu",
  "description": "…",
  "spriteVersionNumber": 2,
  "spritesheetPath": "spritesheet.webp"
}
```

その 2 ファイルが入ったフォルダを置くだけでメニューに現れる。コードの変更も、ペットごとの
調整も要らない。タイミング表と `lines.json` は全ペットで共有する。

## 自分で描く

ランタイムは `pet.json` が指す Codex Pet v2 アトラスを読む。**その絵はここには無い。**
`SPRITE_SPEC.md` に規格が全部ある — 1536×2288、192×208 のセルが 8×11、状態 9 行と視線 2 行 —
自分のキャラクターを描くか、権利を持っているシートをローダーに渡せばいい。

## 中身

| パス | |
|---|---|
| `overlay/yui_pet.py` | PySide6 の透過オーバーレイ |
| `overlay/config.json`, `lines.json` | 表示設定と、書き換えられるセリフ |
| `hooks/` | Claude Code と Codex が共用する状態記録スクリプト |
| `tools/` | フック登録ヘルパー、`yui` CLI、スプライトのアップスケーラ |
| `pets/*/pet.json` | 5 キャラクターのパッケージマニフェスト |
| `preview/` | 状態アニメーション、視線方向、ロスター |
| `SPRITE_SPEC.md` | 自分で描くためのアトラス規格 |
| `install.sh` | ワンコマンド配置 |
| `README.{ko,ja,zh-CN}.md` | 同じ README の韓国語・日本語・簡体中国語版 |

## ライセンス

- コード — MIT © 2026 SeongJin Kim（`LICENSE`）
- フォント — `PretendardVariable.ttf`、Kil Hyung-jin、SIL オープンフォントライセンス
- キャラクターの絵 — *けいおん!* のキャラクターで、権利は権利者に帰属する
  （© かきふらい · 芳文社 · TBS · 京都アニメーション）。ファンによる非営利の制作物で、
  いかなるライセンスでも提供しない。公開しているのは低解像度のプレビューだけで、
  スプライトシートは配布しない。
