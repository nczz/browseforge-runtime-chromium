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

func TestBuildPlanAddsNetworkAutomationMitigations(t *testing.T) {
	cfg := Config{UserDataDir: t.TempDir()}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{automationControlledArg, webrtcIPHandlingArg} {
		if !containsArg(plan.Args, want) {
			t.Fatalf("missing mitigation arg %q: %v", want, plan.Args)
		}
	}
}

func TestBuildPlanAddsTimezoneFingerprintArg(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			Timezone: "Asia/Taipei",
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	if !containsArg(plan.Args, "--fingerprint-timezone=Asia/Taipei") {
		t.Fatalf("missing timezone arg: %v", plan.Args)
	}
}

func TestBuildPlanAddsPlatformFingerprintArg(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			Platform: "Win32",
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	if !containsArg(plan.Args, "--fingerprint-platform=Win32") {
		t.Fatalf("missing platform arg: %v", plan.Args)
	}
}

func TestBuildPlanAddsHardwareFingerprintArgs(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			HardwareConcurrency: 8,
			DeviceMemoryGB:      16,
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"--fingerprint-hardware-concurrency=8", "--fingerprint-device-memory=16"} {
		if !containsArg(plan.Args, want) {
			t.Fatalf("missing hardware arg %q: %v", want, plan.Args)
		}
	}
}

func TestBuildPlanAddsScreenFingerprintArgs(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			ScreenWidth:       1920,
			ScreenHeight:      1080,
			ScreenAvailWidth:  1900,
			ScreenAvailHeight: 1040,
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"--fingerprint-screen-width=1920", "--fingerprint-screen-height=1080", "--fingerprint-screen-avail-width=1900", "--fingerprint-screen-avail-height=1040"} {
		if !containsArg(plan.Args, want) {
			t.Fatalf("missing screen arg %q: %v", want, plan.Args)
		}
	}
}

func TestBuildPlanRejectsManagedExtraArgs(t *testing.T) {
	cfg := Config{UserDataDir: t.TempDir(), ExtraArgs: []string{"--user-data-dir=/tmp/evil", "--disable-blink-features=Other", "--force-webrtc-ip-handling-policy=default_public_interface_only", stealthConfigArg + "=/tmp/evil.json"}}
	_, err := cfg.BuildPlan()
	if err == nil {
		t.Fatal("expected managed arg collision")
	}
}

func TestBuildPlanAddsNativeStealthConfig(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			NativeConfigPath: filepath.Join("testdata", "persona.json"),
			NativeMode:       "strict",
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(plan.Args, "\n")
	if !strings.Contains(joined, stealthConfigArg+"=") {
		t.Fatalf("missing native stealth config arg: %v", plan.Args)
	}
	if !strings.Contains(joined, stealthModeArg+"=strict") {
		t.Fatalf("missing native stealth mode arg: %v", plan.Args)
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

func containsArg(args []string, want string) bool {
	for _, arg := range args {
		if arg == want {
			return true
		}
	}
	return false
}
