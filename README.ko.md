<div align="center">

# Yui Codex Pet

**Claude Code** 와 **Codex** 가 지금 하는 일을 그대로 비추는 데스크톱 펫.

[English](README.md) · **한국어** · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

바탕화면에 작은 캐릭터가 살면서 코딩 에이전트가 지금 뭘 하고 있는지 보여준다 —
**Claude Code** 와 **Codex** 둘 다.
에이전트가 일을 시작하면 같이 일하고, 멈춰서 답을 기다리면 같이 고개를 돌리고 기다린다.
뭔가 실패하면 창을 옮기지 않아도 멀리서 눈에 들어온다.

창은 투명하고 항상 위에 떠 있어서, 하던 일을 가리지 않고 그 위에 얹힌다.
Windows에서 **PySide6**(Qt)로 그리고, 상태를 물어다 주는 훅은 WSL에서 돈다.

<p align="center">
  <img src="preview/overlay-states.gif" width="420" alt="작업 중·대기·실패 상태에 반응하는 펫"/>
</p>
<p align="center"><sub>실제 화면. <b>작업 중</b>이면 프로젝트 이름과 경과 시간이, <b>대기</b>면 주황색이, <b>실패</b>면 빨간색이 뜬다. 세션이 여럿이면 <code>≡ N</code>이 붙는다.</sub></p>
<p align="center">
  <img src="preview/all-states.gif" width="130" alt="애니메이션 상태"/>
  &nbsp;
  <img src="preview/16-directions.gif" width="130" alt="16방향 시선"/>
  <br><sub>아홉 가지 애니메이션 상태와 열여섯 방향 시선.</sub>
</p>

---

## 무슨 상태를 비추나

Claude Code 는 훅으로 제 상태를 작은 파일에 남긴다. Codex 는 설정할 게 아무것도 없다 —
Codex 가 이미 남기는 기록을 오버레이가 직접 읽는다. 어느 쪽이든 오버레이가 폴링해
맞는 애니메이션을 튼다.

| 에이전트가 | 펫은 | |
|---|---|:---:|
| 놀고 있거나 세션이 없으면 | 쉰다 | <img src="preview/states/00-idle.gif" width="90"/> |
| 작업 중이면 | 집중해서 일한다 | <img src="preview/states/07-active-work.gif" width="90"/> |
| 입력을 기다리면 | 이쪽을 보며 기다린다 | <img src="preview/states/06-waiting.gif" width="90"/> |
| 검토하며 마무리하면 | 훑어본다 | <img src="preview/states/08-review.gif" width="90"/> |
| 오류를 만나면 | 반응한다 | <img src="preview/states/05-failed.gif" width="90"/> |
| 작업을 옮기면 | 가로질러 달린다 | <img src="preview/states/01-running-right.gif" width="90"/> |
| 인사할 때 | 손을 흔든다 | <img src="preview/states/03-waving.gif" width="90"/> |

세션을 네 개 띄워도 펫은 하나다. 오버레이가 `대기 > 실패 > 작업중 > 완료 > idle` 순으로
따져서 가장 급한 것을 보여주고, 구석에 세션 수를 적는다.

## 다섯 명

다섯 캐릭터를 한 세트로 그렸다. 아틀라스 규격도, 아홉 가지 상태도, 타이밍 표도 같다.
우클릭하면 스프라이트를 가진 캐릭터끼리 바꿔 낄 수 있다.

<p align="center">
  <img src="preview/roster.png" width="720" alt="다섯 펫을 나란히 놓은 시트"/>
</p>

| | 펫 | 정체성 | 패키지 |
|:---:|---|---|---|
| <img src="preview/pets/yui-idle.gif" width="80"/> | **히라사와 유이** | 오른손잡이 깁슨 레스폴 | `pets/yui/` |
| <img src="preview/pets/mio-idle.gif" width="80"/> | **아키야마 미오** | 왼손잡이 선버스트 재즈베이스 | `pets/mio/` |
| <img src="preview/pets/ritsu-idle.gif" width="80"/> | **타이나카 리츠** | 드럼스틱, 멜로우 옐로 힙긱 키트 | `pets/ritsu/` |
| <img src="preview/pets/tsumugi-idle.gif" width="80"/> | **코토부키 츠무기** | KORG TRITON Extreme 76키 | `pets/tsumugi/` |
| <img src="preview/pets/azusa-idle.gif" width="80"/> | **나카노 아즈사** | 캔디 애플 레드 펜더 머스탱 | `pets/azusa/` |

