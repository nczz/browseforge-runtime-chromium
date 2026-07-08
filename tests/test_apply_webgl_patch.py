from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_webgl_patch.py"

spec = importlib.util.spec_from_file_location("apply_webgl_patch", SCRIPT)
assert spec and spec.loader
apply_webgl_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_webgl_patch"] = apply_webgl_patch
spec.loader.exec_module(apply_webgl_patch)

WEBGL_FIXTURE = '''#include "third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.h"

#include <memory>

#include "base/bit_cast.h"
#include "base/byte_size.h"
#include "base/compiler_specific.h"

namespace blink {

ScriptValue WebGLRenderingContextBase::getParameter(ScriptState* script_state,
                                                    GLenum pname) {
  switch (pname) {
    case WebGLDebugRendererInfo::kUnmaskedRendererWebgl:
      if (ExtensionEnabled(kWebGLDebugRendererInfoName)) {
        return WebGLAny(script_state,
                        String(ContextGL()->GetString(GL_RENDERER)));
      }
      SynthesizeGLError(
          GL_INVALID_ENUM, "getParameter",
          "invalid parameter name, WEBGL_debug_renderer_info not enabled");
      return ScriptValue::CreateNull(script_state->GetIsolate());
    case WebGLDebugRendererInfo::kUnmaskedVendorWebgl:
      if (ExtensionEnabled(kWebGLDebugRendererInfoName)) {
        return WebGLAny(script_state,
                        String(ContextGL()->GetString(GL_VENDOR)));
      }
      SynthesizeGLError(
          GL_INVALID_ENUM, "getParameter",
          "invalid parameter name, WEBGL_debug_renderer_info not enabled");
      return ScriptValue::CreateNull(script_state->GetIsolate());
  }
  return ScriptValue::CreateNull(script_state->GetIsolate());
}

}  // namespace blink
'''


class ApplyWebGLPatchTests(unittest.TestCase):
    def test_patches_webgl_vendor_renderer(self) -> None:
        patched = apply_webgl_patch.patch_webgl_context(WEBGL_FIXTURE)
        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('"fingerprint-webgl-renderer"', patched)
        self.assertIn('"fingerprint-webgl-vendor"', patched)
        self.assertIn('BrowseForgeWebGLStringOverride', patched)

    def test_patch_is_idempotent(self) -> None:
        patched = apply_webgl_patch.patch_webgl_context(WEBGL_FIXTURE)
        self.assertEqual(patched, apply_webgl_patch.patch_webgl_context(patched))

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            context_path = src / apply_webgl_patch.WEBGL_CONTEXT_CC
            context_path.parent.mkdir(parents=True)
            (src / ".git").mkdir()
            context_path.write_text(WEBGL_FIXTURE, encoding="utf-8")
            changed = apply_webgl_patch.apply_patch(src)
            self.assertEqual([apply_webgl_patch.WEBGL_CONTEXT_CC], changed)
            self.assertIn("fingerprint-webgl-renderer", context_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
