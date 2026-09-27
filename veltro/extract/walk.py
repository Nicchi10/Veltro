"""

veltro/extract/walk.py

Which files an extractor is allowed to read, for every language.

This exists because of a real and embarrassing result: pointing the Python
extractor at a project root produced 25,735 types, of which **99.6% came from
the virtualenv**. One module out of 6,020 was the project. The TypeScript
extractor already pruned 'node_modules' and friends; the Python and C# ones
walked everything. The lesson was learned once and not shared, which is exactly
what a common module is for.

Two lists, and the difference matters:

- DEPENDENCY_DIRS is other people's code and build output. Never the
  architecture under study, never worth reading, pruned always.
- TEST_DIRS is your own code, but it mirrors the production types and drowns
  them (the NestJS lesson: sample apps outnumbered the framework). Pruned by
  default, kept with 'keep_tests'.

What this does NOT do is read '.gitignore'. A half-implemented ignore file
silently drops real source, which is a worse failure than reading too much, and
the patterns below already cover the case that actually bites. Use '--exclude'
for anything else.

"""

import fnmatch
import os

# Never source, in any language: other people's code, caches, VCS and editor state
DEPENDENCY_DIRS = frozenset({
    # version control and editors
    ".git", ".hg", ".svn", ".idea", ".vs", ".vscode",
    # Python environments and caches
    "__pycache__", "venv", ".venv", "site-packages",
    ".tox", ".nox", ".eggs", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    # JavaScript
    "node_modules", ".next", ".nuxt", "bower_components",
    # vendored dependencies and coverage output
    "vendor", "third_party", "coverage", "htmlcov",
})

# Build output is language-specific, and guessing it globally is dangerous: a monorepo keeps its SOURCE in 'packages' (nest and angular both do), 
# which is also where NuGet puts its downloads. Pruning that everywhere would silently return an empty graph for the two TypeScript examples this repo ships. 
# So each language prunes only what its own toolchain generates.
BUILD_DIRS_BY_EXTENSION = {
    ".py": frozenset({"build", "dist"}),
    ".cs": frozenset({"bin", "obj", "packages"}),
    ".java": frozenset({"target", "build", ".gradle"}),
    ".ts": frozenset({"dist", "out", "build"}),
}

# The TypeScript family shares one toolchain
for _extension in (".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".d.ts"):
    BUILD_DIRS_BY_EXTENSION[_extension] = BUILD_DIRS_BY_EXTENSION[".ts"]

# Your own code, but fixtures rather than architecture
TEST_DIRS = frozenset({
    "test", "tests", "__tests__", "__mocks__", "e2e", "spec", "testdata", "fixtures",
})

# Test FILES that sit next to the code they exercise, per language convention
TEST_FILE_PATTERNS = (
    "test_*.py", "*_test.py",                 # Python
    "*.spec.*", "*.test.*",                   # TypeScript / JavaScript
    "*Test.cs", "*Tests.cs", "*Test.java", "*Tests.java",
)


def new_report() -> dict:
    """

    A fresh record of what a walk looked at and what it refused.

    Returns:
        dict: 'files' (kept), 'skipped_files', 'pruned' (directory names, with
            how many times each was pruned)

    """
    return {"files": 0, "skipped_files": 0, "pruned": {}}


def looks_like_a_test(file_name: str) -> bool:
    """

    Whether a file name follows one of the per-language test conventions.

    Args:
        file_name (str): the base name, not the path

    Returns:
        bool: True when it matches a test pattern

    """
    for pattern in TEST_FILE_PATTERNS:
        if fnmatch.fnmatch(file_name, pattern):
            return True
    return False


def matches_any(relative_path: str, patterns) -> bool:
    """

    Whether a path matches one of the caller's exclude globs.

    Both separators are tried, so '--exclude "docs/*"' works on Windows too.

    Args:
        relative_path (str): the path relative to the walk root
        patterns (iterable[str]): glob patterns

    Returns:
        bool: True when any pattern matches

    """
    candidates = [relative_path, relative_path.replace(os.sep, "/")]
    for pattern in patterns:
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, pattern):
                return True
    return False


def iter_source_files(root: str, extensions, keep_tests: bool = False, exclude=(), report: dict = None):
    """

    Yield every source file under 'root' worth extracting, in a stable order.

    Directories are pruned in place during the walk, so a virtualenv or a
    'node_modules' costs nothing at all rather than being read and discarded.

    Args:
        root (str): the directory to scan
        extensions (tuple[str]): file suffixes to keep, e.g. ('.py',)
        keep_tests (bool): read test directories and test files too
        exclude (iterable[str]): extra glob patterns, matched against the path
            relative to 'root'
        report (dict): filled in as the walk goes (see new_report)

    Yields:
        str: absolute path of each file to extract

    """
    if report is None:
        report = new_report()
    patterns = list(exclude)

    pruned_dirs = set(DEPENDENCY_DIRS)
    for extension in extensions:
        pruned_dirs |= BUILD_DIRS_BY_EXTENSION.get(extension, frozenset())
    if not keep_tests:
        pruned_dirs = pruned_dirs | TEST_DIRS

    root = os.path.abspath(root)
    for current_root, directories, files in os.walk(root):
        kept_directories = []
        for name in directories:
            relative = os.path.relpath(os.path.join(current_root, name), root)
            if name in pruned_dirs or matches_any(relative, patterns):
                report["pruned"][name] = report["pruned"].get(name, 0) + 1
                continue
            kept_directories.append(name)
        # assigning to the slice is what tells os.walk not to descend
        directories[:] = sorted(kept_directories)

        for file_name in sorted(files):
            if not file_name.endswith(tuple(extensions)):
                continue
            absolute_path = os.path.join(current_root, file_name)
            relative = os.path.relpath(absolute_path, root)
            if matches_any(relative, patterns):
                report["skipped_files"] += 1
                continue
            if not keep_tests and looks_like_a_test(file_name):
                report["skipped_files"] += 1
                continue
            report["files"] += 1
            yield absolute_path


def describe(report: dict) -> str:
    """

    One line saying what the walk read and what it left out.

    Silence about a pruned virtualenv is how someone ends up believing their
    project has 25,000 types, so this is printed even when nothing was pruned.

    Args:
        report (dict): from new_report, after a walk

    Returns:
        str: a human-readable summary

    """
    line = f"{report['files']} files read"
    if report["skipped_files"]:
        line += f", {report['skipped_files']} skipped"
    if report["pruned"]:
        names = sorted(report["pruned"], key=report["pruned"].get, reverse=True)
        shown = ", ".join(names[:5])
        if len(names) > 5:
            shown += f", +{len(names) - 5} more"
        total = sum(report["pruned"].values())
        line += f", {total} directories pruned ({shown})"
    return line


def add_walk_arguments(parser):
    """

    The walk options every extractor's command line shares.

    Args:
        parser (argparse.ArgumentParser): the extractor's parser

    """
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",help="skip paths matching this glob, relative to the source root (repeatable)")
    parser.add_argument("--include-tests", action="store_true",help="read test directories and test files too (they are skipped by default)")
