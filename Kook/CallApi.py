import os
import uuid
import mimetypes
from urllib.parse import urlparse, unquote

from ErisPulse.Core import client

try:
    import filetype
except ImportError:  # pragma: no cover
    filetype = None


# 常见媒体格式的魔数前缀
_MEDIA_MAGIC_PREFIXES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"OggS",
    b"fLaC",
    b"ID3",
    b"RIFF",
    b"%PDF",
    b"PK\x03\x04",
    b"\x1a\x45\xdf\xa3",
)


def _sniff_extension(data: bytes) -> str:
    """按魔数探测文件扩展名；未识别返回空串"""
    if filetype is not None:
        try:
            kind = filetype.guess(data)
        except Exception:
            kind = None
        if kind:
            return "." + kind.extension
    if any(data.startswith(prefix) for prefix in _MEDIA_MAGIC_PREFIXES):
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return ".gif"
        if data.startswith(b"OggS"):
            return ".ogg"
        if data.startswith(b"fLaC"):
            return ".flac"
        if data.startswith(b"ID3"):
            return ".mp3"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return ".webp"
        if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
            return ".wav"
        if data.startswith(b"%PDF"):
            return ".pdf"
        if data.startswith(b"PK\x03\x04"):
            return ".zip"
        if data.startswith(b"\x1a\x45\xdf\xa3"):
            return ".mkv"
    if len(data) > 12 and data[4:8] == b"ftyp":
        return ".mp4"
    if len(data) > 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0:
        return ".mp3"
    return ""


