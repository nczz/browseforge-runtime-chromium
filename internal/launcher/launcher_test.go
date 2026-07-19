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

func TestBuildPlanMapsProxyExitIPToWebRTCOverride(t *testing.T) {
	cfg := Config{UserDataDir: t.TempDir(), Proxy: ProxyConfig{Server: "socks5://proxy.example:9050", ExitIP: "203.0.113.10"}}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(plan.Args, "\n")
	if !strings.Contains(joined, "--fingerprint-webrtc-ip=203.0.113.10") {
		t.Fatalf("missing proxy exit WebRTC arg: %v", plan.Args)
	}
}

func TestBuildPlanRejectsInvalidWebRTCIP(t *testing.T) {
	for name, cfg := range map[string]Config{
		"fingerprint": {UserDataDir: t.TempDir(), Fingerprint: FingerprintConfig{WebRTCIP: "not-an-ip"}},
		"proxy":       {UserDataDir: t.TempDir(), Proxy: ProxyConfig{Server: "socks5://proxy.example:9050", ExitIP: "auto"}},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := cfg.BuildPlan(); err == nil {
				t.Fatal("expected invalid WebRTC IP error")
			}
		})
	}
}

func TestBuildPlanAddsNetworkMitigations(t *testing.T) {
	cfg := Config{UserDataDir: t.TempDir()}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	if !containsArg(plan.Args, webrtcIPHandlingArg) {
		t.Fatalf("missing WebRTC mitigation arg %q: %v", webrtcIPHandlingArg, plan.Args)
	}
	if containsArg(plan.Args, "--disable-blink-features=AutomationControlled") {
		t.Fatalf("unexpected AutomationControlled disable arg: %v", plan.Args)
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
	if plan.Env["TZ"] != "Asia/Taipei" {
		t.Fatalf("missing timezone env: %v", plan.Env)
	}
}

func TestBuildPlanRejectsInvalidTimezoneFingerprintArg(t *testing.T) {
	for name, timezone := range map[string]string{
		"space":   "Asia/Taipei Local",
		"unicode": "Asia/Taipei\u2603",
		"long":    strings.Repeat("A", 65),
	} {
		t.Run(name, func(t *testing.T) {
			cfg := Config{
				UserDataDir: t.TempDir(),
				Fingerprint: FingerprintConfig{
					Timezone: timezone,
				},
			}
			if _, err := cfg.BuildPlan(); err == nil {
				t.Fatal("expected timezone validation error")
			}
		})
	}
}

func TestBuildPlanPreservesExplicitTimezoneEnv(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Env:         map[string]string{"TZ": "Europe/Paris"},
		Fingerprint: FingerprintConfig{
			Timezone: "Asia/Taipei",
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	if plan.Env["TZ"] != "Europe/Paris" {
		t.Fatalf("overrode explicit timezone env: %v", plan.Env)
	}
}
func TestBuildPlanAddsLocaleFingerprintArgs(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			Locale:         "zh-TW",
			AcceptLanguage: "zh-TW,zh;q=0.9,en;q=0.8",
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"--fingerprint-locale=zh-TW", "--fingerprint-accept-language=zh-TW,zh;q=0.9,en;q=0.8"} {
		if !containsArg(plan.Args, want) {
			t.Fatalf("missing locale arg %q: %v", want, plan.Args)
		}
	}
	if plan.Env["BROWSEFORGE_INTL_LOCALE"] != "zh-TW" {
		t.Fatalf("missing Intl locale env: %v", plan.Env)
	}
}

func TestBuildPlanRejectsInvalidLocaleFingerprintArgs(t *testing.T) {
	for name, fingerprint := range map[string]FingerprintConfig{
		"locale_slash":          {Locale: "zh/TW"},
		"locale_too_long":       {Locale: strings.Repeat("a", 257)},
		"accept_language_emoji": {AcceptLanguage: "zh-TW,\u2603"},
	} {
		t.Run(name, func(t *testing.T) {
			cfg := Config{
				UserDataDir: t.TempDir(),
				Fingerprint: fingerprint,
			}
			if _, err := cfg.BuildPlan(); err == nil {
				t.Fatal("expected locale validation error")
			}
		})
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

func TestBuildPlanRejectsInvalidPlatformFingerprintArg(t *testing.T) {
	for name, platform := range map[string]string{
		"slash":   "Mac/Intel",
		"unicode": "Win32\u2603",
		"long":    strings.Repeat("W", 65),
	} {
		t.Run(name, func(t *testing.T) {
			cfg := Config{
				UserDataDir: t.TempDir(),
				Fingerprint: FingerprintConfig{
					Platform: platform,
				},
			}
			if _, err := cfg.BuildPlan(); err == nil {
				t.Fatal("expected platform validation error")
			}
		})
	}
}

func TestBuildPlanAddsUserAgentFingerprintArgs(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			UserAgent:         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
			UAFullVersion:     "146.0.7680.177",
			UAPlatform:        "Windows",
			UAPlatformVersion: "19.0.0",
			UAArchitecture:    "x86",
			UABitness:         "64",
			UAMobile:          true,
			UAWoW64:           true,
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{
		"--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
		"--fingerprint-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
		"--fingerprint-ua-full-version=146.0.7680.177",
		"--fingerprint-ua-platform=Windows",
		"--fingerprint-ua-platform-version=19.0.0",
		"--fingerprint-ua-architecture=x86",
		"--fingerprint-ua-bitness=64",
		"--fingerprint-ua-mobile=true",
		"--fingerprint-ua-wow64=true",
	} {
		if !containsArg(plan.Args, want) {
			t.Fatalf("missing user-agent arg %q: %v", want, plan.Args)
		}
	}
}

func TestBuildPlanRejectsInvalidUserAgentFingerprintArgs(t *testing.T) {
	for name, fingerprint := range map[string]FingerprintConfig{
		"user_agent_control": {UserAgent: "Mozilla\n5.0"},
		"user_agent_long":    {UserAgent: strings.Repeat("A", 513)},
		"full_version_unicode": {
			UAFullVersion: "146.0\u2603",
		},
		"architecture_long": {UAArchitecture: strings.Repeat("x", 33)},
		"bitness_long":      {UABitness: strings.Repeat("6", 17)},
		"model_long":        {UAModel: strings.Repeat("M", 129)},
	} {
		t.Run(name, func(t *testing.T) {
			cfg := Config{
				UserDataDir: t.TempDir(),
				Fingerprint: fingerprint,
			}
			if _, err := cfg.BuildPlan(); err == nil {
				t.Fatal("expected user-agent validation error")
			}
		})
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

func TestBuildPlanRejectsInvalidHardwareFingerprintArgs(t *testing.T) {
	for name, fingerprint := range map[string]FingerprintConfig{
		"concurrency_too_large": {HardwareConcurrency: maxHardwareConcurrency + 1},
		"device_memory_too_large": {
			DeviceMemoryGB: maxDeviceMemoryGB + 1,
		},
		"device_memory_negative": {DeviceMemoryGB: -1},
	} {
		t.Run(name, func(t *testing.T) {
			cfg := Config{
				UserDataDir: t.TempDir(),
				Fingerprint: fingerprint,
			}
			if _, err := cfg.BuildPlan(); err == nil {
				t.Fatal("expected hardware validation error")
			}
		})
	}
}

func TestBuildPlanAddsScreenFingerprintArgs(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			ScreenWidth:             1920,
			ScreenHeight:            1080,
			ScreenAvailWidth:        1900,
			ScreenAvailHeight:       1040,
			ScreenDeviceScaleFactor: 1.25,
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"--fingerprint-screen-width=1920", "--fingerprint-screen-height=1080", "--fingerprint-screen-avail-width=1900", "--fingerprint-screen-avail-height=1040", "--window-position=0,0", "--window-size=1900,1040", "--force-device-scale-factor=1.25", "--fingerprint-screen-device-scale-factor=1.25"} {
		if !containsArg(plan.Args, want) {
			t.Fatalf("missing screen arg %q: %v", want, plan.Args)
		}
	}
}

func TestBuildPlanRejectsInvalidScreenFingerprintArgs(t *testing.T) {
	for name, fingerprint := range map[string]FingerprintConfig{
		"width_too_large":       {ScreenWidth: maxScreenDimension + 1},
		"height_too_large":      {ScreenHeight: maxScreenDimension + 1},
		"avail_width_too_large": {ScreenAvailWidth: maxScreenDimension + 1},
		"avail_height_negative": {ScreenAvailHeight: -1},
		"scale_negative":        {ScreenDeviceScaleFactor: -1},
		"scale_too_large":       {ScreenDeviceScaleFactor: maxScreenDeviceScaleFactor + 0.1},
	} {
		t.Run(name, func(t *testing.T) {
			cfg := Config{
				UserDataDir: t.TempDir(),
				Fingerprint: fingerprint,
			}
			if _, err := cfg.BuildPlan(); err == nil {
				t.Fatal("expected screen validation error")
			}
		})
	}
}

func TestBuildPlanAddsStorageQuotaFingerprintArg(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			StorageQuotaMB: 4096,
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	if !containsArg(plan.Args, "--fingerprint-storage-quota=4096") {
		t.Fatalf("missing storage quota arg: %v", plan.Args)
	}
}

func TestBuildPlanRejectsStorageQuotaAboveNativeLimit(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			StorageQuotaMB: int(maxStorageQuotaMB + 1),
		},
	}
	if _, err := cfg.BuildPlan(); err == nil {
		t.Fatal("expected storage quota native limit error")
	}
}

func TestBuildPlanAddsPluginsPDFFingerprintArg(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			PluginsPDF: "enabled",
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	if !containsArg(plan.Args, "--fingerprint-plugins-pdf=enabled") {
		t.Fatalf("missing plugins PDF arg: %v", plan.Args)
	}
}

func TestBuildPlanRejectsInvalidPluginsPDFMode(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			PluginsPDF: "maybe",
		},
	}
	if _, err := cfg.BuildPlan(); err == nil {
		t.Fatal("expected plugins PDF mode validation error")
	}
}

