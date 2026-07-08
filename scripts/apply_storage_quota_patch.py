#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
STORAGE_MANAGER_CC = Path("third_party/blink/renderer/modules/quota/storage_manager.cc")
STORAGE_BUCKET_CC = Path("third_party/blink/renderer/modules/buckets/storage_bucket.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
STRING_CONVERSIONS_INCLUDE = '#include "base/strings/string_number_conversions.h"\n'
MANAGER_INCLUDE_ANCHOR = '#include "mojo/public/cpp/bindings/callback_helpers.h"\n'
BUCKET_INCLUDE_ANCHOR = '#include "base/time/time.h"\n'
MANAGER_NAMESPACE_ANCHOR = "namespace {\n\n"
BUCKET_NAMESPACE_ANCHOR = "namespace blink {\n\n"

QUOTA_HELPER = '''int64_t BrowseForgeStorageQuotaOverrideOrDefault(int64_t usage_in_bytes,
                                                 int64_t default_quota) {
  uint64_t quota_mb = 0;
  if (!base::StringToUint64(
          base::CommandLine::ForCurrentProcess()->GetSwitchValueASCII(
              "fingerprint-storage-quota"),
          &quota_mb) ||
      quota_mb == 0 || quota_mb > 1024ull * 1024ull * 1024ull) {
    return default_quota;
  }
  int64_t quota_bytes = static_cast<int64_t>(quota_mb * 1024ull * 1024ull);
  return quota_bytes < usage_in_bytes ? usage_in_bytes : quota_bytes;
}

'''

ORIGINAL_MANAGER_QUOTA = '''  StorageEstimate* estimate = StorageEstimate::Create();
  estimate->setUsage(usage_in_bytes);
  estimate->setQuota(quota_in_bytes);
'''
PATCHED_MANAGER_QUOTA = '''  StorageEstimate* estimate = StorageEstimate::Create();
  estimate->setUsage(usage_in_bytes);
  estimate->setQuota(
      BrowseForgeStorageQuotaOverrideOrDefault(usage_in_bytes, quota_in_bytes));
'''

ORIGINAL_BUCKET_QUOTA = '''  StorageEstimate* estimate = StorageEstimate::Create();
  estimate->setUsage(current_usage);
  estimate->setQuota(current_quota);
'''
PATCHED_BUCKET_QUOTA = '''  StorageEstimate* estimate = StorageEstimate::Create();
  estimate->setUsage(current_usage);
  estimate->setQuota(
      BrowseForgeStorageQuotaOverrideOrDefault(current_usage, current_quota));
'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    for rel in (STORAGE_MANAGER_CC, STORAGE_BUCKET_CC):
        if not (src / rel).is_file():
            raise SystemExit(f"Chromium source file is missing: {src / rel}")


def ensure_include(text: str, anchor: str, include: str, label: str) -> str:
    if include in text:
        return text
    if anchor not in text:
        raise SystemExit(f"{label} include anchor not found")
    return text.replace(anchor, anchor + include, 1)


def ensure_quota_includes(text: str, anchor: str, label: str) -> str:
    patched = ensure_include(text, anchor, COMMAND_LINE_INCLUDE, label)
    return ensure_include(patched, COMMAND_LINE_INCLUDE, STRING_CONVERSIONS_INCLUDE, label)


def patch_storage_manager(text: str) -> str:
    patched = ensure_quota_includes(text, MANAGER_INCLUDE_ANCHOR, "storage_manager.cc")
    if "BrowseForgeStorageQuotaOverrideOrDefault" not in patched:
        if MANAGER_NAMESPACE_ANCHOR not in patched:
            raise SystemExit("storage_manager.cc namespace anchor not found")
        patched = patched.replace(MANAGER_NAMESPACE_ANCHOR, MANAGER_NAMESPACE_ANCHOR + QUOTA_HELPER, 1)
    if PATCHED_MANAGER_QUOTA in patched:
        return patched
    if ORIGINAL_MANAGER_QUOTA not in patched:
        raise SystemExit("StorageManager quota assignment anchor not found")
    return patched.replace(ORIGINAL_MANAGER_QUOTA, PATCHED_MANAGER_QUOTA, 1)


def patch_storage_bucket(text: str) -> str:
    patched = ensure_quota_includes(text, BUCKET_INCLUDE_ANCHOR, "storage_bucket.cc")
    if "BrowseForgeStorageQuotaOverrideOrDefault" not in patched:
        if BUCKET_NAMESPACE_ANCHOR not in patched:
            raise SystemExit("storage_bucket.cc namespace anchor not found")
        patched = patched.replace(BUCKET_NAMESPACE_ANCHOR, BUCKET_NAMESPACE_ANCHOR + "namespace {\n\n" + QUOTA_HELPER + "}  // namespace\n\n", 1)
    if PATCHED_BUCKET_QUOTA in patched:
        return patched
    if ORIGINAL_BUCKET_QUOTA not in patched:
        raise SystemExit("StorageBucket quota assignment anchor not found")
    return patched.replace(ORIGINAL_BUCKET_QUOTA, PATCHED_BUCKET_QUOTA, 1)


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    changed: list[Path] = []
    manager_path = src / STORAGE_MANAGER_CC
    bucket_path = src / STORAGE_BUCKET_CC
    if write_if_changed(manager_path, patch_storage_manager(manager_path.read_text(encoding="utf-8"))):
        changed.append(STORAGE_MANAGER_CC)
    if write_if_changed(bucket_path, patch_storage_bucket(bucket_path.read_text(encoding="utf-8"))):
        changed.append(STORAGE_BUCKET_CC)
    return changed or [STORAGE_MANAGER_CC, STORAGE_BUCKET_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge storage quota source patches")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_storage_manager((src / STORAGE_MANAGER_CC).read_text(encoding="utf-8"))
        patch_storage_bucket((src / STORAGE_BUCKET_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / STORAGE_MANAGER_CC}")
        print(f"ready: {src / STORAGE_BUCKET_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
