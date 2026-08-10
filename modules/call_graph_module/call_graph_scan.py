import os
import json
import lmdb
import hashlib
import logging
import asyncio
import gc
from typing import Dict, Any, Optional
from collections import deque
from mobsec_modules_library.static.static_module import StaticModule

# Androguard imports
from androguard.misc import AnalyzeAPK
from androguard.core.analysis.analysis import Analysis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("call_graph_module")


def sha1_short(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:16]


class LMDBCallGraphStore:
    def __init__(self, path: str, map_size: int = 8 * 1024**3):
        # path: directory for LMDB files; ensure exists
        os.makedirs(path, exist_ok=True)
        # open env once; single writer expected
        self.env = lmdb.open(
            path,
            map_size=map_size,
            subdir=True,
            max_dbs=1,
            writemap=True,
            lock=True,
        )

    def _node_key(self, file_hash: str, node_hash: str) -> bytes:
        return f"{file_hash}:node:{node_hash}".encode()

    def _edge_key(self, file_hash: str, from_hash: str, to_hash: str) -> bytes:
        return f"{file_hash}:edge:{from_hash}:{to_hash}".encode()

    def put_nodes_edges_batch(self, file_hash: str, node_items, edge_items):
        """
        node_items: iterable of (node_hash, node_json_str)
        edge_items: iterable of (from_hash, to_hash)
        Writes in a single transaction.
        """
        with self.env.begin(write=True) as txn:
            for node_hash, node_json in node_items:
                txn.put(self._node_key(file_hash, node_hash), node_json.encode())
            for from_h, to_h in edge_items:
                txn.put(self._edge_key(file_hash, from_h, to_h), b"1")

    def put_node(self, file_hash: str, node_hash: str, node_json: str):
        with self.env.begin(write=True) as txn:
            txn.put(self._node_key(file_hash, node_hash), node_json.encode())

    def put_edge(self, file_hash: str, from_h: str, to_h: str):
        with self.env.begin(write=True) as txn:
            txn.put(self._edge_key(file_hash, from_h, to_h), b"1")

    def write_stats(self, file_hash: str, stats: Dict[str, Any]):
        with self.env.begin(write=True) as txn:
            txn.put(f"{file_hash}:meta:stats".encode(), json.dumps(stats).encode())

    def read_stats(self, file_hash: str) -> Optional[Dict[str, Any]]:
        with self.env.begin() as txn:
            b = txn.get(f"{file_hash}:meta:stats".encode())
            if not b:
                return None
            return json.loads(b.decode())

    def export_json_stream(
        self, file_hash: str, output_path: str, batch_size: int = 1000
    ):
        """
        Exports nodes and edges to JSON file in streaming mode.
        Format: {"nodes": [...], "edges": [...], "stats": {...}}
        """
        with open(output_path, "w", encoding="utf-8") as fout:
            fout.write('{"nodes":[')
            first = True
            with self.env.begin() as txn:
                cursor = txn.cursor()
                prefix = f"{file_hash}:node:".encode()
                # iterate nodes
                cursor.set_range(prefix)
                count = 0
                for k, v in cursor:
                    if not k.startswith(prefix):
                        break
                    if not first:
                        fout.write(",")
                    fout.write(v.decode())
                    first = False
                    count += 1
                    if count % batch_size == 0:
                        fout.flush()
            fout.write('],"edges":[')
            first = True
            with self.env.begin() as txn:
                cursor = txn.cursor()
                prefix = f"{file_hash}:edge:".encode()
                cursor.set_range(prefix)
                for k, _ in cursor:
                    if not k.startswith(prefix):
                        break
                    # reconstruct from, to from key
                    parts = k.decode().split(":")
                    # format file_hash:edge:from:to
                    if len(parts) < 4:
                        continue
                    from_h = parts[2]
                    to_h = parts[3]
                    edge_json = json.dumps({"from_hash": from_h, "to_hash": to_h})
                    if not first:
                        fout.write(",")
                    fout.write(edge_json)
                    first = False
            fout.write('],"stats":')
            stats = self.read_stats(file_hash) or {}
            fout.write(json.dumps(stats))
            fout.write("}")
            fout.flush()


