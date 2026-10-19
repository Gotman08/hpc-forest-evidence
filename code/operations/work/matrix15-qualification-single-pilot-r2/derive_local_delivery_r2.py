"""Keep r1 receipts untouched; reuse local sealing/delivery logic for the r2 pins."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT.parents[1]
PREVIOUS = CURRENT / "work/matrix15-qualification-single-pilot-r1"

seal = (PREVIOUS / "seal_q15.py").read_text(encoding="utf8")
seal = seal.replace("HPC-Forest-Q15-Pilote-Unique-r1", "HPC-Forest-Q15-Pilote-Unique-r2")
seal = seal.replace("work/matrix15-single-pilot-r1/project", "work/matrix15-admission-no-cycle-r2/project")
seal = re.sub(r"\b(353|127|126)\b", lambda m: {"353": "354", "127": "128", "126": "127"}[m[0]], seal)
seal = seal.replace('ROOT / "TESTS-Q15-NEUTRES-r1.xml"', 'ROOT / "TESTS-Q15-BOOTSTRAP-NEUTRES-r2.xml"')
seal = seal.replace('remote_root = "/scratch_p/nimarano/hpc-forest-q15-single-pilot-20261019-r1-" + receipt["archive"]["sha256"][:12]',
                    'remote_root = "/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01"')
seal = seal.replace('"/scratch_p/nimarano/HPC-Forest-Q15-single-pilot-" + receipt["archive"]["sha256"][:12] + ".tar.gz"',
                    'remote_root + "-inputs/HPC-Forest-Q15-baseline-source-r1.tar.gz"')
with (ROOT / "seal_q15.py").open("x", encoding="utf8", newline="\n") as stream:
    stream.write(seal)

delivery = (PREVIOUS / "prepare_transfer.py").read_text(encoding="utf8")
delivery = delivery.replace("HPC-Forest-Q15-Pilote-Unique-r1", "HPC-Forest-Q15-Pilote-Unique-r2")
delivery = delivery.replace('"transfer-root-r1"', '"transfer-root-r2"')
delivery = delivery.replace("SCRIPT-LINUX-ROOT-r1.sh", "SCRIPT-LINUX-ROOT-r2.sh")
delivery = delivery.replace("JOB-PREPARE-ARGS-ROOT-r1.json", "JOB-PREPARE-ARGS-ROOT-r2.json")
delivery = delivery.replace("36c95aa92150239e126c95de05b596c445e20dc59d3bb68d3554ef09a7d46ad0",
                            "7e6b90fe3f50190b42eb3cd02f902802e4d87deb83d3080329fe248e46fe6c49")
delivery = delivery.replace("dc43083bb65d49fd477a7edcb56d675d77b7cdc9f4dfde04611e9715962baa45",
                            "e3b5a34c6ab7799e237d69cbb1205ec71a543a232361cc354d30dc68e795aafe")
delivery = delivery.replace("TESTS-BOOTSTRAP-r1.xml", "TESTS-Q15-BOOTSTRAP-NEUTRES-r2.xml")
delivery = delivery.replace('suite.attrib["tests"] == "29"', 'suite.attrib["tests"] == "68"')
with (ROOT / "prepare_transfer.py").open("x", encoding="utf8", newline="\n") as stream:
    stream.write(delivery)
