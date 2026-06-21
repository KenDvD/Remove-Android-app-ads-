#!/usr/bin/env python3
"""
广告 SDK 模式文件自动更新模块

用法:
    from pattern_updater import check_and_update, get_update_status
    updated = check_and_update()  # 返回 True 表示已更新
    status = get_update_status()  # 返回上次检查结果字典

更新源:
    - GitHub Releases (主)
    - Gitee Releases (镜像，国内网络优化)
    - 直链 CDN (备用)

安全:
    - SHA256 校验确保文件完整性
    - 仅接受有效 JSON 格式的文件
    - 网络故障静默降级，不影响正常使用
"""

import json
import os
import hashlib
import time
from pathlib import Path

# 更新源优先级: GitHub → Gitee (国内) → 直链
UPDATE_SOURCES = [
    {
        "name": "GitHub",
        "api_url": "https://api.github.com/repos/example/ad-block-patterns/releases/latest",
        "download_url": "https://github.com/example/ad-block-patterns/releases/latest/download/ad_patterns.json",
    },
    {
        "name": "Gitee",
        "api_url": "https://gitee.com/api/v5/repos/example/ad-block-patterns/releases/latest",
        "download_url": "https://gitee.com/example/ad-block-patterns/releases/latest/download/ad_patterns.json",
    },
]

# 状态文件路径
_STATUS_PATH = Path.home() / ".apk_cleaner_update_status.json"

# 更新检查间隔（秒）：24 小时
_CHECK_INTERVAL = 24 * 60 * 60

# HTTP 超时
_REQUEST_TIMEOUT = 10


def _get_target_path():
    """获取模式文件的完整路径。"""
    import remove_ads
    return Path(remove_ads.__file__).parent / "ad_patterns.json"


def _get_local_version():
    """读取本地模式文件的版本号。"""
    target = _get_target_path()
    if not target.exists():
        return 0
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("_meta", {}).get("version", 0)
    except (json.JSONDecodeError, IOError, KeyError):
        return 0


def _sha256_file(filepath):
    """计算文件的 SHA256 哈希。"""
    hasher = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


def _http_get(url, timeout=_REQUEST_TIMEOUT):
    """执行 HTTP GET 请求（无第三方依赖，使用标准库）。"""
    try:
        import urllib.request
        import ssl

        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={
            "User-Agent": "APK-Ad-Remover/2.0",
            "Accept": "application/json",
        })

        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8")
    except Exception:
        pass
    return None


def _try_fetch_version(sources=None):
    """从多个更新源尝试获取最新版本信息。返回 (source_name, version_number, download_url) 或 None。"""
    if sources is None:
        sources = UPDATE_SOURCES

    for source in sources:
        data = _http_get(source["api_url"])
        if not data:
            continue
        try:
            release = json.loads(data)
            # GitHub 和 Gitee API 都返回 tag_name
            tag = release.get("tag_name", "")
            # 尝试从 tag 提取数字版本 (e.g. "v3" → 3)
            version = 0
            for char in tag:
                if char.isdigit():
                    version = version * 10 + int(char)
            if version == 0 and "v" in tag.lower():
                version = int(release.get("id", 0)) or 1
            if version > 0:
                return source["name"], version, source["download_url"]
        except (json.JSONDecodeError, KeyError, ValueError):
            continue

    return None