<details>
<summary><b>캐릭터별 아홉 가지 상태 전부</b></summary>
<p align="center">
  <img src="preview/pets/yui-all-states.gif" width="120" alt="유이, 아홉 상태"/>
  <img src="preview/pets/mio-all-states.gif" width="120" alt="미오, 아홉 상태"/>
  <img src="preview/pets/ritsu-all-states.gif" width="120" alt="리츠, 아홉 상태"/>
  <img src="preview/pets/tsumugi-all-states.gif" width="120" alt="츠무기, 아홉 상태"/>
  <img src="preview/pets/azusa-all-states.gif" width="120" alt="아즈사, 아홉 상태"/>
</p>
<p align="center"><sub>idle · running-right · running-left · waving · jumping · failed · waiting · active-work · review</sub></p>
</details>

`pet.json` 매니페스트는 패키지 형식을 읽어 볼 수 있게 넣어 뒀다. 스프라이트시트는 없다.
[직접 그리기](#직접-그리기)를 보면 된다.

## 그 밖에 하는 일

에이전트를 비추는 것 말고도, 펫은 제 나름의 생활이 있고 몇 가지는 대신 해 준다.

**혼자서.** 아무 일도 없으면 화면을 가로질러 돌아다니고, 불규칙한 간격으로 눈을 깜빡이고,
열려 있는 창의 윗변에 올라가 그 위를 걷고, 화면 벽을 타고 오른다. 잡아서 끌면 끄는 방향으로
달리고, 움직이는 채로 놓으면 포물선을 그리며 날아가 화면 끝에서 튕기고 자리를 잡는다.

**쳐다보긴 하는데 계속은 아니다.** 열여섯 방향 시선을 쓰되, 커서가 들어오거나 클릭하거나
상태가 바뀔 때만 3~5초 눈을 준다. 타이핑하는 동안에는 먼저 쳐다보지 않는다. 계속 바라보면
그건 응시가 되기 때문이다.

**시켜서.** 우클릭 메뉴에는 손 흔들기, 점프, 벽 타기, 뽀모도로 시작(25분 집중 5분 휴식),
펫 바꾸기, 음악 플레이어 열기가 있다. 나머지는 설정 창 한자리에 모았다 — 언어, 크기,
투명도, 클릭했을 때, 자율 행동 켜고 끄기, 대사와 목소리, 음악 폴더, 작업 표시 설정.
트레이에도 올라가는데, 클릭 통과를 켠 뒤 되돌리는 길이 트레이뿐이다.

**음악.** 내 폴더의 음원을 플레이어 창으로 튼다. 검색·무작위와 노래·반주·배경음악 필터가
있고, 펫이 말하는 동안에는 음량이 잠깐 줄어든다.

**세 가지 언어.** 한국어·English·日本語. 화면 문구뿐 아니라 펫이 하는 대사까지 바뀌고,
다시 켤 필요 없이 그 자리에서 반영된다.

**말풍선.** 작업 제목과 한 줄짜리 설명이 담긴다. `privacyMode`가 기본으로 켜져 있어서
대화 내용을 그대로 옮기는 대신 무슨 도구를 썼는지로 말한다. 실제 내용을 보고 싶으면
`config.json`에서 끄면 된다. `showJapanese`를 켜면 한국어 아래 일본어가 한 줄 붙는다.

**전체화면.** 전체화면 앱이 뜨면 알아서 숨고, 끝나면 돌아온다.

## 동작 구조

```
Claude Code 훅 ──▶ sessions/<source>/<session_id>.json   (작은 PetState 파일)
                                │   (세션마다 자기 것을 쓴다)
                                ▼
                     오버레이가 폴링해 우선순위로 집계
                (waiting > failed > working > done > idle)
                                ▼
                        펫 애니메이션 + 말풍선
```

```
PetState = {source, session_id, phase, title, detail, transcript, ts, expires_at?}
phase    = idle | working | waiting | done | failed
```

이 형식에는 클로드에만 해당하는 게 하나도 없다. JSON 파일을 쓸 수 있는 것이면 무엇이든
펫을 움직일 수 있고, 아래 CLI가 하는 일이 정확히 그것이다.

## 설치

```bash
./install.sh          # 오버레이를 배치하고 Claude Code 훅을 등록한다
./install.sh --dry-run
```

Windows 쪽에 Python과 PySide6가, WSL 쪽에 훅이 필요하다. `settings.json`에 이미 있던 훅은
그대로 두고, `--uninstall`로 전부 되돌릴 수 있다. 자세한 건 `overlay/README.md`에 있다.

## 내 스크립트에서 부리기

같이 들어 있는 `yui` CLI가 같은 `PetState`를 쓴다. 오래 도는 작업이면 무엇이든 펫에게
말을 걸 수 있다.

```bash
yui start "학습"                    # 작업 중으로 바뀐다
yui done  "학습" "3에폭 끝"          # 녹색 체크, 그다음 손 흔들기
yui fail  "빌드" "테스트 실패"        # 빨간색
yui wait  "확인 필요"                # 주황색, 이쪽을 본다
yui clear                          # idle로 되돌린다

# 명령을 감싸도 된다. 종료 코드가 완료·실패를 정하고, 그대로 전달된다
yui run -t "학습" -- python train.py
```

호출하는 쪽마다 `sessions/cli/<id>.json`에 쓴다. CLI 작업 하나와 Claude Code 세션 셋이
서로 밟지 않고 공존한다.

## 펫 바꾸기

펫을 우클릭하고 **펫 바꾸기**를 고른다. 고른 값은 `config.json`에 남는다.

```jsonc
{ "pet": "" }        // "" = 배포 폴더 루트의 기본 시트
{ "pet": "ritsu" }   // = pets/ritsu/spritesheet.webp
```

오버레이는 배포된 `pets/*/`를 훑어 매니페스트와 시트가 같이 있는 폴더를 찾는다.

```text
~/.yui-pet/
├── spritesheet.webp        ← 기본 펫, 배포 폴더 루트
├── config.json
└── pets/
    ├── mio/{pet.json, spritesheet.webp}
    ├── ritsu/{pet.json, spritesheet.webp}
    └── …
```

매니페스트는 다섯 줄이다.

```json
{
  "id": "ritsu",
  "displayName": "Tainaka Ritsu",
  "description": "…",
  "spriteVersionNumber": 2,
  "spritesheetPath": "spritesheet.webp"
}
```

두 파일이 든 폴더를 넣기만 하면 메뉴에 뜬다. 코드를 고칠 일도, 펫마다 따로 맞출 일도 없다.
타이밍 표와 `lines.json`은 모든 펫이 같이 쓴다.

## 직접 그리기

런타임은 `pet.json`이 가리키는 Codex Pet v2 아틀라스를 읽는다. **그 그림은 여기 없다.**
`SPRITE_SPEC.md`에 규격이 다 있으니 — 1536×2288, 192×208 셀 8×11, 상태 아홉 행과 시선 두 행 —
직접 캐릭터를 그리거나, 권리를 가진 시트를 로더에 물리면 된다.

## 뭐가 들어 있나

| 경로 | |
|---|---|
| `overlay/yui_pet.py` | PySide6 투명 오버레이 |
| `overlay/config.json`, `lines.json` | 표시 설정과 고쳐 쓸 수 있는 대사 |
| `hooks/` | Claude Code 와 Codex 가 같이 쓰는 상태 기록기 |
| `tools/` | 훅 등록 도구, `yui` CLI, 스프라이트 업스케일러 |
| `pets/*/pet.json` | 다섯 캐릭터의 패키지 매니페스트 |
| `preview/` | 상태 애니메이션, 시선 방향, 로스터 시트 |
| `SPRITE_SPEC.md` | 직접 그릴 때 볼 아틀라스 규격 |
| `install.sh` | 한 줄 배포 |
| `README.{ko,ja,zh-CN}.md` | 같은 README의 한국어·일본어·중국어판 |

## 어디서 왔나

Codex Pet v2, 그리고 Shimeji와 그 후예들이 이어 온 데스크톱 마스코트의 계보에서 출발했다.
오버레이와 훅 기반 상태 구조, 애니메이션 세트는 그 위에 얹은 내 작업이다.

## 라이선스와 에셋

**소스 코드**는 MIT © 2026 김성진 (`LICENSE` 참고).

**폰트** `PretendardVariable.ttf`는 길형진 님의 작업이고 SIL 오픈 폰트 라이선스를 따른다.

**캐릭터 그림은 이야기가 다르다.** 히라사와 유이, 아키야마 미오, 타이나카 리츠,
코토부키 츠무기, 나카노 아즈사는 *케이온!*의 캐릭터이고 권리는 권리자에게 있다
(© Kakifly · 호분샤 · TBS · 교토 애니메이션). 여기 있는 그림은 팬이 만든 비영리물이고,
어떤 라이선스로도 제공하지 않으며, 가져다 쓰면 안 된다. 저해상 미리보기 애니메이션만
공개했고 스프라이트시트 자체는 배포하지 않는다. 직접 캐릭터를 그리는 쪽으로 가면 된다 —
`SPRITE_SPEC.md`가 그러라고 있는 문서다. 이 프로젝트는 권리자와 아무 관계가 없고
승인을 받은 적도 없다.
