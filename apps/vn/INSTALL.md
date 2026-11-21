# 千恋万花 · iPod nano 7 移植版 — 安装与使用指南

> 全剧情 37,201 句 · 88 章 · 真实背景/立绘/CG · 存档/快进/流程图
> 个人自用移植（你自己的游戏副本 + 自己的 nano）

## 一、这是什么

把 Windows 版《千恋＊万花》（柚子社）的完整剧情移植到 iPod nano 7
自制系统（NanoApps）上的横屏视觉小说播放器。

| 内容 | 数量 |
|---|---|
| 剧情台词 | 37,201 句（88 章，简体中文） |
| 背景/场景图 | 97 张（真实游戏图） |
| 立绘 | 19 张代表（全部 1,725 张已解码，见下"可选增强"） |
| CG 鉴赏 | 75 张 EV CG（带缩略图网格+解锁） |
| 字体 | 1,267 字形点阵 |
| 总体积 | 约 40 MB |

## 二、安装（无需重新编译应用时）

1. 在 Mac/Linux 上已完成一次 `./start build vn && ./start install vn`
   （应用本体的安装；以后只更新数据不用重复）
2. iPod 处于 **Home 主屏**状态（不是"已连接"磁盘模式），插上电脑
3. 把 `NanoApps/build/sb_full/` **里面的内容**（不是文件夹本身）
   全部拷入 iPod 磁盘的 `/Data/vn/` 目录
4. 拔线，在 nano 上打开「千恋万花」

## 三、操作说明（横屏，Home 键在左手边）

| 按键 | 功能 |
|---|---|
| 点按屏幕 | 推进对话 / 确认 |
| 音量+ 长按 | 快进（连跳） |
| 音量- | 快退（回看最近 24 行历史） |
| 双击 / 菜单手势 | 呼出游戏内菜单 |
| 游戏内菜单 | 存档/读档、快速存读档、返回标题、设置 |
| 标题界面 | 开始 / 继续 / 存档 / CG鉴赏 / 流程图 / 设置 |

- **存档**：8 个手动槽 + 快速槽 + 自动槽（每句台词自动续写），
  带预览文字；跨章节记忆（读档自动跳回所在章）
- **流程图**：已到访的章节点亮，点击直接跳转
- 章节末自动衔接下一章（点按继续）

## 四、从游戏原始文件重新生成数据包（Windows，已验证）

前提：KrkrExtract 已 dump 到 `K:\千恋＊万花\outPath`（剧本/立绘/背景
/BGM/语音真名文件）。

```
cd NanoApps
python tools/unpack_xp3.py extract "K:\千恋＊万花\bgimage720.xp3" build/sb_bg --decrypt "K:\千恋＊万花\补丁\解密补丁\xp3filter.tjs"
python tools/scn_carve.py    "K:\千恋＊万花\scenario.pck" build/sb_scn
python tools/sb_extract.py   build/sb_scn  build/sb_dialogue.tsv
python tools/sb_tjs_extract.py          # 权威：说话人+语音名+章BGM (约6分钟)
python tools/sb_topack.py    build/sb_dialogue.tsv build/sb_pack
python tools/sb_bgimport.py  build/sb_full          # bg 逻辑名表
python tools/sb_bgimport2.py build/sb_full          # 真名精确直连 83/115
python tools/sb_sprimport.py build/sb_full 2000
python tools/sb_cgimport.py  build/sb_full
python tools/sb_fullpack.py  build/sb_pack  build/sb_full
python tools/sb_checkall.py  build/sb_full     # 应输出 0 bad
python tools/sb_preview.py   build/sb_full build/sb_full_preview.png
```

## 五、语音 / BGM（可选包，KrkrExtract dump 后转换）

主包（15.8 MB zip）已含 24,248 句的**语音绑定指令**——装上语音包
即逐句发声，进度条同步；不装则安静阅读，互不影响。

### 1. 语音包（约 4.5 GB 全量 / 按章选装）

dump 了 voice.xp3（真名 ogg）后：

```powershell
# 全量（大！只适合设备空间充裕时）
python tools/sb_voiceimport.py "K:\千恋＊万花\outPath\voice.xp3" NanoApps\build\sb_voice

# 只转共通线前 3 章（试听/小空间）
python tools/sb_voiceimport.py "K:\千恋＊万花\outPath\voice.xp3" NanoApps\build\sb_voice 001 002 003

# 只转某条个人线（1=芳乃线全部 1xx 章，2=茉子 …）
python tools/sb_voiceimport.py "K:\千恋＊万花\outPath\voice.xp3" NanoApps\build\sb_voice 1
```

输出 22.05 kHz 单声道 WAV（每句平均 ~190 KB）。把 `voice/` 整个
文件夹拷到 iPod `/Data/vn/voice/` 即完成。

### 2. BGM 包（约 230 MB，25 首）

```powershell
python tools/sb_bgmimport.py "K:\千恋＊万花\outPath\bgm.xp3" NanoApps\build\sb_bgm
```

把 `bgm/` 拷到 `/Data/vn/bgm/`。每章开场自动播放该章原版 BGM。

## 六、已知边界

- 语音/BGM 均为可选包：不装无声、装上即响，主包体积不受影响
- 语音切句采用"不叠音"策略：快速点击时新句静音（设备音频
  API 为单发），正常逐句听读体验完整
- 立绘为"说话人切换"式出场（11 位主要角色，取自 dump 角色表）
- 部分背景为近似图（83/115 精确真名直连，其余启发式匹配；
  可编辑 `NanoApps/build/bg_map.tsv` 后重跑管线手动校正）