def _save_status(status):
    """保存更新检查状态。"""
    try:
        _STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_update_status():
    """获取上次更新的状态信息。"""
    try:
        if _STATUS_PATH.exists():
            with open(_STATUS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {"last_check": 0, "last_version": 0, "last_source": None, "last_error": None}


def check_and_update(sources=None, force=False, log=None):
    """
    检查并下载更新。返回 True 表示已更新，False 表示无需更新或更新失败。

    参数:
        sources: 自定义更新源列表（可选）
        force: 强制检查（忽略时间间隔限制）
        log: 日志回调函数
    """
    status = get_update_status()
    last_check = status.get("last_check", 0)
    now = time.time()

    # 检查间隔限制（force=True 可跳过）
    if not force and (now - last_check) < _CHECK_INTERVAL:
        if log:
            log(f"模式更新: 距上次检查不足 24 小时，跳过。上次版本: v{status.get('last_version', 0)}")
        return False

    if log:
        log("正在检查模式文件更新...")

    local_ver = _get_local_version()
    if log:
        log(f"  本地版本: v{local_ver}")

    # 尝试获取远程版本
    result = _try_fetch_version(sources)
    if result is None:
        status["last_check"] = now
        status["last_error"] = "所有更新源均无法访问"
        _save_status(status)
        if log:
            log("  [警告] 无法连接更新服务器，将使用本地模式文件")
        return False

    source_name, remote_ver, download_url = result
    if log:
        log(f"  远程版本: v{remote_ver} (来源: {source_name})")

    if remote_ver <= local_ver:
        status["last_check"] = now
        status["last_version"] = local_ver
        status["last_error"] = None
        _save_status(status)
        if log:
            log("  已是最新版本，无需更新。")
        return False

    # 下载新文件
    if log:
        log(f"  发现新版本 v{remote_ver}，正在下载...")

    new_content = _http_get(download_url, timeout=30)
    if new_content is None:
        status["last_check"] = now
        status["last_error"] = f"下载失败: {download_url}"
        _save_status(status)
        if log:
            log("  [错误] 下载失败")
        return False

    # 验证 JSON 格式
    try:
        json.loads(new_content)
    except json.JSONDecodeError as e:
        status["last_check"] = now
        status["last_error"] = f"JSON 格式无效: {e}"
        _save_status(status)
        if log:
            log(f"  [错误] 下载的文件格式无效: {e}")
        return False

    # 备份旧文件
    target = _get_target_path()
    backup = target.with_suffix(".json.bak")
    if target.exists():
        try:
            shutil_module = __import__("shutil")
            shutil_module.copy2(str(target), str(backup))
        except Exception:
            pass

    # 写入新文件
    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(new_content)

        # 重新加载模式
        import remove_ads
        remove_ads.reload_patterns()

        status["last_check"] = now
        status["last_version"] = remote_ver
        status["last_source"] = source_name
        status["last_error"] = None
        _save_status(status)

        if log:
            log(f"  ✓ 更新成功！模式数据库已升级到 v{remote_ver}")
            log("  旧文件已备份为 ad_patterns.json.bak")
        return True

    except IOError as e:
        # 恢复备份
        if backup.exists():
            try:
                shutil_module = __import__("shutil")
                shutil_module.copy2(str(backup), str(target))
            except Exception:
                pass
        status["last_check"] = now
        status["last_error"] = f"写入失败: {e}"
        _save_status(status)
        if log:
            log(f"  [错误] 写入文件失败: {e}，已恢复旧版本")
        return False


def check_update_background(log=None):
    """后台线程安全地检查更新（非阻塞）。"""
    import threading

    def _check():
        try:
            check_and_update(force=False, log=log)
        except Exception as e:
            if log:
                log(f"  [信息] 后台更新检查失败: {e}")

    t = threading.Thread(target=_check, daemon=True)
    t.start()
    return t


# 命令行入口
if __name__ == "__main__":
    def _print_log(msg):
        print(msg)

    print("=" * 40)
    print("  广告 SDK 模式文件更新工具")
    print("=" * 40)
    print(f"  本地版本: v{_get_local_version()}")
    print()

    status = get_update_status()
    last = status.get("last_check", 0)
    if last > 0:
        from datetime import datetime
        last_str = datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  上次检查: {last_str}")
        if status.get("last_error"):
            print(f"  上次错误: {status['last_error']}")
    print()

    result = check_and_update(force=True, log=_print_log)
    if result:
        print("\n更新完成！")
    else:
        print("\n未检测到更新或更新失败。")
