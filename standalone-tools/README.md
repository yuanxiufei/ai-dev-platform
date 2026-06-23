# 🖥️ 远程唤醒 WOL 完整教程

> **从公司/外面远程唤醒家里休眠的电脑** — 零成本方案
>
> 使用你自己的阿里云域名 + 华为路由器 + Python 脚本

---

## 目录

1. [原理概述](#1-原理概述)
2. [前置条件](#2-前置条件)
3. [第一步：获取阿里云 AccessKey](#3-第一步获取阿里云-accesskey)
4. [第二步：配置 DDNS 脚本](#4-第二步配置-ddns-脚本)
5. [第三步：路由器端口转发](#5-第三步路由器端口转发)
6. [第四步：测试与使用](#6-第四步测试与使用)
7. [开机自启（可选）](#7-开机自启可选)
8. [常见问题排查](#8-常见问题排查)
9. [快速参考卡](#9-快速参考卡)

---

## 1. 原理概述

### 什么是 Wake-on-LAN (WOL)

WOL 是一种网络标准，让电脑在关机/休眠状态下通过网卡接收特殊的「魔术包」（Magic Packet）来唤醒。

```
正常开机: 按电源按钮 → BIOS → 引导 → 操作系统
WOL唤醒:   收到魔术包 → 网卡唤醒主板 → BIOS → 引导 → 操作系统
```

魔术包结构：
```
┌─────────────┬──────────────────────────────────────────────┐
│ 6字节前缀    │  MAC 地址重复 16 次（共 48 字节）             │
│ FF FF FF FF │ AA BB CC DD EE FF × 16                      │
│ FF FF       │                                              │
└─────────────┴──────────────────────────────────────────────┘
总大小: 102 字节, 通过 UDP 端口 9（或 7）发送
```

### 为什么不能直接跨互联网唤醒

```
❌ 不行的情况:
公司电脑 ──(Internet)──→ 家路由器 ──x──→ 休眠的电脑
                           ↑
                  广播包在这里被丢弃！
                  路由器不转发跨子网广播

✅ 我们的方案:
公司电脑 ──(UDP:9)──→ wake.reginyuan.com(DDNS) ──→ 路由器端口转发
                                                         ↓
                                                   局域网广播 → 电脑唤醒
```

### 整体架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                        你的家（局域网）                            │
│                                                                  │
│  ┌──────────────┐    UDP:9     ┌──────────────┐                 │
│  │ 电脑(休眠)    │◄────────────│ 华为路由器     │                 │
│  │ MAC:xx:xx:xx │   广播/转发   │ 192.168.3.1  │                 │
│  │ IP:.11 (固定)│              │ 端口映射:9→9  │                 │
│  └──────────────┘              └──────┬───────┘                 │
│                                        │                         │
│                              公网 IP（动态变化）                  │
│                                   │                             │
└───────────────────────────────────┼─────────────────────────────┘
                                    │ Internet
                                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                        阿里云 DNS                                │
│                                                                  │
│  wake.reginyuan.com ──A记录──► 自动更新为当前公网 IP              │
│                       （每5分钟检测一次）                          │
└──────────────────────────────────┬───────────────────────────────┘
                                   │ DNS 解析
                                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                      公司 / 外面任意位置                           │
│                                                                  │
│  python wake_server.py                                           │
│    --mac xx:xx:xx:xx:xx:xx                                      │
│    --broadcast wake.reginyuan.com                                │
│    --port 9                                                      │
│                                                                  │
│  发送 UDP 魔术包 → wake.reginyuan.com:9 → 家里 → 唤醒！          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. 前置条件

### 硬件要求

| 项目 | 要求 |
|------|------|
| 被唤醒的电脑 | 支持网卡 WOL（近10年电脑基本都支持） |
| 路由器 | 有线连接到电脑（WOL 通常只支持有线网卡） |
| 域名 | 一个阿里云管理的域名 |

### 软件准备

```bash
# 本项目已包含所有脚本，位于 standalone-tools/ 目录：
standalone-tools/
├── wake/
│   ├── wake_server.py      ← WOL 魔术包发送工具
│   └── wake_server.bat     ← Windows 一键启动
└── ddns/
    ├── aliddns.py          ← 阿里云 DDNS 自动更新
    ├── aliddns_config.json ← 配置文件（自动生成）
    ├── run_aliddns.bat     ← 启动 DDNS 守护进程
    └── install_ddns_service.bat ← 注册 Windows 开机自启
```

### BIOS 设置（被唤醒的电脑）

1. 重启电脑，按 **Del / F2 / F10** 进入 BIOS
2. 找到 **Power Management**（电源管理）
3. 开启 **Wake-on-LAN** 或 **Power By PCI-E**
4. **关闭 ErP / EuP**（欧洲节能模式，会彻底断电导致无法唤醒）
5. 按 **F10** 保存退出

> 不同品牌 BIOS 菜单位置不同，常见路径：
> - ASUS: Advanced → APM Configuration → Power On By PCI-E
> - Dell: Power Management → Wake-on-LAN
> - Lenovo: Power → Wake on LAN
> - HP: Advanced → Power-On Options

### Windows 网卡设置（被唤醒的电脑）

1. **Win + X** → **设备管理器**
2. 展开 **网络适配器**，找到你的网卡（Realtek/Intel）
3. 右键 → **属性** → **电源管理** 选项卡
4. ✅ **勾选**「允许此设备唤醒计算机」
5. ✅ **勾选**「只允许魔术包唤醒计算机」
6. 切换到 **高级** 选项卡
7. 找到 **Wake on Magic Packet** → 设为 **Enabled**
8. 找到 **Shutdown Wake-On-LAN** → 设为 **Enabled**

```
设备管理器 → 网络适配器 → 你的网卡
├── 电源管理选项卡
│   ✓ 允许此设备唤醒计算机
│   ✓ 只允许魔术包唤醒计算机
│   ☐ 关闭以节约电量（不要勾这个！）
└── 高级选项卡
    ✓ Wake on Magic Packet = Enabled
    ✓ Shutdown Wake-On-LAN = Enabled
```

> ⚠️ **关键验证**: 正确配置后，电脑关机后网卡灯应该还亮着（橙灯/绿灯），表示网卡仍在供电等待接收魔术包。

---

## 3. 第一步：获取阿里云 AccessKey

> ⚠️ **安全提醒**: 不要用主账号 Root 的 Key！必须创建 RAM 子账号，只给 DNS 权限。

### 3.1 创建 RAM 子用户

1. 打开 https://ram.console.aliyun.com/users
2. 点击 **创建用户**
3. 填写信息：

| 字段 | 示例值 |
|------|--------|
| 登录名称 | `ddns-updater`（可自定义） |
| 显示名称 | `DDNS自动更新` |
| 访问方式 | ✅ **勾选 OpenAPI 调用访问** |
| 控制台密码 | 可选（纯 API 调用不需要） |

4. 点击 **确定** 创建

### 3.2 授权 DNS 权限

1. 在用户列表中点击刚创建的用户名 `ddns-updater`
2. 点击 **权限管理** 标签页 → **新增授权**
3. 搜索框输入：`AliyunDNSFullAccess`
4. 选择该策略 → **确定**

```
RAM 子账号 ddns-updater 的权限树:

Root (主账号)
└── ddns-updater (子账号)
    ├── AliyunDNSFullAccess  ✅ 只有这个！
    └── AccessKey (待创建)
```

> 只给 DNS 权限，即使 Key 泄露也只能改域名解析，动不了其他资源。

### 3.3 创建 AccessKey

1. 在用户详情页点击 **认证管理** 标签页
2. 点击 **创建 AccessKey**
3. 选择 **本地开发环境中使用**（我们的场景就是本地运行脚本）
4. 勾选安全提示 → **继续创建**
5. **立即复制保存** AccessKey ID 和 Secret（只显示一次！）

```
AccessKey ID:     LTAI5t6w1xxxxxxxxx
AccessKey Secret: xxxxxxxxxxxxxxxxxx    ← 保密！不要分享给任何人
```

---

## 4. 第二步：配置 DDNS 脚本

### 方式一：命令行向导（推荐首次使用）

打开 PowerShell / CMD：

```bash
cd d:\code\ai-fullstack-platform\standalone-tools\ddns

python aliddns.py --setup
```

交互式填写：

```
============================================================
  阿里云 DDNS 配置向导
============================================================

【第1步】阿里云 AccessKey 凭证
  AccessKey ID: LTAI5t6w1xxxxxxxxx        ← 输入后回车
  AccessKey Secret: xxxxxxxxxxxxxxxxxx     ← 输入后回车

【第2步】域名配置
  你的域名 (例如: example.com): reginyuan.com  ← 输入你的域名
  子域名 (默认: wake): wake                    ← 回车或输 wake

【第3步】记录类型
  选择类型 [A/AAAA，默认: A]: A               ← 直接回车

【第4步】其他设置
  检测间隔秒数 (默认: 300):                   ← 回车（5分钟）
  DNS TTL 秒数 (默认: 600):                   ← 回车（10分钟）

============================================================
✅ 配置已保存！
   配置文件: d:\...\aliddns_config.json
   你的动态域名: wake.reginyuan.com
============================================================
```

### 方式二：手动编辑配置文件

如果不想用向导，直接编辑 `ddns/aliddns_config.json`：

```json
{
  "access_key_id": "LTAI5t6w1xxxxxxxxx",
  "access_key_secret": "xxxxxxxxxxxxxxxx",
  "domain": "reginyuan.com",
  "subdomain": "wake",
  "record_type": "A",
  "interval": 300,
  "ttl": 600,
  "created_at": "2026-06-20T20:00:00",
  "last_ip": "",
  "last_updated": ""
}
```

| 字段 | 说明 | 示例 |
|------|------|------|
| `access_key_id` | RAM 用户的 AK ID | `LTAI5t6w...` |
| `access_key_secret` | RAM 用户的密钥 | `V221NMTp...` |
| `domain` | 你在阿里云管理的域名 | `reginyuan.com` |
| `subdomain` | 子域名前缀 | `wake` → 最终: `wake.reginyuan.com` |
| `record_type` | `A`=IPv4, `AAAA`=IPv6 | `A` |
| `interval` | 检测间隔（秒） | `300` = 5分钟 |
| `ttl` | DNS 缓存时间（秒） | `600` = 10分钟 |

### 测试 DDNS 是否工作

```powershell
cd d:\code\ai-fullstack-platform\standalone-tools\ddns

python aliddns.py --test
```

成功输出：

```
2026-06-20 20:00:00 [INFO] 成功获取公网 IPv4: 123.45.67.89
2026-06-20 20:00:01 [INFO] [新增记录] wake.reginyuan.com → 123.45.67.89
2026-06-20 20:00:02 [INFO] ✅ DNS 已更新: wake.reginyuan.com → 123.45.67.89
```

> 如果看到 `[无需更新] IP 未变` 也算成功，说明记录已存在且 IP 没变。

### 验证 DNS 解析

等 1-2 分钟后（DNS 生效需要一点时间）：

```bash
# Windows CMD
nslookup wake.reginyuan.com

# PowerShell
Resolve-DnsName wake.reginyuan.com

# 或者直接 ping
ping wake.reginyuan.com
```

返回你家公网 IP 就说明 DDNS 配置成功了！

---

## 5. 第三步：路由器端口转发

> 以华为路由器为例，其他品牌路由器类似。

### 5.1 进入路由器管理页面

1. 浏览器打开 **http://192.168.3.1**（华为默认地址）
2. 输入管理员密码登录

### 5.2 固定电脑 IP（静态绑定）

确保被唤醒的电脑有固定 IP，这样端口转发才能稳定指向它：

1. 左侧菜单：**网络设置** → **局域网**
2. 找到 **静态 IP 地址绑定列表** → 点 **➕**
3. 填写：

| 字段 | 示例值 |
|------|--------|
| 设备名称 | 我的电脑 |
| MAC 地址 | `84:9E:56:02:7C:01`（你电脑网卡的MAC） |
| IP 地址 | `192.168.3.11` |

4. 点保存

> 如何查看电脑 MAC 地址？Windows 下打开 CMD 运行 `ipconfig /all`，找「物理地址」。

### 5.3 配置端口映射

1. 左侧菜单：**安全设置** → **NAT 服务**
2. 找到 **端口映射** 区域 → 点右边的 **➕ 加号**
3. 填写：

| 字段 | 值 | 说明 |
|------|-----|------|
| 服务名 | `WOL唤醒` | 随便起名 |
| 服务类型 | 端口映射 | 默认值不变 |
| 设备 | 我的主机 | 选你的电脑 |
| 主机 IP | `192.168.3.11` | 固定的内网IP |
| 协议类型 | **UDP** | **关键！必须是 UDP 不是 TCP** |
| 内部端口 | **9** | WOL 默认端口 |
| 外部端口 | **9** | 对外暴露的端口 |

4. 点 **保存**

```
华为路由器端口映射配置示例：

┌──────────────────────────────────────┐
│  编辑服务                             │
│                                      │
│  服务名:    WOL唤醒                   │
│  服务类型:  端口映射                  │
│  设备:      我的主机 ▼                │
│  主机 IP:   192.168.3.11             │
│  协议类型:  UDP ▼         ← 必须是UDP!│
│  内部端口:  9                         │
│  外部端口:  9                         │
│                                      │
│     [取消]              [保存]        │
└──────────────────────────────────────┘
```

> ⚠️ **三个关键点**:
> 1. 协议必须是 **UDP**（TCP 不能发广播）
> 2. 内外端口都是 **9**（WOL 标准）
> 3. 如果能填广播地址 `192.168.3.255` 更好；填单机 IP 大部分情况也能工作

---

## 6. 第四步：测试与使用

### 6.1 先测试局域网唤醒（确认电脑 WOL 已开）

在家里另一台设备上（或手机装 WOL App）：

```bash
cd d:\code\ai-fullstack-platform\standalone-tools\wake

python wake_server.py --mac 84:9E:56:02:7C:01
```

或者用 bat 一键启动（先编辑 bat 文件填入你的 MAC）：

```bash
wake_server.bat
```

电脑应该在 **10-60 秒内** 启动。如果不启动，回到第 2 节检查 BIOS 和网卡设置。

### 6.2 测试跨互联网唤醒（最终目标）

在公司或用手机流量（确保不在家里 WiFi）：

```bash
cd d:\code\ai-fullstack-platform\standalone-tools\wake

python wake_server.py --mac 84:9E:56:02:7C:01 --broadcast wake.reginyuan.com --port 9
```

预期输出：

```
  [DNS] 正在解析域名: wake.reginyuan.com ...
  [DNS] 解析成功: wake.reginyuan.com → 123.45.67.89

  ✓ 魔术包已发送！
    目标 MAC : 84:9E:56:02:7C:01
    目标地址 : 123.45.67.89:9 (wake.reginyuan.com)
    包大小   : 102 字节

  如果目标机器已正确配置 Wake-on-LAN，
  它将在 10-60 秒内启动。
```

### 6.3 常用命令速查

```bash
# === WOL 唤醒 ===

# 局域网唤醒（最简单）
python wake_server.py --mac AA:BB:CC:DD:EE:FF

# 指定广播地址
python wake_server.py --mac AA:BB:CC:DD:EE:FF --broadcast 192.168.3.255

# 跨互联网唤醒（DDNS 域名）
python wake_server.py --mac AA:BB:CC:DD:EE:FF --broadcast wake.yourdomain.com --port 9

# 连续发 3 次（提高可靠性）
python wake_server.py --mac AA:BB:CC:DD:EE:FF --count 3

# === DDNS 管理 ===

# 单次测试
python aliddns.py --test

# 后台守护模式（持续运行）
python aliddns.py

# 查看状态
python aliddns.py --status

# 强制更新（忽略IP是否变化）
python aliddns.py --force
```

---

## 7. 开机自启（可选）

让家里的电脑开机后自动运行 DDNS 更新脚本，这样公网 IP 变化时域名始终指向最新地址。

### 方式一：安装为 Windows 计划任务（推荐）

```bash
# 管理员权限运行
cd d:\code\ai-fullstack-platform\standalone-tools\ddns
install_ddns_service.bat
```

这会注册一个 Windows 计划任务：
- 触发条件：**用户登录时**
- 动作：后台运行 `aliddns.py`
- 每 **5分钟** 检测一次公网 IP 并更新 DNS

### 方式二：手动添加到启动文件夹

1. **Win + R** → 输入 `shell:startup` → 回车
2. 把 `run_aliddns.bat` 的快捷方式复制进去
3. 以后每次登录 Windows 会自动运行 DDNS

### 方式三：创建快捷方式双击启动

编辑 `run_aliddns.bat`（已经预配好了），双击即可运行：

```bat
@echo off
chcp 65001 >nul
title AliDDNS - 阿里云动态域名更新
echo ============================================
echo   AliDDNS 守护模式
echo   按 Ctrl+C 可停止
echo ============================================
echo.

cd /d "%~dp0"
python aliddns.py
pause
```

---

## 8. 常见问题排查

### Q1: 发了魔术包但电脑没反应

| 可能原因 | 解决方法 |
|----------|----------|
| BIOS 没 开 WOL | 重启进 BIOS 开启 Wake-on-LAN |
| ErP/EuP 没关 | BIOS 里关闭节能模式 |
| 网卡设置不对 | 设备管理器→网卡→电源管理→允许唤醒 |
| 电脑是无线上网 | WOL 一般只支持有线网卡，插网线！ |
| 关机后网卡灯灭了 | BIOS 设置没生效，重新检查 |
| 用的是 WiFi 连接 | 必须**有线连接**到路由器 |

### Q2: DDNS 测试报错

```
错误: 无法解析域名 / API 调用失败
```

| 错误信息 | 原因 | 解决 |
|----------|------|------|
| `配置文件不存在` | 还没运行 `--setup` | 先运行 `python aliddns.py --setup` |
| `InvalidAccessKeyId` | Key 填错了 | 检查 config.json 里的 key |
| `SignatureDoesNotMatch` | Secret 填错了 | 重新复制粘贴 Secret |
| `Forbidden.DoNotHavePermission` | 没给 DNS 权限 | 去 RAM 控制台加 `AliyunDNSFullAccess` |
| `DomainRecordNotExist` | 首次使用，还没建记录 | 这是正常的，脚本会自动创建 |
| `所有 IP 检测服务均失败` | 网络不通 | 检查能否上网 |

### Q3: 从外面发魔术包收不到

| 症状 | 原因 | 解决 |
|------|------|------|
| 能解析域名但连不上 | 端口转发没生效 | 检查路由器端口映射是否保存 |
| DNS 解析超时 | DDNS 脚本没在跑 | 家里电脑上运行 `run_aliddns.bat` |
| 解析到的 IP 不对 | 公网 IP 变了但脚本没更新 | 检查脚本是否正常运行中 |
| 运营商封了 UDP:9 | 部分运营商限制 | 尝试换外部端口（如 1234） |

### Q4: 公网 IP 变了但 DDNS 没更新

```bash
# 查看 DDNS 当前状态
python aliddns.py --status

# 手动强制触发一次更新
python aliddns.py --force

# 查看 DDNS 日志
type aliddns.log
```

### Q5: 华为路由器找不到端口转发

不同固件版本菜单位置可能略有差异：

```
尝试以下路径：
安全设置 → NAT 服务 → 端口映射
安全设置 → 端口转发 → 虚拟服务器
更多功能 → 高级设置 → NAT → 端口映射
```

---

## 9. 快速参考卡

### 你的个人信息（填入你的实际值）

```
┌─────────────────────────────────────────────┐
│           WOL 远程唤醒 — 个人配置卡            │
├─────────────────────────────────────────────┤
│                                             │
│  电脑 MAC 地址:  84:9E:56:02:7C:01          │
│  家里内网 IP:    192.168.3.11               │
│  路由器地址:     192.168.3.1 (华为)          │
│  广播地址:       192.168.3.255              │
│                                             │
│  动态域名:        wake.reginyuan.com         │
│  WOL 端口:        9 (UDP)                   │
│                                             │
│  阿里云域名:      reginyuan.com              │
│  RAM 用户:        ddns-updater               │
│                                             │
├─────────────────────────────────────────────┤
│  唤醒命令（从公司执行）:                      │
│                                             │
│  cd standalone-tools/wake                   │
│  python wake_server.py \                    │
│    --mac 84:9E:56:02:7C:01 \               │
│    --broadcast wake.reginyuan.com \         │
│    --port 9                                 │
│                                             │
├─────────────────────────────────────────────┤
│  DDNS 维护命令（家里电脑）:                   │
│                                             │
│  cd standalone-tools/ddns                   │
│  python aliddns.py --status   # 查状态      │
│  python aliddns.py --test     # 测试        │
│  python aliddns.py            # 守护运行    │
│                                             │
└─────────────────────────────────────────────┘
```

### 架构总览

```
┌──────────┐  ①DDNS自动更新   ┌────────────┐
│ 家里电脑  │ ───────────────→ │ 阿里云DNS   │
│ 运行脚本  │   每5分钟        │            │
└────┬─────┘                 └─────┬──────┘
     │                              │
     │ ②UDP:9 端口映射              │ ③A记录
     ▼                              ▼
┌────────────┐              ┌──────────────┐
│ 华为路由器  │◄─────────────│wake.reginyuan│
│ .3.1       │   Internet   │    .com      │
└─────┬──────┘              └──────────────┘
      │ ④广播
      ▼
┌──────────┐  ⑤收到魔术包
│ 目标电脑  │ ──────────────→ 开机!
│ (休眠)   │
└──────────┘

⑥从任意位置发送:
  python wake_server.py --mac XX:XX:XX:XX:XX:XX \
    --broadcast wake.reginyuan.com --port 9
```

---

## 附录：相关链接

| 资源 | 链接 |
|------|------|
| 阿里云 RAM 控制台 | https://ram.console.aliyun.com/users |
| 阿里云 AccessKey 管理 | https://ram.console.aliyun.com/manage/ak |
| 阿里云 DNS 控制台 | https://dns.console.aliyun.com |
| 华为路由器管理 | http://192.168.3.1 |
| 项目 GitHub | https://github.com/your-repo/ai-fullstack-platform |

---

*最后更新: 2026-06-20 | AI Fullstack Platform — Standalone Tools*
