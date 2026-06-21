#!/usr/bin/env python3
"""
APK 通用去广告后端模块 v2.0
用法:
    作为命令行工具:
      python remove_ads.py                        → 交互模式
      python remove_ads.py app.apk                → 命令行模式（自动签名）
      python remove_ads.py app.apk output.apk     → 命令行模式（指定输出）
      python remove_ads.py app.apk --no-sign      → 不自动签名
      python remove_ads.py app.apk -s             → 强制自动签名（默认）
      python remove_ads.py app.apk --stub         → 生成空桩 smali 防检测

    作为模块导入:
      from remove_ads import process_apk
      process_apk("app.apk", "output.apk", options={"manifest": True, "assets": True, "so": False, "sign": True}, log_callback=print)

需要: Java, apktool.jar, uber-apk-signer.jar (放在同目录或系统PATH)
"""

import sys
import os
import re
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

# ============================================================
# 内置默认 SDK 模式（JSON 文件加载失败时的回退）
# 完整规则见 ad_patterns.json
# ============================================================
_BUILTIN_AD_SDK_KEYWORDS = [
    "bytedance", "pangle", "ss.android.socialbase", "ss.android.downloadlib",
    "byted.live", "kwad.sdk", "kwai.auth", "qq.e.ads", "qq.e.comm",
    "baidu.mobads", "baidu.oauth", "sigmob", "beizi", "windmill",
    "miui.ads", "mimo.sdk", "huawei.hms.ads", "ylh.sdk",
    "google.android.gms.ads", "unity3d.ads", "vungle", "applovin",
    "ironsource", "mintegral", "chartboost", "tapjoy", "inmobi",
    "sxwl.ads", "adnxs", "mopub", "adcolony", "fyber", "ogury",
    "smaato", "verve",
]

_BUILTIN_AD_PERMISSION_KEYWORDS = [
    "openadsdk", "TT_PANGOLIN", "KW_SDK", "GDT_SDK",
    "BAIDU_AD", "SIGMOB", "WINDMILL",
]

_BUILTIN_AD_ASSETS = [
    "bdxadsdk.jar", "gdt_plugin", "supplierconfig.json",
    "ksad_common_encrypt_image.png", "ksad_idc.json", "saio_res",
]

_BUILTIN_AD_SO_FILES = [
    "libpangle", "libpglbizssdk", "libsgcore", "libgdt",
    "libksad", "libbytedance", "libbdad", "libbeizi",
    "libwindmill", "libsigmob",
]

_BUILTIN_AD_RES_KEYWORDS = [
    "tt_", "pangle_", "pangolin_", "gdt_", "ksad_",
    "bdxad_", "sigmob_", "beizi_", "windmill_",
    "byted_", "qq_e_", "mbridge_",
]

# AndroidManifest.xml 命名空间映射
_MANIFEST_NS = {
    "android": "http://schemas.android.com/apk/res/android",
}

# SDK 依赖关系
_SDK_DEPENDENCY_MAP = {
    "ylh": ["gdt", "tencent"],
    "windmill": ["sigmob", "pangle", "gdt"],
    "applovin": ["mintegral"],
    "mopub": ["admob", "facebook"],
}

# 需要保守处理的权限（可能影响非广告功能）
_CONSERVATIVE_PERMISSIONS = {"AD_ID"}

DEFAULT_OPTIONS = {
    "manifest": True,
    "assets": True,
    "so": False,
    "res": False,
    "smali": False,
    "sign": True,
    "stub": False,
}


def _load_patterns():
    """加载 SDK 签名数据库。优先从 JSON 文件读取，失败时回退到内置默认值。"""
    json_path = Path(__file__).parent / "ad_patterns.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sdks = data.get("sdks", [])
            keywords = set()
            permissions = set()
            assets = set()
            so_files = set()
            res_patterns = set()
            dependency_map = data.get("dependency_map", _SDK_DEPENDENCY_MAP)
            allowlist = data.get("allowlist", {"permissions": [], "classes": []})

            for sdk in sdks:
                for kw in sdk.get("keywords", []):
                    keywords.add(kw)
                for p in sdk.get("permission_patterns", []):
                    permissions.add(p)
                for a in sdk.get("assets_patterns", []):
                    assets.add(a)
                for so in sdk.get("so_patterns", []):
                    so_files.add(so)
                for rp in sdk.get("res_patterns", []):
                    if rp.endswith("_*"):
                        res_patterns.add(rp[:-2])
                    else:
                        res_patterns.add(rp)

            return {
                "sdks": sdks,
                "keywords": keywords,
                "permissions": permissions,
                "assets": assets,
                "so_files": so_files,
                "res_patterns": res_patterns,
                "dependency_map": dependency_map,
                "allowlist": allowlist,
                "loaded_from": str(json_path),
            }
        except (json.JSONDecodeError, IOError) as e:
            pass  # 回退到内置默认值

    # 内置回退
    return {
        "sdks": [],
        "keywords": set(_BUILTIN_AD_SDK_KEYWORDS),
        "permissions": set(_BUILTIN_AD_PERMISSION_KEYWORDS),
        "assets": set(_BUILTIN_AD_ASSETS),
        "so_files": set(_BUILTIN_AD_SO_FILES),
        "res_patterns": set(_BUILTIN_AD_RES_KEYWORDS),
        "dependency_map": _SDK_DEPENDENCY_MAP,
        "allowlist": {"permissions": ["AD_ID"], "classes": []},
        "loaded_from": "builtin",
    }


# 模块加载时初始化模式数据
_PATTERNS = _load_patterns()


def reload_patterns():
    """重新加载模式数据（用于自动更新后）。"""
    global _PATTERNS
    _PATTERNS = _load_patterns()
    return _PATTERNS["loaded_from"]


class _CmdResult:
    """subprocess.run 兼容的返回值包装，用于 Popen 轮询模式。"""
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _default_log(message):
    """默认日志回调：直接打印到控制台。"""
    print(message)


def find_apktool():
    """查找 apktool.jar。找不到时抛出 FileNotFoundError。"""
    script_dir = Path(__file__).parent
    local_jar = script_dir / "apktool.jar"
    if local_jar.exists():
        return str(local_jar)

    cwd_jar = Path.cwd() / "apktool.jar"
    if cwd_jar.exists():
        return str(cwd_jar)

    if shutil.which("apktool"):
        return "apktool"

    raise FileNotFoundError(
        "找不到 apktool.jar，请把它放在脚本同目录下\n"
        "下载地址: https://ibotpeaches.github.io/Apktool/"
    )