class CallApi:
    """Kook REST API 封装（基于 sdk.client）"""

    def __init__(self, adapter, token: str = ""):
        self.adapter = adapter
        self.token = token

    @property
    def logger(self):
        return self.adapter.logger

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
        }

    def _auth_headers(self) -> dict:
        """仅含 Authorization 的请求头（用于 multipart 上传）"""
        return {"Authorization": f"Bot {self.token}"}

    def _standardize(self, raw_response: dict, message_id: str = "") -> dict:
        """将 Kook API 响应标准化为 OneBot12 风格响应"""
        if not isinstance(raw_response, dict):
            return self.adapter.make_error(
                retcode=34100,
                message=f"API 返回了意外格式: {type(raw_response)}",
                raw=raw_response,
            )

        code = raw_response.get("code", 10002)
        msg = raw_response.get("message", "")

        if code == 0:
            raw_data = raw_response.get("data", {})
            kook_msg_id = message_id or raw_data.get("msg_id", "")
            standardized_data = dict(raw_data)
            if "message_id" not in standardized_data and "msg_id" in standardized_data:
                standardized_data["message_id"] = standardized_data["msg_id"]

            resp = self.adapter.make_response(
                status="ok",
                retcode=0,
                data=standardized_data,
                message_id=kook_msg_id,
                message=msg,
                raw=raw_response,
            )
            resp["kook_raw"] = raw_response
            return resp
        else:
            # 平台返回错误统一 34100，Kook 原始 code 保留在 kook_raw 中
            err = self.adapter.make_error(
                retcode=34100,
                message=msg or f"操作失败 (code={code})",
                raw=raw_response,
            )
            err["kook_raw"] = raw_response
            err["kook_code"] = code
            return err

    def _token_error(self) -> dict:
        err = self.adapter.make_error(
            retcode=10002,
            message="token未刷新, 请刷新后重试",
            raw=None,
        )
        err["kook_raw"] = None
        return err

    async def send_message(
        self,
        target_id: str,
        type: int,
        content: str,
        quote: str = None,
        template_id: str = None,
        **kwargs,
    ) -> dict:
        """发送频道消息"""
        if not self.token:
            return self._token_error()

        self.logger.debug(
            f"send_message: target_id={target_id}, type={type}, "
            f"content={content[:50] if content else 'None'}..."
        )

        nonce = str(uuid.uuid4())
        payload = {
            "nonce": nonce,
            "target_id": target_id,
            "type": type,
            "content": content,
        }
        if quote:
            payload["quote"] = quote
        if template_id:
            payload["template_id"] = template_id

        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        self.logger.debug(f"send_message payload: {payload}")

        resp = await client.post(
            "https://www.kookapp.cn/api/v3/message/create",
            json=payload,
            headers=self._headers(),
        )
        raw = await resp.json()
        message_id = raw.get("data", {}).get("msg_id", "")
        return self._standardize(raw, message_id)

    async def send_direct_message(
        self,
        target_id: str,
        type: int,
        content: str,
        quote: str = None,
        template_id: str = None,
        **kwargs,
    ) -> dict:
        """发送私信消息"""
        if not self.token:
            return self._token_error()

        nonce = str(uuid.uuid4())
        payload = {
            "nonce": nonce,
            "target_id": target_id,
            "type": type,
            "content": content,
        }
        if quote:
            payload["quote"] = quote
        if template_id:
            payload["template_id"] = template_id

        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        resp = await client.post(
            "https://www.kookapp.cn/api/v3/direct-message/create",
            json=payload,
            headers=self._headers(),
        )
        raw = await resp.json()
        message_id = raw.get("data", {}).get("msg_id", "")
        return self._standardize(raw, message_id)

    async def update_direct_message(
        self,
        msg_id: str,
        content: str,
        quote: str = None,
        template_id: str = None,
        **kwargs,
    ) -> dict:
        if not self.token:
            return self._token_error()

        payload = {
            "msg_id": msg_id,
            "content": content,
        }
        if quote is not None:
            payload["quote"] = quote
        if template_id:
            payload["template_id"] = template_id

        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        resp = await client.post(
            "https://www.kookapp.cn/api/v3/direct-message/update",
            json=payload,
            headers=self._headers(),
        )
        raw = await resp.json()
        return self._standardize(raw, message_id=msg_id)

    async def delete_direct_message(self, msg_id: str, **kwargs) -> dict:
        """删除私信消息"""
        if not self.token:
            return self._token_error()

        payload = {"msg_id": msg_id}

        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        resp = await client.post(
            "https://www.kookapp.cn/api/v3/direct-message/delete",
            json=payload,
            headers=self._headers(),
        )
        raw = await resp.json()
        return self._standardize(raw, message_id=msg_id)

    async def update_channel_message(
        self,
        msg_id: str,
        content: str,
        quote: str = None,
        temp_target_id: str = None,
        template_id: str = None,
        **kwargs,
    ) -> dict:
        """更新频道消息（仅支持 KMarkdown type=9 和 CardMessage type=10）"""
        if not self.token:
            return self._token_error()

        payload = {
            "msg_id": msg_id,
            "content": content,
        }
        if quote is not None:
            payload["quote"] = quote
        if temp_target_id:
            payload["temp_target_id"] = temp_target_id
        if template_id:
            payload["template_id"] = template_id

        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        resp = await client.post(
            "https://www.kookapp.cn/api/v3/message/update",
            json=payload,
            headers=self._headers(),
        )
        raw = await resp.json()
        return self._standardize(raw, message_id=msg_id)

    async def delete_channel_message(self, msg_id: str, **kwargs) -> dict:
        """删除频道消息"""
        if not self.token:
            return self._token_error()

        payload = {"msg_id": msg_id}

        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        resp = await client.post(
            "https://www.kookapp.cn/api/v3/message/delete",
            json=payload,
            headers=self._headers(),
        )
        raw = await resp.json()
        return self._standardize(raw, message_id=msg_id)

    async def upload_asset(self, file=None, file_path=None, file_url=None, filename=None) -> dict:
        if not self.token:
            return self._token_error()

        # 如果是 URL，先下载文件内容
        if file_url:
            self.logger.debug(f"从URL下载文件: {file_url}")
            try:
                resp = await client.get(file_url)
                if resp.status != 200:
                    err = self.adapter.make_error(
                        retcode=10002,
                        message=f"下载URL失败: HTTP {resp.status}",
                        raw=None,
                    )
                    err["kook_raw"] = None
                    return err
                file = await resp.read()
            except Exception as e:
                self.logger.error(f"下载URL失败: {e}")
                err = self.adapter.make_error(
                    retcode=10002,
                    message=f"下载URL失败: {e}",
                    raw=None,
                )
                err["kook_raw"] = None
                return err

        # 如果是本地文件路径，读取文件
        if file_path:
            if not os.path.exists(file_path):
                err = self.adapter.make_error(
                    retcode=10002,
                    message=f"文件不存在: {file_path}",
                    raw=None,
                )
                err["kook_raw"] = None
                return err
            try:
                with open(file_path, "rb") as f:
                    file = f.read()
            except Exception as e:
                err = self.adapter.make_error(
                    retcode=10002,
                    message=f"读取文件失败: {e}",
                    raw=None,
                )
                err["kook_raw"] = None
                return err

        # 如果是二进制数据，直接上传
        if file is None:
            err = self.adapter.make_error(
                retcode=10002,
                message="缺少文件数据",
                raw=None,
            )
            err["kook_raw"] = None
            return err

        try:
            from aiohttp import FormData

            upload_filename = self._get_filename(file_path, file_url, filename, file)
            self.logger.debug(
                f"上传文件到Kook服务器: {upload_filename}, 文件大小: {len(file)} bytes"
            )

            content_type, _ = mimetypes.guess_type(upload_filename)
            file_type = self._get_file_type(upload_filename)
            self.logger.debug(
                f"文件名: {upload_filename}, Content-Type: {content_type}, file_type: {file_type}"
            )

            form = FormData()
            form.add_field("file", file, filename=upload_filename, content_type=content_type)
            form.add_field("file_type", file_type)

            resp = await client.post(
                "https://www.kookapp.cn/api/v3/asset/create",
                headers=self._auth_headers(),
                data=form,
            )
            self.logger.debug(f"上传响应状态码: {resp.status}")
            raw = await resp.json()
            self.logger.debug(f"上传响应数据: {raw}")
            result = self._standardize(raw)
            self.logger.debug(f"标准化上传结果: {result}")
            return result
        except Exception as e:
            self.logger.error(f"上传文件失败: {e}")
            err = self.adapter.make_error(
                retcode=10002,
                message=f"上传文件失败: {e}",
                raw=None,
            )
            err["kook_raw"] = None
            return err

    def _get_file_type(self, filename):
        """根据文件名推断Kook API的file_type参数"""
        if not filename:
            return "file"

        filename_lower = filename.lower()
        if filename_lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")):
            return "image"
        elif filename_lower.endswith(
            (".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv")
        ):
            return "video"
        elif filename_lower.endswith((".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac")):
            return "audio"
        else:
            return "file"

    def _get_filename(self, file_path=None, file_url=None, filename=None, file_bytes=None) -> str:
        """确定上传文件名：显式 filename > 路径 basename > URL basename > bytes 魔数探测扩展名 > upload.bin"""
        if filename:
            return filename
        if file_path:
            return os.path.basename(file_path)
        if file_url:
            parsed = urlparse(file_url)
            name = unquote(os.path.basename(parsed.path))
            if name:
                return name
        if file_bytes:
            ext = _sniff_extension(file_bytes)
            if ext:
                return "upload" + ext
        return "upload.bin"

    async def get_ws_gateway(self, need_compress: bool = True) -> str:
        if not self.token:
            return ""
        resp = await client.post(
            "https://www.kookapp.cn/api/v3/gateway/index",
            headers=self._headers(),
            json={"need_compress": 1 if need_compress else 0},
        )
        raw = await resp.json()
        if raw.get("code") == 0:
            return raw.get("data", {}).get("url", "")
        return ""

    async def request(self, method: str, path: str, params: dict = None) -> dict:
        """通用 Kook v3 REST 请求（Api DSL 使用）

        :param method: HTTP 方法（GET 时 params 作为 query）
        :param path: API 路径（如 "/users/@me"）
        :param params: 请求参数
        """
        if not self.token:
            return self._token_error()
        url = f"https://www.kookapp.cn/api/v3{path}"
        try:
            if method.upper() == "GET":
                resp = await client.get(url, params=params or {}, headers=self._headers())
            else:
                resp = await client.post(url, json=params or {}, headers=self._headers())
            raw = await resp.json()
            return self._standardize(raw)
        except Exception as e:
            return self.adapter.make_error(retcode=33001, message=f"Kook API 请求异常: {e}", raw=None)