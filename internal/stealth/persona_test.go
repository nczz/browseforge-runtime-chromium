package stealth

import (
	"strings"
	"testing"
)

func completePersona() PersonaConfig {
	return PersonaConfig{
		SchemaVersion: SchemaVersion,
		RuntimeID:     "browseforge-chromium",
		Seed:          123456789,
		Browser: BrowserIdentity{
			Family:      "chromium",
			Major:       150,
			FullVersion: "150.0.7871.101",
			Brands:      []string{"Chromium", "Google Chrome", "Not A(Brand"},
			UserAgent:   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.7871.101 Safari/537.36",
		},
		Platform: PlatformIdentity{
			OS:         "windows",
			Arch:       "x86_64",
			Platform:   "Win32",
			PlatformCH: "Windows",
			Bitness:    "64",
		},
		Locale: LocaleIdentity{
			Timezone:       "America/New_York",
			Locale:         "en-US",
			AcceptLanguage: "en-US,en;q=0.9",
		},
		Hardware: HardwareIdentity{HardwareConcurrency: 8, DeviceMemoryGB: 8},
		Screen:   ScreenIdentity{Width: 1920, Height: 1080, AvailWidth: 1920, AvailHeight: 1040, DPR: 1, ColorDepth: 24},
		GPU:      GPUIdentity{Vendor: "Google Inc. (NVIDIA)", Renderer: "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)"},
		WebRTC:   WebRTCPolicy{Mode: "proxy_coherent", ProxyRegion: "us-east", DirectIPRedaction: true},
		Storage:  StoragePolicy{QuotaMB: 4096, Persistent: true},
	}
}

func TestResolveDeterministicSnapshot(t *testing.T) {
	cfg := completePersona()
	first, err := Resolve(cfg)
	if err != nil {
		t.Fatal(err)
	}
	second, err := Resolve(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if first.PersonaIDHash == "" || first.OriginSaltKey == "" {
		t.Fatalf("snapshot identifiers missing: %+v", first)
	}
	if first.PersonaIDHash != second.PersonaIDHash || first.OriginSaltKey != second.OriginSaltKey {
		t.Fatalf("snapshot is not deterministic: %+v %+v", first, second)
	}
	cfg.Seed++
	third, err := Resolve(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if first.PersonaIDHash == third.PersonaIDHash || first.OriginSaltKey == third.OriginSaltKey {
		t.Fatalf("different seed did not change snapshot: %+v %+v", first, third)
	}
}

func TestValidateFailsClosedWhenPersonaIncomplete(t *testing.T) {
	cfg := completePersona()
	cfg.Locale.Timezone = ""
	err := Validate(cfg)
	if err == nil {
		t.Fatal("expected missing timezone to fail closed")
	}
	if !strings.Contains(err.Error(), "locale.timezone") || !strings.Contains(err.Error(), "fail closed") {
		t.Fatalf("unexpected validation error: %v", err)
	}
}

func TestValidateRejectsIncoherentScreen(t *testing.T) {
	cfg := completePersona()
	cfg.Screen.AvailWidth = cfg.Screen.Width + 1
	if err := Validate(cfg); err == nil || !strings.Contains(err.Error(), "available size exceeds") {
		t.Fatalf("expected incoherent screen rejection, got %v", err)
	}
}