def find_signer():
    """查找 uber-apk-signer.jar。找不到时抛出 FileNotFoundError。"""
    script_dir = Path(__file__).parent
    local_jar = script_dir / "uber-apk-signer.jar"
    if local_jar.exists():
        return str(local_jar)

    cwd_jar = Path.cwd() / "uber-apk-signer.jar"
    if cwd_jar.exists():
        return str(cwd_jar)

    raise FileNotFoundError(
        "找不到 uber-apk-signer.jar，请把它放在脚本同目录下\n"
        "下载地址: https://github.com/patrickfav/uber-apk-signer"
    )


# apktool 输出进度标记（用于细粒度进度更新）
_APKTOOL_PROGRESS_MARKERS = [
    (r"I: Using Apktool", "初始化 apktool"),
    (r"I: Baksmaling.*classes\.dex", "反编译 dex 文件"),
    (r"I: Copying.*classes\.dex", "复制 dex 文件"),
    (r"I: Loading resource table", "加载资源表"),
    (r"I: Decoding (AndroidManifest|values)", "解析资源文件"),
    (r"I: (Building|Copying)", "构建资源"),
    (r"I: Smaling.*smali", "编译 smali 文件"),
    (r"I: Building apk", "打包 APK 文件"),
]


def _parse_apktool_progress(line, log=None, progress_cb=None, step_base=0.0, step_range=1.0):
    """解析 apktool 输出行，发射细粒度进度更新。"""
    for pattern, label in _APKTOOL_PROGRESS_MARKERS:
        if re.search(pattern, line):
            if log:
                log(f"      {label}...")
            return
    # 通用资源解码行
    if re.match(r"I: Decoding file.*", line):
        return


def _run_subprocess(cmd, log=None, cancel_event=None,
                    progress_cb=None, step_base=0.0, step_range=1.0):
    """运行子进程，支持取消和进度解析。"""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
        bufsize=1,
    )
    try:
        last_progress = step_base
        while proc.poll() is None:
            try:
                # 非阻塞读取一行
                line = proc.stdout.readline()
                if line:
                    _parse_apktool_progress(line.strip(), log=log)
                    if progress_cb:
                        last_progress += step_range * 0.02
                        progress_cb(min(last_progress, step_base + step_range))
                else:
                    proc.wait(timeout=0.3)
            except subprocess.TimeoutExpired:
                if cancel_event and cancel_event.is_set():
                    _graceful_kill(proc)
                    raise RuntimeError("操作已被用户取消")

        stdout, stderr = proc.communicate()
        if log and stdout:
            for line in stdout.splitlines():
                _parse_apktool_progress(line.strip(), log=log)
        if log and stderr:
            for line in stderr.splitlines():
                stripped = line.strip()
                if stripped:
                    log(f"      [apktool] {stripped}")
        return _CmdResult(proc.returncode, stdout or "", stderr or "")
    except Exception:
        _graceful_kill(proc)
        raise


def _graceful_kill(proc):
    """优雅关闭子进程：先 SIGTERM，再 SIGKILL。"""
    try:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def decompile_apk(apk_path, output_dir, apktool_path, log=None, cancel_event=None,
                  progress_cb=None):
    """用 apktool 解包 APK。"""
    if log:
        log("正在解包 APK (这可能需要几分钟)...")
    cmd = ["java", "-jar", apktool_path, "d", "-f", apk_path, "-o", output_dir]
    result = _run_subprocess(cmd, log=log, cancel_event=cancel_event,
                             progress_cb=progress_cb, step_base=0.1, step_range=0.15)
    if result.returncode != 0:
        raise RuntimeError(f"解包失败:\n{result.stderr}")
    if progress_cb:
        progress_cb(0.25)
    if log:
        log("      解包成功。")


def _get_android_version_info(manifest_path):
    """从 AndroidManifest.xml 或 apktool.yml 读取目标 SDK 版本信息。"""
    info = {"min_sdk": 1, "target_sdk": 1, "compile_sdk": 1, "version_code": 0}

    # 优先从 apktool.yml 读取
    yml_path = os.path.join(os.path.dirname(manifest_path), "apktool.yml")
    if os.path.exists(yml_path):
        try:
            with open(yml_path, "r", encoding="utf-8") as f:
                content = f.read()
            for field, key in [("minSdkVersion", "min_sdk"),
                               ("targetSdkVersion", "target_sdk"),
                               ("versionCode", "version_code")]:
                m = re.search(rf"^\s*{field}:\s*'?(\d+)'?", content, re.MULTILINE)
                if m:
                    info[key] = int(m.group(1))
            # compileSdkVersion 只在 apktool.yml 有
            cm = re.search(r"^\s*compileSdkVersion:\s*'?(\d+)'?", content, re.MULTILINE)
            if cm:
                info["compile_sdk"] = int(cm.group(1))
        except Exception:
            pass

    # 从 manifest 补全
    if os.path.exists(manifest_path):
        try:
            tree = ET.parse(manifest_path)
            root = tree.getroot()
            for attr, key in [("minSdkVersion", "min_sdk"),
                              ("targetSdkVersion", "target_sdk"),
                              ("versionCode", "version_code")]:
                full_attr = f"{{{_MANIFEST_NS['android']}}}{attr}"
                val = root.get(full_attr)
                if val:
                    try:
                        info[key] = int(val)
                    except ValueError:
                        pass

            # compileSdkVersion
            compile_attr = f"{{{_MANIFEST_NS['android']}}}compileSdkVersion"
            cv = root.get(compile_attr)
            if cv:
                try:
                    info["compile_sdk"] = int(cv)
                except ValueError:
                    pass
        except Exception:
            pass

    return info


def _matches_any_keyword(value, keywords):
    """检查字符串值是否包含任意 SDK 关键词。"""
    if not value:
        return False
    value_lower = value.lower()
    for kw in keywords:
        if kw in value_lower:
            return True
    return False


def _resolve_dependencies(matched_sdks):
    """根据 SDK 依赖图，返回所有受影响 SDK 的集合。"""
    all_affected = set(matched_sdks)
    for sdk in matched_sdks:
        deps = _PATTERNS["dependency_map"].get(sdk, [])
        for dep in deps:
            all_affected.add(dep)
    return all_affected


