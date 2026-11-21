# Linux 虚拟机构建指南（千恋万花 NanoApps 移植）

> 目标：在 Linux 虚拟机里编译 vn 应用并安装到 iPod nano 7。
> 以下按 Ubuntu/Debian 写；Fedora/Arch 包名见文末对照。

## 一、虚拟机准备

1. 建议 **Ubuntu 24.04 Desktop**（虚拟机已装好就跳过）
2. **网络必须可用**：构建要自动 clone LVGL 和下载 Font Awesome
   （国内网络慢可在虚拟机里配代理，或提前告诉我，我给你离线方案）
3. **USB 直通**：iPod 插宿主机后，需要在虚拟机软件里把 USB 设备
   "连接到虚拟机"：
   - VMware：可移动设备 → Apple iPod → 连接
   - VirtualBox：设置 → USB → 添加筛选器（Apple, Inc.）
4. 建议装 **open-vm-tools / virtualbox-guest-utils** 并启用共享文件夹，
   方便把仓库拷进去

## 二、装依赖（一条命令）

```bash
sudo apt update
sudo apt install -y gcc gcc-arm-none-eabi make git python3-pip   \
    cargo binutils eject dosfstools util-linux
pip3 install --user Pillow
# 把 ~/.local/bin 和 ~/.cargo/bin 加进 PATH（若没有）：
echo 'export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## 三、把仓库拷进虚拟机

在 **Windows 宿主机**上（PowerShell）：

```powershell
Compress-Archive -Path C:\Users\TIANJING\Documents\code\NanoApps `
  -DestinationPath C:\Users\TIANJING\Documents\code\nanoapps-src.zip -Force
```

把 `nanoapps-src.zip` 通过共享文件夹/浏览器拖拽传进虚拟机，然后：

```bash
unzip nanoapps-src.zip -d ~
cd ~/NanoApps
chmod +x start
```

## 四、构建（不碰设备，先验证编译通过）

```bash
cd ~/NanoApps
./start build vn
```

首次运行会自动：clone LVGL（固定 commit）、下载 Font Awesome、
编译全部系统+应用。**vn 编译通过 = 引擎代码没有编译错误**。
有任何报错把完整输出复制给我。

## 五、安装到 iPod（两种方式）

### 方式 A：直接拷贝（简单，推荐先试这个）

`./start build vn` 之后，构建产物在 `apps/vn/build/`（或 build 输出
目录）里是一个 `.nanoapp` 文件夹（含 `.hbapp` + `Info.plist`）。
**iPod 处于磁盘模式**（或用 `./start remount` 挂载），把整个
`.nanoapp` 文件夹拷到 iPod 磁盘的 **`/Apps/`** 下即可：

```bash
cp -r apps/vn/build/*.nanoapp /Volumes/NANO/Apps/
```

数据包同样拷 `/Data/vn/`（见下）。

### 方式 B：SCSI 传输（自动化）

1. iPod 插宿主机 → USB 直通到虚拟机 → 在 iPod 上保持
   **Home 主屏**状态（不要进"已连接"磁盘模式）
2. ```bash
   ./start install vn
   ```
   这会走 SCSI 传输层安装应用（工具会自动装齐设备侧依赖）。

### 数据包（两种方式都要）

```bash
./start remount
cp -r build/sb_full/* /Volumes/NANO/Data/vn/   # 挂载点按实际
./start eject
```
（数据包也可以拔下来回 Windows 宿主机拷，效果一样）

## 六、常见问题

| 症状 | 处理 |
|---|---|
| clone LVGL 超时 | 虚拟机配代理，或告诉我做离线包 |
| `arm-none-eabi-gcc: not found` | 依赖没装全，重跑第二节 |
| 找不到 iPod | 检查 USB 直通；`lsusb` 里应有 Apple 设备 |
| install 报 SCSI 错误 | iPod 必须在 Home 屏，不能是磁盘模式；换 USB 口/线 |
| 编译错误（vn.c） | 把完整报错贴给我，我改好你再重试 |

## 附：其他发行版包名

| Ubuntu (apt) | Fedora (dnf) | Arch (pacman) |
|---|---|---|
| gcc-arm-none-eabi | arm-none-eabi-gcc-cs | arm-none-eabi-gcc |
| cargo | cargo | rust |
| dosfstools | dosfstools | dosfstools |

## 检查清单（做完了就绪）

- [ ] 虚拟机能上网
- [ ] 第二节依赖装完（`arm-none-eabi-gcc --version` 有输出）
- [ ] 仓库已拷入并 `chmod +x start`
- [ ] `./start build vn` 编译通过
- [ ] USB 直通成功（`lsusb` 见 Apple 设备）
- [ ] `./start install vn` 完成
- [ ] 数据包已拷入 `/Data/vn/`
- [ ] iPod 上打开「千恋万花」🎉
