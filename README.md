<div align="center">

<img src=".github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse KookAdapter" />

# ErisPulse KookAdapter

**Kook（开黑啦）机器人适配器 —— 基于 ErisPulse 框架。**

基于开源机器人框架 ErisPulse 的 Kook（开黑啦）机器人适配器，支持频道 / 私信消息收发、KMarkdown、卡片消息、@提及与回复等完整能力。

<p>
  <a href="https://pypi.org/project/ErisPulse-KookAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-KookAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-KookAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-KookAdapter"><img src="https://img.shields.io/github/stars/ErisPulse/ErisPulse-KookAdapter?style=for-the-badge&logo=github&color=brightgreen" alt="Stars"></a>
  <a href="https://pepy.tech/project/ErisPulse-KookAdapter"><img src="https://img.shields.io/pepy/dt/ErisPulse-KookAdapter?style=for-the-badge&color=blue" alt="Downloads"></a>
  <a href="https://github.com/ErisPulse/ErisPulse"><img src="https://img.shields.io/badge/Powered_by-ErisPulse-FF6B9D?style=for-the-badge&logo=bookstack&logoColor=white" alt="ErisPulse"></a>
</p>

</div>

---

项目目前已托管至PyPi，使用以下命令以完成安装：
```bash
pip install ErisPulse-KookAdapter
```
此时执行`ep list`，应该可以看到`ErisPulse-KookAdapter`在已安装的适配器列表中。

## 使用
```python
from ErisPulse import sdk
adapter = sdk.adapter.get("Kook")
```
然后就可以对adapter变量进行适配器方法操作了。

适配器支持链式调用：
```python
# @用户
await kook.Send.To("group", "频道ID").At("用户ID").Text("Hello")

# @多个用户
await kook.Send.To("group", "频道ID").At("用户1").At("用户2").Text("Hello")

# @全体
await kook.Send.To("group", "频道ID").AtAll().Text("公告")

# 回复消息
await kook.Send.To("group", "频道ID").Reply("消息ID").Text("回复内容")

# 组合使用
await kook.Send.To("group", "频道ID").At("用户ID").Reply("消息ID").Text("Hello")
```

另外，支持不同消息`SendDSL`调用：
```python
# 文本消息
await kook.Send.To("group", "频道ID").Text("Hello World")

# 图片消息
await kook.Send.To("group", "频道ID").Image("http://example.com/image.jpg")

# 视频消息
await kook.Send.To("group", "频道ID").Video("http://example.com/video.mp4")

# 文件消息
await kook.Send.To("group", "频道ID").File("http://example.com/file.pdf")

# 语音消息
await kook.Send.To("group", "频道ID").Voice("http://example.com/voice.mp3")

# KMarkdown 消息
await kook.Send.To("group", "频道ID").Markdown("**粗体** *斜体*")

# 卡片消息
await kook.Send.To("group", "频道ID").Card({
    "type": "card",
    "theme": "primary",
    "size": "lg",
    "modules": [
        {"type": "header", "text": {"type": "plain-text", "content": "标题"}},
        {"type": "section", "text": {"type": "kmarkdown", "content": "内容"}}
    ]
})
```

### 私信消息
```python
# 发送私信给指定用户
await kook.Send.To("user", "用户ID").Text("Hello")
await kook.Send.To("user", "用户ID").Markdown("**私信内容**")
await kook.Send.To("user", "用户ID").Card({...})
```

### 消息编辑与撤回
```python
# 发送消息并获取消息ID
result = await kook.Send.To("group", "频道ID").Markdown("**原始内容**")
msg_id = result["data"]["msg_id"]

# 编辑消息（仅支持 KMarkdown 和 CardMessage）
await kook.Send.To("group", "频道ID").Edit(msg_id, "**更新后的内容**")

# 撤回消息
await kook.Send.To("group", "频道ID").Recall(msg_id)

# 上传本地文件 并获取文件URL
result = await kook.Send.Upload("C:/path/to/image.jpg")
file_url = result["data"]["url"]
```


## 参考文档
- [Kook API 文档](https://developer.kookapp.cn/doc)  
- [ErisPulse 文档](https://erisdev.com)  
- [ErisPulse 主库](https://github.com/ErisPulse/ErisPulse)