def clean_manifest(manifest_path, log=None, generate_stubs=False, stub_dir=None):
    """
    使用 XML ElementTree 解析并清理 AndroidManifest.xml 中的广告组件。
    返回 (removed_count, detected_sdks, stubs_generated)。

    组件类型: activity / service / receiver / provider / activity-alias
    过滤逻辑: 检查 android:name 属性是否匹配 SDK 关键词。
    """
    if log:
        log("清理 AndroidManifest.xml 广告组件 (XML 解析模式)...")

    version_info = _get_android_version_info(manifest_path)
    if log:
        log(f"      目标 SDK: min={version_info['min_sdk']}, target={version_info['target_sdk']}, compile={version_info['compile_sdk']}")

    keywords = _PATTERNS["keywords"]
    permission_kw = _PATTERNS["permissions"]
    allowlist_perms = set(_PATTERNS["allowlist"].get("permissions", []))

    try:
        tree = ET.parse(manifest_path)
        root = tree.getroot()
    except ET.ParseError as e:
        if log:
            log(f"      [警告] XML 解析失败 ({e})，回退到正则模式")
        return _clean_manifest_regex_fallback(manifest_path, log=log)

    removed_count = 0
    detected_sdks = set()
    stubs_generated = 0

    # Android namespace
    ns = _MANIFEST_NS["android"]
    ns_prefix = f"{{{ns}}}"

    # 需要在 application 节点下查找组件
    application = root.find("application")
    if application is None:
        application = root.find(f"{{{ns}}}application")
    if application is None:
        if log:
            log("      [警告] 未找到 <application> 节点")
        return 0, set(), 0

    # 要处理的组件类型
    component_tags = {"activity", "service", "receiver", "provider", "activity-alias"}

    # 收集需要移除的节点（不能边遍历边删除）
    nodes_to_remove = []
    stub_components = []

    for tag in component_tags:
        for node in application.iter(tag):
            name = node.get(f"{ns_prefix}name")
            if not name:
                # 尝试无 namespace 前缀
                name = node.get("android:name")

            if _matches_any_keyword(name, keywords):
                nodes_to_remove.append((application, node))
                # 记录检测到的 SDK
                name_lower = name.lower()
                for kw in keywords:
                    if kw in name_lower:
                        detected_sdks.add(kw)
                        break

                if generate_stubs and stub_dir:
                    stub_components.append((tag, name))

    # 权限节点（在根节点下）
    perm_nodes_to_remove = []
    for tag in ("uses-permission", "permission"):
        for node in root.iter(tag):
            perm_name = node.get(f"{ns_prefix}name") or node.get("android:name")
            if not perm_name:
                continue

            # 跳过 allowlist
            should_skip = False
            for allowed in allowlist_perms:
                if allowed.lower() in perm_name.lower():
                    should_skip = True
                    break
            if should_skip:
                continue

            # 版本感知：API 29+ 保留 QUERY_ALL_PACKAGES
            if version_info["min_sdk"] >= 29 and "QUERY_ALL_PACKAGES" in perm_name:
                continue

            if _matches_any_keyword(perm_name, permission_kw):
                perm_nodes_to_remove.append((root, node))

    # 执行删除
    for parent, node in nodes_to_remove:
        parent.remove(node)
        removed_count += 1

    for parent, node in perm_nodes_to_remove:
        parent.remove(node)
        removed_count += 1

    # 生成空桩 smali
    if generate_stubs and stub_dir and stub_components:
        stubs_generated = _generate_component_stubs(stub_components, stub_dir, log=log)

    # 收缩空白行
    try:
        xml_str = ET.tostring(root, encoding="unicode")
        xml_str = re.sub(r"\n\s*\n\s*\n+", "\n    ", xml_str)
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write(xml_str)
    except Exception:
        # 如果序列化失败，写回原始树
        tree.write(manifest_path, encoding="utf-8", xml_declaration=True)

    if log:
        log(f"      清理完成，共移除 {removed_count} 个广告节点。")
        if detected_sdks:
            log(f"      检测到广告 SDK: {', '.join(sorted(detected_sdks))}")
        if stubs_generated:
            log(f"      已生成 {stubs_generated} 个空桩组件（防检测）。")

    return removed_count, detected_sdks, stubs_generated


def _clean_manifest_regex_fallback(manifest_path, log=None):
    """XML 解析失败时的正则回退方案（保持向后兼容）。"""
    if log:
        log("      使用正则模式清理...")

    with open(manifest_path, "r", encoding="utf-8") as f:
        content = f.read()

    keywords = _PATTERNS["keywords"]
    permission_kw = _PATTERNS["permissions"]
    removed_count = 0

    for kw in keywords:
        escaped = re.escape(kw)
        component_patterns = [
            rf'<activity[^>]*android:name="[^"]*{escaped}[^"]*"[^>]*/>\s*',
            rf'<service[^>]*android:name="[^"]*{escaped}[^"]*"[^>]*/>\s*',
            rf'<receiver[^>]*android:name="[^"]*{escaped}[^"]*"[^>]*/>\s*',
            rf'<provider[^>]*android:name="[^"]*{escaped}[^"]*"[^>]*/>\s*',
            rf'<activity-alias[^>]*android:name="[^"]*{escaped}[^"]*"[^>]*/>\s*',
            rf'<activity[^>]*android:name="[^"]*{escaped}[^"]*"[^>]*>.*?</activity>\s*',
            rf'<service[^>]*android:name="[^"]*{escaped}[^"]*"[^>]*>.*?</service>\s*',
            rf'<receiver[^>]*android:name="[^"]*{escaped}[^"]*"[^>]*>.*?</receiver>\s*',
            rf'<provider[^>]*android:name="[^"]*{escaped}[^"]*"[^>]*>.*?</provider>\s*',
            rf'<activity-alias[^>]*android:targetActivity="[^"]*{escaped}[^"]*"[^>]*/>\s*',
        ]
        for pat in component_patterns:
            matches = re.findall(pat, content, re.DOTALL)
            if matches:
                removed_count += len(matches)
                content = re.sub(pat, "", content, flags=re.DOTALL)

    for kw in permission_kw:
        escaped = re.escape(kw)
        perm_patterns = [
            rf'<uses-permission[^>]*android:name="[^"]*{escaped}[^"]*"[^>]*/>\s*',
            rf'<permission[^>]*android:name="[^"]*{escaped}[^"]*"[^>]*>.*?</permission>\s*',
        ]
        for pat in perm_patterns:
            matches = re.findall(pat, content, re.DOTALL)
            if matches:
                removed_count += len(matches)
                content = re.sub(pat, "", content, flags=re.DOTALL)

    content = re.sub(r"\n\s*\n\s*\n+", "\n    ", content)

    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(content)

    if log:
        log(f"      正则模式清理完成，共移除 {removed_count} 个广告节点。")

    return removed_count, set(), 0


