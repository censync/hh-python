"""The rules of the library, checked on its source: integer arithmetic, the standard library
only, documentation on every public object."""

from __future__ import annotations

import ast
import inspect
import os
import re
import unittest
from typing import Iterator, Tuple

import humanized_hash

PACKAGE = os.path.dirname(os.path.abspath(humanized_hash.__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# What the library may import, all of it from the standard library. zlib is optional in
# CPython builds and must not be needed; random, time and the floating point modules have no
# place in a deterministic integer algorithm.
ALLOWED_IMPORTS = {
    "__future__", "argparse", "binascii", "dataclasses", "enum", "functools", "hashlib", "hmac",
    "itertools", "math", "operator", "os", "re", "struct", "sys", "types", "typing",
}


def modules() -> Iterator[Tuple[str, ast.Module]]:
    for name in sorted(os.listdir(PACKAGE)):
        if name.endswith(".py"):
            with open(os.path.join(PACKAGE, name), encoding="utf-8") as file:
                yield name, ast.parse(file.read(), name)


class SourceRulesTest(unittest.TestCase):
    def test_every_module_has_a_docstring_and_postponed_annotations(self) -> None:
        for name, tree in modules():
            self.assertTrue(ast.get_docstring(tree), name)
            future = [
                node
                for node in tree.body
                if isinstance(node, ast.ImportFrom) and node.module == "__future__"
            ]
            names = [alias.name for node in future for alias in node.names]
            self.assertEqual(["annotations"], names, name)

    def test_integer_arithmetic_only(self) -> None:
        for name, tree in modules():
            for node in ast.walk(tree):
                where = f"{name}:{getattr(node, 'lineno', 0)}"
                if isinstance(node, ast.Constant):
                    self.assertNotIsInstance(node.value, (float, complex), where)
                self.assertNotIsInstance(node, ast.Div, where + ": use // instead of /")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, ("float", "round", "complex"), where)

    def test_the_standard_library_only(self) -> None:
        for name, tree in modules():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    imported = [(node.module or "").split(".")[0]]
                    if node.module == "math":
                        self.assertEqual(["isqrt"], [alias.name for alias in node.names], name)
                else:
                    continue
                for module in imported:
                    self.assertIn(module, ALLOWED_IMPORTS, f"{name} imports {module}")

    def test_the_source_is_ascii(self) -> None:
        for name in sorted(os.listdir(PACKAGE)):
            if name.endswith(".py"):
                with open(os.path.join(PACKAGE, name), "rb") as file:
                    file.read().decode("ascii")

    def test_the_package_is_typed(self) -> None:
        self.assertTrue(os.path.isfile(os.path.join(PACKAGE, "py.typed")))


class PublicApiTest(unittest.TestCase):
    def test_all_is_complete(self) -> None:
        names = humanized_hash.__all__
        self.assertEqual(len(set(names)), len(names))
        for name in names:
            self.assertTrue(hasattr(humanized_hash, name), name)
        public = {
            name
            for name, value in vars(humanized_hash).items()
            if not name.startswith("_") and not inspect.ismodule(value) and name != "annotations"
        }
        self.assertEqual(public | {"__version__"}, set(names))

    def test_every_public_object_is_documented(self) -> None:
        for name in humanized_hash.__all__:
            value = getattr(humanized_hash, name)
            if not inspect.isclass(value):
                continue
            self.assertTrue(inspect.getdoc(value), name)
            for member_name, member in vars(value).items():
                if member_name.startswith("_"):
                    continue
                if isinstance(member, (classmethod, staticmethod)):
                    member = member.__func__
                if inspect.isfunction(member) or isinstance(member, property):
                    self.assertTrue(inspect.getdoc(member), f"{name}.{member_name}")

    def test_the_command_is_named_after_the_package(self) -> None:
        # "hh" alone would collide with hh.exe of Windows and the hh of the hstr shell tool.
        from humanized_hash import _cli

        self.assertEqual("humanized-hash", _cli._parser().prog)
        pyproject = os.path.join(ROOT, "pyproject.toml")
        if not os.path.isfile(pyproject):
            self.skipTest("the installed package has no pyproject.toml beside it")
        with open(pyproject, encoding="utf-8") as file:
            scripts = re.search(r"^\[project\.scripts\]\n(.*?)(?:^\[|\Z)", file.read(), re.M | re.S)
        self.assertIsNotNone(scripts)
        self.assertEqual(
            ['humanized-hash = "humanized_hash._cli:main"'],
            [line for line in (scripts.group(1) if scripts else "").split("\n") if line],
        )

    def test_the_version_is_the_one_of_the_changelog(self) -> None:
        self.assertRegex(humanized_hash.__version__, r"^\d+\.\d+\.\d+$")
        changelog = os.path.join(ROOT, "CHANGELOG.md")
        if not os.path.isfile(changelog):
            self.skipTest("the installed package has no changelog beside it")
        with open(changelog, encoding="utf-8") as file:
            releases = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", file.read(), re.MULTILINE)
        self.assertEqual(humanized_hash.__version__, releases[0])


if __name__ == "__main__":
    unittest.main()
