# -*- coding=utf-8 -*-
import logging

logger = logging.getLogger(__name__)

__all__ = ["zfs_send", "zfs_recv"]


def zfs_send(source_dataset: str, snapshot: str, recursive: bool, incremental_base: str, receive_resume_token: str):
    send = ["zfs", "send"]

    if recursive:
        send.append("-R")

    if incremental_base is not None:
        send.extend(["-i", f"{source_dataset}@{incremental_base}"])

    if receive_resume_token is not None:
        send.extend(["-t", receive_resume_token])

    send.append(f"{source_dataset}@{snapshot}")

    return send


def zfs_recv(target_dataset):
    return ["zfs", "recv", "-s", "-F", target_dataset]
