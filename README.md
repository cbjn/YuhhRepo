# Sileo 软件源模板（GitHub Pages）

推送到 `main` 后，GitHub Actions 会自动：

1. 扫描 `debs/` 里的所有 `.deb`
2. 生成 `Packages`、`Packages.gz/.bz2/.xz`、`Release`
3. 生成带「一键添加到 Sileo / Zebra / Installer」按钮的首页
4. 部署到 GitHub Pages

你只需要：丢 deb 进 `debs/` → `git push`。

## 目录结构

```
.
├── repo.conf                  ← 源名称、域名、架构等，只改这里
├── CydiaIcon.png              ← 源图标（Sileo 会读取），记得换成自己的
├── index.template.html        ← 首页模板
├── build.py                   ← 生成索引的脚本
├── debs/                      ← 放 .deb
├── depictions/native/         ← Sileo 原生详情页 JSON（可选）
├── examples/control.rootless  ← rootless 包的 control 文件示例
├── assets/                    ← 图标、截图等静态资源（可选，自己新建）
└── .github/workflows/deploy.yml
```

## 快速开始

### 1. 新建仓库

用这个模板新建一个 GitHub 仓库（建议仓库名随意，用自定义域名时和仓库名无关）。

### 2. 修改 `repo.conf`

至少改这两项：

```
NAME=你的源名称
URL=https://repo.yuhh.win
```

### 3. 开启 Pages

仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。

### 4. 绑定自有域名

**子域名（推荐）**：到你的 DNS 服务商添加一条记录

| 类型 | 主机记录 | 值 |
|---|---|---|
| CNAME | `repo` | `你的GitHub用户名.github.io` |

**根域名**：添加 4 条 A 记录指向 `185.199.108.153`、`185.199.109.153`、`185.199.110.153`、`185.199.111.153`。

然后在 **Settings → Pages → Custom domain** 填入 `repo.yuhh.win` 并保存。证书签发后（几分钟到一小时）勾选 **Enforce HTTPS**。

> 如果域名托管在 Cloudflare，签发证书期间先把这条记录设为「仅 DNS」（灰云），签发完再决定是否开代理。
> 用 Actions 部署时不需要仓库里有 `CNAME` 文件，域名在 Settings 里设置即可。

### 5. 上传第一个 deb

把 deb 放进 `debs/`，提交并推送：

```bash
git add debs/
git commit -m "add xxx 1.0.0"
git push
```

到 **Actions** 页签看构建结果，成功后在 Sileo 里添加 `https://repo.yuhh.win` 即可。
也可以直接在手机上打开首页，点「添加到 Sileo」。

## 本地预览构建结果

```bash
# Debian/Ubuntu: sudo apt install dpkg-dev
# macOS:         brew install dpkg
python3 build.py
python3 -m http.server -d _site 8000
```

## 架构要对应越狱类型

deb 的 `control` 里 `Architecture` 必须和用户越狱类型一致，否则 Sileo 里看不到这个包：

| 越狱类型 | Architecture |
|---|---|
| rootful（传统） | `iphoneos-arm` |
| rootless（Dopamine 等） | `iphoneos-arm64` |
| roothide | `iphoneos-arm64e` |

同一个插件想支持多种类型，就分别打包，每个 deb 各放一份到 `debs/`。

## 给软件包加原生详情页

1. 复制 `depictions/native/com.example.tweak.json`，改名成你的包名，编辑内容
2. 在 deb 的 `control` 文件里加一行：

```
SileoDepiction: https://repo.yuhh.win/depictions/native/你的包名.json
```

3. 重新打包 deb，放进 `debs/`，推送

控件参考：<https://github.com/Sileo/Sileo/wiki>（搜索 Native Depictions）。

## 常见问题

**Sileo 添加后提示源无效 / 没有包**
- 域名是否已生效 HTTPS（浏览器直接打开 `https://repo.yuhh.win/Release` 应该能看到文本）
- `repo.conf` 的 `URL` 是否和实际访问域名一致
- Actions 是否构建成功（Actions 页签里有没有红叉）

**更新了 deb 但 Sileo 里没变化**
- Sileo 下拉刷新；GitHub Pages 有 CDN 缓存，等 1~2 分钟
- 版本号必须比旧版本高

**单个 deb 超过 100MB**
GitHub 单文件上限 100MB，Pages 站点总大小建议 < 1GB。更大的包请改用对象存储（R2 / OSS）或自己的服务器，把 `build.py` 的输出目录原样同步过去即可。

**想只保留最新版本**
`repo.conf` 里把 `KEEP_OLD_VERSIONS` 改成 `0`。
