import unittest
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st

from core.utils import load_files


class FakeUploadedFile:
    def __init__(self, text: str, name: str):
        self._text = text
        self.name = name
        self._pos = 0

    def read(self):
        data = self._text[self._pos:]
        self._pos = len(self._text)
        return data

    def seek(self, pos: int):
        self._pos = pos


class LoadFilesTests(unittest.TestCase):
    def test_load_files_populates_session_state(self):
        fake_state = SimpleNamespace(dfs={})
        original_session_state = st.session_state
        st.session_state = fake_state
        try:
            csv_text = "region,sales\nNorth,10\n"
            uploaded_file = FakeUploadedFile(csv_text, "sales.csv")

            load_files([uploaded_file])

            self.assertIn("sales", fake_state.dfs)
            self.assertEqual(fake_state.dfs["sales"].shape[0], 1)

            # A second load with the same object should still work after rewinding.
            load_files([uploaded_file])
            self.assertEqual(fake_state.dfs["sales"].shape[0], 1)
        finally:
            st.session_state = original_session_state

    def test_load_files_rejects_empty_upload(self):
        fake_state = SimpleNamespace(dfs={})
        original_session_state = st.session_state
        st.session_state = fake_state
        try:
            uploaded_file = FakeUploadedFile("", "empty.csv")
            with self.assertRaises(ValueError):
                load_files([uploaded_file])
        finally:
            st.session_state = original_session_state


if __name__ == "__main__":
    unittest.main()