class CallGraphModule(StaticModule):
    def __init__(self):
        super().__init__("call_graph_module")
        # LMDB path and map size configurable via env
        lmdb_root = os.getenv("LMDB_PATH", "/tmp/lmdb_callgraph")
        lmdb_map_size_env = os.getenv("LMDB_MAP_SIZE_BYTES")
        if lmdb_map_size_env:
            try:
                lmdb_map_size = int(lmdb_map_size_env)
            except Exception:
                lmdb_map_size = 8 * 1024**3
        else:
            lmdb_map_size = 8 * 1024**3  # default 8 GiB
        self.store = LMDBCallGraphStore(lmdb_root, map_size=lmdb_map_size)
        # Batch commit sizes
        self.node_batch_size = int(os.getenv("NODE_BATCH_SIZE", "500"))
        self.edge_batch_size = int(os.getenv("EDGE_BATCH_SIZE", "1000"))

    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        file_path = os.path.join(
            "/shared_data", task_data["folder_path"], task_data["file_name"]
        )

        if not os.path.exists(file_path):
            return {"status": "error", "error": f"File not found: {file_path}"}

        if task_data.get("file_type") != "apk":
            return {
                "status": "error",
                "error": "Call Graph module only supports APK files",
            }

        file_hash = task_data.get(
            "file_hash", sha1_short(task_data.get("file_name", file_path))
        )
        try:
            # Analyze APK (this creates objects in memory)
            logger.info(f"AnalyzeAPK for {file_path}")
            a, d, dx = AnalyzeAPK(file_path)
            logger.info("AnalyzeAPK done. Generating call graph (streaming to LMDB)...")

            # Generate call graph writing directly to LMDB
            stats = self.generate_call_graph(dx, a, file_hash)

            # free large androguard objects asap
            try:
                del dx
                del d
                del a
            except Exception:
                pass
            gc.collect()

            # write stats to LMDB
            self.store.write_stats(file_hash, stats)

            # Export all data to JSON format
            json_data = self.export_to_json(file_hash, stats)

            # Clean up LMDB data after export
            self.cleanup_lmdb_data(file_hash)

            # Return complete JSON data
            result = {"status": "success", "results": json_data}
            return result

        except Exception as e:
            logger.exception(f"Error analyzing APK: {e}")
            return {"status": "error", "error": str(e)}

    def generate_call_graph(self, dx: Analysis, apk, file_hash: str) -> Dict[str, Any]:

        logger.info("Starting call graph generation (LMDB streaming)...")
        import time

        start_time = time.time()
        package_name = apk.get_package()
        package_prefix = f"L{package_name.replace('.', '/')}"
        logger.info(f"Package name: {package_name}")

        # call graph from androguard
        cg = dx.get_call_graph()

        # determine entry points by activity (best-effort)
        main_activity = None
        try:
            for activity in apk.get_activities():
                if "MainActivity" in activity:
                    main_activity = activity
                    break
            if not main_activity:
                acts = apk.get_activities()
                if acts:
                    main_activity = acts[0]
        except Exception:
            main_activity = None

        if main_activity:
            main_activity_class = f"L{main_activity.replace('.', '/')};"
        else:
            main_activity_class = None

        # find initial entry point methods
        entry_points = []
        try:
            for method in cg.nodes():
                try:
                    if (
                        main_activity_class
                        and method.get_class_name() == main_activity_class
                    ):
                        entry_points.append(method)
                except Exception:
                    continue
            # if none found, pick first N public methods as seeds (fallback)
            if not entry_points:
                added = 0
                for method in cg.nodes():
                    try:
                        if method.get_name() == "<init>":
                            continue
                        entry_points.append(method)
                        added += 1
                        if added >= 5:
                            break
                    except Exception:
                        continue
        except Exception:
            # cg.nodes() might be expensive/raise; fallback empty
            entry_points = []

        # BFS with limits; use string id as visited key to avoid holding method objects unnecessarily
        MAX_DEPTH = int(os.getenv("MAX_DEPTH", "1000"))
        visited = set()
        q = deque()
        for m in entry_points:
            try:
                idstr = f"{m.get_class_name()}->{m.get_name()}{m.get_descriptor()}"
                q.append((m, 0))
            except Exception:
                continue

        node_batch = []
        edge_batch = []
        total_nodes = 0
        total_edges = 0
        external_calls = 0
        entry_point_count = len(entry_points)

        # helper to push batch into LMDB
        def flush_batches():
            nonlocal node_batch, edge_batch, total_nodes, total_edges
            if node_batch or edge_batch:
                try:
                    self.store.put_nodes_edges_batch(file_hash, node_batch, edge_batch)
                    total_nodes += len(node_batch)
                    total_edges += len(edge_batch)
                except Exception as e:
                    logger.exception(f"LMDB batch write error: {e}")
                node_batch = []
                edge_batch = []

        processed_counter = 0
        while q:
            current_method, depth = q.popleft()
            if depth > MAX_DEPTH:
                continue

            try:
                class_name = current_method.get_class_name()
                method_name = current_method.get_name()
                descriptor = current_method.get_descriptor()
            except Exception:
                continue

            idstr = f"{class_name}->{method_name}{descriptor}"
            idhash = sha1_short(idstr)

            if idhash in visited:
                continue
            visited.add(idhash)

            # flags and meta
            try:
                access_flags = current_method.get_access_flags_string()
            except Exception:
                access_flags = ""

            node_obj = {
                "id_hash": idhash,
                "id_str": idstr,
                "class": class_name,
                "method": method_name,
                "descriptor": descriptor,
                "is_entry_point": access_flags.startswith("public"),
                "is_external": not class_name.startswith(package_prefix),
                "is_native": "native" in access_flags,
                "depth": depth,
            }

            # count external calls later when we process edges
            node_batch.append((idhash, json.dumps(node_obj)))

            # iterate callees (out edges)
            try:
                for _, callee in cg.out_edges(current_method):
                    try:
                        c_class = callee.get_class_name()
                        c_name = callee.get_name()
                        c_desc = callee.get_descriptor()
                        c_idstr = f"{c_class}->{c_name}{c_desc}"
                        c_hash = sha1_short(c_idstr)

                        # store edge (from -> to)
                        edge_batch.append((idhash, c_hash))

                        # enqueue callee for BFS (we keep method object here until processed)
                        if c_hash not in visited:
                            q.append((callee, depth + 1))

                    except Exception:
                        continue
            except Exception:
                # sometimes cg.out_edges may raise; skip
                pass

            processed_counter += 1

            # flush batches occasionally
            if (
                len(node_batch) >= self.node_batch_size
                or len(edge_batch) >= self.edge_batch_size
            ):
                flush_batches()

            # small periodic GC to help with androguard object churn
            if processed_counter % 2000 == 0:
                gc.collect()

        # final flush
        flush_batches()

        # Count actual entry points (methods with is_entry_point=true)
        actual_entry_points = 0
        try:
            with self.store.env.begin() as txn:
                cursor = txn.cursor()
                node_prefix = f"{file_hash}:node:".encode()
                cursor.set_range(node_prefix)
                for key, value in cursor:
                    if not key.startswith(node_prefix):
                        break
                    try:
                        node_data = json.loads(value.decode())
                        if node_data.get("is_entry_point", False):
                            actual_entry_points += 1
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Error counting entry points: {e}")
            actual_entry_points = entry_point_count

        stats = {
            "total_methods": total_nodes,
            "total_edges": total_edges,
            "entry_points": actual_entry_points,
            "max_depth": MAX_DEPTH,
            "package_name": package_name,
            "generated_at": int(start_time),
        }

        elapsed = time.time() - start_time
        logger.info(
            f"Call graph generation finished: nodes={total_nodes}, edges={total_edges}, time={elapsed:.1f}s"
        )

        return stats

    def export_to_json(self, file_hash: str, stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Export all call graph data from LMDB to JSON format.
        """
        logger.info(f"Exporting call graph data to JSON for {file_hash}")

        nodes = []
        edges = []

        try:
            with self.store.env.begin() as txn:
                # Read all nodes
                cursor = txn.cursor()
                node_prefix = f"{file_hash}:node:".encode()

                # Use set_range to start from the prefix
                cursor.set_range(node_prefix)
                for key, value in cursor:
                    if not key.startswith(node_prefix):
                        break
                    try:
                        node_data = json.loads(value.decode())
                        nodes.append(node_data)
                    except json.JSONDecodeError:
                        continue

                # Read all edges
                edge_prefix = f"{file_hash}:edge:".encode()
                cursor.set_range(edge_prefix)
                for key, _ in cursor:
                    if not key.startswith(edge_prefix):
                        break
                    try:
                        # Parse edge key: file_hash:edge:from_hash:to_hash
                        key_parts = key.decode().split(":")
                        if len(key_parts) >= 4:
                            from_hash = key_parts[2]
                            to_hash = key_parts[3]
                            edges.append({"from_hash": from_hash, "to_hash": to_hash})
                    except Exception:
                        continue

        except Exception as e:
            logger.error(f"Error exporting data from LMDB: {e}")
            return {"error": f"Failed to export data: {str(e)}"}

        logger.info(f"Exported {len(nodes)} nodes and {len(edges)} edges")

        return {"file_hash": file_hash, "nodes": nodes, "edges": edges, "stats": stats}

    def cleanup_lmdb_data(self, file_hash: str):
        """
        Clean up LMDB data for a specific file after export.
        """
        try:
            with self.store.env.begin(write=True) as txn:
                cursor = txn.cursor()

                # Delete all nodes
                node_prefix = f"{file_hash}:node:".encode()
                cursor.set_range(node_prefix)
                keys_to_delete = []
                for key, _ in cursor:
                    if not key.startswith(node_prefix):
                        break
                    keys_to_delete.append(key)

                for key in keys_to_delete:
                    txn.delete(key)

                # Delete all edges
                edge_prefix = f"{file_hash}:edge:".encode()
                cursor.set_range(edge_prefix)
                keys_to_delete = []
                for key, _ in cursor:
                    if not key.startswith(edge_prefix):
                        break
                    keys_to_delete.append(key)

                for key in keys_to_delete:
                    txn.delete(key)

                # Delete stats
                stats_key = f"{file_hash}:meta:stats".encode()
                txn.delete(stats_key)

            logger.info(f"Cleaned up LMDB data for {file_hash}")

        except Exception as e:
            logger.error(f"Error cleaning up LMDB data: {e}")


if __name__ == "__main__":
    module = CallGraphModule()
    try:
        asyncio.run(module.start())
    except KeyboardInterrupt:
        logger.info("Shutting down module (keyboard interrupt).")
