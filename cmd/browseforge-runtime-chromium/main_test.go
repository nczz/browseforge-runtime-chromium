package main

import (
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