def _generate_component_stubs(components, stub_dir, log=None):
    """为被移除的组件生成最小空桩 smali 类，防止 ClassNotFoundException。"""
    os.makedirs(stub_dir, exist_ok=True)
    generated = 0

    stub_templates = {
        "activity": """# Stub generated by APK Ad Remover
.class public L{pkg}/{name};
.super Landroid/app/Activity;

.method public constructor <init>()V
    .locals 0
    invoke-direct {{p0}}, Landroid/app/Activity;-><init>()V
    return-void
.end method

.method protected onCreate(Landroid/os/Bundle;)V
    .locals 0
    invoke-super {{p0, p1}}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V
    return-void
.end method
""",
        "service": """# Stub generated by APK Ad Remover
.class public L{pkg}/{name};
.super Landroid/app/Service;

.method public constructor <init>()V
    .locals 0
    invoke-direct {{p0}}, Landroid/app/Service;-><init>()V
    return-void
.end method

.method public onBind(Landroid/content/Intent;)Landroid/os/IBinder;
    .locals 1
    const/4 v0, 0x0
    return-object v0
.end method
""",
        "receiver": """# Stub generated by APK Ad Remover
.class public L{pkg}/{name};
.super Landroid/content/BroadcastReceiver;

.method public constructor <init>()V
    .locals 0
    invoke-direct {{p0}}, Landroid/content/BroadcastReceiver;-><init>()V
    return-void
.end method

.method public onReceive(Landroid/content/Context;Landroid/content/Intent;)V
    .locals 0
    return-void
.end method
""",
        "provider": """# Stub generated by APK Ad Remover
.class public L{pkg}/{name};
.super Landroid/content/ContentProvider;

.method public constructor <init>()V
    .locals 0
    invoke-direct {{p0}}, Landroid/content/ContentProvider;-><init>()V
    return-void
.end method

.method public onCreate()Z
    .locals 1
    const/4 v0, 0x0
    return v0
.end method

.method public query(Landroid/net/Uri;[Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;Ljava/lang/String;)Landroid/database/Cursor;
    .locals 1
    const/4 v0, 0x0
    return-object v0
.end method

.method public getType(Landroid/net/Uri;)Ljava/lang/String;
    .locals 1
    const/4 v0, 0x0
    return-object v0
.end method

.method public insert(Landroid/net/Uri;Landroid/content/ContentValues;)Landroid/net/Uri;
    .locals 1
    const/4 v0, 0x0
    return-object v0
.end method

.method public delete(Landroid/net/Uri;Ljava/lang/String;[Ljava/lang/String;)I
    .locals 1
    const/4 v0, 0x0
    return v0
.end method

.method public update(Landroid/net/Uri;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I
    .locals 1
    const/4 v0, 0x0
    return v0
.end method
""",
        "activity-alias": """# Stub generated by APK Ad Remover - redirects to stub Activity
.class public L{pkg}/{name};
.super L{pkg}/AdRemovedStubActivity;
.source "{name}.java"
""",
    }

    for tag, full_name in components:
        # 解析包名和类名
        # full_name 形如 "com.bytedance.sdk.openadsdk.TTAdActivity"
        # 或简写 ".TTAdActivity"
        if not full_name:
            continue

        # 处理简写形式
        if full_name.startswith("."):
            # 简写类名需要包名上下文，跳过（包名解析复杂）
            continue

        parts = full_name.rsplit(".", 1)
        if len(parts) == 2:
            pkg, name = parts
        else:
            pkg = "stub"
            name = parts[0]

        template = stub_templates.get(tag)
        if not template:
            continue

        smali_code = template.format(pkg=pkg.replace(".", "/"), name=name)

        # 写入 smali 文件
        smali_path = os.path.join(stub_dir, *pkg.split("."), f"{name}.smali")
        os.makedirs(os.path.dirname(smali_path), exist_ok=True)

        with open(smali_path, "w", encoding="utf-8") as f:
            f.write(smali_code)
        generated += 1

    if log and generated:
        log(f"      生成了 {generated} 个 smali 空桩类。")

    return generated


# ============================================================
# Smali 代码分析 —— 检测和移除广告 SDK 的 smali 代码
# ============================================================

def analyze_smali_for_ads(decompiled_dir, log=None, progress_cb=None):
    """
    扫描 smali 目录，检测广告 SDK 类引用、方法调用和 URL 字符串。
    返回检测报告 dict:
        {
            "ad_classes": int,       # 检测到的广告类数量
            "ad_urls": int,          # 检测到的广告 URL 数量
            "deleted_files": int,    # 已删除的文件数量
            "sdks": {sdk_name: class_count},
        }
    """
    smali_dirs = sorted(Path(decompiled_dir).glob("smali*"))
    if not smali_dirs:
        if log:
            log("[信息] 无 smali 目录，跳过代码分析。")
        return {"ad_classes": 0, "ad_urls": 0, "deleted_files": 0, "sdks": {}}

    sdks = _PATTERNS.get("sdks", [])
    if not sdks:
        return {"ad_classes": 0, "ad_urls": 0, "deleted_files": 0, "sdks": {}}

    # 构建 SDK 检测映射: smali_class_prefix → sdk_name
    sdk_class_map = {}
    sdk_url_map = {}
    for sdk in sdks:
        name = sdk["name"]
        for cls in sdk.get("smali_classes", []):
            # Normalize: "Lcom/bytedance/sdk/openadsdk/" → "com/bytedance/sdk/openadsdk"
            key = cls.strip("L").rstrip("/")
            sdk_class_map[key] = name
        for url in sdk.get("smali_urls", []):
            sdk_url_map[url] = name

    ad_class_files = {}  # sdk_name → [file_paths]
    ad_url_files = {}    # sdk_name → [file_paths]
    total_smali = 0
    scanned = 0

    # 预计算 smali 文件总数用于进度
    smali_files = []
    for d in smali_dirs:
        smali_files.extend(list(d.rglob("*.smali")))
    total_smali = len(smali_files)

    if log:
        log(f"扫描 {total_smali} 个 smali 文件中...")

    for filepath in smali_files:
        scanned += 1
        if progress_cb and total_smali > 0 and scanned % 500 == 0:
            progress_cb(scanned / total_smali)

        rel = str(filepath)
        rel_lower = rel.lower()

        # 检查类路径是否匹配已知广告 SDK
        for cls_key, sdk_name in sdk_class_map.items():
            if cls_key.lower() in rel_lower:
                ad_class_files.setdefault(sdk_name, []).append(str(filepath))
                break

        # 快速字符串匹配（读前几行即可）
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                head = "".join(f.readline() for _ in range(60))
                # 默认 4KB 预留
        except Exception:
            continue

        for url, sdk_name in sdk_url_map.items():
            if url in head.lower():
                ad_url_files.setdefault(sdk_name, []).append(str(filepath))
                break

    report = {
        "ad_classes": sum(len(v) for v in ad_class_files.values()),
        "ad_urls": sum(len(v) for v in ad_url_files.values()),
        "deleted_files": 0,
        "sdks": {},
    }

    for sdk_name, files in ad_class_files.items():
        report["sdks"][sdk_name] = len(files)

    if log:
        log(f"      扫描完成: 找到 {report['ad_classes']} 个广告相关类, "
            f"{report['ad_urls']} 个广告 URL 引用")
        if report["sdks"]:
            for sdk_name, count in sorted(report["sdks"].items(),
                                          key=lambda x: -x[1])[:10]:
                log(f"        - {sdk_name}: {count} 个类")

    return report


