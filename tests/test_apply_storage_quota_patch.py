from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_storage_quota_patch.py"

spec = importlib.util.spec_from_file_location("apply_storage_quota_patch", SCRIPT)
assert spec and spec.loader
apply_storage_quota_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_storage_quota_patch"] = apply_storage_quota_patch
spec.loader.exec_module(apply_storage_quota_patch)

MANAGER_FIXTURE = '''#include "third_party/blink/renderer/modules/quota/storage_manager.h"

#include "mojo/public/cpp/bindings/callback_helpers.h"
#include "third_party/blink/renderer/bindings/modules/v8/v8_storage_estimate.h"

namespace blink {

namespace {

void QueryStorageUsageAndQuotaCallback(
    ScriptPromiseResolver<StorageEstimate>* resolver,
    mojom::blink::QuotaStatusCode status_code,
    int64_t usage_in_bytes,
    int64_t quota_in_bytes,
    UsageBreakdownPtr usage_breakdown) {
  StorageEstimate* estimate = StorageEstimate::Create();
  estimate->setUsage(usage_in_bytes);
  estimate->setQuota(quota_in_bytes);
}

}  // namespace

}  // namespace blink
'''

BUCKET_FIXTURE = '''#include "third_party/blink/renderer/modules/buckets/storage_bucket.h"

#include "base/time/time.h"
#include "third_party/blink/renderer/bindings/modules/v8/v8_storage_estimate.h"

namespace blink {

void StorageBucket::DidGetEstimate(
    ScriptPromiseResolver<StorageEstimate>* resolver,
    int64_t current_usage,
    int64_t current_quota,
    bool success) {
  StorageEstimate* estimate = StorageEstimate::Create();
  estimate->setUsage(current_usage);
  estimate->setQuota(current_quota);
}

}  // namespace blink
'''


class ApplyStorageQuotaPatchTests(unittest.TestCase):
    def test_patches_storage_manager_quota(self) -> None:
        patched = apply_storage_quota_patch.patch_storage_manager(MANAGER_FIXTURE)
        self.assertIn('GetSwitchValueASCII(\n              "fingerprint-storage-quota")', patched)
        self.assertIn("BrowseForgeStorageQuotaOverrideOrDefault(usage_in_bytes, quota_in_bytes)", patched)
        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('#include "base/strings/string_number_conversions.h"', patched)

    def test_patches_storage_bucket_quota(self) -> None:
        patched = apply_storage_quota_patch.patch_storage_bucket(BUCKET_FIXTURE)
        self.assertIn("BrowseForgeStorageQuotaOverrideOrDefault(current_usage, current_quota)", patched)
        self.assertIn("quota_bytes < usage_in_bytes ? usage_in_bytes : quota_bytes", patched)

    def test_patch_is_idempotent(self) -> None:
        patched_manager_once = apply_storage_quota_patch.patch_storage_manager(MANAGER_FIXTURE)
        patched_manager_twice = apply_storage_quota_patch.patch_storage_manager(patched_manager_once)
        self.assertEqual(patched_manager_once, patched_manager_twice)
        patched_bucket_once = apply_storage_quota_patch.patch_storage_bucket(BUCKET_FIXTURE)
        patched_bucket_twice = apply_storage_quota_patch.patch_storage_bucket(patched_bucket_once)
        self.assertEqual(patched_bucket_once, patched_bucket_twice)

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            manager_path = src / apply_storage_quota_patch.STORAGE_MANAGER_CC
            bucket_path = src / apply_storage_quota_patch.STORAGE_BUCKET_CC
            manager_path.parent.mkdir(parents=True)
            bucket_path.parent.mkdir(parents=True)
            (src / ".git").mkdir()
            manager_path.write_text(MANAGER_FIXTURE, encoding="utf-8")
            bucket_path.write_text(BUCKET_FIXTURE, encoding="utf-8")
            changed = apply_storage_quota_patch.apply_patch(src)
            self.assertEqual(
                [
                    apply_storage_quota_patch.STORAGE_MANAGER_CC,
                    apply_storage_quota_patch.STORAGE_BUCKET_CC,
                ],
                changed,
            )
            self.assertIn("fingerprint-storage-quota", manager_path.read_text(encoding="utf-8"))
            self.assertIn("fingerprint-storage-quota", bucket_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
