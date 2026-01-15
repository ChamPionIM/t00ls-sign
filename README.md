# T00ls 自动签到

自用，用于 T00ls 论坛每日签到，防止账号变僵尸号。

签到脚本来源：[HanZeYu-momo/Automatic-check-in-script-for-t00ls](https://github.com/HanZeYu-momo/Automatic-check-in-script-for-t00ls)

## 功能

- 自动登录并签到
- 支持钉钉机器人通知（可选）
- 支持 GitHub Actions 定时运行

## GitHub Actions 配置

### 1. Fork 本仓库

### 2. 配置 Secrets

1. 进入你的 GitHub 仓库页面
2. 点击顶部的 `Settings` 标签
3. 左侧菜单找到 `Secrets and variables` → 点击 `Actions`
4. 点击绿色按钮 `New repository secret`
5. 依次添加以下变量：

| Secret 名称 | 必填 | 说明 |
|------------|------|------|
| `T00LS_USERNAME` | ✅ | T00ls 用户名 |
| `T00LS_PASSWORD` | ✅ | T00ls 密码 |
| `T00LS_QUESTIONID` | ❌ | 安全问题 ID，默认 `0` |
| `T00LS_ANSWER` | ❌ | 安全问题答案 |
| `DD_ACCESS_TOKEN` | ❌ | 钉钉机器人 access_token |
| `DD_SECRET` | ❌ | 钉钉机器人加签密钥 |

### 3. 配置钉钉通知（可选）

1. 打开钉钉，进入一个群（或新建一个群）
2. 点击群设置 → 智能群助手 → 添加机器人
3. 选择「自定义」机器人，设置名称
4. 安全设置选择「加签」，复制生成的 `SEC...` 开头的密钥（即 `DD_SECRET`）
5. 点击完成，复制 Webhook 地址，格式如下：
   ```
   https://oapi.dingtalk.com/robot/send?access_token=xxxxxx
   ```
   `access_token=` 后面那串即为 `DD_ACCESS_TOKEN`
6. 将这两个值添加到 GitHub Secrets

### 4. 启用 Actions

Fork 后需手动启用 Actions，进入 `Actions` 页面点击启用即可。

## 定时执行

默认每天北京时间 8:00 自动执行，可在 `.github/workflows/checkin.yml` 中修改 cron 表达式。

## 手动触发

在 Actions 页面可手动触发 `workflow_dispatch`。

## 免责声明

仅供学习交流，请勿滥用。
