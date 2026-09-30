# 部署到 GitHub Pages（自己操作）

本目录是一个纯静态站点，无需构建步骤。GitHub Pages 会从仓库分支直接托管 `index.html`。

## 目录里的文件

- `index.html` —— 页面与可视化逻辑（ECharts 已本地化，无需联网）
- `dist/echarts.min.js` —— 本地化的 ECharts 库（约 1 MB，必须随站提交）
- `data.json` —— 烘焙好的气候数据：370 个地级市 × 365 天 的 5 年日均温/降雨均值
- `china-geo.json` —— 中国地市边界底图（含南海诸岛九段线，符合地图规范）
- `geo-features.json` —— 自然地理要素：主要河流（折线）、湖泊（点）、山脉（点 + 标注）
- `fetch_geo.py` / `fetch_weather.py` —— 数据生成脚本（重跑数据时用，部署不需要）
- `gh-page.md` —— 本说明

> 注意：`data.json` 和 `china-geo.json` 各几 MB，远在 GitHub 单文件 100MB 限制内，放心提交。

## 步骤

### 1. 在 GitHub 新建仓库
- 打开 https://github.com/new
- Repository name 随意，例如 `china-weather-map`
- 选 **Public**（Private 仓库的 Pages 需要付费/特定计划）
- 不要勾选 "Add a README"（本地已有文件），或勾了也行，下面用 `--force` 覆盖
- 创建后复制仓库地址，形如 `https://github.com/<你的用户名>/china-weather-map.git`

### 2. 推送到仓库
在 `weather-geometry` 目录里执行（把地址换成你自己的）：

```bash
git init -q
git add index.html dist/echarts.min.js data.json china-geo.json geo-features.json gh-page.md
git commit -m "china 365-day livability/travel weather map"
git branch -M main
git remote add origin https://github.com/<你的用户名>/china-weather-map.git
git push -u origin main
```

> 若提示认证失败：用 GitHub 账号密码已不支持，需用 **Personal Access Token**（Settings → Developer settings → PAT，勾 `repo`）当作密码，或配置 SSH key。

### 3. 开启 Pages
- 进入仓库 **Settings → Pages**（左侧）
- Source 选 **Deploy from a branch**
- Branch 选 **main**，目录选 **/ (root)**
- 点 Save
- 等 1–2 分钟，访问 `https://<你的用户名>.github.io/<仓库名>/`

## 常见问题

- **页面空白 / 地图不出来**：打开浏览器控制台（F12）看是否有 `china-geo.json`、`data.json`、`geo-features.json` 或 `dist/echarts.min.js` 404。确认这些文件和 `index.html` 在同一目录、已提交并推送。
- **ECharts 加载不出**：`index.html` 已改为引用本地 `dist/echarts.min.js`（无需联网）。若删过该文件，重新下载 `https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js` 放回 `dist/` 即可。
- **部分城市是灰色（无数据）**：说明 `data.json` 还没抓全。在你的机器上重跑 `python fetch_weather.py`（脚本断点续传，会从已有城市补齐剩余城市），再重新提交 `data.json`。本环境沙箱出口 IP 曾被 Open-Meteo 限流，本地不同 IP 不受此限。
- **想换数据年份 / 城市粒度**：改 `fetch_weather.py` 里的 `START/END` 或 `fetch_geo.py` 里的 `COLLAPSE` 集合，重跑两个脚本，再重新提交 `data.json`。
- **想自定义评分**：评分公式在 `index.html` 的 `scoreOf()` 与 `PRESET` 里，调 `Wt`（温度容忍宽度）、`k`（降雨敏感度）、`w`（降雨权重）即可，无需后端。

## 可调参数（页面内实时生效）

- 维度切换：宜居 / 宜旅行（两套预设）
- 年内第几天滑块 + 播放全年（1–365）
- 舒适温度下限 / 上限（默认 20 / 25 ℃）
- 降雨权重（雨 vs 温，0–0.8）
- 自然地理图层：河流 / 湖泊 / 山脉 可单独勾选显隐（默认全开）