func TestBuildPlanAddsAudioNoiseFingerprintArg(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			AudioNoise: 17,
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	if !containsArg(plan.Args, "--fingerprint-audio-noise=17") {
		t.Fatalf("missing audio noise arg: %v", plan.Args)
	}
}

func TestBuildPlanRejectsAudioNoiseAboveUint32(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			AudioNoise: int(1 << 32),
		},
	}
	if _, err := cfg.BuildPlan(); err == nil {
		t.Fatal("expected audio noise uint32 range error")
	}
}

func TestBuildPlanAddsCanvasNoiseFingerprintArg(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			CanvasNoise: 23,
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	if !containsArg(plan.Args, "--fingerprint-canvas-noise=23") {
		t.Fatalf("missing canvas noise arg: %v", plan.Args)
	}
}

func TestBuildPlanRejectsCanvasNoiseAboveUint32(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			CanvasNoise: int(1 << 32),
		},
	}
	if _, err := cfg.BuildPlan(); err == nil {
		t.Fatal("expected canvas noise uint32 range error")
	}
}

func TestBuildPlanAddsWebGLFingerprintArgs(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			WebGLVendor:   "Google Inc. (NVIDIA)",
			WebGLRenderer: "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)",
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{
		"--fingerprint-webgl-vendor=Google Inc. (NVIDIA)",
		"--fingerprint-webgl-renderer=ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)",
	} {
		if !containsArg(plan.Args, want) {
			t.Fatalf("missing WebGL arg %q: %v", want, plan.Args)
		}
	}
}

