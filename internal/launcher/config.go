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

const stealthConfigArg = "--browseforge-stealth-config"
const stealthModeArg = "--browseforge-stealth-mode"

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
	AcceptLanguage      string `json:"accept_language"`
	Platform            string `json:"platform"`
	UserAgent           string `json:"user_agent"`
	UAFullVersion       string `json:"ua_full_version"`
	UAPlatform          string `json:"ua_platform"`
	UAPlatformVersion   string `json:"ua_platform_version"`
	UAArchitecture      string `json:"ua_architecture"`
	UABitness           string `json:"ua_bitness"`
	UAModel             string `json:"ua_model"`
	UAMobile            bool   `json:"ua_mobile"`
	UAWoW64             bool   `json:"ua_wow64"`
	HardwareConcurrency int    `json:"hardware_concurrency"`
	DeviceMemoryGB      int    `json:"device_memory_gb"`
	ScreenWidth         int    `json:"screen_width"`
	ScreenHeight        int    `json:"screen_height"`
	ScreenAvailWidth    int    `json:"screen_avail_width"`
	ScreenAvailHeight   int    `json:"screen_avail_height"`
	StorageQuotaMB      int    `json:"storage_quota_mb"`
	PluginsPDF          string `json:"plugins_pdf"`
	AudioNoise          int    `json:"audio_noise"`
	CanvasNoise         int    `json:"canvas_noise"`
	WebGLVendor         string `json:"webgl_vendor"`
	WebGLRenderer       string `json:"webgl_renderer"`
	FontsDir            string `json:"fonts_dir"`
	WebRTCIP            string `json:"webrtc_ip"`
	NativeConfigPath    string `json:"native_config_path"`
	NativeMode          string `json:"native_mode"`
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
	"--user-agent",
	"--fingerprint",
	"--fingerprint-",
	"--proxy-server",
	"--enable-automation",
	"--disable-blink-features",
	"--force-webrtc-ip-handling-policy",
	"--webrtc-ip-handling-policy",
	stealthConfigArg,
	stealthModeArg,
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
	if c.Fingerprint.StorageQuotaMB < 0 || c.Fingerprint.AudioNoise < 0 || c.Fingerprint.CanvasNoise < 0 {
		return errors.New("fingerprint.storage_quota_mb, fingerprint.audio_noise, and fingerprint.canvas_noise must be >= 0")
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
	if c.Fingerprint.AcceptLanguage != "" {
		args = append(args, "--fingerprint-accept-language="+c.Fingerprint.AcceptLanguage)
	}
	if c.Fingerprint.Platform != "" {
		args = append(args, "--fingerprint-platform="+c.Fingerprint.Platform)
	}
	if c.Fingerprint.UserAgent != "" {
		args = append(args, "--user-agent="+c.Fingerprint.UserAgent)
		args = append(args, "--fingerprint-user-agent="+c.Fingerprint.UserAgent)
	}
	if c.Fingerprint.UAFullVersion != "" {
		args = append(args, "--fingerprint-ua-full-version="+c.Fingerprint.UAFullVersion)
	}
	if c.Fingerprint.UAPlatform != "" {
		args = append(args, "--fingerprint-ua-platform="+c.Fingerprint.UAPlatform)
	}
	if c.Fingerprint.UAPlatformVersion != "" {
		args = append(args, "--fingerprint-ua-platform-version="+c.Fingerprint.UAPlatformVersion)
	}
	if c.Fingerprint.UAArchitecture != "" {
		args = append(args, "--fingerprint-ua-architecture="+c.Fingerprint.UAArchitecture)
	}
	if c.Fingerprint.UABitness != "" {
		args = append(args, "--fingerprint-ua-bitness="+c.Fingerprint.UABitness)
	}
	if c.Fingerprint.UAModel != "" {
		args = append(args, "--fingerprint-ua-model="+c.Fingerprint.UAModel)
	}
	if c.Fingerprint.UAMobile {
		args = append(args, "--fingerprint-ua-mobile=true")
	}
	if c.Fingerprint.UAWoW64 {
		args = append(args, "--fingerprint-ua-wow64=true")
	}
	if c.Fingerprint.HardwareConcurrency > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-hardware-concurrency=%d", c.Fingerprint.HardwareConcurrency))
	}
	if c.Fingerprint.DeviceMemoryGB > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-device-memory=%d", c.Fingerprint.DeviceMemoryGB))
	}
	if c.Fingerprint.ScreenWidth > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-screen-width=%d", c.Fingerprint.ScreenWidth))
	}
	if c.Fingerprint.ScreenHeight > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-screen-height=%d", c.Fingerprint.ScreenHeight))
	}
	if c.Fingerprint.ScreenAvailWidth > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-screen-avail-width=%d", c.Fingerprint.ScreenAvailWidth))
	}
	if c.Fingerprint.ScreenAvailHeight > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-screen-avail-height=%d", c.Fingerprint.ScreenAvailHeight))
	}
	if c.Fingerprint.StorageQuotaMB > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-storage-quota=%d", c.Fingerprint.StorageQuotaMB))
	}
	if c.Fingerprint.PluginsPDF != "" {
		args = append(args, "--fingerprint-plugins-pdf="+c.Fingerprint.PluginsPDF)
	}
	if c.Fingerprint.AudioNoise > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-audio-noise=%d", c.Fingerprint.AudioNoise))
	}
	if c.Fingerprint.CanvasNoise > 0 {
		args = append(args, fmt.Sprintf("--fingerprint-canvas-noise=%d", c.Fingerprint.CanvasNoise))
	}
	if c.Fingerprint.WebGLVendor != "" {
		args = append(args, "--fingerprint-webgl-vendor="+c.Fingerprint.WebGLVendor)
	}
	if c.Fingerprint.WebGLRenderer != "" {
		args = append(args, "--fingerprint-webgl-renderer="+c.Fingerprint.WebGLRenderer)
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
	if c.Fingerprint.NativeConfigPath != "" {
		nativeConfigPath, err := filepath.Abs(c.Fingerprint.NativeConfigPath)
		if err != nil {
			return CommandPlan{}, fmt.Errorf("resolve fingerprint native config path: %w", err)
		}
		args = append(args, stealthConfigArg+"="+nativeConfigPath)
	}
	if c.Fingerprint.NativeMode != "" {
		args = append(args, stealthModeArg+"="+c.Fingerprint.NativeMode)
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
