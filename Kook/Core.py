import asyncio
import json
import zlib
from dataclasses import dataclass, field
from typing import Any, Dict

from ErisPulse.Core import client
from ErisPulse.Core.Bases.adapter import BaseAdapter
from ErisPulse.Core.Bases.websocket import WSMessage
from ErisPulse.runtime.config_schema import BotAccountConfig, dict_to_dataclass

from .CallApi import CallApi
from .Converter import KookAdapterConverter


@dataclass
class KookAccountConfig(BotAccountConfig):
    token: str = field(
        default="",
        metadata={
            "description": "Kook Bot Token",
            "required": True,
            "secret": True,
            "webui": {"widget": "password", "group": "basic", "order": 1},
        },
    )
    bot_id: str = field(
        default="",
        metadata={
            "description": "机器人ID（可选，不填则从token推断）",
            "required": False,
            "webui": {"widget": "text", "group": "basic", "order": 2},
        },
    )
    compress: bool = field(
        default=True,
        metadata={
            "description": "是否启用WebSocket数据压缩",
            "required": False,
        },
    )


class KookAdapter(BaseAdapter):
    """Kook 适配器（多账户）"""

    AccountConfigClass = KookAccountConfig

    def __init__(self, sdk_ref=None):
        super().__init__(sdk_ref)

        # 每个账户的运行时状态：sn/buffer/websocket/bot_id/api/converter/tasks
        self._account_runtime: Dict[str, dict] = {}
        # 每个账户的连接任务
        self._connect_tasks: Dict[str, asyncio.Task] = {}
        self._running = False

    def _get_config_key(self) -> str:
        return "KookAdapter"

    def _load_accounts(self) -> dict:
        from ErisPulse.Core.config import config as config_mgr

        key = "KookAdapter.accounts"
        data = config_mgr.getConfig(key)

        if not data:
            old_config = config_mgr.getConfig("KookAdapter")
            if old_config and "token" in old_config:
                self.logger.warning("检测到旧格式配置，建议迁移到新格式")
                self.logger.warning(
                    "迁移方法：将现有配置移动到 KookAdapter.accounts.default 下"
                )
                data = {
                    "default": {
                        "token": old_config.get("token", ""),
                        "bot_id": old_config.get("bot_id", ""),
                        "compress": old_config.get("compress", True),
                        "enabled": True,
                    }
                }
                self.logger.warning(
                    "已临时加载旧配置为默认账户，请尽快迁移到新格式"
                )
            else:
                self.logger.info("未找到配置文件，创建默认账户配置")
                data = {
                    "default": {
                        "token": "",
                        "bot_id": "",
                        "compress": True,
                        "enabled": True,
                    }
                }
                try:
                    config_mgr.setConfig(key, data)
                except Exception as e:
                    self.logger.error(f"保存默认账户配置失败: {str(e)}")

        accounts = {}
        for name, account_data in data.items():
            if not isinstance(account_data, dict):
                continue
            if "token" not in account_data or not account_data["token"]:
                self.logger.error(f"账户 {name} 缺少token配置，已跳过")
                continue

            instance = dict_to_dataclass(KookAccountConfig, account_data)
            instance.name = name
            accounts[name] = instance

        self.logger.info(f"Kook适配器初始化完成，共加载 {len(accounts)} 个账户")
        return accounts

    def _get_runtime(self, account_name: str) -> dict:
        """获取/创建某个账户的运行时状态"""
        if account_name not in self._account_runtime:
            self._account_runtime[account_name] = {
                "sn": 0,
                "buffer": [],
                "need_buffer": False,
                "websocket": None,
                "bot_id": "",
                "api": None,
                "converter": None,
                "heartbeat_task": None,
                "receive_task": None,
            }
        return self._account_runtime[account_name]

    def _infer_bot_id(self, account) -> str:
        """从配置/token推断 bot_id"""
        bot_id = account.bot_id or ""
        if not bot_id:
            token = account.token or ""
            parts = token.replace("Bot ", "").split("/")
            bot_id = parts[-1] if parts else ""
        return bot_id

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    async def start(self):
        """启动适配器，为每个启用的账户创建独立连接"""
        self._running = True

        for account_name, account in self.enabled_accounts.items():
            rt = self._get_runtime(account_name)

            bot_id = self._infer_bot_id(account)
            rt["bot_id"] = bot_id

            converter = KookAdapterConverter()
            converter.set_bot_id(bot_id)
            rt["converter"] = converter

            rt["api"] = CallApi(self, account.token)

            await self.emit_meta("connect", bot_id)

            self._connect_tasks[account_name] = asyncio.create_task(
                self._connect_account(account_name)
            )
            self.logger.info(
                f"账户 {account_name} (bot_id: {bot_id}) 已启动"
            )

        self.logger.info(
            f"Kook适配器启动完成，共 {len(self.enabled_accounts)} 个账户"
        )

    async def _connect_account(self, account_name: str):
        """单个账户的连接循环（含 RESUME / HELLO / 重连）"""
        account = self.accounts.get(account_name)
        if not account:
            return

        rt = self._get_runtime(account_name)
        compress = account.compress

        while self._running:
            ws = None
            try:
                # 尝试 RESUME（如果 sn > 0）
                if rt["sn"] > 0:
                    self.logger.info(f"[{account_name}] 尝试使用 RESUME 恢复连接...")
                    if await self._try_resume(account_name):
                        await self._start_message_processing(account_name)
                        continue
                    else:
                        self.logger.info(f"[{account_name}] RESUME 失败，重新获取 gateway...")
                        rt["sn"] = 0
                        rt["buffer"].clear()
                        rt["need_buffer"] = False

                # 全新连接（HELLO 流程）
                url = await rt["api"].get_ws_gateway(compress)
                ws = await client.ws_connect(url)
                result = await self._wait_server_hello(ws, account_name)
                if not result:
                    self.logger.error(
                        f"[{account_name}] 启动失败, 连接关闭, 5秒后重试"
                    )
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    await asyncio.sleep(5)
                    continue

                rt["websocket"] = ws
                self.logger.info(f"[{account_name}] 连接成功，开始处理消息")

                # 启动消息处理
                await self._start_message_processing(account_name)

            except Exception as e:
                self.logger.error(f"[{account_name}] 连接异常: {e}, 5秒后重试")
                if ws is not None:
                    try:
                        await ws.close()
                    except Exception:
                        pass
                await asyncio.sleep(5)

    async def _try_resume(self, account_name: str) -> bool:
        """
        尝试使用 RESUME[4] 恢复连接

        Returns:
            bool: 是否成功恢复
        """
        rt = self._get_runtime(account_name)
        account = self.accounts.get(account_name)
        if not account:
            return False

        ws = None
        try:
            url = await rt["api"].get_ws_gateway(account.compress)
            ws = await client.ws_connect(url)

            # 发送 RESUME 信令
            resume_payload = {"s": 4, "sn": rt["sn"]}
            await ws.send_text(json.dumps(resume_payload))
            self.logger.info(f"[{account_name}] 发送 RESUME[4] 信令，sn={rt['sn']}")

            # 等待响应
            msg = await asyncio.wait_for(ws.receive(), timeout=6)
            raw = self._decode_ws_message(msg, account.compress)
            if raw is None:
                self.logger.warning(f"[{account_name}] RESUME 失败，无法解析响应")
                await ws.close()
                return False
            data = json.loads(raw)

            if data.get("s") == 6:
                session_id = data.get("d", {}).get("session_id", "")
                self.logger.info(
                    f"[{account_name}] RESUME 成功，session_id: {session_id}"
                )
                rt["websocket"] = ws
                return True
            else:
                self.logger.warning(f"[{account_name}] RESUME 失败，收到响应: {data}")
                await ws.close()
                return False
        except Exception as e:
            self.logger.error(f"[{account_name}] RESUME 尝试失败: {e}")
            if ws is not None:
                try:
                    await ws.close()
                except Exception:
                    pass
            return False

    async def _start_message_processing(self, account_name: str):
        """启动消息处理（心跳和接收）"""
        rt = self._get_runtime(account_name)
        rt["heartbeat_task"] = asyncio.create_task(
            self._send_heartbeat(account_name)
        )
        rt["receive_task"] = asyncio.create_task(
            self._receive_messages(account_name)
        )

        # 等待任务完成（连接断开时会返回）
        await asyncio.gather(
            rt["heartbeat_task"], rt["receive_task"], return_exceptions=True
        )

    def _decode_ws_message(self, msg, compress: bool = True) -> "str | None":
        """将 WSMessage 解码为字符串（处理 zlib 压缩）"""
        if msg.type in (WSMessage.CLOSE, WSMessage.ERROR):
            return None
        raw = msg.data
        if isinstance(raw, bytes):
            if compress:
                try:
                    raw = zlib.decompress(raw)
                except Exception:
                    pass
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
        return raw

    async def _wait_server_hello(self, websocket, account_name: str) -> bool:
        """等待服务器发送 hello 消息"""
        account = self.accounts.get(account_name)
        compress = account.compress if account else True
        try:
            msg = await asyncio.wait_for(websocket.receive(), timeout=6)
            raw = self._decode_ws_message(msg, compress)
            if raw is None:
                return False
            data = json.loads(raw)
            if data["s"] == 1:
                self.logger.info(
                    f"[{account_name}] 成功接收到服务器信令: HELLO[1], 开始处理消息"
                )
                if data.get("d", {}).get("code", -1) == 0:
                    self.logger.info(f"[{account_name}] 连接成功")
                    return True
                return False
            return False
        except asyncio.TimeoutError:
            self.logger.error(
                f"[{account_name}] 等待服务器发送HELLO[1]信令超时, 请重试"
            )
            await websocket.close()
            return False

    async def _receive_messages(self, account_name: str):
        """持续接收消息"""
        rt = self._get_runtime(account_name)
        account = self.accounts.get(account_name)
        compress = account.compress if account else True
        websocket = rt["websocket"]

        while self._running and websocket:
            try:
                msg = await websocket.receive()

                if msg.type in (WSMessage.CLOSE, WSMessage.ERROR):
                    self.logger.warning(f"[{account_name}] WebSocket连接已关闭")
                    return

                raw = self._decode_ws_message(msg, compress)
                if raw is None:
                    return

                data = json.loads(raw)
                signal_type = data.get("s")

                self.logger.debug(f"[{account_name}] 收到消息: {data}")

                if signal_type == 0:
                    # 正常消息事件
                    await self._handle_message_signal(data, account_name)
                elif signal_type == 3:
                    # 心跳响应（PONG）
                    self.logger.debug(f"[{account_name}] 收到心跳响应 PONG[3]")
                elif signal_type == 5:
                    # 需要重连
                    code = data.get("d", {}).get("code", "")
                    err = data.get("d", {}).get("err", "")
                    self.logger.error(
                        f"[{account_name}] 收到RECONNECT[5]信令，连接已失效，code={code}, err={err}"
                    )
                    await self._handle_reconnect_signal(account_name)
                    return
                elif signal_type == 6:
                    # RESUME 成功
                    session_id = data.get("d", {}).get("session_id", "")
                    self.logger.info(
                        f"[{account_name}] RESUME成功，session_id: {session_id}"
                    )
                else:
                    self.logger.warning(
                        f"[{account_name}] 收到未知信令类型: {signal_type}"
                    )

            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.warning(f"[{account_name}] WebSocket接收异常: {e}")
                return

    async def _send_heartbeat(self, account_name: str):
        """发送心跳"""
        rt = self._get_runtime(account_name)
        websocket = rt["websocket"]

        while (
            self._running
            and websocket
            and not websocket.closed
        ):
            try:
                payload = {"s": 2, "sn": rt["sn"]}
                await websocket.send_text(json.dumps(payload))
                self.logger.debug(
                    f"[{account_name}] 发送心跳 PING[2]，sn={rt['sn']}"
                )
                await self.emit_meta("heartbeat", rt["bot_id"])
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.error(f"[{account_name}] 心跳发送异常: {e}")
                return

    async def _handle_reconnect_signal(self, account_name: str):
        """
        处理 RECONNECT[5] 信令

        Kook 规则:
        1. 收到 RECONNECT 后，必须重新获取 gateway
        2. 清空 sn 计数和消息队列
        3. 重新连接（HELLO 流程）
        """
        rt = self._get_runtime(account_name)
        self.logger.warning(
            f"[{account_name}] 收到 RECONNECT[5] 信令，开始重新连接..."
        )

        # 取消心跳任务
        if rt["heartbeat_task"]:
            rt["heartbeat_task"].cancel()
            try:
                await rt["heartbeat_task"]
            except asyncio.CancelledError:
                pass
            rt["heartbeat_task"] = None

        # 关闭当前连接
        ws = rt["websocket"]
        if ws and not ws.closed:
            try:
                await ws.close()
            except Exception:
                pass
        rt["websocket"] = None

        # 清空状态
        rt["sn"] = 0
        rt["buffer"].clear()
        rt["need_buffer"] = False

        # 重新连接会在 _connect_account() 方法的循环中自动进行

    async def _handle_message_signal(self, data: dict, account_name: str):
        """
        处理信令[0] - 正常消息接收

        Args:
            data: 消息数据，包含事件类型和事件数据
                  格式: {"s": 0, "d": {...}, "sn": 123}
            account_name: 账户名
        """
        rt = self._get_runtime(account_name)
        msg_sn = data.get("sn", 0)
        expected_sn = rt["sn"] + 1

        if msg_sn != expected_sn:
            if not rt["need_buffer"]:
                rt["need_buffer"] = True
                self.logger.warning(
                    f"[{account_name}] 消息序号不连续，进入暂存模式。"
                    f"期望sn={expected_sn}，实际sn={msg_sn}"
                )
            rt["buffer"].append(data)
            rt["buffer"].sort(key=lambda x: x.get("sn", 0))
            return

        await self._process_message(data, account_name)

        # 处理暂存区中的消息
        while rt["buffer"]:
            next_expected = rt["sn"] + 1
            found = False
            for i, buffered_msg in enumerate(rt["buffer"]):
                if buffered_msg.get("sn", 0) == next_expected:
                    self.logger.debug(
                        f"[{account_name}] 从暂存区处理消息，sn={next_expected}"
                    )
                    await self._process_message(buffered_msg, account_name)
                    rt["buffer"].pop(i)
                    found = True
                    break
            if not found:
                break

        if not rt["buffer"]:
            rt["need_buffer"] = False
            self.logger.debug(f"[{account_name}] 暂存区已清空，退出暂存模式")

    async def _process_message(self, data: dict, account_name: str):
        """
        处理单条消息，转换为OneBot12格式并分发到事件系统

        Args:
            data: 消息数据
            account_name: 账户名
        """
        rt = self._get_runtime(account_name)
        rt["sn"] = data.get("sn", rt["sn"])

        converter = rt["converter"]

        # 检查是否为机器人发送的消息（仅针对消息事件）
        d = data.get("d", {})
        kook_type = d.get("type", 0)
        if kook_type != 255:  # 非 notice 事件才过滤机器人消息
            author = d.get("extra", {}).get("author", {})
            if author.get("bot", False):
                return

        try:
            onebot_event = converter.convert(data)
            await self.sdk.adapter.emit(onebot_event)
            self.logger.debug(
                f"[{account_name}] 事件已分发: "
                f"{onebot_event.get('type')} - {onebot_event.get('detail_type')}"
            )
        except Exception as e:
            self.logger.error(
                f"[{account_name}] 事件处理异常: {e}, 原始数据: {data}"
            )

    async def shutdown(self):
        """关闭适配器，断开所有账户连接"""
        self._running = False

        # 取消连接任务
        for task in self._connect_tasks.values():
            if not task.done():
                task.cancel()
        if self._connect_tasks:
            await asyncio.gather(
                *self._connect_tasks.values(), return_exceptions=True
            )
        self._connect_tasks.clear()

        # 关闭每个账户的资源
        for account_name, rt in self._account_runtime.items():
            # 取消心跳/接收任务
            for key in ("heartbeat_task", "receive_task"):
                t = rt.get(key)
                if t and not t.done():
                    t.cancel()
            try:
                if rt.get("heartbeat_task"):
                    await rt["heartbeat_task"]
            except (asyncio.CancelledError, Exception):
                pass

            ws = rt.get("websocket")
            if ws and not ws.closed:
                try:
                    await ws.close()
                except Exception as e:
                    self.logger.error(
                        f"[{account_name}] 关闭连接失败: {e}"
                    )

        # 对每个账户发送 disconnect meta
        for account_name, account in self.enabled_accounts.items():
            rt = self._get_runtime(account_name)
            bot_id = rt.get("bot_id") or account.bot_id or ""
            try:
                await self.emit_meta("disconnect", bot_id)
            except Exception:
                pass

        self.logger.info("Kook适配器已关闭")

    async def call_api(self, endpoint: str, _account_id: str = None, **params):
        """调用平台 API

        根据 endpoint 和 target_type 映射到具体的 API 方法：
        - /message/create + target_type=group -> send_message (频道消息)
        - /message/create + target_type=user -> send_direct_message (私信消息)
        - /message/update + target_type=user -> update_direct_message (更新私信消息)
        - /message/delete + target_type=user -> delete_direct_message (删除私信消息)
        - /asset/create -> upload_file
        """
        account_name, account = self._resolve_account(_account_id)
        rt = self._get_runtime(account_name)
        api = rt.get("api")
        if api is None:
            raise RuntimeError(f"账户 {account_name} 的 API 实例未初始化")

        target_type = params.get("target_type", "group")

        # 移除内部使用的 target_type 参数，避免传递给 API
        api_params = {k: v for k, v in params.items() if k != "target_type"}

        if endpoint == "/message/create":
            if target_type in ("private", "user"):
                return await api.send_direct_message(**api_params)
            else:
                return await api.send_message(**api_params)
        elif endpoint == "/message/update":
            if target_type in ("private", "user"):
                return await api.update_direct_message(**api_params)
            else:
                return await api.update_channel_message(**api_params)
        elif endpoint == "/message/delete":
            if target_type in ("private", "user"):
                return await api.delete_direct_message(**api_params)
            else:
                return await api.delete_channel_message(**api_params)
        elif endpoint == "/asset/create":
            return await api.upload_asset(**params)
        else:
            raise ValueError(f"未知的 API endpoint: {endpoint}")

    # ------------------------------------------------------------------
    # Send 类
    # ------------------------------------------------------------------
    class Send(BaseAdapter.Send):
        _KOOK_MSG_TYPE_MAP = {
            "text": 1,
            "image": 2,
            "video": 3,
            "file": 4,
            "audio": 8,
            "record": 8,
            "markdown": 9,
            "kook_card": 10,
        }

        def _build_modifiers(self) -> dict:
            modifiers = {}
            if self._at_all:
                modifiers["mention_all"] = True
            if self._at_user_ids:
                modifiers["mention"] = self._at_user_ids
            if self._reply_message_id:
                modifiers["quote"] = self._reply_message_id
            return modifiers

        def _error_response(self, message: str, retcode: int = -1) -> dict:
            err = self._adapter.make_error(
                retcode=retcode,
                message=message,
                raw=None,
            )
            err["kook_raw"] = None
            return err

        def Text(self, text: str):
            return self.Raw_ob12([{"type": "text", "data": {"text": text}}])

        def Image(self, file):
            return self.Raw_ob12([{"type": "image", "data": {"file": file}}])

        def Video(self, file):
            return self.Raw_ob12([{"type": "video", "data": {"file": file}}])

        def File(self, file, filename=None):
            return self.Raw_ob12(
                [{"type": "file", "data": {"file": file, "filename": filename}}]
            )

        def Voice(self, file):
            return self.Raw_ob12([{"type": "audio", "data": {"file": file}}])

        def Markdown(self, text: str):
            return self.Raw_ob12([{"type": "markdown", "data": {"markdown": text}}])

        def Card(self, card_data: dict):
            return self.Raw_ob12([{"type": "kook_card", "data": {"card": card_data}}])

        async def _upload_file(self, file, filename=None):
            if isinstance(file, bytes):
                upload_result = await self._adapter.call_api(
                    endpoint="/asset/create",
                    _account_id=self.send_context.get("account_id"),
                    file=file,
                    file_path=filename,
                )
            elif isinstance(file, str):
                if file.startswith(("http://", "https://")):
                    upload_result = await self._adapter.call_api(
                        endpoint="/asset/create",
                        _account_id=self.send_context.get("account_id"),
                        file_url=file,
                        file_path=filename,
                    )
                else:
                    upload_result = await self._adapter.call_api(
                        endpoint="/asset/create",
                        _account_id=self.send_context.get("account_id"),
                        file_path=file,
                    )
            else:
                return None
            if upload_result["retcode"] != 0:
                return None
            return upload_result["data"]["url"]

        def Raw_ob12(self, message):
            import asyncio

            async def _send():
                if isinstance(message, dict):
                    segments = [message]
                else:
                    segments = message

                modifiers = self._build_modifiers()
                results = []

                for segment in segments:
                    seg_type = segment.get("type")
                    seg_data = segment.get("data", {})

                    if seg_type == "mention":
                        modifiers.setdefault("mention", [])
                        if seg_data.get("user_id") not in modifiers["mention"]:
                            modifiers["mention"].append(seg_data["user_id"])
                        continue
                    elif seg_type == "mention_all":
                        modifiers["mention_all"] = True
                        continue
                    elif seg_type == "reply":
                        modifiers["quote"] = seg_data.get("message_id")
                        continue

                    kook_type = self._KOOK_MSG_TYPE_MAP.get(seg_type)
                    if kook_type is None:
                        self._adapter.logger.warning(f"不支持的消息段类型: {seg_type}")
                        continue

                    if seg_type in ("text", "markdown"):
                        content = seg_data.get("text") or seg_data.get("markdown", "")
                        if kook_type == 10:
                            content = json.dumps(seg_data.get("card", {}))
                    elif seg_type == "kook_card":
                        content = json.dumps(seg_data.get("card", {}))
                        kook_type = 10
                    elif seg_type in ("image", "video", "file", "audio", "record"):
                        file_source = seg_data.get("file") or seg_data.get("url", "")
                        filename = seg_data.get("filename")
                        url = await self._upload_file(file_source, filename)
                        if url is None:
                            results.append(
                                self._error_response(f"文件上传失败: {seg_type}")
                            )
                            continue
                        content = url
                    else:
                        content = str(seg_data)

                    result = await self._adapter.call_api(
                        endpoint="/message/create",
                        _account_id=self.send_context.get("account_id"),
                        target_type=self._target_type,
                        target_id=self._target_id,
                        content=content,
                        type=kook_type,
                        **modifiers,
                    )
                    results.append(result)

                return (
                    results[-1]
                    if results
                    else self._error_response("没有可发送的消息段")
                )

            return asyncio.create_task(_send())

        def Edit(self, msg_id: str, content: str):
            """编辑消息（仅支持 KMarkdown 和 CardMessage）"""
            import asyncio

            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="/message/update",
                    _account_id=self.send_context.get("account_id"),
                    target_type=self._target_type,
                    msg_id=msg_id,
                    content=content,
                )
            )

        def Recall(self, msg_id: str):
            """撤回消息"""
            import asyncio

            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="/message/delete",
                    _account_id=self.send_context.get("account_id"),
                    target_type=self._target_type,
                    msg_id=msg_id,
                )
            )

        def Upload(self, file_path: str):
            """上传本地文件

            Args:
                file_path: 本地文件路径

            Returns:
                上传结果，包含文件的 URL
            """
            import asyncio

            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="/asset/create",
                    _account_id=self.send_context.get("account_id"),
                    file_path=file_path,
                )
            )
