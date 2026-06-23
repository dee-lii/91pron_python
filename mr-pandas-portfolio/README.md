# Mr. Panda's Psychologically Safe Portfolio - 本地克隆版本

## ⚡ 快速启动（推荐）

### macOS / Linux
**双击 `start.command` 文件**，服务器会自动启动并在浏览器中打开网站！

### Windows
**双击 `start.bat` 文件**，服务器会自动启动并在浏览器中打开网站！

---

## ❗ 重要说明

**不能直接双击 `index.html` 打开！**

由于浏览器的 CORS 安全策略，使用了 ES6 模块（`type="module"`）的网站必须通过 HTTP(S) 服务器访问，直接用 `file://` 协议打开会被浏览器阻止。

错误示例：
```
Access to script from origin 'null' has been blocked by CORS policy
```

**解决方案**：使用上面的启动脚本，或按照下面的手动方式启动本地服务器。

---

## 📁 项目结构

```
mr-pandas-portfolio/                        # 总大小: 18MB
├── start.command                           # 🚀 一键启动脚本 (macOS/Linux)
├── start.bat                               # 🚀 一键启动脚本 (Windows)
├── index.html                              # 主页面 (1.2KB) - 使用相对路径
├── README.md                               # 本说明文档
├── 使用说明.md                              # 快速使用指南
├── 克隆完成报告.md                          # 克隆清单报告
├── 资源完整性检查报告.md                    # 资源完整性报告
├── assets/
│   ├── index--Xm2hwTR.js                  # JavaScript 主文件 (1.9MB)
│   └── index-V2LrUlmw.css                 # CSS 样式文件 (4.7KB)
├── basis/                                  # Basis Universal 解码器 (571KB)
│   ├── basis_transcoder.js                # 解码器 JavaScript (56KB)
│   └── basis_transcoder.wasm              # 解码器 WASM (515KB)
├── models/                                 # 3D 模型文件 (GLB 格式，共 100KB)
│   ├── Moving_Extras.glb                  # 移动装饰元素 (19KB)
│   ├── Panda.glb                          # 熊猫模型 (1.6KB)
│   ├── scene_1.glb                        # 场景 1 (28KB)
│   ├── scene_2.glb                        # 场景 2 (11KB)
│   ├── scene_3.glb                        # 场景 3 (12KB)
│   ├── scene_4.glb                        # 场景 4 (12KB)
│   └── single_sheet.glb                   # 单页模型 (4.5KB)
├── textures/                               # 纹理文件 (KTX2 格式，共 13.4MB)
│   ├── Moving_extras.ktx2                 # 移动装饰纹理 (1.4MB)
│   ├── desert.ktx2                        # 沙漠场景纹理 (126KB)
│   ├── dirt.ktx2                          # 泥土纹理 (4.8KB)
│   ├── kpop.ktx2                          # K-pop 场景纹理 (141KB)
│   ├── not_waterfall.ktx2                 # 瀑布场景纹理 (1.4MB)
│   ├── pirate.ktx2                        # 海盗场景纹理 (132KB)
│   ├── regular.ktx2                       # 常规纹理 (119KB)
│   ├── samurai.ktx2                       # 武士场景纹理 (134KB)
│   ├── zombie.ktx2                        # 僵尸场景纹理 (125KB)
│   ├── scene_1_bg.ktx2                    # 场景 1 背景 (2.3MB)
│   ├── scene_1.ktx2                       # 场景 1 纹理 (1.5MB)
│   ├── scene_2.ktx2                       # 场景 2 纹理 (2.0MB)
│   ├── scene_3.ktx2                       # 场景 3 纹理 (1.9MB)
│   ├── scene_4.ktx2                       # 场景 4 纹理 (1.9MB)
│   ├── single_sheet.ktx2                  # 单页纹理 (155KB)
│   ├── waterfall_one.ktx2                 # 瀑布纹理 1 (34KB)
│   └── waterfall_two.ktx2                 # 瀑布纹理 2 (35KB)
├── fonts/                                  # Plus Jakarta Sans 完整字体家族
│   ├── PlusJakartaSans-ExtraLight.woff    # 超细体
│   ├── PlusJakartaSans-ExtraLight.woff2
│   ├── PlusJakartaSans-ExtraLightItalic.woff
│   ├── PlusJakartaSans-ExtraLightItalic.woff2
│   ├── PlusJakartaSans-Light.woff         # 细体
│   ├── PlusJakartaSans-Light.woff2
│   ├── PlusJakartaSans-LightItalic.woff
│   ├── PlusJakartaSans-LightItalic.woff2
│   ├── PlusJakartaSans-Regular.woff       # 常规
│   ├── PlusJakartaSans-Regular.woff2
│   ├── PlusJakartaSans-Italic.woff
│   ├── PlusJakartaSans-Italic.woff2
│   ├── PlusJakartaSans-Medium.woff        # 中等
│   ├── PlusJakartaSans-Medium.woff2
│   ├── PlusJakartaSans-MediumItalic.woff
│   ├── PlusJakartaSans-MediumItalic.woff2
│   ├── PlusJakartaSans-SemiBold.woff      # 半粗体
│   ├── PlusJakartaSans-SemiBold.woff2
│   ├── PlusJakartaSans-SemiBoldItalic.woff
│   ├── PlusJakartaSans-SemiBoldItalic.woff2
│   ├── PlusJakartaSans-Bold.woff          # 粗体
│   ├── PlusJakartaSans-Bold.woff2
│   ├── PlusJakartaSans-BoldItalic.woff
│   ├── PlusJakartaSans-BoldItalic.woff2
│   ├── PlusJakartaSans-ExtraBold.woff     # 超粗体
│   ├── PlusJakartaSans-ExtraBold.woff2
│   ├── PlusJakartaSans-ExtraBoldItalic.woff
│   └── PlusJakartaSans-ExtraBoldItalic.woff2
└── media/
    ├── favicon-96x96.png                  # 网站图标 96x96 (7.6KB)
    ├── favicon.svg                        # SVG 图标 (261KB)
    ├── favicon.ico                        # ICO 图标 (15KB)
    ├── apple-touch-icon.png               # Apple 设备图标 (18KB)
    ├── og-image.webp                      # Open Graph 图片 (125KB)
    └── site.webmanifest                   # Web 应用清单文件 (436B)
```

