"""The Python examples of the documentation run as they are written, the README, which is also
the long description on PyPI, points at files that exist, and the documents of hh-cpp are
linked at the release the vectors came from."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from typing import Any, Dict, List

import humanized_hash

from .support import read_bytes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def document(*path: str) -> str:
    """The text of a Markdown or TOML file of the repository."""
    name = os.path.join(ROOT, *path)
    if not os.path.isfile(name):
        raise unittest.SkipTest("the installed package has no documentation beside it")
    with open(name, encoding="utf-8") as file:
        return file.read()


def python_blocks(*path: str) -> List[str]:
    """The ``python`` code blocks of a Markdown file."""
    return re.findall(r"^```python\n(.*?)^```$", document(*path), re.MULTILINE | re.DOTALL)


def section(text: str, heading: str) -> str:
    """The text of one ``##`` section of a Markdown document."""
    found = re.search(r"^## " + re.escape(heading) + r"\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if found is None:
        raise AssertionError("the document has no section " + heading)
    return found.group(1)


def blocks_of(text: str) -> List[str]:
    """The ``python`` code blocks of a piece of Markdown."""
    return re.findall(r"^```python\n(.*?)^```$", text, re.MULTILINE | re.DOTALL)


class DocumentationTest(unittest.TestCase):
    def test_the_quick_start_of_the_readme(self) -> None:
        names: Dict[str, Any] = {"key_bytes": bytes(range(32))}
        blocks = blocks_of(section(document("README.md"), "Quick start"))
        self.assertEqual(2, len(blocks))
        for block in blocks:
            exec(compile(block, "README.md", "exec"), names)
        self.assertEqual("TKSPVH", names["tag"])
        self.assertTrue(names["png"].startswith(b"\x89PNG"))
        self.assertIs(humanized_hash.Mode.KEYED, names["private"].mode)
        self.assertTrue(names["key"].closed)

    def test_the_looks_of_the_readme(self) -> None:
        names: Dict[str, Any] = {name: getattr(humanized_hash, name) for name in humanized_hash.__all__}
        blocks = blocks_of(section(document("README.md"), "Looks"))
        self.assertEqual(1, len(blocks))
        exec(compile(blocks[0], "README.md", "exec"), names)
        options = names["options"]
        self.assertEqual((humanized_hash.Shape.ROUND, humanized_hash.FrameStyle.TICKS),
                         (options.shape, options.frame))
        self.assertEqual(0, options.background_alpha)
        # Transparent over a white page is what the white column of the table shows.
        self.assertEqual(300, names["report"].figures_x100)
        self.assertEqual(257, humanized_hash.RenderOptions(background=0xE8EEF7).measure_contrast().figures_x100)
        # Any style of the shape, in either mode: the same pixels for the same bytes.
        pictures = [
            humanized_hash.Fingerprint.from_bytes(bytes(range(32)), mode).render(64, options)
            for mode in humanized_hash.Mode
        ]
        self.assertEqual(pictures[0], pictures[1])

    def test_the_complete_program_of_the_readme(self) -> None:
        # The section is a whole program: it runs as main.py in a directory of its own.
        program = blocks_of(section(document("README.md"), "A complete program"))[0]
        environment = dict(os.environ)
        package_parent = os.path.dirname(os.path.dirname(os.path.abspath(humanized_hash.__file__)))
        environment["PYTHONPATH"] = package_parent
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "main.py"), "w", encoding="utf-8") as file:
                file.write(program)
            done = subprocess.run(
                [sys.executable, "-W", "error", "main.py"],
                cwd=directory,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual((0, b""), (done.returncode, done.stderr))
            self.assertEqual("TKS-PVH", done.stdout.decode("ascii").strip())
            with open(os.path.join(directory, "address.png"), "rb") as file:
                picture = file.read()
        self.assertEqual(read_bytes("golden", "evm-1-universal-128.png"), picture)

    def test_the_recipes_of_the_integration_guide(self) -> None:
        names: Dict[str, Any] = {
            "address": "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",
            "size": 64,
            "options": humanized_hash.RenderOptions(),
            "key_bytes": bytes(range(32)),
        }
        ran = 0
        with humanized_hash.SecretKey(bytes(range(32))) as names["key"]:
            for block in python_blocks("docs", "INTEGRATION.md"):
                # The recipes for servers and toolkits need what the tests do not have.
                if re.search(r"wsgiref|tkinter|QImage|hmac_from_elsewhere", block):
                    continue
                exec(compile(block, "INTEGRATION.md", "exec"), names)
                ran += 1
        self.assertEqual(4, ran)
        self.assertEqual(names["public_png"](names["address"].lower(), 32)[:4], b"\x89PNG")
        self.assertEqual(4, len(names["stored_check_value"]))
        self.assertLess(names["report"].figures_x100, 400)
        # The look of section 5 renders in either mode.
        options = names["options"]
        self.assertIs(humanized_hash.FrameStyle.DOUBLE, options.frame)
        universal = humanized_hash.Fingerprint.universal(names["digest"])
        for fingerprint in (universal, names["fingerprint"]):
            self.assertEqual(64, fingerprint.render(64, options).width)

    def test_the_readme_links_to_files_of_this_repository(self) -> None:
        # PyPI shows the README outside the repository: a relative link or image leads nowhere
        # there, so everything is absolute and names the default branch, which always has the
        # files the current README talks about.
        text = document("README.md")
        targets = re.findall(r"\]\(([^)\s]+)\)", text)
        pages = "https://github.com/censync/hh-python/blob/main/"
        images = "https://raw.githubusercontent.com/censync/hh-python/main/"
        found = {"pages": 0, "images": 0}
        for target in targets:
            self.assertRegex(target, r"^https://[a-z]", "a relative link: " + target)
            if "/censync/hh-python" not in target:
                continue
            kind = "images" if target.startswith(images) else "pages"
            self.assertTrue(target.startswith((pages, images)), target)
            path = target[len(images if kind == "images" else pages) :]
            self.assertTrue(os.path.isfile(os.path.join(ROOT, *path.split("/"))), target)
            found[kind] += 1
        self.assertEqual({"pages": 5, "images": 13}, found)
        for image in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
            self.assertTrue(image.startswith(images), image)
        self.assertNotRegex(text, r"(?i)<img|<a\s|\]:\s")

    def test_documents_of_hh_cpp_are_linked_at_the_release_of_the_vectors(self) -> None:
        # The specification and the guides of hh-cpp are linked at the tag that testdata/SOURCE
        # names: they describe the rules that the copied vectors test.
        source = read_bytes("SOURCE").decode("utf-8")
        tag = re.search(r"^tag: (v\d+\.\d+\.\d+)$", source, re.MULTILINE)
        self.assertIsNotNone(tag)
        for path in (("README.md",), ("docs", "INTEGRATION.md"), ("pyproject.toml",)):
            text = document(*path)
            pinned = re.findall(r"https://github\.com/censync/hh-cpp/(?:blob|tree)/([^/]+)/", text)
            self.assertTrue(pinned, path)
            self.assertEqual({tag.group(1) if tag else ""}, set(pinned), path)


if __name__ == "__main__":
    unittest.main()
