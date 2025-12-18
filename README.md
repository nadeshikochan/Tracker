# ⏱️ AI 时间追踪系统 v2.0

一个智能的 Windows 桌面时间追踪工具，自动记录你的电脑使用行为，并通过 AI 进行智能分类分析。

## ✨ 功能特性

### 核心功能
- 🖥️ **自动窗口追踪** - 实时监控前台窗口，记录软件使用情况
- 🌐 **浏览器 URL 捕获** - 支持 Chrome/Edge/Firefox/Opera/Brave 等主流浏览器
- ⌨️ **活跃度检测** - 监测键鼠操作频率，判断用户专注程度
- 🤖 **AI 智能分类** - 自动将活动归类为开发/学习/娱乐等 9 大类别
- 💤 **空闲检测** - 自动识别休息时间，不计入工作时长

### 数据可视化
- 📊 **交互式仪表盘** - Streamlit 构建的现代化 Web 界面
- 📈 **多维度图表** - 饼图、柱状图、热力图、时间轴
- 🎯 **目标追踪** - 设定每日目标，实时显示完成进度
- 📅 **多日报告** - 支持单日/日期范围/周报查看
- 📥 **数据导出** - CSV/Markdown 格式导出

### 稳定性保障
- 🛡️ **防抖机制** - 忽略短暂的窗口切换干扰
- 🔄 **自动重试** - AI 请求失败自动重试
- 💾 **失败备份** - 处理失败的日志自动保存
- 🌙 **休眠处理** - 正确处理系统休眠/唤醒
- ✂️ **跨天切割** - 自动按日期分割活动记录

## 🚀 快速开始

### 环境要求
- Windows 10/11
- Python 3.8+
- 稳定的网络连接（用于 AI API）

### 安装步骤

1. **下载项目**
   ```
   解压到任意目录，如 D:\TimeTracker
   ```

2. **配置 API Key**
   
   编辑 `config.json`，填入你的 API Key：
   ```json
   {
       "api_key": "你的API密钥",
       "base_url": "https://api-inference.modelscope.cn/v1/",
       "model": "Qwen/Qwen2.5-72B-Instruct"
   }
   ```
   
   推荐 API 服务：
   - [阿里云 ModelScope](https://modelscope.cn) - 免费额度
   - [OpenAI](https://platform.openai.com) - 需付费
   - 其他 OpenAI 兼容服务

3. **启动程序**
   
   双击 `start.bat`，首次运行会自动：
   - 创建虚拟环境
   - 安装依赖包
   - 启动系统托盘

4. **打开仪表盘**
   
   双击系统托盘图标，或访问 http://localhost:8502

## 📁 项目结构

```
TimeTracker/
├── start.bat          # 启动脚本
├── launcher.py        # 系统托盘启动器
├── tracker.py         # 核心追踪模块
├── webui.py           # Web 仪表盘
├── common.py          # 公共工具函数
├── config.json        # 主配置文件
├── goals.json         # 目标配置
├── requirements.txt   # 依赖清单
└── logs/              # 数据目录
    ├── 2024-01-15.csv # 每日记录
    ├── raw/           # 原始日志
    ├── failed/        # 失败备份
    └── runtime.log    # 运行日志
```

## ⚙️ 配置说明

### config.json

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `api_key` | AI 服务 API 密钥 | 必填 |
| `base_url` | API 服务地址 | ModelScope |
| `model` | 使用的模型名称 | Qwen2.5-72B |
| `check_interval` | 窗口切换防抖时间(秒) | 30 |
| `batch_size` | 日志批量处理数量 | 5 |
| `idle_timeout` | 空闲检测阈值(秒) | 300 |
| `ai_retry_times` | AI 请求重试次数 | 3 |
| `browser_processes` | 需获取URL的浏览器 | Chrome/Edge等 |

### goals.json

| 配置项 | 说明 |
|--------|------|
| `enabled` | 是否启用目标追踪 |
| `targets` | 各分类目标时长(分钟) |
| `limits` | 上限类型分类(如娱乐) |

## 🏷️ 分类规则

| 分类 | 识别规则 |
|------|----------|
| 开发 | VSCode, PyCharm, GitHub, 终端 |
| AI | ChatGPT, Claude, 文心一言 |
| 知识库 | Obsidian, Notion, 语雀 |
| 学习 | 网课视频, PDF阅读, 百科 |
| 办公 | Word, Excel, 邮件, 会议 |
| 社交 | 微信, QQ, Telegram |
| 娱乐 | 游戏, 娱乐视频, 音乐 |
| 系统 | 文件管理器, 设置, 桌面 |
| 休息 | 长时间无操作 |

## 🔧 常见问题

### Q: 程序无法启动？
1. 确认 Python 已正确安装并加入 PATH
2. 检查端口 8502 是否被占用
3. 查看 `logs/runtime.log` 获取错误信息

### Q: 浏览器 URL 无法获取？
- 确保浏览器进程名在 `config.json` 的 `browser_processes` 中
- Firefox 需要启用无障碍功能

### Q: AI 分类不准确？
- 可以在仪表盘"数据明细"页面手动修正
- 分类规则可通过修改 `tracker.py` 中的 `SYSTEM_PROMPT` 调整

### Q: 如何清除历史数据？
- 删除 `logs/` 目录下对应的 `.csv` 文件

## 📝 更新日志

### v2.0 (当前版本)
- ✅ 修复跨天切割逻辑（支持多天跨越）
- ✅ 修复 CSV 保存日期错误
- ✅ 新增空闲状态检测
- ✅ 新增 AI 请求重试机制
- ✅ 新增每日目标追踪功能
- ✅ 新增数据导出功能
- ✅ 新增活动热力图
- ✅ 支持更多浏览器
- ✅ 优化时间轴显示

### v1.0
- 基础窗口追踪
- AI 分类
- WebUI 仪表盘

## 📜 许可证

MIT License

---

💡 **提示**: 如有问题或建议，欢迎反馈！