def remove_ad_smali_classes(decompiled_dir, log=None, progress_cb=None, dry_run=False):
    """
    删除已识别为广告 SDK 的 smali 类文件。
    基于 smali_class 路径前缀精确匹配，避免误删。
    返回删除的文件列表。
    """
    sdks = _PATTERNS.get("sdks", [])
    if not sdks:
        return []

    smali_dirs = sorted(Path(decompiled_dir).glob("smali*"))
    if not smali_dirs:
        return []

    # 收集所有广告类前缀
    ad_prefixes = set()
    for sdk in sdks:
        for cls in sdk.get("smali_classes", []):
            cls_normal = cls.strip("L").lstrip("/")
            ad_prefixes.add(cls_normal.replace(".", "/").lower())

    deleted = []
    total_scanned = 0

    for smali_dir in smali_dirs:
        for filepath in list(smali_dir.rglob("*.smali")):
            total_scanned += 1
            rel = str(filepath.relative_to(smali_dir))
            rel_lower = rel.replace("\\", "/").lower()

            matched = False
            for prefix in ad_prefixes:
                if rel_lower.startswith(prefix) or f"/{prefix}" in rel_lower:
                    matched = True
                    break

            if matched:
                if not dry_run:
                    try:
                        filepath.unlink()
                        deleted.append(str(filepath.relative_to(decompiled_dir)))
                    except (OSError, PermissionError):
                        pass
                else:
                    deleted.append(str(filepath.relative_to(decompiled_dir)))

    if log:
        mode = "(试运行)" if dry_run else ""
        if deleted:
            log(f"      已删除 {len(deleted)} 个广告 smali 类{mode}")
        else:
            log(f"      未找到可删除的广告 smali 类{mode}")

    return deleted


def stub_ad_methods(decompiled_dir, log=None, progress_cb=None):
    """
    对嵌入在非 SDK 类中的广告加载方法进行空桩处理。
    查找 invoke 模式指向广告 SDK 的方法，在方法入口注入 return-void。

    注意：此操作风险较高，默认仅在 --stub 模式下启用。
    返回被桩化的方法数量。
    """
    sdks = _PATTERNS.get("sdks", [])
    if not sdks:
        return 0

    # 收集要检测的广告方法调用目标
    ad_invoke_targets = set()
    for sdk in sdks:
        for cls in sdk.get("smali_classes", []):
            if cls.startswith("L"):
                cls_path = cls.rstrip("/")
            else:
                cls_path = "L" + cls.rstrip("/")
            for method in sdk.get("keywords", []):
                ad_invoke_targets.add((cls_path.lower(), method.lower()))

    smali_dirs = sorted(Path(decompiled_dir).glob("smali*"))
    if not smali_dirs:
        return 0

    stubbed_methods = 0
    total_scanned = 0

    for smali_dir in smali_dirs:
        for filepath in list(smali_dir.rglob("*.smali")):
            total_scanned += 1
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue

            modified = False
            in_method = False
            method_start_line = -1
            lines_to_inject = []
            current_method = ""

            for i, line in enumerate(lines):
                stripped = line.strip()

                # 检测方法开始
                if stripped.startswith(".method "):
                    in_method = True
                    method_start_line = i
                    current_method = stripped
                    lines_to_inject = []
                    continue

                if in_method and stripped.startswith(".end method"):
                    # 检查方法中是否调用了广告 SDK
                    if lines_to_inject:
                        # 注入 return-void 桩
                        insert_line = method_start_line + 1
                        # 检查方法返回值类型
                        is_void = "V" in current_method.split(")")[-1] if ")" in current_method else True

                        if is_void:
                            stub_line = "    return-void\n"
                        else:
                            # 非 void 方法：返回 null/0
                            return_type = current_method.split(")")[-1].strip() if ")" in current_method else "V"
                            if return_type.startswith("L") or return_type == "Ljava/lang/Object;":
                                stub_line = "    const/4 v0, 0x0\n    return-object v0\n"
                            elif return_type in ("I", "S", "B", "Z"):
                                stub_line = "    const/4 v0, 0x0\n    return v0\n"
                            elif return_type in ("J",):
                                stub_line = "    const-wide/16 v0, 0x0\n    return-wide v0\n"
                            elif return_type in ("F",):
                                stub_line = "    const/4 v0, 0x0\n    return v0\n"
                            elif return_type in ("D",):
                                stub_line = "    const-wide/16 v0, 0x0\n    return-wide v0\n"
                            else:
                                stub_line = "    return-void\n"

                        lines.insert(insert_line, stub_line)
                        modified = True
                        stubbed_methods += 1

                    in_method = False
                    method_start_line = -1
                    lines_to_inject = []
                    continue

                # 检测方法内的广告 SDK 调用
                if in_method and "invoke-" in stripped:
                    for target, method_name in ad_invoke_targets:
                        # smali invoke 格式: invoke-virtual {v0, v1}, Lxxx;->methodName(...)V
                        if target in stripped.lower() and method_name in stripped.lower():
                            lines_to_inject.append(stripped)
                            break

            if modified:
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                except Exception:
                    stubbed_methods -= 1

    if log and stubbed_methods:
        log(f"      已对 {stubbed_methods} 个广告调用方法进行空桩处理")

    return stubbed_methods


def delete_ad_assets(decompiled_dir, log=None):
    """删除广告 SDK 的资源文件，返回已删除的文件名列表。"""
    if log:
        log("清理广告 Assets 资源...")
    assets_dir = Path(decompiled_dir) / "assets"
    if not assets_dir.exists():
        if log:
            log("      无 assets 目录，跳过。")
        return []

    ad_assets = _PATTERNS["assets"]
    ad_keywords = _PATTERNS["keywords"]
    deleted = []

    # 精确匹配
    for asset in ad_assets:
        path = assets_dir / asset
        if path.exists():
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink()
                deleted.append(asset)
            except (OSError, PermissionError):
                pass

    # 关键词模糊匹配
    for item in list(assets_dir.iterdir()):
        name = item.name.lower()
        for kw in ad_keywords:
            if len(kw) >= 3 and kw in name:
                try:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink()
                    if item.name not in deleted:
                        deleted.append(item.name)
                except (OSError, PermissionError):
                    pass
                break

    if log:
        if deleted:
            log(f"      已删除: {', '.join(deleted)}")
        else:
            log("      未发现匹配的广告资源文件。")

    return deleted


