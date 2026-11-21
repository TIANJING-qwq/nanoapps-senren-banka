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

```
cd NanoApps
python tools/unpack_xp3.py extract "K:\千恋＊万花\bgimage720.xp3" build/sb_bg --decrypt "K:\千恋＊万花\补丁\解密补丁\xp3filter.tjs"
python tools/scn_carve.py    "K:\千恋＊万花\scenario.pck" build/sb_scn
python tools/sb_extract.py   build/sb_scn  build/sb_dialogue.tsv
python tools/sb_topack.py    build/sb_dialogue.tsv build/sb_pack
python tools/sb_bgimport.py  build/sb_full
python tools/sb_sprimport.py build/sb_full 2000
python tools/sb_cgimport.py  build/sb_full
python tools/sb_fullpack.py  build/sb_pack  build/sb_full
python tools/sb_checkall.py  build/sb_full     # 应输出 0 bad
python tools/sb_preview.py   build/sb_full build/sb_full_preview.png
```

## 五、可选增强（需要你协助，二选一或都做）

### 1. 每句说话人名字 + 立绘真名 + 背景精确名
用 KrkrExtract GUI（你找的 https://github.com/xmoezzz/KrkrExtract）：
放进游戏目录 → 启动游戏 → 点 `!!Dump!!` → 等待完成 →
把生成的 dump 目录路径告诉我。之后每句台词都会显示
说话人名字并切换对应立绘。

### 2. 语音 / BGM（需要 KrkrExtract dump + 空间预算）
原始音档很大：**voice.xp3 1.29 GB、bgm.xp3 251 MB**，全部转成
nano 能直读的 WAV 会更大——**全量语音在本机不可行**（体积要求冲突）。
实测确认剧本数据里不含逐句语音绑定（37,188 句中仅 34 句带语音引用），
逐句归属只在 .ks 文本里。因此语音是"**dump 后按需精选**"的可选项：
dump 完成后告诉我想保留哪些角色线/章节，我按体积预算
（建议 ≤300 MB）精选转换接入。BGM 同理（可先挑 10 首左右）。

## 六、已知边界

- 语音/BGM 默认无声：原始 OGG 体积（1.29 GB）超出"体积不过大"要求，
  且逐句绑定只在 .ks 文本里——见"可选增强 2"
- 立绘为"章节主角"式出场（精确到每句需 dump 数据）
- 部分场景切换为近似图（背景真名映射同样待 dump 精确化；
  可编辑 `NanoApps/build/bg_map.tsv` 后重跑第四节管线手动校正）
