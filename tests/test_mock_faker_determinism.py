from collections.abc import Callable
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from scripts.generate_mock_excel import (
    generate_mock_excel,
    generate_mvp1_mock_excel,
    generate_mvp2a3_mock_excel,
)


Generator = Callable[[Path], tuple[Path, Path]]


def _assert_generator_writes_deterministic_files(
    tmp_path: Path,
    generator: Generator,
) -> None:
    first_paths = generator(tmp_path / "first")
    second_paths = generator(tmp_path / "second")

    for first_path, second_path in zip(first_paths, second_paths, strict=True):
        first_df = pd.read_excel(first_path)
        second_df = pd.read_excel(second_path)

        assert_frame_equal(first_df, second_df)


def test_generate_mock_excel_is_deterministic(tmp_path: Path) -> None:
    _assert_generator_writes_deterministic_files(tmp_path, generate_mock_excel)


def test_generate_mvp1_mock_excel_is_deterministic(tmp_path: Path) -> None:
    _assert_generator_writes_deterministic_files(tmp_path, generate_mvp1_mock_excel)


def test_generate_mvp2a3_mock_excel_is_deterministic(tmp_path: Path) -> None:
    _assert_generator_writes_deterministic_files(tmp_path, generate_mvp2a3_mock_excel)