def delete_ad_resources(decompiled_dir, log=None):
    """扫描并删除 res/ 目录下的广告布局/资源文件。"""
    if log:
        log("清理广告 Res 布局资源...")
    res_dir = Path(decompiled_dir) / "res"
    if not res_dir.exists():
        if log:
            log("      无 res 目录，跳过。")
        return []

    res_patterns = _PATTERNS["res_patterns"]
    deleted = []

    for pattern in res_patterns:
        if not pattern:
            continue
        pattern_lower = pattern.lower()
        # 在 res/layout/, res/drawable/, res/values/ 等子目录下搜索
        for item in list(res_dir.rglob("*")):
            name_lower = item.name.lower()
            if pattern_lower in name_lower or name_lower.startswith(pattern_lower):
                try:
                    if item.is_file():
                        item.unlink()
                        deleted.append(str(item.relative_to(res_dir)))
                    elif item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                        deleted.append(str(item.relative_to(res_dir)))
                except (OSError, PermissionError):
                    pass

    if log:
        if deleted:
            log(f"      已删除 {len(deleted)} 个广告资源文件")
        else:
            log("      未发现匹配的广告资源文件。")

    return deleted


def delete_ad_so_files(decompiled_dir, log=None):
    """删除广告 SDK 的 .so 原生库，返回已删除的文件名列表。"""
    if log:
        log("清理广告 .so 动态库...")
    lib_dir = Path(decompiled_dir) / "lib"
    if not lib_dir.exists():
        return []

    ad_so = _PATTERNS["so_files"]
    deleted = []

    for so_pattern in ad_so:
        for so_file in lib_dir.rglob(f"*{so_pattern}*"):
            try:
                so_file.unlink()
                deleted.append(so_file.name)
            except (OSError, PermissionError):
                pass

    if log and deleted:
        log(f"      已删除 .so: {', '.join(deleted)}")

    return deleted


def detect_ad_sdks(decompiled_dir, log=None):
    """扫描解包目录，检测已集成的广告 SDK（轻量预扫描）。"""
    detected = {}
    sdks = _PATTERNS.get("sdks", [])

    if not sdks:
        return detected

    manifest_path = os.path.join(decompiled_dir, "AndroidManifest.xml")
    manifest_content = ""
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_content = f.read().lower()
        except Exception:
            pass

    assets_dir = os.path.join(decompiled_dir, "assets")
    assets_content = ""
    if os.path.exists(assets_dir):
        assets_content = " ".join(os.listdir(assets_dir)).lower()

    for sdk in sdks:
        sdk_name = sdk["name"]
        sdk_keywords = sdk.get("keywords", [])
        match_count = 0

        for kw in sdk_keywords:
            if kw.lower() in manifest_content:
                match_count += 1
            if kw.lower() in assets_content:
                match_count += 1

        if match_count > 0:
            detected[sdk_name] = {
                "vendor": sdk.get("vendor", "unknown"),
                "matches": match_count,
                "keywords": sdk_keywords,
            }

    return detected


def rebuild_apk(decompiled_dir, output_apk, apktool_path, log=None, cancel_event=None,
                progress_cb=None):
    """用 apktool 重打包。"""
    if log:
        log("正在重打包 APK...")
    cmd = ["java", "-jar", apktool_path, "b", decompiled_dir, "-o", output_apk]
    result = _run_subprocess(cmd, log=log, cancel_event=cancel_event,
                             progress_cb=progress_cb, step_base=0.6, step_range=0.3)
    if result.returncode != 0:
        raise RuntimeError(f"重打包失败:\n{result.stderr}")
    if progress_cb:
        progress_cb(0.9)
    if log:
        log("      重打包成功。")


def sign_apk(apk_path, output_dir, signer_path, log=None, cancel_event=None):
    """用 uber-apk-signer 自动签名。"""
    if log:
        log("自动签名 APK...")
    for out_flag in ("--out", "--outDir"):
        cmd = ["java", "-jar", signer_path, "--apks", apk_path, out_flag, output_dir]
        result = _run_subprocess(cmd, log=log, cancel_event=cancel_event)
        if result.returncode == 0:
            break
        if out_flag not in (result.stderr or ""):
            break
    if result.returncode != 0:
        raise RuntimeError(f"签名失败:\n{result.stderr}")
    if log:
        log("      签名完成。")

    base_name = Path(apk_path).stem
    expected = os.path.join(output_dir, f"{base_name}-aligned-debugSigned.apk")
    if os.path.exists(expected):
        return expected

    for f in sorted(Path(output_dir).glob("*.apk"), key=lambda p: p.stat().st_mtime, reverse=True):
        name_lower = f.name.lower()
        if ("signed" in name_lower or "-align" in name_lower) and f.name != os.path.basename(apk_path):
            return str(f)

    raise RuntimeError("签名后文件未找到，请检查 uber-apk-signer 输出")


