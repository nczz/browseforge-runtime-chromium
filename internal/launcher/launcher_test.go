package launcher

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestBuildPlanAddsProxyWebRTCPolicy(t *testing.T) {
	cfg := Config{UserDataDir: t.TempDir(), Proxy: ProxyConfig{Server: "socks5://127.0.0.1:9050"}}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(plan.Args, "\n")
	if !strings.Contains(joined, "--proxy-server=socks5://127.0.0.1:9050") {
		t.Fatalf("missing proxy arg: %v", plan.Args)
	}
	if !strings.Contains(joined, "--fingerprint-webrtc-ip=auto") {
		t.Fatalf("missing auto WebRTC arg: %v", plan.Args)
	}
}

func TestBuildPlanRejectsManagedExtraArgs(t *testing.T) {
	cfg := Config{UserDataDir: t.TempDir(), ExtraArgs: []string{"--user-data-dir=/tmp/evil"}}
	_, err := cfg.BuildPlan()
	if err == nil {
		t.Fatal("expected managed arg collision")
	}
}

func TestProfileLockPreventsConcurrentUse(t *testing.T) {
	dir := t.TempDir()
	lock, err := AcquireProfileLock(dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := AcquireProfileLock(dir); err == nil {
		t.Fatal("expected second lock failure")
	}
	if err := lock.Release(); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dir, ".browseforge-runtime.lock")); !os.IsNotExist(err) {
		t.Fatalf("lock file still present: %v", err)
	}
}

func TestRunDryRunDoesNotRequireBrowserBinary(t *testing.T) {
	cfg := Config{UserDataDir: t.TempDir(), Fingerprint: FingerprintConfig{Seed: 42, Timezone: "Asia/Taipei", Locale: "zh-TW"}}
	var out strings.Builder
	if err := Run(t.Context(), cfg, RunOptions{DryRun: true, Stdout: &out}); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "--fingerprint=42") {
		t.Fatalf("dry-run output missing seed: %s", out.String())
	}
}
