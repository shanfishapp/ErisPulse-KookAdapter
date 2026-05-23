# Kook适配器与OneBot12协议的转换对照

## Kook特有事件类型

Kook平台提供以下事件类型，可在消息处理中检测使用：

### 1. 消息事件

| Kook消息类型 | type值 | 说明 | 转换后 |
|---|---|---|---|
| 文本消息 | 1 | 普通文本消息 | OneBot12 `message` 事件，`detail_type` 为 `group` 或 `private` |
| 图片消息 | 2 | 图片消息 | OneBot12 `message` 事件，`message` 段为 `image` |
| 视频消息 | 3 | 视频消息 | OneBot12 `message` 事件，`message` 段为 `video` |
| 文件消息 | 4 | 文件消息 | OneBot12 `message` 事件，`message` 段为 `file` |
| 语音消息 | 8 | 语音消息 | OneBot12 `message` 事件，`message` 段为 `record` |
| KMarkdown消息 | 9 | KMarkdown格式消息 | OneBot12 `message` 事件，`message` 段为 `text`（提取纯文本） |
| 卡片消息 | 10 | CardMessage卡片消息 | OneBot12 `message` 事件，`message` 段为 `json` |

> 消息事件的 `detail_type` 由 `channel_type` 字段决定：`GROUP` → `group`，`PERSON` → `private`

### 2. 通知事件（type=255）

| Kook事件类型 | 说明 | 转换后 |
|---|---|---|
| added_reaction | 频道消息添加表情回应 | OneBot12 `notice` 事件，`detail_type` 为 `group`，`sub_type` 为 `added_reaction` |
| deleted_reaction | 频道消息移除表情回应 | OneBot12 `notice` 事件，`detail_type` 为 `group`，`sub_type` 为 `deleted_reaction` |
| private_added_reaction | 私信消息添加表情回应 | OneBot12 `notice` 事件，`detail_type` 为 `private`，`sub_type` 为 `private_added_reaction` |
| private_deleted_reaction | 私信消息移除表情回应 | OneBot12 `notice` 事件，`detail_type` 为 `private`，`sub_type` 为 `private_deleted_reaction` |
| updated_private_message | 私信消息被更新 | OneBot12 `notice` 事件，`detail_type` 为 `private`，`sub_type` 为 `updated_private_message` |
| deleted_private_message | 私信消息被删除 | OneBot12 `notice` 事件，`detail_type` 为 `private`，`sub_type` 为 `deleted_private_message` |
| 其他系统事件 | 其他未识别的系统通知 | OneBot12 `notice` 事件，`sub_type` 为原始事件类型 |

### 3. 事件处理示例

```python
from ErisPulse.Core.Event import notice, message

# 处理消息事件
@message.on_message()
async def handle_message(event):
    if event.get("platform") != "kook":
        return

    detail_type = event.get("detail_type")

    if detail_type == "private":
        text = event.get_text()
        # 处理私聊消息...
    elif detail_type == "group":
        # 处理频道消息...
        channel_id = event.get("group_id")

# 处理通知事件
@notice.on_notice()
async def handle_notice(event):
    if event.get("platform") != "kook":
        return

    sub_type = event.get("sub_type")

    if sub_type == "added_reaction":
        emoji = event.get("emoji", {})
        user_id = event.get("user_id")
        msg_id = event.get("message_id")
    elif sub_type == "private_added_reaction":
        emoji = event.get("emoji", {})
        user_id = event.get("user_id")
    elif sub_type == "updated_private_message":
        msg_id = event.get("message_id")
        content = event.get("content")
    elif sub_type == "deleted_private_message":
        msg_id = event.get("message_id")
```

---

## 消息事件转换对照

### 1. 频道文本消息（type=1）

原始事件:
```json
{
  "s": 0,
  "d": {
    "channel_type": "GROUP",
    "type": 1,
    "target_id": "CHANNEL_ID",
    "author_id": "AUTHOR_ID",
    "content": "Hello World",
    "msg_id": "msg_id_example",
    "msg_timestamp": 1745558400000,
    "nonce": "nonce_string",
    "extra": {
      "type": 1,
      "guild_id": "GUILD_ID",
      "channel_name": "channel_name",
      "mention": [],
      "mention_all": false,
      "author": {
        "id": "AUTHOR_ID",
        "username": "用户名",
        "bot": false
      }
    }
  },
  "sn": 123
}
```

