<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="preview/logo-dark.png">
  <img src="preview/logo-light.png" width="360" alt="Yui Codex Pet">
</picture>

一只显示 **Claude Code** 与 **Codex** 此刻在做什么的桌面宠物。

[English](README.md) · [한국어](README.ko.md) · [日本語](README.ja.md) · **简体中文**

</div>

桌面上住着一个小角色，它会显示编码智能体此刻在做什么，**Claude Code** 和 **Codex** 都能看。

智能体开始干活，它就跟着干活；智能体停下来等你回话，它也转过身来等。出错的时候它会变红，
不用切窗口也能注意到。

窗口透明且始终置顶，不会挡住你正在做的事情。这是 Windows 上的 **PySide6**（Qt）程序，
记录状态的钩子跑在 WSL 里。

<p align="center">
  <img src="preview/overlay-states.gif" width="420" alt="宠物对工作中、等待、报错三种状态的反应"/>
</p>
<p align="center"><sub>真实录屏。<b>工作中</b>会显示项目名和已耗时长，<b>等待</b>转为橙色，<b>报错</b>转为红色；同时跑多个会话时角上会出现 <code>≡ N</code>。</sub></p>
<p align="center">
  <img src="preview/all-states.gif" width="240" alt="动画状态"/>
  &nbsp;
  <img src="preview/16-directions.gif" width="240" alt="十六个朝向"/>
  <br><sub>九种动画状态，十六个视线朝向。</sub>
</p>

---

## 它显示的状态

Claude Code 需要注册钩子，Codex 不用配置，因为叠加层直接读 Codex 本来就在写的日志。
叠加层定期检查这些文件，播放对应状态的动画。

| 智能体 | 宠物 | |
|---|---|:---:|
| 空闲，或者没有会话 | 歇着 | <img src="preview/states/00-idle.png" width="90"/> |
| 正在干活 | 埋头忙活 | <img src="preview/states/07-active-work.png" width="90"/> |
| 等你输入 | 转过来等着 | <img src="preview/states/06-waiting.png" width="90"/> |
| 收尾复查 | 从头看一遍 | <img src="preview/states/08-review.png" width="90"/> |
| 撞上错误 | 有反应 | <img src="preview/states/05-failed.png" width="90"/> |
| 切换任务 | 横穿屏幕跑过去 | <img src="preview/states/01-running-right.png" width="90"/> |
| 跟你打招呼 | 挥手 | <img src="preview/states/03-waving.png" width="90"/> |

开四个会话，宠物还是一只。叠加层按 `等待 > 失败 > 工作中 > 完成 > idle` 排序，
显示最需要你的那个，并在角落标出会话数。

## 五个人

右键切换。只有你手上有素材的角色才会出现在菜单里。

<p align="center">
  <img src="preview/roster.png" width="720" alt="五只宠物并排"/>
</p>

| | 宠物 | 身份标识 | 包 |
|:---:|---|---|---|
| <img src="preview/pets/yui-idle.png" width="80"/> | **平泽唯** | 右手持吉普森 Les Paul | `pets/yui/` |
| <img src="preview/pets/mio-idle.png" width="80"/> | **秋山澪** | 左手持渐层色 Jazz Bass | `pets/mio/` |
| <img src="preview/pets/ritsu-idle.png" width="80"/> | **田井中律** | 鼓棒与 Mellow Yellow Hipgig 鼓组 | `pets/ritsu/` |
| <img src="preview/pets/tsumugi-idle.png" width="80"/> | **琴吹紬** | KORG TRITON Extreme 76 键 | `pets/tsumugi/` |
| <img src="preview/pets/azusa-idle.png" width="80"/> | **中野梓** | 糖果苹果红 Fender Mustang | `pets/azusa/` |

<details>
<summary><b>每个角色的九种状态</b></summary>
<p align="center">
  <img src="preview/pets/yui-all-states.gif" width="240" alt="唯，九种状态"/>
  <img src="preview/pets/mio-all-states.gif" width="240" alt="澪，九种状态"/>
  <img src="preview/pets/ritsu-all-states.gif" width="240" alt="律，九种状态"/>
  <img src="preview/pets/tsumugi-all-states.gif" width="240" alt="紬，九种状态"/>
  <img src="preview/pets/azusa-all-states.gif" width="240" alt="梓，九种状态"/>
</p>
<p align="center"><sub>idle · running-right · running-left · waving · jumping · failed · waiting · active-work · review</sub></p>
</details>

