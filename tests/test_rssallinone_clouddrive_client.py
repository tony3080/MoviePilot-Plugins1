"""CloudDrive2 client pagination and exact cloud-file lookup."""

import importlib.util
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "plugins.v2" / "rssallinone" / "clouddrive_client.py"
SPEC = importlib.util.spec_from_file_location("rssallinone_cd2_client_test", MODULE_PATH)
client_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = client_module
SPEC.loader.exec_module(client_module)


class Request:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class UploadStatus:
    @staticmethod
    def Name(value):
        return {5: "Finish"}.get(value, str(value))


class FakePb2:
    GetUploadFileListRequest = Request
    ListSubFileRequest = Request
    FindFileByPathRequest = Request
    UploadFileInfo = types.SimpleNamespace(Status=UploadStatus)
    google_dot_protobuf_dot_empty__pb2 = types.SimpleNamespace(Empty=Request)


class FakeChannel:
    def __init__(self, stub):
        self.stub = stub

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeGrpc:
    StatusCode = types.SimpleNamespace(NOT_FOUND="not-found")

    def __init__(self, stub):
        self.stub = stub

    def insecure_channel(self, _address):
        return FakeChannel(self.stub)


class FakePb2Grpc:
    @staticmethod
    def CloudDriveFileSrvStub(channel):
        return channel.stub


class RuntimeClient(client_module.CloudDriveClient):
    def __init__(self, stub):
        super().__init__("cd2:19798", "token")
        self.fake_grpc = FakeGrpc(stub)

    def _runtime(self):
        return self.fake_grpc, FakePb2, FakePb2Grpc


def upload_row(index):
    return types.SimpleNamespace(
        key=f"key-{index}",
        destPath=f"/cloud/{index}.mkv",
        size=1024,
        transferedBytes=0,
        status="Finish",
        statusEnum=5,
        errorMessage="",
        operatorType=2,
    )


class CloudDriveClientTest(unittest.TestCase):
    def test_mounted_destination_root_is_resolved_to_cd2_api_root(self):
        class Stub:
            def GetAllCloudApis(self, _request, **_kwargs):
                return types.SimpleNamespace(apis=[
                    types.SimpleNamespace(path="/115"),
                    types.SimpleNamespace(path="/116"),
                ])

        resolved = RuntimeClient(Stub()).resolve_destination_root(
            "/SSD/CloudDrive/115/MediaLibrary"
        )

        self.assertEqual(resolved, "/115/MediaLibrary")

    def test_upload_list_reads_all_pages(self):
        class Stub:
            def __init__(self):
                self.pages = []

            def GetUploadFileList(self, request, **_kwargs):
                self.pages.append(request.pageNumber)
                start = (request.pageNumber - 1) * 500
                count = 500 if request.pageNumber == 1 else 1
                return types.SimpleNamespace(
                    uploadFiles=[upload_row(index) for index in range(start, start + count)],
                    totalCount=501,
                    totalCountFiltered=501,
                )

        stub = Stub()
        rows = RuntimeClient(stub).list_uploads()

        self.assertEqual(len(rows), 501)
        self.assertEqual(stub.pages, [1, 2])
        self.assertEqual(rows[-1]["key"], "key-500")

    def test_force_refresh_file_lookup_uses_exact_parent_listing(self):
        stamp = types.SimpleNamespace(
            ToDatetime=lambda tzinfo=None: datetime(2026, 8, 8, tzinfo=timezone.utc)
        )
        wrong = types.SimpleNamespace(
            id="wrong",
            name="Other.mkv",
            fullPathName="/cloud/Movie/Other.mkv",
            size=10,
            isDirectory=False,
            createTime=stamp,
            writeTime=stamp,
        )
        expected = types.SimpleNamespace(
            id="expected",
            name="Movie.mkv",
            fullPathName="/cloud/Movie/Movie.mkv",
            size=1024,
            isDirectory=False,
            createTime=stamp,
            writeTime=stamp,
        )

        class Stub:
            def __init__(self):
                self.request = None

            def GetSubFiles(self, request, **_kwargs):
                self.request = request
                return [types.SimpleNamespace(subFiles=[wrong, expected])]

        stub = Stub()
        result = RuntimeClient(stub).find_file(
            "/cloud/Movie/Movie.mkv", force_refresh=True
        )

        self.assertEqual(stub.request.path, "/cloud/Movie")
        self.assertTrue(stub.request.forceRefresh)
        self.assertEqual(result["id"], "expected")
        self.assertEqual(result["size"], 1024)
        self.assertEqual(result["full_path"], "/cloud/Movie/Movie.mkv")

    def test_force_refresh_groups_files_by_parent_directory(self):
        rows = [
            types.SimpleNamespace(
                id=f"episode-{index}",
                name=f"E{index:02d}.mkv",
                fullPathName=f"/cloud/Show/E{index:02d}.mkv",
                size=index,
                isDirectory=False,
                createTime=None,
                writeTime=None,
            )
            for index in range(1, 4)
        ]

        class Stub:
            def __init__(self):
                self.calls = 0

            def GetSubFiles(self, _request, **_kwargs):
                self.calls += 1
                return [types.SimpleNamespace(subFiles=rows)]

        stub = Stub()
        result = RuntimeClient(stub).find_files(
            [f"/cloud/Show/E{index:02d}.mkv" for index in range(1, 4)],
            force_refresh=True,
        )

        self.assertEqual(stub.calls, 1)
        self.assertEqual(len([row for row in result.values() if row]), 3)


if __name__ == "__main__":
    unittest.main()
