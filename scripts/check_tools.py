import sys
sys.path.insert(0, '.')
from tools.tool_registry import registry
from tools.base_tool import ToolStatus
registry.discover()

print("=== image_generation tools ===")
for t in registry.get_by_capability('image_generation'):
    s = t.get_status()
    print(f"  {t.name}: status={s.value}, provider={t.provider}, is_avail={s == ToolStatus.AVAILABLE}")

print()
print("=== video_generation tools ===")
for t in registry.get_by_capability('video_generation'):
    s = t.get_status()
    print(f"  {t.name}: status={s.value}, provider={t.provider}, is_avail={s == ToolStatus.AVAILABLE}")

print()
print("=== All Agnes tools ===")
for t in registry.get_by_provider('agnes'):
    s = t.get_status()
    print(f"  {t.name}: status={s.value}, is_avail={s == ToolStatus.AVAILABLE}")
