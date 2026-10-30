import json
import os
import asyncio
from typing import Dict, Any, List, Optional
import logging
from mobsec_modules_library.static.static_module import StaticModule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

MAX_SNIPPET_LINES = 50


class SemgrepModule(StaticModule):
    def __init__(self):
        super().__init__("semgrep_module")

    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        base_path = os.path.join("/shared_data", task_data["folder_path"])
        code_dir = os.path.join(base_path, "source_code")

        if not os.path.exists(code_dir):
            return {
                "status": "error",
                "error": "Decompiled source code not found. Run JADX module first.",
            }

        process = await asyncio.create_subprocess_exec(
            "semgrep",
            "--metrics=off",
            "--no-rewrite-rule-ids",
            "-q",
            "--config",
            "./rules",
            "--json",
            code_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        if stderr:
            logger.info(stderr.decode(errors="replace"))

        if process.returncode != 0:
            return {"status": "error", "error": stderr.decode(errors="replace")}

        try:
            scan_results = json.loads(stdout.decode())

            summary = self.summarize_results(scan_results)
            findings = await asyncio.to_thread(
                self.process_findings,
                scan_results.get("results", []),
                code_dir,
            )

            return {
                "status": "success",
                "results": {
                    "summary": summary,
                    "findings": findings,
                    "metrics": {
                        "total_findings": len(findings),
                        "scan_time": scan_results.get("time", {}),
                    },
                },
            }
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"Failed to parse Semgrep output: {str(e)}",
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to process results: {str(e)}",
            }

    def summarize_results(self, scan_results: Dict) -> Dict[str, Any]:
        findings = scan_results.get("results", [])
        severity_counts: Dict[str, int] = {}
        categories: Dict[str, int] = {}

        for finding in findings:
            severity = finding.get("extra", {}).get("severity", "LOW")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

            rule_id = finding.get("check_id", "unknown")
            categories[rule_id] = categories.get(rule_id, 0) + 1

        return {
            "severity_counts": severity_counts,
            "category_counts": categories,
            "scanned_files": len(scan_results.get("paths", {}).get("scanned", [])),
        }

    @staticmethod
    def _resolve_path(file_path: Optional[str], code_dir: str) -> Optional[str]:
        if not file_path:
            return None
        if os.path.isfile(file_path):
            return file_path
        candidate = os.path.join(code_dir, file_path)
        if os.path.isfile(candidate):
            return candidate
        return None

    @staticmethod
    def _get_file_lines(
        path: str, cache: Dict[str, Optional[List[str]]]
    ) -> Optional[List[str]]:
        if path not in cache:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    cache[path] = f.read().splitlines()
            except OSError as e:
                logger.warning(f"Cannot read {path}: {e}")
                cache[path] = None
        return cache[path]

    def _extract_code(
        self,
        file_path: Optional[str],
        start_line: Optional[int],
        end_line: Optional[int],
        code_dir: str,
        cache: Dict[str, Optional[List[str]]],
    ) -> str:
        if not file_path or not start_line:
            return ""

        resolved = self._resolve_path(file_path, code_dir)
        if resolved is None:
            return ""

        file_lines = self._get_file_lines(resolved, cache)
        if not file_lines:
            return ""

        end_line = end_line or start_line
        end_line = min(end_line, start_line + MAX_SNIPPET_LINES - 1)
        snippet = file_lines[start_line - 1 : end_line]
        return "\n".join(snippet)

    def process_findings(self, findings: List[Dict], code_dir: str) -> List[Dict]:
        processed_findings = []
        file_cache: Dict[str, Optional[List[str]]] = {}

        for finding in findings:
            extra = finding.get("extra", {})
            file_path = finding.get("path")
            start_line = finding.get("start", {}).get("line")
            end_line = finding.get("end", {}).get("line")

            processed_findings.append(
                {
                    "rule_id": finding.get("check_id"),
                    "severity": extra.get("severity", "WARNING"),
                    "message": extra.get("message", ""),
                    "location": {
                        "file": file_path,
                        "start_line": start_line,
                        "end_line": end_line,
                        "code": self._extract_code(
                            file_path, start_line, end_line, code_dir, file_cache
                        ),
                    },
                }
            )

        return processed_findings


if __name__ == "__main__":
    module = SemgrepModule()
    asyncio.run(module.start())
