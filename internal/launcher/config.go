package launcher

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

const (
	RuntimeID      = "browseforge-chromium"
	RuntimeFamily  = "chromium"
	WrapperVersion = "v0.1.0-alpha.0"
)

const automationControlledArg = "--disable-blink-features=AutomationControlled"

const webrtcIPHandlingArg = "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"

type Config struct {
	BrowserBinary   string            `json:"browser_binary"`
	UserDataDir     string            `json:"user_data_dir"`
	ProfileID       string            `json:"profile_id"`
	Fingerprint     FingerprintConfig `json:"fingerprint"`
	Proxy           ProxyConfig       `json:"proxy"`
	RemoteDebugging RemoteDebugging   `json:"remote_debugging"`
	ExtraArgs       []string          `json:"extra_args"`
	Env             map[string]string `json:"env"`
	NoSandbox       bool              `json:"no_sandbox"`
}

type FingerprintConfig struct {
	Seed                uint32 `json:"seed"`
	Timezone            string `json:"timezone"`
	Locale              string `json:"locale"`
	Platform            string `json:"platform"`
	HardwareConcurrency int    `json:"hardware_concurrency"`
	ScreenWidth         int    `json:"screen_width"`
	ScreenHeight        int    `json:"screen_height"`
	StorageQuotaMB      int    `json:"storage_quota_mb"`
	FontsDir            string `json:"fonts_dir"`
	WebRTCIP            string `json:"webrtc_ip"`
}

type ProxyConfig struct {
	Server string `json:"server"`
	ExitIP string `json:"exit_ip"`
}

type RemoteDebugging struct {
	Address string `json:"address"`
	Port    int    `json:"port"`
}

type CommandPlan struct {
	RuntimeID      string            `json:"runtime_id"`
	WrapperVersion string            `json:"wrapper_version"`
	OS             string            `json:"os"`
	Arch           string            `json:"arch"`
	BrowserBinary  string            `json:"browser_binary"`
	UserDataDir    string            `json:"user_data_dir"`
	Args           []string          `json:"args"`
	Env            map[string]string `json:"env,omitempty"`
}

var managedArgPrefixes = []string{
	"--user-data-dir",
	"--remote-debugging-address",
	"--remote-debugging-port",
	"--fingerprint",
	"--fingerprint-",
	"--proxy-server",
	"--enable-automation",
	"--disable-blink-features",
	"--force-webrtc-ip-handling-policy",
	"--webrtc-ip-handling-policy",
}

func LoadConfig(path string) (Config, error) {
	var cfg Config
	data, err := os.ReadFile(path)
	if err != nil {
		return cfg, err
	}
	if err := json.Unmarshal(data, &cfg); err != nil {
		return cfg, err
	}
	return cfg, nil
}

func (c Config) Validate(requireBinary bool) error {
	if requireBinary && c.BrowserBinary == "" {
		return errors.New("browser_binary is required")
	}
	if c.UserDataDir == "" {
		return errors.New("user_data_dir is required")
	}
	if c.RemoteDebugging.Port < 0 || c.RemoteDebugging.Port > 65535 {
		return fmt.Errorf("remote_debugging.port must be 0..65535")
	}
	if c.Fingerprint.StorageQuotaMB < 0 {
		return errors.New("fingerprint.storage_quota_mb must be >= 0")
	}
	if c.Fingerprint.HardwareConcurrency < 0 || c.Fingerprint.ScreenWidth < 0 || c.Fingerprint.ScreenHeight < 0 {
		return errors.New("fingerprint numeric values must be >= 0")
	}
	for _, arg := range c.ExtraArgs {
		if hasManagedPrefix(arg) {
			return fmt.Errorf("extra arg %q collides with BrowseForge-managed runtime policy", arg)
		}
	}
	return nil
}

func (c Config) BuildPlan() (CommandPlan, error) {
	if err := c.Validate(false); err != nil {
		return CommandPlan{}, err
	}
	userDataDir, err := filepath.Abs(c.UserDataDir)
	if err != nil {
		return CommandPlan{}, fmt.Errorf("resolve user_data_dir: %w", err)
	}
	args := []string{"--no-first-run", "--test-type", automationControlledArg, webrtcIPHandlingArg, "--user-data-dir=" + userDataDir}
	if c.RemoteDebugging.Address != "" {
		args = append(args, "--remote-debugging-address="+c.RemoteDebugging.Address)
	}
	if c.RemoteDebugging.Port > 0 {
		args = append(args, fmt.Sprintf("--remote-debugging-port=%d", c.RemoteDebugging.Port))
	}
	if c.Fingerprint.Seed > 0 {
		args = append(args, fmt.Sprintf("--fingerprint=%d", c.Fingerprint.Seed))
	}
	if c.Fingerprint.Timezone != "" {
		args = append(args, "--fingerprint-timezone="+c.Fingerprint.Timezone)
	}
	if c.Fingerprint.Locale != "" {
		args = append(args, "--fingerprint-locale="+c.Fingerprint.Locale)
	}
	if c.Fingerprint.Platform != "" {
		args = append(args, "--fingerprint-platform="+c.Fingerprint.Platform)
	}
	if c.Fingerprint.HardwareConcurrency > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-hardware-concurrency=%d", c.Fingerprint.HardwareConcurrency))
	}
	if c.Fingerprint.ScreenWidth > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-screen-width=%d", c.Fingerprint.ScreenWidth))
	}
	if c.Fingerprint.ScreenHeight > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-screen-height=%d", c.Fingerprint.ScreenHeight))
	}
	if c.Fingerprint.StorageQuotaMB > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-storage-quota=%d", c.Fingerprint.StorageQuotaMB))
	}
	if c.Fingerprint.FontsDir != "" {
		fontsDir, err := filepath.Abs(c.Fingerprint.FontsDir)
		if err != nil {
			return CommandPlan{}, fmt.Errorf("resolve fingerprint fonts dir: %w", err)
		}
		args = append(args, "--fingerprint-fonts-dir="+fontsDir)
	}
	webrtcIP := c.Fingerprint.WebRTCIP
	if c.Proxy.Server != "" {
		args = append(args, "--proxy-server="+c.Proxy.Server)
		if webrtcIP == "" {
			webrtcIP = "auto"
		}
		if c.Proxy.ExitIP != "" {
			webrtcIP = c.Proxy.ExitIP
		}
	}
	if webrtcIP != "" {
		args = append(args, "--fingerprint-webrtc-ip="+webrtcIP)
	}
	if c.NoSandbox {
		args = append(args, "--no-sandbox")
	}
	args = append(args, c.ExtraArgs...)
	return CommandPlan{
		RuntimeID:      RuntimeID,
		WrapperVersion: WrapperVersion,
		OS:             runtime.GOOS,
		Arch:           runtime.GOARCH,
		BrowserBinary:  c.BrowserBinary,
		UserDataDir:    userDataDir,
		Args:           args,
		Env:            c.Env,
	}, nil
}

func hasManagedPrefix(arg string) bool {
	for _, prefix := range managedArgPrefixes {
		if arg == prefix || strings.HasPrefix(arg, prefix+"=") || strings.HasPrefix(arg, prefix) && strings.HasSuffix(prefix, "-") {
			return true
		}
	}
	return false
}