转换后:
```json
{
  "id": "msg_id_example",
  "time": 1745558400,
  "type": "message",
  "detail_type": "group",
  "sub_type": "",
  "platform": "kook",
  "self": {
    "platform": "kook",
    "user_id": "BOT_ID"
  },
  "kook_raw": { "s": 0, "d": {...}, "sn": 123 },
  "kook_raw_type": "1",
  "message_id": "msg_id_example",
  "user_id": "AUTHOR_ID",
  "group_id": "CHANNEL_ID",
  "channel_id": "CHANNEL_ID",
  "message": [
    {
      "type": "text",
      "data": {
        "text": "Hello World"
      }
    }
  ],
  "alt_message": "Hello World"
}
```

### 2. 私聊文本消息（type=1）

原始事件:
```json
{
  "s": 0,
  "d": {
    "channel_type": "PERSON",
    "type": 1,
    "target_id": "TARGET_USER_ID",
    "author_id": "AUTHOR_ID",
    "content": "Private Hello",
    "msg_id": "private_msg_id",
    "msg_timestamp": 1745558400000,
    "extra": {
      "type": 1,
      "mention": [],
      "mention_all": false,
      "author": {
        "id": "AUTHOR_ID",
        "username": "用户名",
        "bot": false
      }
    }
  },
  "sn": 124
}
```

转换后:
```json
{
  "id": "private_msg_id",
  "time": 1745558400,
  "type": "message",
  "detail_type": "private",
  "sub_type": "",
  "platform": "kook",
  "self": {
    "platform": "kook",
    "user_id": "BOT_ID"
  },
  "kook_raw": { "s": 0, "d": {...}, "sn": 124 },
  "kook_raw_type": "1",
  "message_id": "private_msg_id",
  "user_id": "AUTHOR_ID",
  "message": [
    {
      "type": "text",
      "data": {
        "text": "Private Hello"
      }
    }
  ],
  "alt_message": "Private Hello"
}
```

### 3. 频道图片消息（type=2）

原始事件:
```json
{
  "s": 0,
  "d": {
    "channel_type": "GROUP",
    "type": 2,
    "target_id": "CHANNEL_ID",
    "author_id": "AUTHOR_ID",
    "content": "IMAGE_URL",
    "msg_id": "image_msg_id",
    "msg_timestamp": 1745558400000,
    "extra": {
      "type": 2,
      "author": {
        "id": "AUTHOR_ID",
        "username": "用户名",
        "bot": false
      },
      "attachments": {
        "url": "https://img.kookapp.cn/attachments/example.png"
      }
    }
  },
  "sn": 125
}
```

转换后:
```json
{
  "id": "image_msg_id",
  "time": 1745558400,
  "type": "message",
  "detail_type": "group",
  "sub_type": "",
  "platform": "kook",
  "self": {
    "platform": "kook",
    "user_id": "BOT_ID"
  },
  "kook_raw": { "s": 0, "d": {...}, "sn": 125 },
  "kook_raw_type": "2",
  "message_id": "image_msg_id",
  "user_id": "AUTHOR_ID",
  "group_id": "CHANNEL_ID",
  "channel_id": "CHANNEL_ID",
  "message": [
    {
      "type": "image",
      "data": {
        "file": "https://img.kookapp.cn/attachments/example.png",
        "url": "https://img.kookapp.cn/attachments/example.png"
      }
    }
  ],
  "alt_message": "IMAGE_URL"
}
```

### 4. 带Mention的KMarkdown消息（type=9）

原始事件:
```json
{
  "s": 0,
  "d": {
    "channel_type": "GROUP",
    "type": 9,
    "target_id": "CHANNEL_ID",
    "author_id": "AUTHOR_ID",
    "content": "(met)USER_ID_1(met) Hello KMarkdown",
    "msg_id": "kmarkdown_msg_id",
    "msg_timestamp": 1745558400000,
    "extra": {
      "type": 9,
      "author": {
        "id": "AUTHOR_ID",
        "username": "用户名",
        "bot": false
      },
      "mention": ["USER_ID_1"],
      "mention_all": false,
      "kmarkdown": {
        "raw_content": "Hello KMarkdown"
      }
    }
  },
  "sn": 126
}
```

