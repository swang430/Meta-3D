import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from scripts.mpdb_conducted_project import ChooseClustering, build, hyperrt_executable


def sample(path, links, change=None):
    desc = {"records": {}, "meta": {"lauraycsPlatform": {
        "direction": "downlink", "angleCoordinateSystem": "GCS"}, "mode": "CIR", "numFrequency": 1}}
    ident = np.arange(links, dtype="<i4")
    n = links * 2
    data = {
        "LINK": dict(FRAME_ID=10 + 3 * (ident // 8), TX_ANT=(ident % 8) // 2,
                     RX_ANT=ident % 2, LINK_ID=ident, FREQUENCY=np.full(links, 2.5e9)),
        "CHANNEL": dict(LINK_ID=np.repeat(ident, 2), H=np.tile([1+2j, 2-1j], links),
                        DELAY=np.tile([1e-8, 2e-8], links), DOPPLER=np.tile([-2., 3.], links),
                        **{key: np.ones(n) for key in ("AOA", "AOD", "ZOA", "ZOD")}),
    }
    with zipfile.ZipFile(path, "w") as db:
        for name, columns in data.items():
            desc["records"][name] = {}
            for key, values in columns.items():
                dtype = {"i": "I32", "f": "F64", "c": "C128"}[values.dtype.kind]
                if key not in ("LINK_ID", "TX_ANT", "RX_ANT", "FRAME_ID"):
                    values = values.reshape(-1, 1)
                shards = []
                mid = len(values) // 2
                for start, end in ((0, mid), (mid, len(values))):
                    part = values[start:end]
                    header = json.dumps({"data": {"dtype": dtype, "shape": part.shape,
                                                  "data_offsets": [0, part.nbytes]}}).encode()
                    entry = f"{name}/{key}/{start}"
                    db.writestr(entry, len(header).to_bytes(8, "little") + header + part.tobytes())
                    shards.append({"rowStart": start, "rowEnd": end, "entry": entry})
                desc["records"][name][key] = {"rowCount": len(values), "shape": list(values.shape),
                                              "dtype": "torch." + str(values.dtype), "shards": shards}
        if change:
            change(desc)
        db.writestr("mpdb.json", json.dumps(desc))


class ConductedProjectTest(unittest.TestCase):
    def test_members_take_precedence_and_missing_members_require_choice(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
                "scripts.mpdb_conducted_project.hyperrt_executable",
                side_effect=AssertionError("不应启动 HyperRT")):
            root = Path(tmp)
            source = root / "source"
            sample(source, 8)
            with self.assertRaises(ChooseClustering):
                build(source, root / "out")
            labels = {f"L{i}": np.array([0, 1]) for i in range(8)}
            members = root / "members.npz"
            np.savez(members, source_sha256="wrong", **labels)
            with self.assertRaisesRegex(ValueError, "与本次输入不符"):
                build(source, root / "out", "hyperrt", members)
            np.savez(members, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), **labels)
            self.assertEqual(build(source, root / "out", "hyperrt", members)["clustering_method"], "supplied_members")
            self.assertEqual(build(source, root / "bins", "delay_bins")["clustering_method"], "delay_bins")

    def test_runtime_lookup_and_guidance(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PATH": tmp}, clear=True):
            with self.assertRaisesRegex(FileNotFoundError, "HYPERRT_PATH.*PATH"):
                hyperrt_executable()
            runtime = Path(tmp) / "HyperRT"
            runtime.touch(mode=0o755)
            self.assertEqual(hyperrt_executable(), runtime.resolve())
            os.environ["HYPERRT_PATH"] = str(runtime.with_name("missing"))
            with self.assertRaisesRegex(FileNotFoundError, "发行目录"):
                hyperrt_executable()

    def test_reject_wrong_channel_metadata(self):
        for group, key, value in (("lauraycsPlatform", "direction", "uplink"),
                                  ("lauraycsPlatform", "angleCoordinateSystem", "LCS"),
                                  (None, "numFrequency", 2), (None, "mode", "CFR")):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                def change(desc):
                    meta = desc["meta"]
                    (meta[group] if group else meta)[key] = value
                sample(root / "source", 8, change)
                with self.assertRaisesRegex(ValueError, "下行|全局角度"):
                    build(root / "source", root / "out")
                self.assertFalse((root / "out").exists())

    def test_reject_misaligned_shards(self):
        from scripts.imt_conducted_spectrum import column
        for target, key, value in ((1, "rowStart", 7), (1, "rowStart", 9),
                                   (1, "rowEnd", 15), (None, "shape", [16, 2]),
                                   (None, "rowCount", 15), (0, "entry", "CHANNEL/LINK_ID/0")):
            with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "source"
                def change(desc):
                    info = desc["records"]["CHANNEL"]["H"]
                    (info if target is None else info["shards"][target])[key] = value
                sample(path, 8, change)
                with zipfile.ZipFile(path) as db, self.assertRaises(ValueError):
                    column(db, json.loads(db.read("mpdb.json")), "CHANNEL", "H")

    def test_reject_duplicate_member_in_actual_zip(self):
        from scripts.imt_conducted_spectrum import column
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source"
            sample(path, 8)
            with zipfile.ZipFile(path, "a") as db, self.assertWarns(UserWarning):
                db.writestr("CHANNEL/H/0", db.read("CHANNEL/H/0"))
            with zipfile.ZipFile(path) as db, self.assertRaisesRegex(ValueError, "同名文件"):
                column(db, json.loads(db.read("mpdb.json")), "CHANNEL", "H")

    def test_reject_short_binary_shard(self):
        from scripts.imt_conducted_spectrum import column
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample(root / "valid", 8)
            with zipfile.ZipFile(root / "valid") as src, zipfile.ZipFile(root / "short", "w") as dst:
                for name in src.namelist():
                    data = src.read(name)
                    dst.writestr(name, data[:-16] if name == "CHANNEL/H/0" else data)
            with zipfile.ZipFile(root / "short") as db, self.assertRaisesRegex(ValueError, "CHANNEL.H"):
                column(db, json.loads(db.read("mpdb.json")), "CHANNEL", "H")

    def test_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                build(Path("missing"), Path(tmp))

    @unittest.skipUnless(os.environ.get("HYPERRT_PATH"), "需要配置 HyperRT 发行环境")
    def test_full_build_and_missing_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mpdb"
            sample(source, 15)
            with self.assertRaisesRegex(ValueError, "八条唯一链路"):
                build(source, root / "out")
            self.assertFalse((root / "out").exists())
            sample(source, 16)
            archive = root / "batch.zip"
            sample(archive, 8)
            with zipfile.ZipFile(archive, "a") as outer:
                outer.write(source, "R0B0S0D.mpdb")
            manifest = build(archive, root / "out", "hyperrt")
            self.assertEqual(manifest["source"]["mpdb"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(manifest["frames"], [10, 13])
            self.assertEqual(len(manifest["links"]), 8)
            docs = [json.loads((root / "out" / f"{name}.json").read_text())
                    for name in ("results", "evidence")]
            self.assertEqual(docs[0]["source"], docs[1]["source"])
            for row, evidence in zip(docs[0]["rows"], docs[1]["rows"], strict=True):
                for key in ("frame", "tx", "rx", "cluster"):
                    self.assertEqual(row[key], evidence[key])
                self.assertTrue(math.isclose(row["real"], evidence["sumReal"]))
                self.assertTrue(math.isclose(row["imag"], evidence["sumImag"]))
                self.assertLessEqual(evidence["minHz"], row["doppler"])
                self.assertLessEqual(row["doppler"], evidence["maxHz"])
            self.assertEqual(sum(e["count"] for e in docs[1]["rows"]), 32)
