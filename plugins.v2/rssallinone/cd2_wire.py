"""Adapters for the existing generated CloudDrive2 remote-upload protocol."""

from .generated import clouddrive_pb2 as pb
from .generated.clouddrive_pb2_grpc import CloudDriveFileSrvStub as Client


MESSAGES = {
    "Empty": pb.google_dot_protobuf_dot_empty__pb2.Empty,
    "ChannelRequest": pb.RemoteUploadChannelRequest,
    "StartRequest": pb.StartRemoteUploadRequest,
    "ListRequest": pb.ListSubFileRequest,
    "ReadUpload": pb.RemoteReadDataUpload,
    "HashProgress": pb.RemoteHashProgressUpload,
    "ControlRequest": pb.RemoteUploadControlRequest,
}
