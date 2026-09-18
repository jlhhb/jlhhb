# 订单跟踪

本地小工具：在页面里粘贴金山文档分享链接（或上传 xlsx），自动只查**未到货**订单，用承运商固定接口刷新状态，再下载更新后的表格。

查单过程不走 AI，不消耗对话 token。

## 能做什么

1. 读取 `https://www.kdocs.cn/l/...` 公开分享（需允许访客下载）
2. 自动识别承运商、运单号、状态列（兼容当前发货清单：N 承运商 / O 运单号 / P 状态）
3. 跳过已写「签收 / 已签收 / Delivered」的行
4. 无运单号标记为「未填单号」
5. 8DT（永利八达通）走 HTTP 接口批量查询
6. USPS / UPS / FedEx / Canada Post / 澳洲 TGX / DPD 可用系统 Chrome 打开官网（可选，机房 IP 可能被拦）
7. 把新状态、最新轨迹、查询时间写进 xlsx，供导入覆盖

金山文档开放平台写回需要企业营业执照，本工具**不会直接改在线表**。下载「发货清单-已更新状态.xlsx」后，在金山文档中用导入/覆盖即可。

## 启动

```bash
cd order-tracker
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-browser.txt   # 可选
python3 -m playwright install chromium               # 可选，仅官网浏览器查询需要
python3 -m app
```

浏览器打开 http://127.0.0.1:8787

指定工作表、运单号列和运输公司列。查询顺序：

1. 有免费开放接口则先调 API（目前 8DT / 永利八达通）
2. 没有免费接口、接口失败、或出现人机验证时，走 AI 查询（读取官网页面；配置 `ORDER_TRACKER_AI_API_KEY` 时用大模型抽取状态）
3. 结果在网页汇总，并写回你指定的状态列

页面加载后请确认：

- 工作表（例如 `新模板`）
- 运单号列
- 运输公司列
- 状态列（没有就选表尾新增的「订单状态」）

可选环境变量：

- `CHROME_PATH` 系统 Chrome 路径，默认 `/usr/bin/google-chrome-stable`
- `ORDER_TRACKER_AI_API_KEY` / `ORDER_TRACKER_AI_BASE_URL` / `ORDER_TRACKER_AI_MODEL` 用于 AI 抽取

人机验证码无法自动解开，会标记为「人机验证」。金山文档个人账号无法直接改在线文件，请下载更新表后导入覆盖。

## 测试

```bash
cd order-tracker
python3 -m pytest -q
```
