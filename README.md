<p align="center">
  <img src="https://img.shields.io/badge/version-2.0-blue?style=flat-square" alt="Version 2.0">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2B-lightgrey?style=flat-square" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.8%2B-green?style=flat-square" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/license-MIT-orange?style=flat-square" alt="License MIT">
  <img src="https://img.shields.io/badge/SDKs-46-brightgreen?style=flat-square" alt="46 SDKs">
</p>

<h1 align="center">🔧 APK 纯净大师</h1>
<h3 align="center">Android APK 通用去广告 & 反检测封装工具</h3>

<p align="center">
  <b>一键移除 APK 中的广告 SDK，支持 46 种主流广告网络，含反检测机制</b>
</p>

---

## 📖 目录

- [功能特性](#-功能特性)
- [支持的广告 SDK](#-支持的广告-sdk)
- [快速开始](#-快速开始)
- [使用方式](#-使用方式)
- [命令行参数](#-命令行参数)
- [技术架构](#-技术架构)
- [反检测机制](#-反检测机制)
- [自动更新](#-自动更新)
- [从源码构建](#-从源码构建)
- [依赖要求](#-依赖要求)
- [常见问题](#-常见问题)
- [免责声明](#-免责声明)
- [贡献指南](#-贡献指南)

---

## ✨ 功能特性

<table>
<tr>
<td width="50%">

### 🎯 核心能力
- **XML 结构化解析** — 精准定位 AndroidManifest 中广告组件，消除正则误匹配
- **五维度签名库** — Manifest / Smali / SO / Assets / Res 全覆盖检测
- **46 种广告 SDK** — 穿山甲、广点通、优量汇、快手、百度、Sigmob 等国内外主流平台
- **Smali 代码级分析** — 扫描字节码中的广告类引用、方法调用和 URL 常量
- **智能依赖解析** — YLH→GDT、WindMill→Sigmob 等 SDK 依赖链自动追踪

</td>
<td width="50%">

### 🛡️ 反检测 & 兼容
- **组件空桩生成** — 为移除的广告组件生成无操作桩，防止 `ClassNotFoundException` 触发反屏蔽弹窗
- **Android 版本感知** — API 31+ 保留 exported receiver，避免崩溃
- **权限智能过滤** — AD_ID、QUERY_ALL_PACKAGES 等敏感权限白名单保护
- **自动签名** — 集成 uber-apk-signer，输出 APK 可直接安装

### 🎨 用户体验
- **双模式运行** — GUI 图形界面 + CLI 命令行，适配不同场景
- **SDK 预扫描** — 处理前预览检测到的广告 SDK，支持按 SDK 粒度开关
- **细粒度进度** — 实时显示 apktool 解包/重打包子步骤进度
- **取消防抖** — 优雅终止子进程，无残留临时文件
- **配置持久化** — 主题、窗口位置、选项偏好自动保存

</td>
</tr>
</table>

---

## 📊 支持的广告 SDK

### 中国市场主流平台

| SDK | 厂商 | 覆盖维度 |
| --- | --- | --- |
| **穿山甲 / Pangle / CSJ** | ByteDance 字节跳动 | Manifest · Smali · SO · Assets · Res · URL |
| **广点通 / GDT** | Tencent 腾讯 | Manifest · Smali · SO · Assets · Res · URL |
| **优量汇 / YLH** | Tencent 腾讯 | Manifest · Smali · SO · Assets · Res · URL |
| **快手广告 / Kuaishou Ads** | Kuaishou 快手 | Manifest · Smali · SO · Assets · Res · URL |
| **百度广告 / Baidu Mobads** | Baidu 百度 | Manifest · Smali · SO · Assets · Res · URL |
| **Sigmob Ads** | Sigmob | Manifest · Smali · SO · Assets · Res |
| **BeiZi Ads** | BeiZi | Manifest · Smali · SO · Assets |
| **WindMill 聚合** | Sigmob | Manifest · Smali · SO · Assets · Res |
| **Mintegral / MTG** | Mintegral | Manifest · Smali · SO · Assets · Res |
| **小米广告 / MiAds** | Xiaomi 小米 | Manifest · Smali · SO · Assets · Res |
| **华为广告 / HMS Ads** | Huawei 华为 | Manifest · Smali · SO · Assets · Res |
| **OPPO 广告** | OPPO | Manifest · Smali · SO · Assets · Res |
| **vivo 广告** | vivo | Manifest · Smali · SO · Assets · Res |
| **淘宝/阿里妈妈 Tanx** | Alibaba 阿里巴巴 | Manifest · Smali · SO · Assets · Res |
| **360 广告** | 360 | Manifest · Smali · SO · Assets |
| **京东广告 / JD Ads** | JD 京东 | Manifest · Smali · SO · Assets |
| **美团广告** | Meituan 美团 | Manifest · Smali · SO · Assets |
| **B站广告 / Bilibili Ads** | Bilibili B站 | Manifest · Smali · URL |
| **网易广告 / NetEase Ads** | NetEase 网易 | Manifest · Smali · SO · Assets |
| **搜狐广告 / Sohu Ads** | Sohu 搜狐 | Manifest · Smali · Assets |
| **UC / Alibaba Ads** | Alibaba 阿里巴巴 | Manifest · Smali · SO · Assets |

### 国际平台

| SDK | 厂商 | 覆盖维度 |
| --- | --- | --- |
| **AdMob** | Google | Manifest · Smali · SO · Assets · Res · URL |
| **Unity Ads** | Unity | Manifest · Smali · SO · Assets · URL |
| **AppLovin** | AppLovin | Manifest · Smali · SO · Assets · URL |
| **Vungle** | Vungle (Liftoff) | Manifest · Smali · SO · Assets · URL |
| **ironSource** | ironSource (Unity) | Manifest · Smali · SO · Assets · URL |
| **Meta Audience Network** | Meta (Facebook) | Manifest · Smali · SO · Assets · Res · URL |
| **Mintegral** | Mintegral | Manifest · Smali · SO · Assets · Res |
| **Chartboost** | Chartboost | Manifest · Smali · SO · Assets · URL |
| **Tapjoy** | Tapjoy | Manifest · Smali · SO · Assets · URL |
| **InMobi** | InMobi | Manifest · Smali · SO · Assets · URL |
| **AdColony** | AdColony | Manifest · Smali · SO · Assets · URL |
| **MoPub** (Legacy) | MoPub | Manifest · Smali · SO · Assets · URL |
| **Fyber / Digital Turbine** | Digital Turbine | Manifest · Smali · SO · Assets · URL |
| **Smaato** | Smaato | Manifest · Smali · URL |
| **Verve** | Verve | Manifest · Smali |
| **AppNexus / Xandr** | Microsoft | Manifest · Smali · URL |
| **Criteo** | Criteo | Manifest · Smali · SO · URL |
| **Yandex Ads** | Yandex | Manifest · Smali · SO · Assets · URL |
| **MyTarget / VK Ads** | VK (Mail.ru) | Manifest · Smali · SO · Assets · URL |

> **共计 46 种广告 SDK**，覆盖 manifest / smali / so / assets / res / url 六个维度，持续更新中。

---

## 🚀 快速开始

### 方式一：直接使用预编译版本（推荐）

从 [Releases](../../releases) 下载 `remove_ads_gui.exe`，双击运行即可。

**前置条件：** 需要安装 **Java Runtime (JRE 8+)**，用于运行 apktool 和签名工具。

### 方式二：从源码运行

```bash
# 1. 克隆仓库
git clone https://github.com/yourusername/apk-ad-remover.git
cd apk-ad-remover

# 2. 安装依赖
pip install customtkinter pyinstaller

# 3. 运行 GUI
python remove_ads_gui.py

# 4. 或运行 CLI
python remove_ads.py app.apk
```

---

## 📋 使用方式

### GUI 图形界面

1. 双击 `remove_ads_gui.exe` 启动
2. 拖放或浏览选择 APK 文件
3. 程序自动预扫描检测广告 SDK，结果显示在预览面板
4. 勾选需要的清理选项：
   - ✅ **AndroidManifest** — 移除广告组件和权限（推荐）
   - ✅ **Assets 资源** — 删除广告 SDK 配置文件
   - ⚠️ **.so 动态库** — 删除广告原生库（可能导致闪退）
   - 📐 **Res 布局** — 删除广告 UI 布局资源
   - ⚠️ **Smali 代码** — 删除广告字节码（高风险）
   - ✅ **自动签名** — 输出可直接安装的 APK
   - 🛡️ **防检测空桩** — 生成无操作桩类防反屏蔽
5. 点击「开始处理」
6. 查看结果摘要，确认移除详情

### CLI 命令行

```bash
# 基本用法：处理 APK 并自动签名
remove_ads.exe app.apk

# 指定输出路径
remove_ads.exe app.apk output_clean.apk

# 不自动签名（需手动签名）
remove_ads.exe app.apk --no-sign

# 启用防检测空桩
remove_ads.exe app.apk --stub

# 启用 Smali 级代码清理（高风险）
remove_ads.exe app.apk --smali --stub

# 交互模式（逐步引导）
remove_ads.exe

# 查看帮助
remove_ads.exe --help
```

### 作为 Python 模块导入

```python
from remove_ads import process_apk, detect_ad_sdks

# 处理单个 APK
result = process_apk(
    "app.apk",
    output_apk="app_killad.apk",
    options={
        "manifest": True,   # 清理 AndroidManifest
        "assets": True,     # 删除广告资源
        "so": False,        # 不删 .so（安全）
        "res": True,        # 清理广告布局
        "smali": False,     # 不删 smali（高风险）
        "sign": True,       # 自动签名
        "stub": True,       # 生成防检测桩
    },
    log_callback=print,
    progress_callback=lambda step, total, msg: print(f"[{step}/{total}] {msg}"),
)

print(f"输出: {result['output_path']}")
print(f"缩减: {(result['original_size'] - result['final_size']) / 1024 / 1024:.1f} MB")
print(f"检测到 SDK: {[s['name'] for s in result['detected_sdks']]}")
```

---

## ⚙️ 命令行参数

| 参数 | 说明 |
| --- | --- |
| `app.apk` | 输入 APK 文件路径 |
| `output.apk` | 输出 APK 文件路径（可选，默认添加 `_killad` 后缀） |
| `--sign`, `-s` | 处理后自动签名（默认启用） |
| `--no-sign` | 不自动签名 |
| `--stub` | 为移除的广告组件生成空桩 smali，防止应用检测到组件缺失 |
| `--smali` | 扫描并删除广告 smali 代码（**高风险**，可能导致应用崩溃） |

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────┐
│                 remove_ads_gui.py                │
│           (customtkinter GUI Layer)              │
│   SDK Preview  │  Options  │  Progress │ Result  │
└─────────────────────┬───────────────────────────┘
                      │ process_apk()
┌─────────────────────▼───────────────────────────┐
│                 remove_ads.py                    │
│                (Core Engine)                     │
│                                                  │
│  ┌──────────┐ ┌──────────┐ ┌───────────────┐   │
│  │ Manifest │ │ Assets / │ │  Smali Code   │   │
│  │  Cleaner │ │ Res / SO │ │  Analysis     │   │
│  │ (XML)    │ │ (FS Ops) │ │  & Stubbing   │   │
│  └──────────┘ └──────────┘ └───────────────┘   │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │        ad_patterns.json                  │   │
│  │   46 SDKs × 6 dimensions signature DB    │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  ┌──────────┐ ┌──────────┐ ┌───────────────┐   │
│  │ apktool  │ │  Signer  │ │  Version      │   │
│  │  De/Re-  │ │  (uber-  │ │  Awareness    │   │
│  │  compile │ │  apk-)   │ │  (API Level)  │   │
│  └──────────┘ └──────────┘ └───────────────┘   │
└─────────────────────┬───────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────┐
│              pattern_updater.py                  │
│  GitHub Releases ─► SHA256 Verify ─► Hot Reload │
│  Gitee Mirror    ─► Backup Old    ─► Apply      │
└─────────────────────────────────────────────────┘
```

### 处理流程

```
APK 输入
  │
  ├─ 1. apktool 解包 → smali + res + manifest
  ├─ 2. SDK 预扫描 → 检测已集成的广告 SDK
  ├─ 3. XML 解析 manifest → 移除广告组件 & 权限
  ├─ 3b. [可选] 生成空桩 smali → 防检测
  ├─ 4. 文件系统扫描 → 删除 ad assets / res / so
  ├─ 5. [可选] Smali 代码分析 → 删除广告类 & 桩化方法
  ├─ 6. apktool 重打包 → 新 APK
  └─ 7. uber-apk-signer 签名 → 可直接安装的 APK
```

---

## 🛡️ 反检测机制

部分应用会在运行时检测广告 SDK 组件是否完整，若缺失则弹出"非官方渠道"或"应用已损坏"等提示。本工具提供以下对抗策略：

### 1. 组件空桩生成 (`--stub`)

移除广告组件时，同步在 smali 目录生成最小化无操作桩类：

```smali
# Activity 桩: 仅调用 super.onCreate() 后返回
.class public Lcom/bytedance/sdk/openadsdk/TTAdActivity;
.super Landroid/app/Activity;

.method protected onCreate(Landroid/os/Bundle;)V
    .locals 0
    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V
    return-void
.end method
```

支持的桩类型：`Activity` · `Service` · `BroadcastReceiver` · `ContentProvider`

### 2. Android 版本感知

- **API 31+ (Android 12+)**: 保留 exported receiver，避免其他应用查询失败
- **API 29+**: 保留 `QUERY_ALL_PACKAGES` 权限
- **全局**: 仅在有明确广告上下文时移除 `AD_ID` 权限

### 3. 权限白名单

- `AD_ID` — Google Advertising ID（可能被非广告功能使用）
- `QUERY_ALL_PACKAGES` — Android 11+ 包可见性（高版本可能为必要权限）

---

## 🔄 自动更新

模式数据库 `ad_patterns.json` 支持在线自动更新，确保 SDK 覆盖始终最新：

```
启动时后台检查
  ├─ GitHub Release API → 获取最新版本号
  └─ Gitee Release API → 国内镜像加速

发现新版本
  ├─ 下载 ad_patterns.json
  ├─ SHA256 完整性校验
  ├─ 备份旧文件 → ad_patterns.json.bak
  └─ 热重载模式数据库
```

- **检查频率**: 每 24 小时一次
- **网络故障**: 静默降级，使用本地模式文件
- **更新失败**: 自动回退备份版本

> 默认更新源为示例地址，Fork 后请在 `pattern_updater.py` 中的 `UPDATE_SOURCES` 替换为自己的仓库地址。

---

## 🔧 从源码构建

```bash
# 安装构建依赖
pip install pyinstaller customtkinter

# 构建 CLI 版本
python -m PyInstaller remove_ads.spec --noconfirm --clean
# 输出: dist/remove_ads.exe

# 构建 GUI 版本
python -m PyInstaller remove_ads_gui.spec --noconfirm --clean
# 输出: dist/remove_ads_gui.exe
```

构建产物为独立可执行文件，包含 Python 运行时和所有依赖，无需目标电脑安装 Python。

---

## 📦 依赖要求

### 运行环境
| 依赖 | 版本要求 | 说明 |
| --- | --- | --- |
| **Windows** | 10 / 11 (64-bit) | 主要支持平台 |
| **Java Runtime** | JRE 8+ | 运行 apktool 和 uber-apk-signer |
| **Python** | 3.8+ | 仅源码运行需要 |

### Python 依赖 (自动打包进 exe)
```
customtkinter >= 5.0    # GUI 框架
Pillow >= 9.0           # 图片处理
numpy >= 1.20           # 数组计算
tkinterdnd2 >= 0.3      # 拖放支持 (可选)
```

### 内置工具 (已包含在项目中)
| 工具 | 文件 | 用途 |
| --- | --- | --- |
| **apktool** | `apktool.jar` | APK 解包 / 重打包 |
| **uber-apk-signer** | `uber-apk-signer.jar` | APK 自动签名 |

---

## ❓ 常见问题

<details>
<summary><b>Q: 处理后应用闪退怎么办？</b></summary>

可能原因：
1. 勾选了「删除 .so 动态库」— 某些应用深度依赖广告 SDK 的 native 代码，取消勾选重试
2. 勾选了「清理 Smali 代码」— 误删了非广告代码，建议先不使用 `--smali`
3. 应用有完整性校验 — 尝试勾选「防检测空桩」
4. Android 12+ 设备 — 工具已自动适配版本感知清理，若仍有问题请提 Issue
</details>

<details>
<summary><b>Q: 提示"找不到 apktool.jar"？</b></summary>

确保 `apktool.jar` 与 `remove_ads_gui.exe` 在同一目录下。使用预编译版本时已自动打包。
</details>

<details>
<summary><b>Q: 处理后广告仍然存在？</b></summary>

可能原因：
1. 应用使用了不在数据库中的新型 SDK — 请提交 Issue 附带 APK 名称
2. 广告通过 WebView 加载（H5 广告）— 此类广告无法通过 SDK 清理移除
3. 更新模式数据库：删除 `ad_patterns.json` 后重新运行，或等待自动更新生效
</details>

<details>
<summary><b>Q: 支持哪些广告类型？</b></summary>

- ✅ SDK 嵌入式广告（开屏、信息流、插屏、激励视频、Banner）
- ✅ 原生自渲染广告
- ❌ WebView 内嵌 H5 广告
- ❌ 应用自身业务逻辑中硬编码的推广内容
- ❌ 加固/加密后的 APK（需先脱壳）
</details>

<details>
<summary><b>Q: 为什么 GUI 版本比 CLI 大？</b></summary>

GUI 版本额外打包了 customtkinter、Tkinter、PIL/Pillow、numpy 等图形库，约增加 20MB。
</details>

---

## ⚠️ 免责声明

**本项目仅供学习研究和安全测试用途。**

- 请勿将本工具用于任何侵犯他人合法权益的行为
- 使用本工具处理应用可能违反该应用的服务条款
- 处理后的 APK 可能导致应用功能异常、数据丢失或账号封禁
- 使用者应自行承担因使用本工具产生的一切后果与风险
- 开发者不对因使用本工具造成的任何直接或间接损失承担责任
- 请遵守当地法律法规，在获得合法授权的前提下使用

---

## 🤝 贡献指南

欢迎提交 PR 来扩展 SDK 覆盖或改进功能！

### 添加新的广告 SDK

编辑 `ad_patterns.json`，按模板添加新条目：

```json
{
  "name": "Your SDK Name",
  "vendor": "vendor_name",
  "keywords": ["sdk.package.keyword"],
  "manifest_patterns": ["com.example.ads"],
  "permission_patterns": ["EXAMPLE_AD"],
  "so_patterns": ["libexample_ad"],
  "assets_patterns": ["example_sdk_config"],
  "res_patterns": ["example_ad_"],
  "smali_classes": ["Lcom/example/ads/"],
  "smali_urls": ["ad.example.com"]
}
```

### 提交规范

- 确保 JSON 格式有效（`python -m json.tool ad_patterns.json`）
- 附上包含该 SDK 的 APK 样本信息（名称、版本、可下载来源）
- 尽量提供 4 个以上维度的签名数据

---

## 📄 开源协议

MIT License — 详见 [LICENSE](LICENSE) 文件。

---

<p align="center">
  <sub>Made with ❤️ by reverse engineering enthusiasts</sub>
</p>
