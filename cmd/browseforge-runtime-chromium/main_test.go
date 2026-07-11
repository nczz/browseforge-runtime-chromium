package main

import (
	"flag"
	"testing"

	"github.com/nczz/browseforge-runtime-chromium/internal/launcher"
)

func TestMergeConfigPreservesConfigRemoteDebuggingAddressWithoutFlag(t *testing.T) {
	loaded := launcher.Config{
		RemoteDebugging: launcher.RemoteDebugging{Address: "0.0.0.0", Port: 9222},
	}
	flags := launcher.Config{}

	mergeConfig(&loaded, flags)

	if loaded.RemoteDebugging.Address != "0.0.0.0" {
		t.Fatalf("remote debugging address was overwritten: %q", loaded.RemoteDebugging.Address)
	}
	if loaded.RemoteDebugging.Port != 9222 {
		t.Fatalf("remote debugging port was overwritten: %d", loaded.RemoteDebugging.Port)
	}
}

func TestMergeConfigAllowsRemoteDebuggingAddressFlagOverride(t *testing.T) {
	loaded := launcher.Config{
		RemoteDebugging: launcher.RemoteDebugging{Address: "127.0.0.1", Port: 9222},
	}
	flags := launcher.Config{
		RemoteDebugging: launcher.RemoteDebugging{Address: "0.0.0.0", Port: 9333},
	}

	mergeConfig(&loaded, flags)

	if loaded.RemoteDebugging.Address != "0.0.0.0" {
		t.Fatalf("remote debugging address was not overridden: %q", loaded.RemoteDebugging.Address)
	}
	if loaded.RemoteDebugging.Port != 9333 {
		t.Fatalf("remote debugging port was not overridden: %d", loaded.RemoteDebugging.Port)
	}
}

func TestBindLaunchFlagsAcceptsFingerprintSurfaceFlags(t *testing.T) {
	fs := flag.NewFlagSet("launch", flag.ContinueOnError)
	cfg, _, _, _, fonts, _ := bindLaunchFlags(fs)

	if err := fs.Parse([]string{
		"-fingerprint-accept-language", "zh-TW,zh;q=0.9",
		"-fingerprint-user-agent", "BrowseForgeUA/1",
		"-fingerprint-ua-full-version", "150.0.7871.101",
		"-fingerprint-ua-platform", "macOS",
		"-fingerprint-ua-platform-version", "26.5.1",
		"-fingerprint-ua-architecture", "arm",
		"-fingerprint-ua-bitness", "64",
		"-fingerprint-ua-model", "",
		"-fingerprint-ua-mobile",
		"-fingerprint-ua-wow64",
		"-fingerprint-device-memory", "8",
		"-fingerprint-screen-avail-width", "1920",
		"-fingerprint-screen-avail-height", "1040",
		"-fingerprint-plugins-pdf", "enabled",
		"-fingerprint-audio-noise", "17",
		"-fingerprint-canvas-noise", "29",
		"-fingerprint-webgl-vendor", "Intel Inc.",
		"-fingerprint-webgl-renderer", "Intel Iris",
		"-fingerprint-font", "Arial",
		"-fingerprint-font", "Helvetica",
	}); err != nil {
		t.Fatal(err)
	}

	if cfg.Fingerprint.AcceptLanguage != "zh-TW,zh;q=0.9" {
		t.Fatalf("accept language flag was not bound: %q", cfg.Fingerprint.AcceptLanguage)
	}
	if cfg.Fingerprint.UserAgent != "BrowseForgeUA/1" {
		t.Fatalf("user agent flag was not bound: %q", cfg.Fingerprint.UserAgent)
	}
	if cfg.Fingerprint.UAFullVersion != "150.0.7871.101" {
		t.Fatalf("UA full version flag was not bound: %q", cfg.Fingerprint.UAFullVersion)
	}
	if cfg.Fingerprint.UAPlatform != "macOS" || cfg.Fingerprint.UAPlatformVersion != "26.5.1" {
		t.Fatalf("UA platform flags were not bound: %#v", cfg.Fingerprint)
	}
	if cfg.Fingerprint.UAArchitecture != "arm" || cfg.Fingerprint.UABitness != "64" {
		t.Fatalf("UA architecture flags were not bound: %#v", cfg.Fingerprint)
	}
	if !cfg.Fingerprint.UAMobile || !cfg.Fingerprint.UAWoW64 {
		t.Fatalf("UA boolean flags were not bound: mobile=%v wow64=%v", cfg.Fingerprint.UAMobile, cfg.Fingerprint.UAWoW64)
	}
	if cfg.Fingerprint.DeviceMemoryGB != 8 {
		t.Fatalf("device memory flag was not bound: %d", cfg.Fingerprint.DeviceMemoryGB)
	}
	if cfg.Fingerprint.ScreenAvailWidth != 1920 || cfg.Fingerprint.ScreenAvailHeight != 1040 {
		t.Fatalf("screen available flags were not bound: %dx%d", cfg.Fingerprint.ScreenAvailWidth, cfg.Fingerprint.ScreenAvailHeight)
	}
	if cfg.Fingerprint.PluginsPDF != "enabled" || cfg.Fingerprint.AudioNoise != 17 || cfg.Fingerprint.CanvasNoise != 29 {
		t.Fatalf("plugin/audio/canvas flags were not bound: %#v", cfg.Fingerprint)
	}
	if cfg.Fingerprint.WebGLVendor != "Intel Inc." || cfg.Fingerprint.WebGLRenderer != "Intel Iris" {
		t.Fatalf("WebGL flags were not bound: vendor=%q renderer=%q", cfg.Fingerprint.WebGLVendor, cfg.Fingerprint.WebGLRenderer)
	}
	if len(*fonts) != 2 || (*fonts)[0] != "Arial" || (*fonts)[1] != "Helvetica" {
		t.Fatalf("font flags were not bound: %#v", *fonts)
	}
}

