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

func TestBindLaunchFlagsAcceptsDeviceMemory(t *testing.T) {
	fs := flag.NewFlagSet("launch", flag.ContinueOnError)
	cfg, _, _, _, _ := bindLaunchFlags(fs)

	if err := fs.Parse([]string{"-fingerprint-device-memory", "8"}); err != nil {
		t.Fatal(err)
	}

	if cfg.Fingerprint.DeviceMemoryGB != 8 {
		t.Fatalf("device memory flag was not bound: %d", cfg.Fingerprint.DeviceMemoryGB)
	}
}

func TestMergeConfigAllowsDeviceMemoryFlagOverride(t *testing.T) {
	loaded := launcher.Config{
		Fingerprint: launcher.FingerprintConfig{DeviceMemoryGB: 4},
	}
	flags := launcher.Config{
		Fingerprint: launcher.FingerprintConfig{DeviceMemoryGB: 8},
	}

	mergeConfig(&loaded, flags)

	if loaded.Fingerprint.DeviceMemoryGB != 8 {
		t.Fatalf("device memory was not overridden: %d", loaded.Fingerprint.DeviceMemoryGB)
	}
}