转换后:
```json
{
  "id": "kmarkdown_msg_id",
  "time": 1745558400,
  "type": "message",
  "detail_type": "group",
  "sub_type": "",
  "platform": "kook",
  "self": {
    "platform": "kook",
    "user_id": "BOT_ID"
  },
  "kook_raw": { "s": 0, "d": {...}, "sn": 126 },
  "kook_raw_type": "9",
  "message_id": "kmarkdown_msg_id",
  "user_id": "AUTHOR_ID",
  "group_id": "CHANNEL_ID",
  "channel_id": "CHANNEL_ID",
  "mentions": ["USER_ID_1"],
  "message": [
    {
      "type": "mention",
      "data": {
        "user_id": "USER_ID_1"
      }
    },
    {
      "type": "text",
      "data": {
        "text": "Hello KMarkdown"
      }
    }
  ],
  "alt_message": "(met)USER_ID_1(met) Hello KMarkdown"
}
```

### 5. 频道添加表情回应通知（type=255, added_reaction）

原始事件:
```json
{
  "s": 0,
  "d": {
    "type": 255,
    "channel_type": "GROUP",
    "target_id": "CHANNEL_ID",
    "author_id": "AUTHOR_ID",
    "extra": {
      "type": "added_reaction",
      "body": {
        "channel_id": "CHANNEL_ID",
        "msg_id": "msg_id_example",
        "user_id": "REACTION_USER_ID",
        "emoji": {
          "id": "",
          "name": "👍"
        }
      },
      "author": {
        "id": "AUTHOR_ID",
        "username": "用户名"
      }
    }
  },
  "sn": 127
}
```

转换后:
```json
{
  "id": "auto_generated_uuid",
  "time": 1745558400,
  "type": "notice",
  "detail_type": "group",
  "sub_type": "added_reaction",
  "platform": "kook",
  "self": {
    "platform": "kook",
    "user_id": "BOT_ID"
  },
  "kook_raw": { "s": 0, "d": {...}, "sn": 127 },
  "kook_raw_type": "255",
  "message_id": "msg_id_example",
  "user_id": "REACTION_USER_ID",
  "group_id": "CHANNEL_ID",
  "emoji": {
    "id": "",
    "name": "👍"
  }
}
```

### 6. 私信消息更新通知（type=255, updated_private_message）

原始事件:
```json
{
  "s": 0,
  "d": {
    "type": 255,
    "channel_type": "PERSON",
    "extra": {
      "type": "updated_private_message",
      "body": {
        "msg_id": "private_msg_id",
        "author_id": "AUTHOR_ID",
        "content": "更新后的内容"
      },
      "author": {
        "id": "AUTHOR_ID",
        "username": "用户名"
      }
    }
  },
  "sn": 128
}
```

转换后:
```json
{
  "id": "auto_generated_uuid",
  "time": 1745558400,
  "type": "notice",
  "detail_type": "private",
  "sub_type": "updated_private_message",
  "platform": "kook",
  "self": {
    "platform": "kook",
    "user_id": "BOT_ID"
  },
  "kook_raw": { "s": 0, "d": {...}, "sn": 128 },
  "kook_raw_type": "255",
  "message_id": "private_msg_id",
  "user_id": "AUTHOR_ID",
  "content": "更新后的内容"
}
```

### 7. 私信消息删除通知（type=255, deleted_private_message）

原始事件:
```json
{
  "s": 0,
  "d": {
    "type": 255,
    "channel_type": "PERSON",
    "extra": {
      "type": "deleted_private_message",
      "body": {
        "msg_id": "private_msg_id",
        "author_id": "AUTHOR_ID"
      },
      "author": {
        "id": "AUTHOR_ID",
        "username": "用户名"
      }
    }
  },
  "sn": 129
}
```

转换后:
```json
{
  "id": "auto_generated_uuid",
  "time": 1745558400,
  "type": "notice",
  "detail_type": "private",
  "sub_type": "deleted_private_message",
  "platform": "kook",
  "self": {
    "platform": "kook",
    "user_id": "BOT_ID"
  },
  "kook_raw": { "s": 0, "d": {...}, "sn": 129 },
  "kook_raw_type": "255",
  "message_id": "private_msg_id",
  "user_id": "AUTHOR_ID",
  "group_id": ""
}
```

---

## Kook发送消息类型（OneBot12扩展）

Kook适配器支持使用 OneBot12 消息段格式发送消息，支持以下类型：

### 1. 基础消息类型

| 类型 | 说明 | 参数 | Kook type值 |
|------|------|------|-------------|
| `text` | 纯文本 | `text`: 文本内容 | 1 |
| `markdown` | KMarkdown格式 | `markdown`: KMarkdown内容 | 9 |
| `kook_card` | 卡片消息 | `card`: 卡片结构体数据 | 10 |

### 2. 媒体消息类型

