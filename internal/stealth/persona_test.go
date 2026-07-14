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
			Arch:       "x86",
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

func TestValidatePlatformCoherence(t *testing.T) {
	tests := []struct {
		name            string
		patch           func(*PlatformIdentity)
		wantErrContains []string
	}{
		{
			name: "accepts windows x64 vocabulary",
			patch: func(platform *PlatformIdentity) {
				platform.OS = "windows"
				platform.Platform = "Win32"
				platform.Arch = "x86"
				platform.Bitness = "64"
				platform.PlatformCH = "Windows"
			},
		},
		{
			name: "accepts macos x64 vocabulary",
			patch: func(platform *PlatformIdentity) {
				platform.OS = "macos"
				platform.Platform = "MacIntel"
				platform.Arch = "x86"
				platform.Bitness = "64"
				platform.PlatformCH = "macOS"
			},
		},
		{
			name: "accepts macos arm64 vocabulary",
			patch: func(platform *PlatformIdentity) {
				platform.OS = "macos"
				platform.Platform = "MacIntel"
				platform.Arch = "arm"
				platform.Bitness = "64"
				platform.PlatformCH = "macOS"
			},
		},
		{
			name: "accepts linux x64 vocabulary",
			patch: func(platform *PlatformIdentity) {
				platform.OS = "linux"
				platform.Platform = "Linux x86_64"
				platform.Arch = "x86"
				platform.Bitness = "64"
				platform.PlatformCH = "Linux"
			},
		},
		{
			name: "accepts linux arm64 vocabulary",
			patch: func(platform *PlatformIdentity) {
				platform.OS = "linux"
				platform.Platform = "Linux aarch64"
				platform.Arch = "arm"
				platform.Bitness = "64"
				platform.PlatformCH = "Linux"
			},
		},
		{
			name: "rejects linux platform arch mismatch",
			patch: func(platform *PlatformIdentity) {
				platform.OS = "linux"
				platform.Platform = "Linux aarch64"
				platform.Arch = "x86"
				platform.Bitness = "64"
				platform.PlatformCH = "Linux"
			},
			wantErrContains: []string{"os/platform/arch/bitness"},
		},
		{
			name: "rejects windows arch mismatch",
			patch: func(platform *PlatformIdentity) {
				platform.OS = "windows"
				platform.Platform = "Win32"
				platform.Arch = "x86_64"
				platform.Bitness = "64"
				platform.PlatformCH = "Windows"
			},
			wantErrContains: []string{"os/platform/arch/bitness"},
		},
		{
			name: "rejects platform client hint mismatch",
			patch: func(platform *PlatformIdentity) {
				platform.OS = "linux"
				platform.Platform = "Linux x86_64"
				platform.Arch = "x86"
				platform.Bitness = "64"
				platform.PlatformCH = "Windows"
			},
			wantErrContains: []string{"os/platform/arch/bitness"},
		},
		{
			name: "rejects missing bitness as incomplete",
			patch: func(platform *PlatformIdentity) {
				platform.Bitness = ""
			},
			wantErrContains: []string{"platform.bitness", "fail closed"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := completePersona()
			tt.patch(&cfg.Platform)

			err := Validate(cfg)
			if len(tt.wantErrContains) > 0 {
				if err == nil {
					t.Fatal("expected platform validation to fail")
				}
				for _, want := range tt.wantErrContains {
					if !strings.Contains(err.Error(), want) {
						t.Fatalf("expected error %q to contain %q", err.Error(), want)
					}
				}
				return
			}
			if err != nil {
				t.Fatalf("expected platform identity to be accepted, got %v", err)
			}
		})
	}
}

func TestValidateRejectsIncoherentScreen(t *testing.T) {
	cfg := completePersona()
	cfg.Screen.AvailWidth = cfg.Screen.Width + 1
	if err := Validate(cfg); err == nil || !strings.Contains(err.Error(), "available size exceeds") {
		t.Fatalf("expected incoherent screen rejection, got %v", err)
	}
}

func TestValidateProxyRegionLabels(t *testing.T) {
	tests := []struct {
		name        string
		proxyRegion string
		wantErr     bool
	}{
		{name: "accepts metadata label", proxyRegion: "tw-taipei-datacenter"},
		{name: "accepts empty optional label", proxyRegion: ""},
		{name: "rejects whitespace padded label", proxyRegion: " tw-taipei-datacenter ", wantErr: true},
		{name: "rejects raw IPv4 address", proxyRegion: "203.0.113.7", wantErr: true},
		{name: "rejects URL with credentials", proxyRegion: "https://user:pass@example.com", wantErr: true},
		{name: "rejects label longer than 64 bytes", proxyRegion: strings.Repeat("a", 65), wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := completePersona()
			cfg.WebRTC.ProxyRegion = tt.proxyRegion

			err := Validate(cfg)
			if tt.wantErr {
				if err == nil || !strings.Contains(err.Error(), "invalid WebRTC proxy region") {
					t.Fatalf("expected proxy region rejection, got %v", err)
				}
				return
			}
			if err != nil {
				t.Fatalf("expected proxy region %q to be accepted, got %v", tt.proxyRegion, err)
			}
		})
	}
}
