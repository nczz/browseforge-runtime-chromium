from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_plugins_patch.py"

spec = importlib.util.spec_from_file_location("apply_plugins_patch", SCRIPT)
assert spec and spec.loader
apply_plugins_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_plugins_patch"] = apply_plugins_patch
spec.loader.exec_module(apply_plugins_patch)

PLUGIN_FIXTURE = '''#include "third_party/blink/renderer/modules/plugins/dom_plugin_array.h"

#include "third_party/blink/public/common/features.h"
#include "third_party/blink/renderer/core/page/plugin_data.h"

namespace blink {

namespace {
DOMPlugin* MakeFakePlugin(String plugin_name, LocalDOMWindow* window) {
  return nullptr;
}
}  // namespace

bool DOMPluginArray::IsPdfViewerAvailable() {
  auto* data = GetPluginData();
  if (!data)
    return false;
  for (const Member<MimeClassInfo>& mime_info : data->Mimes()) {
    if (mime_info->Type() == "application/pdf")
      return true;
  }
  return false;
}

}  // namespace blink
'''


class ApplyPluginsPatchTests(unittest.TestCase):
    def test_patches_pdf_viewer_switch(self) -> None:
        patched = apply_plugins_patch.patch_plugins(PLUGIN_FIXTURE)
        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('GetSwitchValueASCII(\n      "fingerprint-plugins-pdf")', patched)
        self.assertIn('BrowseForgePluginsPDFOverrideOrDefault(pdf_available)', patched)
        self.assertIn('mode == "enabled"', patched)
        self.assertIn('mode == "disabled"', patched)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_plugins_patch.patch_plugins(PLUGIN_FIXTURE)
        patched_twice = apply_plugins_patch.patch_plugins(patched_once)
        self.assertEqual(patched_once, patched_twice)

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            plugin_path = src / apply_plugins_patch.DOM_PLUGIN_ARRAY_CC
            plugin_path.parent.mkdir(parents=True)
            (src / ".git").mkdir()
            plugin_path.write_text(PLUGIN_FIXTURE, encoding="utf-8")
            changed = apply_plugins_patch.apply_patch(src)
            self.assertEqual([apply_plugins_patch.DOM_PLUGIN_ARRAY_CC], changed)
            self.assertIn("fingerprint-plugins-pdf", plugin_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