def process_apk(input_apk, output_apk=None, options=None,
                log_callback=None, progress_callback=None,
                cancel_event=None):
    """
    处理 APK 去广告的核心入口。

    参数:
        input_apk: 输入 APK 路径
        output_apk: 输出 APK 路径，为 None 时自动生成
        options: 字典，可包含 manifest/assets/so/res/sign/stub 布尔值
        log_callback: 日志回调函数，接收单条字符串消息
        progress_callback: 进度回调，签名 progress_callback(step, total, message)
        cancel_event: threading.Event，设为已触发时中止处理

    返回:
        dict: {
            "output_path": str,
            "original_size": int (bytes),
            "final_size": int (bytes),
            "manifest_removed": int,
            "assets_removed": list,
            "so_removed": list,
            "res_removed": list,
            "detected_sdks": list,
            "stubs_generated": int,
            "signed": bool,
        }
    """
    if not os.path.exists(input_apk):
        raise FileNotFoundError(f"找不到文件: {input_apk}")

    opts = dict(DEFAULT_OPTIONS)
    if options:
        opts.update(options)

    log = log_callback or _default_log
    progress = progress_callback

    apktool = find_apktool()
    log(f"找到 apktool: {apktool}")
    log(f"模式数据库: {_PATTERNS['loaded_from']}")

    signer = None
    if opts.get("sign", True):
        signer = find_signer()
        log(f"找到签名工具: {signer}")

    input_size = os.path.getsize(input_apk)

    base_name = os.path.basename(input_apk)
    if base_name.lower().endswith(".apk"):
        base_name = base_name[:-4]

    if not output_apk:
        output_apk = os.path.join(
            os.path.dirname(os.path.abspath(input_apk)),
            f"{base_name}_killad.apk",
        )

    out_dir = os.path.dirname(os.path.abspath(output_apk))
    os.makedirs(out_dir, exist_ok=True)

    base_output_name = Path(output_apk).stem
    unsigned_apk = os.path.join(out_dir, f"{base_output_name}_unsigned.apk")

    # 累加器
    manifest_removed = 0
    assets_deleted = []
    so_deleted = []
    res_deleted = []
    smali_deleted = []
    detected_sdks_list = []
    stubs_generated = 0

    tmpdir = tempfile.mkdtemp(prefix="apk_clean_")
    try:
        decompiled_dir = os.path.join(tmpdir, "decompiled")

        steps = []
        total_steps = 3  # 解包 + 清理 + 重打包 (最小)
        if opts.get("manifest", True):
            total_steps += 0
        if opts.get("assets", True):
            total_steps += 0

        # Step 1: 解包 (细粒度进度 0.0 → 0.25)
        steps.append(("解包 APK", lambda: decompile_apk(
            input_apk, decompiled_dir, apktool, log=log,
            cancel_event=cancel_event,
            progress_cb=lambda v: progress(1, 5, f"解包... {int(v*100)}%") if progress else None)))

        # Step 2: 预扫描检测 SDK (轻量)
        if opts.get("manifest", True):
            detected = detect_ad_sdks(decompiled_dir, log=log)
            if detected:
                if log:
                    log(f"      预扫描检测到 {len(detected)} 个广告 SDK:")
                    for sdk_name, info in detected.items():
                        log(f"        - {sdk_name} ({info['vendor']}, {info['matches']} 处匹配)")
                detected_sdks_list = [{"name": k, **v} for k, v in detected.items()]

        # Step 3: 清理 Manifest (细粒度进度 0.25 → 0.40)
        if opts.get("manifest", True):
            def _step_manifest():
                nonlocal manifest_removed, stubs_generated
                manifest = os.path.join(decompiled_dir, "AndroidManifest.xml")
                if os.path.exists(manifest):
                    stub_dir = os.path.join(decompiled_dir, "smali_stubs") if opts.get("stub") else None
                    if stub_dir:
                        # 整合进 smali 目录
                        smali_dirs = sorted(Path(decompiled_dir).glob("smali*"))
                        if smali_dirs:
                            stub_dir = os.path.join(str(smali_dirs[0]), "adstub")
                    manifest_removed, _, stubs_generated = clean_manifest(
                        manifest, log=log,
                        generate_stubs=opts.get("stub", False),
                        stub_dir=stub_dir)
                else:
                    log("[警告] 未找到 AndroidManifest.xml")
            steps.append(("清理 Manifest 广告组件", _step_manifest))

        # Step 4: 清理 Assets (细粒度进度 0.40 → 0.45)
        if opts.get("assets", True):
            def _step_assets():
                nonlocal assets_deleted
                assets_deleted = delete_ad_assets(decompiled_dir, log=log) or []
            steps.append(("清理广告 Assets 资源", _step_assets))

        # Step 5: 清理 Res 布局 (细粒度进度 0.45 → 0.50)
        if opts.get("res", False):
            def _step_res():
                nonlocal res_deleted
                res_deleted = delete_ad_resources(decompiled_dir, log=log) or []
            steps.append(("清理广告 Res 布局", _step_res))

        # Step 6: 清理 SO (细粒度进度 0.50 → 0.55)
        if opts.get("so", False):
            def _step_so():
                nonlocal so_deleted
                so_deleted = delete_ad_so_files(decompiled_dir, log=log) or []
            steps.append(("清理广告 .so 动态库", _step_so))

        # Step 6b: 清理 Smali 广告代码 (细粒度进度 0.55 → 0.60)
        if opts.get("smali", False):
            def _step_smali():
                nonlocal smali_deleted
                # 先分析
                report = analyze_smali_for_ads(decompiled_dir, log=log)
                # 再删除
                smali_deleted = remove_ad_smali_classes(decompiled_dir, log=log)
                # 如果启用了 stub，也桩化嵌入方法
                if opts.get("stub", False):
                    stub_ad_methods(decompiled_dir, log=log)
            steps.append(("分析并清理 Smali 广告代码", _step_smali))

        # Step 7: 重打包 (细粒度进度 0.55 → 0.90)
        steps.append(("重打包 APK", lambda: rebuild_apk(
            decompiled_dir, unsigned_apk, apktool, log=log,
            cancel_event=cancel_event,
            progress_cb=lambda v: progress(3, 5, f"重打包...") if progress else None)))

        # 执行所有步骤
        total = len(steps)
        main_total = 5  # 统一的进度分母
        for i, (label, step_fn) in enumerate(steps, 1):
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("操作已被用户取消")
            if progress:
                progress(i, main_total, label)
            log(f"[{i}/{total}] {label}")
            step_fn()

        # 尽早清理临时目录中的大文件
        _cleanup_decompiled(decompiled_dir)

    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    # 签名或移动输出文件
    if signer:
        sign_label = "自动签名 APK"
        if progress:
            progress(4, 5, sign_label)
        log(f"[4/5] {sign_label}")
        signed_apk = sign_apk(unsigned_apk, out_dir, signer, log=log, cancel_event=cancel_event)
        if os.path.exists(output_apk):
            os.remove(output_apk)
        os.rename(signed_apk, output_apk)
        if os.path.exists(unsigned_apk):
            os.remove(unsigned_apk)
    else:
        if os.path.exists(output_apk):
            os.remove(output_apk)
        os.rename(unsigned_apk, output_apk)

    final_size = os.path.getsize(output_apk)

    if progress:
        progress(5, 5, "完成")

    result = {
        "output_path": output_apk,
        "original_size": input_size,
        "final_size": final_size,
        "manifest_removed": manifest_removed,
        "assets_removed": assets_deleted,
        "so_removed": so_deleted,
        "res_removed": res_deleted,
        "smali_removed": smali_deleted,
        "detected_sdks": detected_sdks_list,
        "stubs_generated": stubs_generated,
        "signed": bool(signer),
    }

    orig_mb = input_size / (1024 * 1024)
    final_mb = final_size / (1024 * 1024)
    diff_mb = (input_size - final_size) / (1024 * 1024)

    log("=" * 50)
    log("处理完成！")
    log(f"输出文件: {output_apk}")
    log(f"原始大小: {orig_mb:.1f} MB → 最终大小: {final_mb:.1f} MB (缩减 {diff_mb:.1f} MB)")
    if stubs_generated:
        log(f"已生成 {stubs_generated} 个防检测空桩")
    if signer:
        log("已自动签名，可直接安装。")
    else:
        log("下一步: 请使用 MT 管理器或 apksigner 对新 APK 进行签名后再安装。")

    return result


