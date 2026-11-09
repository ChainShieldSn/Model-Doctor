"""Self-check for model-doctor. Hermetic: needs no Hermes install and touches no
operator state — it loads model_doctor.py by path and points the snapshot at a
throwaway HERMES_HOME. Run: python3 selfcheck.py
"""
import importlib.util, os, tempfile
from pathlib import Path

# Isolate the snapshot before the module is loaded (get_hermes_home() reads env per call).
os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="model-doctor-selfcheck-")
_spec = importlib.util.spec_from_file_location(
    "model_doctor", Path(__file__).resolve().parent / "model_doctor.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class _Ctx:
    """Minimal stand-in for the plugin context Hermes hands to register()."""

    def __init__(self):
        self.hooks, self.tools = {}, {}

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_tool(self, name, handler, **kwargs):
        self.tools[name] = handler


# 0) start from a clean slate — the temp HERMES_HOME guarantees that
mod.RECORDS.clear()
mod._load_snapshot()

# 1) registration contract, then recording through the registered hooks
ctx = _Ctx()
mod.register(ctx)
assert sorted(ctx.hooks) == ["api_request_error", "post_api_request", "pre_api_request"], ctx.hooks
assert sorted(ctx.tools) == ["model_doctor_refresh", "model_doctor_status"], ctx.tools
def hook(name, **kwargs):
    ctx.hooks[name](**kwargs)


hook("post_api_request", model="live/probe", provider="p",
     base_url="u", status_code=200, finish_reason="stop",
     assistant_content_chars=50, api_duration=0.5)
hook("api_request_error", model="live/probe", provider="p",
     base_url="u", status_code=401,
     error={"type": "auth", "message": "bad key"})

st = ctx.tools["model_doctor_status"]({})
row = [r for r in st["models"] if r["model"] == "live/probe"][0]
assert row["counts"]["ok"] == 1 and row["counts"]["auth"] == 1, row
print("PASS hooks record events:", row["counts"])

# 2) classification correctness
c = mod._classify(401, "", 0, 0, {"type": "auth", "message": "x"})
assert c["verdict"] == "AUTH", c
c = mod._classify(503, "", 0, 1, None)
assert c["verdict"] == "UPSTREAM", c
c = mod._classify(200, "length", 0, 1, None)
assert c["verdict"] == "EMPTY", c
c = mod._classify(None, "", 0, 0, {"type": "timeout", "message": "t"})
assert c["verdict"] == "ERROR", c
c = mod._classify(200, "stop", 100, 2, None)
assert c["verdict"] == "OK", c
print("PASS classification: AUTH/UPSTREAM/EMPTY/ERROR/OK")

# 3) snapshot roundtrip
mod._save_snapshot()
before = len(mod.RECORDS)
mod.RECORDS.clear()
mod._load_snapshot()
assert len(mod.RECORDS) == before, "snapshot lost records"
print("PASS snapshot roundtrip:", before, "records")

print("ALL CHECKS PASSED")
