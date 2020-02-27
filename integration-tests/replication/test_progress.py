# -*- coding=utf-8 -*-
import subprocess
import textwrap
from unittest.mock import Mock

import pytest
import yaml

from zettarepl.definition.definition import Definition
from zettarepl.replication.task.task import ReplicationTask
from zettarepl.observer import (ReplicationTaskStart, ReplicationTaskSnapshotStart, ReplicationTaskSnapshotProgress,
                                ReplicationTaskSnapshotSuccess, ReplicationTaskSuccess)
from zettarepl.utils.itertools import select_by_class
from zettarepl.utils.test import transports, create_zettarepl, wait_replication_tasks_to_complete


@pytest.mark.parametrize("transport", transports())
def test_push_replication(transport):
    subprocess.call("zfs destroy -r data/src", shell=True)
    subprocess.call("zfs destroy -r data/dst", shell=True)

    subprocess.check_call("zfs create data/src", shell=True)

    subprocess.check_call("zfs create data/src/src1", shell=True)
    subprocess.check_call("zfs snapshot data/src/src1@2018-10-01_01-00", shell=True)
    subprocess.check_call("dd if=/dev/urandom of=/mnt/data/src/src1/blob bs=1M count=1", shell=True)
    subprocess.check_call("zfs snapshot data/src/src1@2018-10-01_02-00", shell=True)
    subprocess.check_call("rm /mnt/data/src/src1/blob", shell=True)
    subprocess.check_call("zfs snapshot data/src/src1@2018-10-01_03-00", shell=True)

    subprocess.check_call("zfs create data/src/src2", shell=True)
    subprocess.check_call("zfs snapshot data/src/src2@2018-10-01_01-00", shell=True)
    subprocess.check_call("zfs snapshot data/src/src2@2018-10-01_02-00", shell=True)
    subprocess.check_call("zfs snapshot data/src/src2@2018-10-01_03-00", shell=True)
    subprocess.check_call("zfs snapshot data/src/src2@2018-10-01_04-00", shell=True)

    definition = yaml.safe_load(textwrap.dedent("""\
        timezone: "UTC"

        replication-tasks:
          src:
            direction: push
            source-dataset:
            - data/src/src1
            - data/src/src2
            target-dataset: data/dst
            recursive: true
            also-include-naming-schema:
            - "%Y-%m-%d_%H-%M"
            auto: false
            retention-policy: none
            retries: 1
    """))
    definition["replication-tasks"]["src"]["transport"] = transport
    if transport["type"] == "ssh":
        definition["replication-tasks"]["src"]["speed-limit"] = 10240 * 9

    definition = Definition.from_data(definition)
    zettarepl = create_zettarepl(definition)
    zettarepl._spawn_replication_tasks(select_by_class(ReplicationTask, definition.tasks))
    wait_replication_tasks_to_complete(zettarepl)

    result = [
        ReplicationTaskStart("src"),
        ReplicationTaskSnapshotStart("src",     "data/src/src1", "2018-10-01_01-00", 0, 3),
        ReplicationTaskSnapshotSuccess("src",   "data/src/src1", "2018-10-01_01-00", 1, 3),
        ReplicationTaskSnapshotStart("src",     "data/src/src1", "2018-10-01_02-00", 1, 3),
        ReplicationTaskSnapshotSuccess("src",   "data/src/src1", "2018-10-01_02-00", 2, 3),
        ReplicationTaskSnapshotStart("src",     "data/src/src1", "2018-10-01_03-00", 2, 3),
        ReplicationTaskSnapshotSuccess("src",   "data/src/src1", "2018-10-01_03-00", 3, 3),
        ReplicationTaskSnapshotStart("src",     "data/src/src2", "2018-10-01_01-00", 3, 7),
        ReplicationTaskSnapshotSuccess("src",   "data/src/src2", "2018-10-01_01-00", 4, 7),
        ReplicationTaskSnapshotStart("src",     "data/src/src2", "2018-10-01_02-00", 4, 7),
        ReplicationTaskSnapshotSuccess("src",   "data/src/src2", "2018-10-01_02-00", 5, 7),
        ReplicationTaskSnapshotStart("src",     "data/src/src2", "2018-10-01_03-00", 5, 7),
        ReplicationTaskSnapshotSuccess("src",   "data/src/src2", "2018-10-01_03-00", 6, 7),
        ReplicationTaskSnapshotStart("src",     "data/src/src2", "2018-10-01_04-00", 6, 7),
        ReplicationTaskSnapshotSuccess("src",   "data/src/src2", "2018-10-01_04-00", 7, 7),
        ReplicationTaskSuccess("src"),
    ]
    if transport["type"] == "ssh":
        result.insert(4, ReplicationTaskSnapshotProgress("src", "data/src/src1", "2018-10-01_02-00", 1, 3,
                                                         10240 * 9 * 10,    # We poll for progress every 10 seconds so
                                                                            # we would have transfered 10x speed limit
                                                         2162784            # Empirical value
        ))

    for i, message in enumerate(result):
        call = zettarepl.observer.call_args_list[i]

        assert call[0][0].__class__ == message.__class__

        d1 = call[0][0].__dict__
        d2 = message.__dict__

        if isinstance(message, ReplicationTaskSnapshotProgress):
            bytes_sent_1 = d1.pop("bytes_sent")
            bytes_total_1 = d1.pop("bytes_total")
            bytes_sent_2 = d2.pop("bytes_sent")
            bytes_total_2 = d2.pop("bytes_total")

            assert 0.8 <= bytes_sent_1 / bytes_sent_2 <= 1.2
            assert 0.8 <= bytes_total_1 / bytes_total_2 <= 1.2

        assert d1 == d2