## 🚀 本地运行方式

### 🌟 方式 1：一键启动（最简单，强烈推荐！）

**macOS / Linux**：双击 `start.command` 文件

**Windows**：双击 `start.bat` 文件

服务器会自动启动，并在 2 秒后自动在浏览器中打开 `http://localhost:8000`

---

### 方式 2：使用 Python 内置服务器（手动）

```bash
cd /Users/deelii/code/mr-pandas-portfolio
python3 -m http.server 8000
```

然后在浏览器访问：`http://localhost:8000`

### 方式 2：使用 Node.js http-server（手动）

首先安装 http-server（如果还没安装）：
```bash
npm install -g http-server
```

然后运行：
```bash
cd /Users/deelii/code/mr-pandas-portfolio
http-server -p 8000
```

然后在浏览器访问：`http://localhost:8000`

### 方式 3：使用 PHP 内置服务器（手动）

```bash
cd /Users/deelii/code/mr-pandas-portfolio
php -S localhost:8000
```

然后在浏览器访问：`http://localhost:8000`

---

## 📊 文件统计

- **总文件数**: 70 个文件
- **总大小**: 18 MB
- **主要技术**: React + Three.js（3D WebGL）
- **内容分类**:
  - **字体**: 28 个文件（Plus Jakarta Sans 完整字体家族）
  - **3D 模型**: 7 个 GLB 文件（熊猫、多个场景）
  - **纹理贴图**: 17 个 KTX2 文件（高性能压缩纹理，13.4MB）
  - **媒体资源**: 6 个文件（图标、图片等）
  - **解码器**: 2 个文件（Basis Universal WASM 解码器）
  - **代码**: HTML、CSS、JavaScript

## 📝 说明

这是从原始网站 `https://www.mr-pandas-psychologically-safe-portfolio.com/` 完整克隆的版本，包含所有必要的资源文件。

克隆时间：2026年1月7日