func TestBuildPlanStrictNativeModeSuppressesHighRiskSpoofArgsButKeepsFontCorpus(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			NativeMode:       "strict",
			AudioNoise:       17,
			CanvasNoise:      23,
			WebGLVendor:      "Google Inc. (NVIDIA)",
			WebGLRenderer:    "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)",
			FontsDir:         filepath.Join("testdata", "fonts"),
			Fonts:            []string{"Segoe UI", "Calibri"},
			NativeConfigPath: filepath.Join("testdata", "persona.json"),
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	for _, blocked := range []string{
		"--fingerprint-audio-noise=17",
		"--fingerprint-canvas-noise=23",
		"--fingerprint-webgl-vendor=Google Inc. (NVIDIA)",
		"--fingerprint-webgl-renderer=ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)",
	} {
		if containsArg(plan.Args, blocked) {
			t.Fatalf("strict native mode must suppress high-risk spoof arg %q: %v", blocked, plan.Args)
		}
	}
	if !containsArg(plan.Args, "--fingerprint-fonts-list=Segoe UI|Calibri") {
		t.Fatalf("strict native mode must keep explicit font corpus until native font consumer exists: %v", plan.Args)
	}
	hasFontsDir := false
	for _, arg := range plan.Args {
		if strings.HasPrefix(arg, "--fingerprint-fonts-dir=") {
			hasFontsDir = true
			break
		}
	}
	if !hasFontsDir {
		t.Fatalf("strict native mode must keep explicit fonts dir until native font consumer exists: %v", plan.Args)
	}
	if !containsArg(plan.Args, stealthModeArg+"=strict") {
		t.Fatalf("missing strict native mode arg: %v", plan.Args)
	}
}

