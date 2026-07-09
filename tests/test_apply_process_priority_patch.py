from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_process_priority_patch.py"

spec = importlib.util.spec_from_file_location("apply_process_priority_patch", SCRIPT)
assert spec and spec.loader
apply_process_priority_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_process_priority_patch"] = apply_process_priority_patch
spec.loader.exec_module(apply_process_priority_patch)

PROCESS_LINUX_FIXTURE = '''#include "base/process/process.h"

#include <errno.h>

#include "base/check.h"
#include "base/files/file_util.h"

namespace base {

bool Process::SetPriority(Priority priority) {
  DCHECK(IsValid());

  if (!CanSetPriority()) {
    return false;
  }

  int priority_value = priority == Priority::kBestEffort ? kBackgroundPriority
                                                         : kForegroundPriority;
  int result =
      setpriority(PRIO_PROCESS, static_cast<id_t>(process_), priority_value);
  DPCHECK(result == 0);
  return result == 0;
}

}  // namespace base
'''


class ApplyProcessPriorityPatchTests(unittest.TestCase):
    def test_patches_setpriority_dcheck_to_warning(self) -> None:
        patched = apply_process_priority_patch.patch_process_linux(PROCESS_LINUX_FIXTURE)
        self.assertIn('#include "base/logging.h"', patched)
        self.assertNotIn("DPCHECK(result == 0)", patched)
        self.assertIn('PLOG(WARNING) << "BrowseForge: setpriority failed"', patched)
        self.assertIn("return result == 0;", patched)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_process_priority_patch.patch_process_linux(PROCESS_LINUX_FIXTURE)
        patched_twice = apply_process_priority_patch.patch_process_linux(patched_once)
        self.assertEqual(patched_once, patched_twice)

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            path = src / apply_process_priority_patch.PROCESS_LINUX_CC
            path.parent.mkdir(parents=True)
            (src / ".git").mkdir()
            path.write_text(PROCESS_LINUX_FIXTURE, encoding="utf-8")
            changed = apply_process_priority_patch.apply_patch(src)
            self.assertEqual([apply_process_priority_patch.PROCESS_LINUX_CC], changed)
            text = path.read_text(encoding="utf-8")
            self.assertIn("BrowseForge: setpriority failed", text)


if __name__ == "__main__":
    unittest.main()