| 类型 | 说明 | 参数 | Kook type值 |
|------|------|------|-------------|
| `image` | 图片 | `file`: 文件路径/URL/bytes | 2 |
| `video` | 视频 | `file`: 文件路径/URL/bytes | 3 |
| `file` | 文件 | `file`: 文件路径/URL/bytes, `filename`: 文件名(可选) | 4 |
| `audio` | 语音 | `file`: 文件路径/URL/bytes | 8 |
| `record` | 语音（别名） | `file`: 文件路径/URL/bytes | 8 |

> 媒体消息会先通过上传接口 `/asset/create` 获取文件 URL，然后以对应 type 值发送。

### 3. 修饰消息类型

| 类型 | 说明 | 参数 |
|------|------|------|
| `mention` | @用户 | `user_id`: 用户ID（通过链式修饰 `.At()` 或消息段设置） |
| `mention_all` | @全体 | 无参数（通过链式修饰 `.AtAll()` 或消息段设置） |
| `reply` | 回复消息 | `message_id`: 消息ID（通过链式修饰 `.Reply()` 或消息段设置） |

### 4. 使用链式调用发送

```python
from ErisPulse import sdk
kook = sdk.adapter.get("kook")

# 基础发送
await kook.Send.To("group", channel_id).Text("Hello")

# 发送带@的消息
await kook.Send.To("group", channel_id).At("user_id").Text("@成员")

# 发送带@全体的消息
await kook.Send.To("group", channel_id).AtAll().Text("公告")

# 发送回复消息
await kook.Send.To("group", channel_id).Reply("msg_id").Text("回复内容")

# 发送KMarkdown消息
await kook.Send.To("group", channel_id).Markdown("**粗体** *斜体*")

# 发送卡片消息
await kook.Send.To("group", channel_id).Card({
    "type": "card",
    "theme": "primary",
    "modules": [
        {"type": "section", "text": {"type": "kmarkdown", "content": "内容"}}
    ]
})

# 使用 Raw_ob12 发送复杂消息
message = [
    {"type": "text", "data": {"text": "第一行"}},
    {"type": "image", "data": {"file": "https://example.com/img.jpg"}},
    {"type": "text", "data": {"text": "第二行"}}
]
await kook.Send.To("group", channel_id).Raw_ob12(message)
```

### 5. 发送目标类型

| target_type | 说明 | API端点 |
|-------------|------|---------|
| `group` | 频道消息 | `/api/v3/message/create` |
| `user` | 私信消息 | `/api/v3/direct-message/create` |

> Kook 的频道消息和私信消息使用不同的 API 端点，适配器会根据 `target_type` 自动选择。

### 6. 媒体上传

发送图片、视频、语音、文件等媒体类型时，适配器会自动调用上传接口：

- 上传端点：`POST /api/v3/asset/create`
- 使用 `FormData` 上传，包含 `file`（文件数据）和 `file_type`（文件类型）

`file` 参数支持以下格式：
- `bytes`：二进制数据
- `str`（URL）：以 `http://` 或 `https://` 开头的网络地址（自动下载后上传）
- `str`（本地路径）：本地文件路径

`file_type` 根据文件扩展名自动推断：
| 扩展名 | file_type |
|--------|-----------|
| .jpg, .jpeg, .png, .gif, .bmp, .webp | image |
| .mp4, .avi, .mov, .mkv, .flv, .wmv | video |
| .mp3, .wav, .ogg, .m4a, .flac, .aac | audio |
| 其他 | file |

### 7. 消息编辑与撤回

Kook适配器额外支持消息编辑和撤回操作：

```python
# 编辑消息（仅支持 KMarkdown 和 CardMessage）
await kook.Send.To("group", channel_id).Edit(msg_id, "**更新内容**")

# 撤回消息
await kook.Send.To("group", channel_id).Recall(msg_id)

# 上传文件获取URL
result = await kook.Send.Upload("C:/path/to/file.jpg")
file_url = result["data"]["url"]
```

> 编辑和撤回操作会根据当前的 `target_type` 自动选择频道或私信的对应API端点。

### 8. 消息类型映射表

适配器内部使用以下映射将 OneBot12 消息段类型转换为 Kook 消息类型：

| OneBot12 消息段类型 | Kook type值 | 说明 |
|---------------------|-------------|------|
| `text` | 1 | 文本消息 |
| `image` | 2 | 图片消息 |
| `video` | 3 | 视频消息 |
| `file` | 4 | 文件消息 |
| `audio` | 8 | 语音消息 |
| `record` | 8 | 语音消息（别名） |
| `markdown` | 9 | KMarkdown消息 |
| `kook_card` | 10 | 卡片消息 |
