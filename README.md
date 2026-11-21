# 千恋万花 · iPod nano 7 移植

**Senren Banka (千恋＊万花) — a full visual-novel port for iPod nano 7,
running as a homebrew NanoApps app. 88 chapters, 37,201 lines of story,
real backgrounds / sprites / CG gallery, chapter-based saves and a
flowchart — on a 240×432 screen turned sideways.**

> 个人自用项目：把我在 Windows 上合法持有的《千恋＊万花》
> （Yuzusoft / 柚子社）移植到自己的 iPod nano 7 上离线游玩。
> **本仓库只包含代码与工具，不含任何游戏资源**——生成数据包
> 需要你自己的游戏副本。

[![English](https://img.shields.io/badge/note-中文为主-blue)](#) 
[![License](https://img.shields.io/badge/license-upstream_NanoApps-green)](LICENSE)

---

## 功能

| 模块 | 说明 |
|---|---|
| 完整剧情 | 92 章 38,246 句中文台词，说话人逐句显示+立绘联动切换 |
| 打字机 | 文字逐字播放（瞬/快/普/慢四档），点击补全、再点下一句 |
| 语音 | 24,248 句绑定原版语音：点下一句播下一句、不叠音；文本框底部语音长度进度条（可选包，见下） |
| 文本框 | 原版式下深上弱渐变 |
| 章节结构 | 共通线/芳乃/茉子/丛雨/蕾娜/小春·芦花/后日谈 七组「章节选择」直达 |
| BGM | 每章自动播放该章原版 BGM（可选包 25 首） |
| 存档 | 8 手动槽 + 快速槽 + 自动槽，**按 chapter 定位**，带预览文字 |
| 流程图 | 92 个章节点，已到访点亮、点击跳转 |
| 快进/快退 | 音量键长按快进；回看最近 24 行历史 |
| 画面 | 83/115 背景真名精确直连 + 立绘（TLG5 全量解码）+ 75 张 EV CG 鉴赏库 |
| 体积 | 主包 15.8 MB（zip）；语音/BGM 可选包另计 |

## 仓库结构

```
apps/vn/          C 引擎（freestanding，~2000 行）：章节系统/存档/流程图/
                  CG 鉴赏/输入/渲染，README.md 是格式规范
tools/            数据管线（Python，Windows 可跑）：
  unpack_xp3.py     XP3 解包 + cxdec 解密
  scn_carve.py      scenario.pck → 92 个 PSB 卷
  sb_extract.py     PSB → 全部台词 TSV
  sb_topack.py      TSV → VNPK 章节脚本 + flow.idx
  sb_bgimport.py    背景/CG 导入（PNG→VNBI RGB565）
  sb_sprimport.py   立绘导入（自研 TLG5 解码器 tlg5.py）
  sb_cgimport.py    CG 鉴赏库
  sb_fullpack.py    汇总数据包（含字形提取）
  sb_checkall.py    全量校验（37,201 句 0 bad）
  sb_preview.py     数据包渲染预览图
LINUX.md          Linux 虚拟机构建指南
INSTALL.md        安装与使用指南（中文）
README.md         本文件
```

## 快速开始

### 构建（Linux / 虚拟机）

见 [LINUX.md](LINUX.md)。核心两步：

```bash
./start build vn        # 产出 .nanoapp 应用
./start install vn      # SCSI 安装（或手动把 .nanoapp 拷进 iPod /Apps/）
```

### 数据包

从你自己的游戏副本生成（Windows，详见 [INSTALL.md](INSTALL.md) 第四节）：

```bash
python tools/unpack_xp3.py extract "<游戏>\bgimage720.xp3" build/sb_bg --decrypt "<游戏>\补丁\解密补丁\xp3filter.tjs"
python tools/scn_carve.py    "<游戏>\scenario.pck" build/sb_scn
python tools/sb_extract.py   build/sb_scn  build/sb_dialogue.tsv
python tools/sb_topack.py    build/sb_dialogue.tsv build/sb_pack
python tools/sb_bgimport.py  build/sb_full
python tools/sb_sprimport.py build/sb_full 2000
python tools/sb_cgimport.py  build/sb_full
python tools/sb_fullpack.py  build/sb_pack  build/sb_full
python tools/sb_checkall.py  build/sb_full    # 应输出 0 bad
```

把 `build/sb_full/` 的**内容**拷入 iPod `/Data/vn/`，打开「千恋万花」。

## 格式规范（引擎 ↔ 工具锁定）

详见 [apps/vn/README.md](apps/vn/README.md)。速览：

- `VNPK` 脚本：opcodes 0-10（END/LABEL/BG/SPR/SPRCLR/BGM/SAY/CHOICE/
  JUMP/WAIT/**NEXT=跨章**）；字符串 = u16 长度 + UTF-8
- `VNBI` 图像：RGB565（fmt0）/ +A8（fmt1）
- `VNSV` 存档 v3：偏移 12 = u16 chapter
- `VNFL` 流程图 v2：节点 = 章号；`VNCG` CG 清单

## 技术笔记

- **TLG5 解码**（tools/tlg5.py）：对照 krkrz 官方 SaveTLG5/LoadTLG
  实现的纯 Python 解码器——LZSS 滑窗（4096，跨块跨通道共享）+
  Wisteria 行差分色变换。1,725 张立绘全量可解。
- **PSB 剧本解析**：EVB 容器扫描 → zlib 流 → PSB v2 结构 → 字符串
  表（u24 步长自动探测）→ 指令流 0x0E 引用提取台词。
- **说话人**：章节主角立绘自动出场（章名匹配）；逐句绑定需要
  KrkrExtract dump 的 .ks 文本（管线接口已备）。

## 致谢与许可

- 底座是 [NanoApps](https://github.com/nfzerox/NanoApps) ——
  iPod nano 7 自制应用平台（LVGL 渲染、Home Screen 集成、SCSI 传输）。
  许可证见 [LICENSE](LICENSE)，平台文档见其上游仓库。
- 游戏本体 © Yuzusoft。本项目不含其任何资源；数据包由用户
  自备副本生成，仅供个人离线游玩。