def _cleanup_decompiled(decompiled_dir):
    """清理解包目录中的大文件（中间步骤后释放磁盘空间）。"""
    # 删除原始的 dex 文件（apktool 已经解出了 smali）
    for item in Path(decompiled_dir).glob("classes*.dex"):
        try:
            item.unlink()
        except (OSError, PermissionError):
            pass


def process_batch(apk_list, output_dir=None, options=None,
                  log_callback=None, progress_callback=None,
                  max_workers=2):
    """
    批量处理多个 APK 文件（线程池并行）。
    返回 dict: {apk_path: result_dict}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    log = log_callback or _default_log
    log(f"批量处理 {len(apk_list)} 个 APK 文件 (最多 {max_workers} 并行)...")

    def _process_one(apk_path):
        out = None
        if output_dir:
            base = os.path.basename(apk_path).replace(".apk", "_killad.apk")
            out = os.path.join(output_dir, base)
        try:
            return apk_path, process_apk(apk_path, output_apk=out, options=options,
                                          log_callback=log_callback,
                                          progress_callback=None,
                                          cancel_event=None)
        except Exception as e:
            log(f"[错误] 处理 {os.path.basename(apk_path)} 失败: {e}")
            return apk_path, {"error": str(e)}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_process_one, apk): apk for apk in apk_list}
        for future in as_completed(futures):
            apk, result = future.result()
            results[apk] = result
            log(f"  完成: {os.path.basename(apk)}")

    return results


def interactive_mode():
    """交互式模式：逐步询问用户输入。"""
    print("=" * 50)
    print("       APK 通用去广告脚本 v2.0")
    print("=" * 50)
    print(f"模式数据库: {_PATTERNS['loaded_from']}")
    print()

    while True:
        apk_dir = input("[?] APK 文件在哪个目录？\n    ").strip().strip('"')
        if not apk_dir:
            print("    目录不能为空，请重新输入\n")
            continue
        apk_dir = os.path.expandvars(os.path.expanduser(apk_dir))
        if not os.path.isdir(apk_dir):
            print(f"    目录不存在: {apk_dir}\n")
            continue
        break

    apk_files = sorted([f for f in os.listdir(apk_dir) if f.lower().endswith(".apk")])
    if not apk_files:
        print(f"    该目录下没有 .apk 文件！")
        sys.exit(1)

    print(f"\n    找到 {len(apk_files)} 个 APK 文件:")
    for i, f in enumerate(apk_files, 1):
        size_mb = os.path.getsize(os.path.join(apk_dir, f)) / (1024 * 1024)
        print(f"      [{i}] {f}  ({size_mb:.1f} MB)")
    print()

    while True:
        choice = input("[?] 请输入文件名（或序号）: ").strip().strip('"')
        if not choice:
            print("    不能为空，请重新输入\n")
            continue
        try:
            idx = int(choice)
            if 1 <= idx <= len(apk_files):
                apk_name = apk_files[idx - 1]
                break
            else:
                print(f"    序号超出范围 (1-{len(apk_files)})\n")
                continue
        except ValueError:
            if not choice.lower().endswith(".apk"):
                choice += ".apk"
            full_path = os.path.join(apk_dir, choice)
            if os.path.exists(full_path):
                apk_name = choice
                break
            if os.path.exists(choice):
                apk_dir = os.path.dirname(choice) or "."
                apk_name = os.path.basename(choice)
                break
            print(f"    文件不存在: {choice}\n")
            continue

    input_apk = os.path.join(apk_dir, apk_name)

    print(f"\n    当前输出目录: {apk_dir}")
    out_dir = input("[?] 输出到哪个目录？（回车=同上）: ").strip().strip('"')
    if not out_dir:
        out_dir = apk_dir
    else:
        out_dir = os.path.expandvars(os.path.expanduser(out_dir))
        os.makedirs(out_dir, exist_ok=True)

    base_name = apk_name
    if base_name.lower().endswith(".apk"):
        base_name = base_name[:-4]
    output_apk = os.path.join(out_dir, f"{base_name}_killad.apk")

    print()
    sign_choice = input("\n[?] 是否自动签名 APK？(Y/n，回车=是): ").strip().lower()
    do_sign = sign_choice in ("", "y", "yes")

    stub_choice = input("[?] 是否生成防检测空桩？(y/N，回车=否): ").strip().lower()
    do_stub = stub_choice in ("y", "yes")

    print(f"\n  输入: {input_apk}")
    print(f"  输出: {output_apk}")
    print(f"  签名: {'是' if do_sign else '否'}")
    print(f"  防检测桩: {'是' if do_stub else '否'}")
    print()

    return input_apk, output_apk, do_sign, do_stub


def main():
    do_sign = True
    do_stub = False
    do_smali = False

    if len(sys.argv) >= 2:
        if sys.argv[1] in ("-h", "--help"):
            print(__doc__)
            print("选项:")
            print("  --sign, -s     处理完成后自动签名（默认）")
            print("  --no-sign      不自动签名")
            print("  --stub         生成空桩 smali 防检测")
            print("  --smali        扫描并删除广告 smali 代码 [高风险]")
            sys.exit(0)

        args = [a for a in sys.argv[1:] if not a.startswith("-")]
        flags = set(a for a in sys.argv[1:] if a.startswith("-"))

        if "--no-sign" in flags:
            do_sign = False
        if "--sign" in flags or "-s" in flags:
            do_sign = True
        if "--stub" in flags:
            do_stub = True
        if "--smali" in flags:
            do_smali = True

        if not args:
            print("[错误] 请提供 APK 文件路径，或使用 --help 查看帮助")
            sys.exit(1)

        input_apk = args[0]
        output_apk = args[1] if len(args) > 1 else None
        if not output_apk:
            output_apk = input_apk.replace(".apk", "_killad.apk")
    else:
        input_apk, output_apk, do_sign, do_stub = interactive_mode()
        do_smali = False  # interactive mode doesn't ask for smali by default

    options = {
        "manifest": True,
        "assets": True,
        "so": False,
        "res": False,
        "smali": do_smali,
        "sign": do_sign,
        "stub": do_stub,
    }

    process_apk(input_apk, output_apk=output_apk, options=options)


if __name__ == "__main__":
    main()