func TestMergeConfigAllowsFingerprintSurfaceFlagOverrides(t *testing.T) {
	loaded := launcher.Config{
		Fingerprint: launcher.FingerprintConfig{
			AcceptLanguage:      "en-US,en;q=0.9",
			UserAgent:           "old",
			UAFullVersion:       "149",
			UAPlatform:          "Windows",
			UAPlatformVersion:   "11",
			UAArchitecture:      "x86",
			UABitness:           "32",
			HardwareConcurrency: 4,
			DeviceMemoryGB:      4,
			ScreenAvailWidth:    1366,
			ScreenAvailHeight:   768,
			PluginsPDF:          "disabled",
			AudioNoise:          1,
			CanvasNoise:         2,
			WebGLVendor:         "old vendor",
			WebGLRenderer:       "old renderer",
			Fonts:               []string{"Old"},
		},
	}
	flags := launcher.Config{
		Fingerprint: launcher.FingerprintConfig{
			AcceptLanguage:      "zh-TW,zh;q=0.9",
			UserAgent:           "new",
			UAFullVersion:       "150",
			UAPlatform:          "macOS",
			UAPlatformVersion:   "26",
			UAArchitecture:      "arm",
			UABitness:           "64",
			UAMobile:            true,
			UAWoW64:             true,
			HardwareConcurrency: 8,
			DeviceMemoryGB:      8,
			ScreenAvailWidth:    1920,
			ScreenAvailHeight:   1040,
			PluginsPDF:          "enabled",
			AudioNoise:          17,
			CanvasNoise:         29,
			WebGLVendor:         "Intel Inc.",
			WebGLRenderer:       "Intel Iris",
			Fonts:               []string{"Arial", "Helvetica"},
		},
	}

	mergeConfig(&loaded, flags)

	if loaded.Fingerprint.AcceptLanguage != "zh-TW,zh;q=0.9" || loaded.Fingerprint.UserAgent != "new" {
		t.Fatalf("language/user agent flags were not overridden: %#v", loaded.Fingerprint)
	}
	if loaded.Fingerprint.UAFullVersion != "150" || loaded.Fingerprint.UAPlatform != "macOS" || loaded.Fingerprint.UAPlatformVersion != "26" {
		t.Fatalf("UA version/platform flags were not overridden: %#v", loaded.Fingerprint)
	}
	if loaded.Fingerprint.UAArchitecture != "arm" || loaded.Fingerprint.UABitness != "64" || !loaded.Fingerprint.UAMobile || !loaded.Fingerprint.UAWoW64 {
		t.Fatalf("UA architecture flags were not overridden: %#v", loaded.Fingerprint)
	}
	if loaded.Fingerprint.HardwareConcurrency != 8 || loaded.Fingerprint.DeviceMemoryGB != 8 {
		t.Fatalf("hardware flags were not overridden: %#v", loaded.Fingerprint)
	}
	if loaded.Fingerprint.ScreenAvailWidth != 1920 || loaded.Fingerprint.ScreenAvailHeight != 1040 {
		t.Fatalf("screen available flags were not overridden: %#v", loaded.Fingerprint)
	}
	if loaded.Fingerprint.PluginsPDF != "enabled" || loaded.Fingerprint.AudioNoise != 17 || loaded.Fingerprint.CanvasNoise != 29 {
		t.Fatalf("plugin/audio/canvas flags were not overridden: %#v", loaded.Fingerprint)
	}
	if loaded.Fingerprint.WebGLVendor != "Intel Inc." || loaded.Fingerprint.WebGLRenderer != "Intel Iris" {
		t.Fatalf("WebGL flags were not overridden: %#v", loaded.Fingerprint)
	}
	if len(loaded.Fingerprint.Fonts) != 2 || loaded.Fingerprint.Fonts[0] != "Arial" || loaded.Fingerprint.Fonts[1] != "Helvetica" {
		t.Fatalf("font flags were not overridden: %#v", loaded.Fingerprint.Fonts)
	}
}
