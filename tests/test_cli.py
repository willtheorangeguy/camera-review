from pathlib import Path

from camreview.cli import main


def test_no_recordings_exit_code(tmp_path: Path) -> None:
    assert main(["inspect", str(tmp_path)]) == 2


def test_conflicting_time_exit_code(tmp_path: Path) -> None:
    (tmp_path / "cam_2026-08-12_03-33-00.mkv").touch()
    assert (
        main(
            [
                "scan",
                str(tmp_path),
                "--time",
                "all",
                "--from",
                "03:00",
                "--to",
                "04:00",
            ]
        )
        == 4
    )