func TestBuildPlanRejectsInvalidWebGLFingerprintArgs(t *testing.T) {
	for name, cfg := range map[string]Config{
		"vendor_control":   {UserDataDir: t.TempDir(), Fingerprint: FingerprintConfig{WebGLVendor: "Google\nInc."}},
		"renderer_unicode": {UserDataDir: t.TempDir(), Fingerprint: FingerprintConfig{WebGLRenderer: "ANGLE \u2603"}},
		"renderer_long":    {UserDataDir: t.TempDir(), Fingerprint: FingerprintConfig{WebGLRenderer: strings.Repeat("A", 257)}},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := cfg.BuildPlan(); err == nil {
				t.Fatal("expected invalid WebGL fingerprint arg error")
			}
		})
	}
}

func TestBuildPlanAddsFontListFingerprintArg(t *testing.T) {
	cfg := Config{
		UserDataDir: t.TempDir(),
		Fingerprint: FingerprintConfig{
			Fonts: []string{"Segoe UI", "Calibri", "Consolas"},
		},
	}
	plan, err := cfg.BuildPlan()
	if err != nil {
		t.Fatal(err)
	}
	want := "--fingerprint-fonts-list=Segoe UI|Calibri|Consolas"
	if !containsArg(plan.Args, want) {
		t.Fatalf("missing font list arg %q: %v", want, plan.Args)
	}
}

func TestBuildPlanRejectsInvalidFontListFingerprintArgs(t *testing.T) {
	encodedLong := make([]string, 64)
	for i := range encodedLong {
		encodedLong[i] = strings.Repeat("A", 128)
	}

	for name, fonts := range map[string][]string{
		"empty":        {""},
		"too_long":     {strings.Repeat("A", 129)},
		"separator":    {"Segoe|UI"},
		"control":      {"Segoe\nUI"},
		"unicode":      {"Noto \u2603"},
		"encoded_long": encodedLong,
	} {
		t.Run(name, func(t *testing.T) {
			cfg := Config{
				UserDataDir: t.TempDir(),
				Fingerprint: FingerprintConfig{
					Fonts: fonts,
				},
			}
			if _, err := cfg.BuildPlan(); err == nil {
				t.Fatal("expected font list validation error")
			}
		})
	}
}

func TestBuildPlanRejectsManagedExtraArgs(t *testing.T) {
	cfg := Config{UserDataDir: t.TempDir(), ExtraArgs: []string{"--user-data-dir=/tmp/evil", "--user-agent=evil", "--disable-blink-features=Other", "--force-webrtc-ip-handling-policy=default_public_interface_only", stealthConfigArg + "=/tmp/evil.json"}}
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

func TestBuildPlanRejectsInvalidNativeStealthMode(t *testing.T) {
	for _, mode := range []string{"maybe", "ENABLED", "strict\n", strings.Repeat("x", 65)} {
		cfg := Config{
			UserDataDir: t.TempDir(),
			Fingerprint: FingerprintConfig{
				NativeMode: mode,
			},
		}
		if _, err := cfg.BuildPlan(); err == nil {
			t.Fatalf("expected native mode validation error for %q", mode)
		}
	}
}

func TestBuildPlanAllowsExplicitNativeStealthNoOpModes(t *testing.T) {
	for _, mode := range []string{"off", "disabled", "false", "0"} {
		cfg := Config{
			UserDataDir: t.TempDir(),
			Fingerprint: FingerprintConfig{
				NativeMode: mode,
			},
		}
		plan, err := cfg.BuildPlan()
		if err != nil {
			t.Fatalf("expected native mode %q to be valid: %v", mode, err)
		}
		if !containsArg(plan.Args, stealthModeArg+"="+mode) {
			t.Fatalf("missing native stealth mode arg for %q: %v", mode, plan.Args)
		}
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

func TestRunAppliesPlanEnvironment(t *testing.T) {
	dir := t.TempDir()
	outPath := filepath.Join(dir, "env.txt")
	browser := filepath.Join(dir, "browser")
	script := "#!/bin/sh\nprintenv TZ > " + outPath + "\n"
	if err := os.WriteFile(browser, []byte(script), 0755); err != nil {
		t.Fatal(err)
	}
	cfg := Config{
		BrowserBinary: browser,
		UserDataDir:   filepath.Join(dir, "profile"),
		Fingerprint: FingerprintConfig{
			Timezone: "Asia/Taipei",
		},
	}
	if err := Run(t.Context(), cfg, RunOptions{}); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(outPath)
	if err != nil {
		t.Fatal(err)
	}
	if strings.TrimSpace(string(got)) != "Asia/Taipei" {
		t.Fatalf("browser did not receive TZ: %q", got)
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
