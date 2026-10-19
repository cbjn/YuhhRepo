#!/usr/bin/env python3
"""生成 Sileo / APT 软件源并输出到 _site/

用法：
    python3 build.py

依赖：python3、dpkg-dev（提供 dpkg-scanpackages / dpkg）。
GitHub Actions 里会自动安装；本地 macOS 可 `brew install dpkg`。
"""
import bz2
import gzip
import hashlib
import html
import json
import lzma
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"


# ---------- 配置 ----------
def load_conf():
    conf_path = ROOT / "repo.conf"
    if not conf_path.exists():
        sys.exit("找不到 repo.conf")
    conf = {}
    for line in conf_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        conf[key.strip()] = value.strip()
    for key in ("NAME", "URL"):
        if not conf.get(key):
            sys.exit(f"repo.conf 缺少必填项：{key}")
    conf["URL"] = conf["URL"].rstrip("/")
    if not conf["URL"].startswith("https://"):
        sys.exit("URL 必须以 https:// 开头（iOS 对 http 源有限制）")
    if "example.com" in conf["URL"]:
        print("⚠️  repo.conf 里的 URL 还是示例域名，记得改成你自己的！")
    return conf


# ---------- 工具函数 ----------
def cmp_version(a, b):
    """用 dpkg 比较两个版本号，返回 -1/0/1"""
    for op, result in (("eq", 0), ("gt", 1)):
        if subprocess.run(["dpkg", "--compare-versions", a, op, b]).returncode == 0:
            return result
    return -1


def parse_packages(text):
    entries = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        entry, last = {}, None
        for line in block.splitlines():
            if line[:1] in (" ", "\t") and last:
                entry[last] += "\n" + line.strip()
            elif ":" in line:
                # 字段名按 APT 规则不区分大小写，统一用小写作 key
                last, _, value = line.partition(":")
                last = last.strip().lower()
                entry[last] = value.strip()
        if "package" in entry:
            entries.append(entry)
    return entries


def file_hashes(path):
    data = path.read_bytes()
    return {
        "MD5Sum": hashlib.md5(data).hexdigest(),
        "SHA1": hashlib.sha1(data).hexdigest(),
        "SHA256": hashlib.sha256(data).hexdigest(),
        "SHA512": hashlib.sha512(data).hexdigest(),
    }, len(data)


# ---------- 构建步骤 ----------
def copy_static():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    (OUT / ".nojekyll").touch()

    (OUT / "debs").mkdir()
    debs = sorted((ROOT / "debs").glob("*.deb"))
    for deb in debs:
        shutil.copy2(deb, OUT / "debs" / deb.name)

    for folder in ("depictions", "assets"):
        src = ROOT / folder
        if src.is_dir():
            shutil.copytree(src, OUT / folder)

    icon = ROOT / "CydiaIcon.png"
    if icon.exists():
        shutil.copy2(icon, OUT / "CydiaIcon.png")
    return debs


def build_packages(conf):
    cmd = ["dpkg-scanpackages"]
    if conf.get("KEEP_OLD_VERSIONS", "1") == "1":
        cmd.append("-m")
    cmd += ["debs", "/dev/null"]
    result = subprocess.run(
        cmd, cwd=OUT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    packages = result.stdout
    # dpkg-scanpackages 会把自定义字段规范成首字母大写（SileoDepiction -> Sileodepiction），
    # 这里还原成 Sileo 文档里的写法
    packages = re.sub(rb"(?m)^Sileodepiction:", b"SileoDepiction:", packages)
    for line in result.stderr.decode("utf-8", "replace").splitlines():
        # 我们不使用 override 文件，这类提示没有意义
        if "override" not in line and not line.startswith("dpkg-scanpackages: warning:   "):
            print(line)

    (OUT / "Packages").write_bytes(packages)
    (OUT / "Packages.gz").write_bytes(gzip.compress(packages, 9, mtime=0))
    (OUT / "Packages.bz2").write_bytes(bz2.compress(packages, 9))
    (OUT / "Packages.xz").write_bytes(lzma.compress(packages, preset=9))
    return packages.decode("utf-8")


def build_release(conf):
    lines = [
        f"Origin: {conf.get('ORIGIN', conf['NAME'])}",
        f"Label: {conf.get('LABEL', conf['NAME'])}",
        f"Suite: {conf.get('SUITE', 'stable')}",
        f"Version: {conf.get('VERSION', '1.0')}",
        f"Codename: {conf.get('CODENAME', 'ios')}",
        f"Architectures: {conf.get('ARCHITECTURES', 'iphoneos-arm iphoneos-arm64')}",
        f"Components: {conf.get('COMPONENTS', 'main')}",
        f"Description: {conf.get('DESCRIPTION', '')}",
        f"Date: {format_datetime(datetime.now(timezone.utc), usegmt=True)}",
    ]
    index_files = ["Packages", "Packages.gz", "Packages.bz2", "Packages.xz"]
    hashes = {name: file_hashes(OUT / name) for name in index_files}
    for algo in ("MD5Sum", "SHA1", "SHA256", "SHA512"):
        lines.append(f"{algo}:")
        for name in index_files:
            digests, size = hashes[name]
            lines.append(f" {digests[algo]} {size:>16} {name}")
    (OUT / "Release").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_package_list(packages_text, conf):
    entries = parse_packages(packages_text)
    latest = {}
    for e in entries:
        key = (e["package"], e.get("architecture", ""))
        old = latest.get(key)
        if old is None or cmp_version(e.get("version", "0"), old.get("version", "0")) > 0:
            latest[key] = e

    allowed = set(conf.get("ARCHITECTURES", "").split())
    items = []
    for (pkg, arch), e in latest.items():
        if allowed and arch not in allowed:
            print(f"⚠️  {pkg} 的架构 {arch} 不在 repo.conf 的 ARCHITECTURES 里")
        items.append(
            {
                "id": pkg,
                "name": e.get("name", pkg),
                "version": e.get("version", ""),
                "arch": arch,
                "section": e.get("section", ""),
                "description": e.get("description", "").split("\n")[0],
                "author": e.get("author", e.get("maintainer", "")),
                "file": e.get("filename", ""),
                "size": int(e.get("size", 0) or 0),
                "depiction": e.get("sileodepiction", e.get("depiction", "")),
                "icon": e.get("icon", ""),
            }
        )
    items.sort(key=lambda x: (x["name"].lower(), x["arch"]))
    (OUT / "packages.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return items


def build_index(conf):
    template = (ROOT / "index.template.html").read_text(encoding="utf-8")
    now = datetime.now(timezone.utc)
    values = {
        "NAME": conf["NAME"],
        "URL": conf["URL"],
        "DESCRIPTION": conf.get("DESCRIPTION", ""),
        "FOOTER": conf.get("FOOTER", ""),
        "BUILD_DATE": now.strftime("%Y-%m-%d %H:%M UTC"),
    }
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", html.escape(value, quote=True))
    (OUT / "index.html").write_text(template, encoding="utf-8")


def main():
    conf = load_conf()
    debs = copy_static()
    packages_text = build_packages(conf)
    build_release(conf)
    items = build_package_list(packages_text, conf)
    build_index(conf)

    print(f"\n✅ 构建完成：{len(debs)} 个 deb，{len(items)} 个软件包 → {OUT}")
    for it in items:
        print(f"   {it['id']:<40} {it['version']:<12} {it['arch']}")
    if not debs:
        print("   （debs/ 里还没有 .deb 文件，源是空的）")


if __name__ == "__main__":
    main()