放 `pet.json` 清单是为了让你看清包的格式。素材图集不在这里，见
[自己画一个](#自己画一个)。

## 它还会做什么

没事的时候它会在屏幕上四处走动，以不规则的间隔眨眼。它爬到你窗口的上沿并沿着走，也会
顺着屏幕边缘往上爬。抓住往哪儿拖它就往哪儿跑；拖动中松手，它会沿一条抛物线飞出去，撞到
屏幕边缘弹一下。

鼠标靠近时它会看过来。光标进入、你点它、状态变化时看三到五秒。不会一直看，你打字的时候
也不会主动看过来。

右键菜单里有挥手、跳一下、爬墙、番茄钟（专注 25 分钟、休息 5 分钟）、换宠物和音乐播放器。
其余都在设置窗口里：语言、大小、透明度、点击行为、各项自主行为的开关、台词与语音、音乐
目录、状态显示选项。它也常驻托盘，开了鼠标穿透之后，托盘是唯一能关掉它的地方。

播放你自己目录里的音频，带一个播放器窗口，有搜索、随机播放，以及按歌曲、伴奏、背景音乐
筛选。宠物说话时音乐会自动降低音量。

界面文案和宠物台词可以选韩语、英语或日语，无需重启，当场生效。中文界面还没做，
语言菜单里只有这三种。

气泡里是任务标题和一行细节。`privacyMode` 默认开启，所以它描述用了什么工具，而不是直接
引用你的对话。想看真实内容就在 `config.json` 里关掉。打开 `showJapanese`，韩文下面会多
一行日文。

有全屏程序占据前台时它自动隐藏，结束后再回来。


## 工作原理

```
Claude Code 钩子 ──▶ sessions/<source>/<session_id>.json   (一个很小的 PetState 文件)
                                │   (每个会话写自己的那份)
                                ▼
                     叠加层轮询并按优先级汇总
                (waiting > failed > working > done > idle)
                                ▼
                        宠物动画 + 气泡
```

```
PetState = {source, session_id, phase, title, detail, transcript, ts, expires_at?}
phase    = idle | working | waiting | done | failed
```


## 安装

```bash
./install.sh          # 部署叠加层并注册 Claude Code 钩子
./install.sh --dry-run
```

Windows 一侧需要 Python 和 PySide6，钩子跑在 WSL 一侧。`settings.json` 里已有的钩子会保留，
`--uninstall` 可以整个撤掉。细节见 `overlay/README.md`。

## 从你自己的脚本驱动它

随包附带的 `yui` CLI 写的是同一份 `PetState`。用它包住一个长任务，宠物就会显示那个任务的状态。

```bash
yui start "训练"                      # 切到工作中
yui done  "训练" "跑完 3 个 epoch"      # 绿色对勾，然后挥手
yui fail  "构建" "测试没过"             # 红色
yui wait  "需要你拿个主意"              # 橙色，转过来看着你
yui clear                            # 回到 idle

# 也可以直接包住一条命令；退出码决定成功还是失败，并原样返回
yui run -t "训练" -- python train.py
```

每个调用方各写各的 `sessions/cli/<id>.json`。一个 CLI 任务和三个 Claude Code 会话
可以互不干扰地共存。

## 换宠物

右键点宠物，选 **Change pet**。选择会存进 `config.json`。

```jsonc
{ "pet": "" }        // "" = 部署目录根下的默认图集
{ "pet": "ritsu" }   // = pets/ritsu/spritesheet.webp
```

叠加层会扫描已部署的 `pets/*/`，找同时有清单和图集的目录。

```text
~/.yui-pet/
├── spritesheet.webp        ← 默认宠物，放在部署目录根下
├── config.json
└── pets/
    ├── mio/{pet.json, spritesheet.webp}
    ├── ritsu/{pet.json, spritesheet.webp}
    └── …
```

清单只有五个字段：

```json
{
  "id": "ritsu",
  "displayName": "Tainaka Ritsu",
  "description": "…",
  "spriteVersionNumber": 2,
  "spritesheetPath": "spritesheet.webp"
}
```

把装着这两个文件的目录丢进去，它就会出现在菜单里。不用改代码，也不用逐只调参，因为时序表和 `lines.json` 是所有宠物共用的。

## 自己画一个

运行时读取的是 `pet.json` 指向的 Codex Pet v2 图集。**那些素材不在这个仓库里。**
`SPRITE_SPEC.md` 写了完整规格（1536×2288，8×11 个 192×208 的格子，九行状态加两行视线），
照着画自己的角色，或者把你拥有权利的图集交给加载器。

## 仓库里有什么

| 路径 | |
|---|---|
| `overlay/yui_pet.py` | PySide6 透明叠加层 |
| `overlay/config.json`、`lines.json` | 显示设置与可自行改写的台词 |
| `hooks/` | Claude Code 与 Codex 共用的状态写入脚本 |
| `tools/` | 钩子注册脚本、`yui` CLI、素材放大工具 |
| `pets/*/pet.json` | 五个角色的包清单 |
| `preview/` | 状态动画、视线朝向、角色合影 |
| `SPRITE_SPEC.md` | 自己作画时用的图集规格 |
| `install.sh` | 一条命令完成部署 |
| `README.{ko,ja,zh-CN}.md` | 同一份 README 的韩文、日文、简体中文版 |

## 许可

- 代码 — MIT © 2026 SeongJin Kim（见 `LICENSE`）
- 字体 — `PretendardVariable.ttf`，Kil Hyung-jin，SIL 开放字体许可证
- 角色画作 — 出自 *轻音少女*，版权归权利方所有（© Kakifly · 芳文社 · TBS · 京都动画）。
  粉丝制作的非商业作品，不以任何许可证提供。公开的只有低分辨率预览，素材图集本身并不分发。
