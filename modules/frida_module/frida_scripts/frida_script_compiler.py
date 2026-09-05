"""Compile Frida scripts with bridge support for Frida 17+."""

import logging
import os
import re
import tempfile

import frida

logger = logging.getLogger(__name__)

AGENT_PROJECT_ROOT = os.getenv(
    "FRIDA_AGENT_ROOT", os.path.join(os.path.dirname(__file__), "agent")
)

BRIDGE_IMPORTS = {
    "java": 'import Java from "frida-java-bridge";\n',
    "objc": 'import ObjC from "frida-objc-bridge";\n',
    "swift": 'import Swift from "frida-swift-bridge";\n',
}

BRIDGE_MARKERS = (
    'from "frida-java-bridge"',
    "from 'frida-java-bridge'",
    'from "frida-objc-bridge"',
    "from 'frida-objc-bridge'",
    'from "frida-swift-bridge"',
    "from 'frida-swift-bridge'",
    "import Java from",
    "import ObjC from",
    "import Swift from",
)


def _needs_compilation(content: str, script_name: str) -> bool:
    if script_name.endswith(".ts"):
        return True
    if any(marker in content for marker in BRIDGE_MARKERS):
        return True
    if re.search(r"\bJava\.(perform|use|available)\b", content):
        return True
    if re.search(r"\bObjC\.(available|classes)\b", content):
        return True
    if re.search(r"\bSwift\.(available|classes)\b", content):
        return True
    return False


def _prepare_source(content: str, script_name: str) -> tuple[str, str]:
    """Return source path and content ready for frida.Compiler."""
    if any(marker in content for marker in BRIDGE_MARKERS) or script_name.endswith(
        ".ts"
    ):
        suffix = ".ts"
        return suffix, content

    preamble = ""
    if re.search(r"\bJava\.(perform|use|available)\b", content):
        preamble += BRIDGE_IMPORTS["java"]
    if re.search(r"\bObjC\.(available|classes)\b", content):
        preamble += BRIDGE_IMPORTS["objc"]
    if re.search(r"\bSwift\.(available|classes)\b", content):
        preamble += BRIDGE_IMPORTS["swift"]

    if preamble:
        return ".ts", f"{preamble}{content}"

    return ".js", content


def compile_script(script_name: str, content: str) -> str:
    """
    Compile a Frida script using frida.Compiler when bridge APIs are used.

    See: https://frida.re/docs/bridges/#python-example
    """
    if not _needs_compilation(content, script_name):
        return content

    suffix, source = _prepare_source(content, script_name)
    logger.info(AGENT_PROJECT_ROOT)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=suffix,
        dir=AGENT_PROJECT_ROOT,
        delete=False,
        encoding="utf-8",
    ) as temp_file:
        temp_file.write(source)
        source_path = temp_file.name

    try:
        compiler = frida.Compiler()
        diagnostics: list[str] = []

        def on_diagnostics(diag: str):
            diagnostics.append(diag)
            logger.warning("Frida compile diagnostic: %s", diag)

        compiler.on("diagnostics", on_diagnostics)
        bundle = compiler.build(source_path, project_root=AGENT_PROJECT_ROOT)

        if diagnostics:
            logger.error(
                "COMPILE DIAGNOSTICS for %s:\n%s", script_name, "\n".join(diagnostics)
            )
        print("=== BUNDLE OUTPUT ===")
        print(bundle[:2000])

        return bundle
    finally:
        try:
            os.unlink(source_path)
        except OSError:
            pass
