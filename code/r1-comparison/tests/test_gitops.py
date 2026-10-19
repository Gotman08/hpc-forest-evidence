import os
import shutil
from importlib.resources import files
from pathlib import Path

from hpc_forest.controller import create_workspace
from hpc_forest.gitops import ensure_clean, git


def test_imported_non_executable_runner_is_clean_and_executable(tmp_path, config, need_compiler):
    source = tmp_path / "import"
    shutil.copytree(Path(str(files("hpc_forest") / "assets" / "matmul")), source)
    (source / "run.sh").chmod(0o644)
    root = create_workspace(tmp_path / "campaign", config, source=source)
    ensure_clean(root / "repo", git(root / "repo", "rev-parse", "HEAD"))
    assert git(root / "repo", "ls-files", "--stage", "run.sh").startswith("100755 ")
    if os.name == "posix":
        assert (root / "repo" / "run.sh").stat().st_mode & 0o100
