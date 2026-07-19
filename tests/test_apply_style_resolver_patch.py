from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_style_resolver_patch.py"

spec = importlib.util.spec_from_file_location("apply_style_resolver_patch", SCRIPT)
assert spec and spec.loader
apply_style_resolver_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_style_resolver_patch"] = apply_style_resolver_patch
spec.loader.exec_module(apply_style_resolver_patch)


def run_main_with_args(args: list[str]) -> int:
    original_argv = sys.argv
    try:
        sys.argv = [str(SCRIPT), *args]
        return apply_style_resolver_patch.main()
    finally:
        sys.argv = original_argv


STYLE_RESOLVER_FIXTURE = '''#include "third_party/blink/renderer/core/css/resolver/style_resolver.h"

#include "base/check.h"
#include "third_party/blink/renderer/core/css/resolver/style_resolver_state.h"

namespace blink {

void StyleResolver::ApplyBaseStyle(
    Element* element,
    const StyleRecalcContext& style_recalc_context,
    const StyleRequest& style_request,
    StyleResolverState& state,
    StyleCascade& cascade) {
  DCHECK(style_request.pseudo_id != kPseudoIdFirstLineInherited);

  if (state.CanTriggerAnimations() && CanReuseBaseComputedStyle(state)) {
    const ComputedStyle* animation_base_computed_style =
        CachedAnimationBaseComputedStyle(state);
    DCHECK(animation_base_computed_style);
#if DCHECK_IS_ON()
    ApplyBaseStyleNoCache(element, style_recalc_context, style_request, state,
                          cascade);
    const ComputedStyle* style_snapshot = state.StyleBuilder().CloneStyle();
    DCHECK_EQ(g_null_atom, ComputeBaseComputedStyleDiff(
                               animation_base_computed_style, *style_snapshot));
#endif

    state.CreateNewClonedStyle(*animation_base_computed_style);
    state.StyleBuilder().SetBaseData(GetBaseData(state));
    MaybeResetCascade(cascade);
    return;
  }

  ApplyBaseStyleNoCache(element, style_recalc_context, style_request, state,
                        cascade);
}

}  // namespace blink
'''


class ApplyStyleResolverPatchTests(unittest.TestCase):
    def test_patches_base_style_dcheck_to_warn_and_recompute(self) -> None:
        patched = apply_style_resolver_patch.patch_style_resolver(STYLE_RESOLVER_FIXTURE)
        self.assertIn('#include "base/logging.h"', patched)
        self.assertNotIn("DCHECK_EQ(g_null_atom, ComputeBaseComputedStyleDiff", patched)
        self.assertIn("const String base_style_diff = ComputeBaseComputedStyleDiff", patched)
        self.assertIn('LOG(WARNING) << "BrowseForge: animation base computed style mismatch: "', patched)
        self.assertIn("MaybeResetCascade(cascade);\n      return;", patched)
        self.assertIn("state.CreateNewClonedStyle(*animation_base_computed_style);", patched)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_style_resolver_patch.patch_style_resolver(STYLE_RESOLVER_FIXTURE)
        patched_twice = apply_style_resolver_patch.patch_style_resolver(patched_once)
        self.assertEqual(patched_once, patched_twice)

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            path = src / apply_style_resolver_patch.STYLE_RESOLVER_CC
            path.parent.mkdir(parents=True)
            (src / ".git").mkdir()
            path.write_text(STYLE_RESOLVER_FIXTURE, encoding="utf-8")
            changed = apply_style_resolver_patch.apply_patch(src)
            self.assertEqual([apply_style_resolver_patch.STYLE_RESOLVER_CC], changed)
            text = path.read_text(encoding="utf-8")
            self.assertIn("BrowseForge: animation base computed style mismatch", text)

    def test_check_mode_validates_without_mutating_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            path = src / apply_style_resolver_patch.STYLE_RESOLVER_CC
            path.parent.mkdir(parents=True)
            (src / ".git").mkdir()
            path.write_text(STYLE_RESOLVER_FIXTURE, encoding="utf-8")
            result = run_main_with_args(["--chromium-src", str(src), "--check"])
            self.assertEqual(0, result)
            self.assertEqual(STYLE_RESOLVER_FIXTURE, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
