import os
import asyncio
from typing import Dict, Any, List
import logging
import magic
import lief
from androguard.core.apk import APK
from mobsec_modules_library.static.static_module import StaticModule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


class NativeLibsModule(StaticModule):
    def __init__(self):
        super().__init__("native_libs_module")

    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        file_path = os.path.join(
            "/shared_data", task_data["folder_path"], task_data["file_name"]
        )

        if not os.path.exists(file_path):
            return {"status": "error", "error": f"File not found: {file_path}"}

        # Only process APK files
        if task_data.get("file_type") != "apk":
            return {
                "status": "error",
                "error": "Native Libraries module only supports APK files",
            }

        try:
            apk = APK(file_path)

            results = {
                "status": "success",
                "results": {
                    "libraries": [],
                    "summary": {"total_libs": 0, "architectures": {}},
                },
            }

            # Get all files from APK
            for file_name in apk.get_files():
                # Check if file is in lib directory and is a shared library
                if file_name.startswith("lib/") and file_name.endswith(".so"):
                    try:
                        # Extract library data
                        lib_data = apk.get_file(file_name)
                        if lib_data:
                            lib_info = self.analyze_native_lib(lib_data, file_name)
                            if lib_info:
                                results["results"]["libraries"].append(lib_info)
                    except Exception as e:
                        logger.warning(
                            f"Failed to analyze library {file_name}: {str(e)}"
                        )
                        results["results"]["libraries"].append(
                            {
                                "name": file_name,
                                "architecture": self.extract_architecture(file_name),
                                "error": str(e),
                            }
                        )

            # Count valid architectures (exclude entries with errors)
            valid_libs = [
                lib for lib in results["results"]["libraries"] if "error" not in lib
            ]

            results["results"]["summary"]["total_libs"] = len(
                results["results"]["libraries"]
            )
            results["results"]["summary"]["architectures"] = self.count_architectures(
                results["results"]["libraries"]
            )

            return results

        except Exception as e:
            logger.error(f"Error analyzing native libraries: {str(e)}")
            return {
                "status": "error",
                "error": f"Failed to analyze native libraries: {str(e)}",
                "results": {
                    "libraries": [],
                    "summary": {"total_libs": 0, "architectures": {}},
                },
            }

    def extract_architecture(self, lib_name: str) -> str:
        parts = lib_name.split("/")
        if len(parts) >= 3 and parts[0] == "lib":
            return parts[1]
        return "unknown"

    def analyze_native_lib(self, lib_data: bytes, lib_name: str) -> Dict[str, Any]:
        architecture = self.extract_architecture(lib_name)
        try:
            # Save library temporarily for analysis
            temp_path = f"/tmp/{os.path.basename(lib_name)}"
            with open(temp_path, "wb") as f:
                f.write(lib_data)

            # Get file type
            file_type = magic.from_file(temp_path)

            # Only analyze ELF files
            if "ELF" not in file_type:
                os.remove(temp_path)
                return {
                    "name": lib_name,
                    "architecture": architecture,
                    "error": "Not an ELF file",
                    "type": file_type,
                }

            # Analyze with LIEF
            try:
                binary = lief.parse(temp_path)
                if binary is None:
                    raise ValueError("Failed to parse binary")

                result = {
                    "name": lib_name,
                    "architecture": architecture,
                    "type": file_type,
                    "symbols": len(binary.exported_functions),
                    "imported_functions": len(binary.imported_functions),
                    "sections": len(binary.sections),
                    "has_debug_symbols": self.has_debug_symbols(binary),
                    "imported_libraries": [lib for lib in binary.libraries],
                    "exported_functions": [
                        func.name for func in binary.exported_functions
                    ],
                }
            except Exception as e:
                result = {
                    "name": lib_name,
                    "architecture": architecture,
                    "error": f"LIEF analysis failed: {str(e)}",
                    "type": file_type,
                }

            # Clean up temp file
            os.remove(temp_path)
            return result

        except Exception as e:
            logger.warning(f"Error analyzing library {lib_name}: {str(e)}")
            return {"name": lib_name, "architecture": architecture, "error": str(e)}

    def has_debug_symbols(self, binary) -> bool:
        return any(
            section.type == lief.ELF.Section.TYPE.SYMTAB for section in binary.sections
        )

    def count_architectures(self, lib_details: List[Dict]) -> Dict[str, int]:
        arch_count = {}
        for lib in lib_details:
            if "architecture" in lib:
                arch = lib["architecture"]
                arch_count[arch] = arch_count.get(arch, 0) + 1
        return arch_count


if __name__ == "__main__":
    module = NativeLibsModule()
    asyncio.run(module.start())
