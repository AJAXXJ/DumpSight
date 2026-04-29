from datetime import timedelta
import threading
from minio import Minio
from minio.error import S3Error
import os
import io


class MinioUtil:
    def __init__(self, config):
        cfg = config["MINIO"]
        self.endpoint = f"http://{cfg['HOST']}"
        self.bucket = cfg["BUCKET_NAME"]
        self.client = Minio(
            cfg["HOST"],
            access_key=cfg["ACCESS_KEY"],
            secret_key=cfg["SECRET_KEY"],
            secure=False,
        )

        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except S3Error as e:
            raise RuntimeError(f"Bucket init failed: {e}")

    def upload_file(self, object_name, file_path, content_type=None):
        """
        上传本地文件到 MinIO
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"{file_path} not found")

        self.client.fput_object(
            bucket_name=self.bucket,
            object_name=object_name,
            file_path=file_path,
            content_type=content_type,
        )

        return f"uploaded: {object_name}"

    def upload_bytes(
        self,
        object_name,
        data,
        content_type="application/octet-stream",
    ):
        """
        上传内存 bytes 数据
        """
        stream = io.BytesIO(data)

        self.client.put_object(
            bucket_name=self.bucket,
            object_name=object_name,
            data=stream,
            length=len(data),
            content_type=content_type,
        )

        return f"uploaded: {object_name}"

    def download_file(self, object_name, file_path):
        """
        下载 MinIO 文件到本地
        """
        self.client.fget_object(
            bucket_name=self.bucket, object_name=object_name, file_path=file_path
        )

        return f"downloaded: {object_name}"

    def get_file_bytes(self, object_name):
        """
        读取 MinIO 文件内容（内存）
        """
        response = self.client.get_object(self.bucket, object_name)
        try:
            data = response.read()
            return data
        finally:
            response.close()
            response.release_conn()

    def stat_file(self, object_name):
        """
        获取文件 metadata
        """
        return self.client.stat_object(self.bucket, object_name)

    def delete_file(self, object_name):
        self.client.remove_object(self.bucket, object_name)
        return f"deleted: {object_name}"

    def get_presigned_url(self, object_name, expires=3600):
        """
        生成临时访问 URL
        """
        return self.client.presigned_get_object(
            self.bucket, object_name, expires=expires
        )

    def get_client(self):
        return self.client

    def get_upload_url(self, object_name, expires=3600):
        """
        获取上传签名
        """
        return self.client.presigned_put_object(
            self.bucket, object_name, expires=timedelta(seconds=3600)
        )


_minio_util: MinioUtil | None = None
_minio_lock = threading.Lock()


def init_minio_util(config):
    global _minio_util
    with _minio_lock:
        if _minio_util is None:
            _minio_util = MinioUtil(config)


def get_minio_util() -> MinioUtil:
    if _minio_util is None:
        raise RuntimeError("MinIO util not initialized")
    return _minio_util
