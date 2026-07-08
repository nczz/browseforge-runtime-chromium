package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"

	"github.com/nczz/browseforge-runtime-chromium/internal/launcher"
)

type stringList []string

func (s *stringList) String() string     { return strings.Join(*s, ",") }
func (s *stringList) Set(v string) error { *s = append(*s, v); return nil }

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	var err error
	switch os.Args[1] {
	case "metadata":
		err = metadata()
	case "doctor":
		err = doctor(os.Args[2:])
	case "launch":
		err = launch(os.Args[2:])
	default:
		usage()
		err = fmt.Errorf("unknown command %q", os.Args[1])
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: browseforge-runtime-chromium <metadata|doctor|launch> [flags]")
}

func metadata() error {
	payload := map[string]any{
		"runtime_id":      launcher.RuntimeID,
		"family":          launcher.RuntimeFamily,
		"wrapper_version": launcher.WrapperVersion,
		"capabilities": map[string]bool{
			"persistent_context": true,
			"playwright_bind":    true,
			"seed_fingerprint":   true,
			"native_proxy":       true,
			"webrtc_masking":     true,
		},
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	return enc.Encode(payload)
}

func doctor(args []string) error {
	fs := flag.NewFlagSet("doctor", flag.ContinueOnError)
	cfg, _, dryRun, extras, seed := bindLaunchFlags(fs)
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg.ExtraArgs = []string(*extras)
	cfg.Fingerprint.Seed = uint32(*seed)
	plan, err := cfg.BuildPlan()
	result := map[string]any{"ok": err == nil, "dry_run": *dryRun, "plan": plan}
	if err != nil {
		result["error"] = err.Error()
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	_ = enc.Encode(result)
	if err != nil {
		return err
	}
	return nil
}

func launch(args []string) error {
	fs := flag.NewFlagSet("launch", flag.ContinueOnError)
	cfg, configPath, dryRun, extras, seed := bindLaunchFlags(fs)
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg.ExtraArgs = []string(*extras)
	cfg.Fingerprint.Seed = uint32(*seed)
	if *configPath != "" {
		loaded, err := launcher.LoadConfig(*configPath)
		if err != nil {
			return err
		}
		mergeConfig(&loaded, *cfg)
		cfg = &loaded
	}
	return launcher.Run(context.Background(), *cfg, launcher.RunOptions{DryRun: *dryRun})
}

func bindLaunchFlags(fs *flag.FlagSet) (*launcher.Config, *string, *bool, *stringList, *uint) {
	cfg := &launcher.Config{}
	var extras stringList
	configPath := fs.String("config", "", "JSON launcher config")
	dryRun := fs.Bool("dry-run-json", false, "print command JSON without launching")
	var seed uint
	fs.StringVar(&cfg.BrowserBinary, "browser-binary", "", "runtime browser binary path")
	fs.StringVar(&cfg.UserDataDir, "user-data-dir", "", "profile-isolated user data directory")
	fs.StringVar(&cfg.ProfileID, "profile-id", "", "BrowseForge profile id")
	fs.UintVar(&seed, "fingerprint-seed", 0, "deterministic fingerprint seed")
	fs.StringVar(&cfg.Fingerprint.Timezone, "fingerprint-timezone", "", "IANA timezone")
	fs.StringVar(&cfg.Fingerprint.Locale, "fingerprint-locale", "", "locale tag")
	fs.StringVar(&cfg.Fingerprint.Platform, "fingerprint-platform", "", "fingerprint platform")
	fs.IntVar(&cfg.Fingerprint.HardwareConcurrency, "fingerprint-hardware-concurrency", 0, "hardware concurrency")
	fs.IntVar(&cfg.Fingerprint.ScreenWidth, "fingerprint-screen-width", 0, "screen width")
	fs.IntVar(&cfg.Fingerprint.ScreenHeight, "fingerprint-screen-height", 0, "screen height")
	fs.IntVar(&cfg.Fingerprint.StorageQuotaMB, "fingerprint-storage-quota", 0, "storage quota MB")
	fs.StringVar(&cfg.Fingerprint.FontsDir, "fingerprint-fonts-dir", "", "fonts directory")
	fs.StringVar(&cfg.Fingerprint.WebRTCIP, "fingerprint-webrtc-ip", "", "WebRTC IP policy")
	fs.StringVar(&cfg.Proxy.Server, "proxy-server", "", "proxy server URI")
	fs.StringVar(&cfg.Proxy.ExitIP, "proxy-exit-ip", "", "redacted/known proxy exit IP for WebRTC coherence")
	fs.StringVar(&cfg.RemoteDebugging.Address, "remote-debugging-address", "127.0.0.1", "remote debugging bind address")
	fs.IntVar(&cfg.RemoteDebugging.Port, "remote-debugging-port", 0, "remote debugging port")
	fs.BoolVar(&cfg.NoSandbox, "no-sandbox", false, "append --no-sandbox")
	fs.Var(&extras, "extra-arg", "additional non-managed Chromium arg; repeatable")
	return cfg, configPath, dryRun, &extras, &seed
}

func mergeConfig(dst *launcher.Config, flags launcher.Config) {
	if flags.BrowserBinary != "" {
		dst.BrowserBinary = flags.BrowserBinary
	}
	if flags.UserDataDir != "" {
		dst.UserDataDir = flags.UserDataDir
	}
	if flags.ProfileID != "" {
		dst.ProfileID = flags.ProfileID
	}
	if flags.Fingerprint.Seed != 0 {
		dst.Fingerprint.Seed = flags.Fingerprint.Seed
	}
	if flags.Fingerprint.Timezone != "" {
		dst.Fingerprint.Timezone = flags.Fingerprint.Timezone
	}
	if flags.Fingerprint.Locale != "" {
		dst.Fingerprint.Locale = flags.Fingerprint.Locale
	}
	if flags.Fingerprint.Platform != "" {
		dst.Fingerprint.Platform = flags.Fingerprint.Platform
	}
	if flags.Fingerprint.HardwareConcurrency != 0 {
		dst.Fingerprint.HardwareConcurrency = flags.Fingerprint.HardwareConcurrency
	}
	if flags.Fingerprint.ScreenWidth != 0 {
		dst.Fingerprint.ScreenWidth = flags.Fingerprint.ScreenWidth
	}
	if flags.Fingerprint.ScreenHeight != 0 {
		dst.Fingerprint.ScreenHeight = flags.Fingerprint.ScreenHeight
	}
	if flags.Fingerprint.StorageQuotaMB != 0 {
		dst.Fingerprint.StorageQuotaMB = flags.Fingerprint.StorageQuotaMB
	}
	if flags.Fingerprint.FontsDir != "" {
		dst.Fingerprint.FontsDir = flags.Fingerprint.FontsDir
	}
	if flags.Fingerprint.WebRTCIP != "" {
		dst.Fingerprint.WebRTCIP = flags.Fingerprint.WebRTCIP
	}
	if flags.Proxy.Server != "" {
		dst.Proxy.Server = flags.Proxy.Server
	}
	if flags.Proxy.ExitIP != "" {
		dst.Proxy.ExitIP = flags.Proxy.ExitIP
	}
	if flags.RemoteDebugging.Address != "" {
		dst.RemoteDebugging.Address = flags.RemoteDebugging.Address
	}
	if flags.RemoteDebugging.Port != 0 {
		dst.RemoteDebugging.Port = flags.RemoteDebugging.Port
	}
	if flags.NoSandbox {
		dst.NoSandbox = true
	}
	if len(flags.ExtraArgs) > 0 {
		dst.ExtraArgs = flags.ExtraArgs
	}
}
